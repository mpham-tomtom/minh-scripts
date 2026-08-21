"""Reddit public RSS feeds. No API key, no scraper, no login.

Add .rss to almost any reddit url and you get structured data back:
- posts:    https://www.reddit.com/r/{sub}/new/.rss
- comments: https://www.reddit.com/r/{sub}/comments/.rss

Posts give you the title, the OP, the link and the body. Comments give you
the username, the full comment, the post it's on, a permalink straight to
it, and a timestamp. That's everything this system needs.

The rate limit is about one request a minute from a single ip. The limiter
below paces every request, and a 429 is handled by waiting rather than
retrying immediately.
"""

from __future__ import annotations

import html
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "reddit-agents rss reader (read-only, ~1 req/min)"


class RateLimiter:
    """Global pacing: at most one request per `min_interval` seconds."""

    def __init__(self, min_interval: float = 60.0):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_request = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()


@dataclass
class FeedItem:
    kind: str  # "post" or "comment"
    subreddit: str
    item_id: str  # reddit's entry id, unique
    title: str
    author: str
    body: str  # text content, html stripped
    permalink: str
    timestamp: str  # ISO 8601 from the feed


def _strip_html(content: str) -> str:
    text = re.sub(r"<[^>]+>", " ", content)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_feed(xml_text: str, subreddit: str, kind: str) -> list[FeedItem]:
    root = ET.fromstring(xml_text)
    items = []
    for entry in root.findall(f"{ATOM}entry"):
        author_el = entry.find(f"{ATOM}author/{ATOM}name")
        link_el = entry.find(f"{ATOM}link")
        content_el = entry.find(f"{ATOM}content")
        items.append(
            FeedItem(
                kind=kind,
                subreddit=subreddit,
                item_id=(entry.findtext(f"{ATOM}id") or "").strip(),
                title=(entry.findtext(f"{ATOM}title") or "").strip(),
                author=(author_el.text or "").strip() if author_el is not None else "",
                body=_strip_html(content_el.text or "") if content_el is not None else "",
                permalink=link_el.get("href", "") if link_el is not None else "",
                timestamp=(entry.findtext(f"{ATOM}updated") or "").strip(),
            )
        )
    return items


class RedditRSS:
    def __init__(self, limiter: RateLimiter):
        self.limiter = limiter
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.requests_made = 0

    def _get(self, url: str) -> str:
        self.limiter.wait()
        resp = self.session.get(url, timeout=30)
        self.requests_made += 1
        if resp.status_code == 429:
            wait = int(resp.headers.get("retry-after", "120"))
            log.warning("429 from reddit, waiting %ss before the next request", wait)
            time.sleep(wait)
            self.limiter.wait()
            resp = self.session.get(url, timeout=30)
            self.requests_made += 1
        resp.raise_for_status()
        return resp.text

    def posts(self, subreddit: str) -> list[FeedItem]:
        url = f"https://www.reddit.com/r/{subreddit}/new/.rss"
        return _parse_feed(self._get(url), subreddit, "post")

    def comments(self, subreddit: str) -> list[FeedItem]:
        url = f"https://www.reddit.com/r/{subreddit}/comments/.rss"
        return _parse_feed(self._get(url), subreddit, "comment")

    def test(self, subreddit: str = "python") -> str:
        """Step 2: test it now and report what fields actually come back."""
        posts = self.posts(subreddit)
        comments = self.comments(subreddit)
        lines = [f"pulled r/{subreddit}: {len(posts)} posts, {len(comments)} comments"]
        if posts:
            p = posts[0]
            lines.append(
                "post fields: title=%r author=%r permalink=%r timestamp=%r body[:80]=%r"
                % (p.title, p.author, p.permalink, p.timestamp, p.body[:80])
            )
        if comments:
            c = comments[0]
            lines.append(
                "comment fields: title=%r author=%r permalink=%r timestamp=%r body[:80]=%r"
                % (c.title, c.author, c.permalink, c.timestamp, c.body[:80])
            )
        return "\n".join(lines)
