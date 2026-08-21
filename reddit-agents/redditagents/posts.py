"""Agent two, step 10: the posts.

Every morning, five posts drafted across the subreddits. Each gives away the
whole method with nothing held back - no link, no product mention - and is
queued with its submit link and a note on what might get it removed. Posting
windows come from when each community is actually active in the collected
history.
"""

from __future__ import annotations

import json
import logging
import re

from . import prompts, product, profiles
from .config import Config
from .llm import LLM
from .storage import Store

log = logging.getLogger(__name__)

SYSTEM = """\
you draft reddit posts that a human will review and post from their own
account. give away the whole method with nothing held back. no link and no
product mention. end with a line offering to answer questions. write in the
target community's tone and language, per its profile. return only json.
"""

POSTS_PER_MORNING = 5


def run(cfg: Config, store: Store, llm: LLM) -> int:
    if not cfg.subreddits:
        return 0
    prod = product.ensure_product_file(cfg)
    queued = 0

    # spread the five posts across the subreddits, round robin
    targets = [cfg.subreddits[i % len(cfg.subreddits)] for i in range(POSTS_PER_MORNING)]
    per_sub: dict[str, int] = {}
    for sub in targets:
        per_sub[sub] = per_sub.get(sub, 0) + 1

    for sub, count in per_sub.items():
        profile = profiles.read_profile(cfg, sub)
        prompt = (
            f"{prompts.STEP10_WRITE_POSTS}\n\n"
            f"draft {count} post(s) for r/{sub}.\n\n"
            f"the subreddit profile (tone section for the shape, language "
            f"section for the words, rules section for removal risk):\n"
            f"<profile>\n{profile}\n</profile>\n\n"
            f"the product file, for what the method should teach - but no "
            f"link and no product mention in the post itself:\n"
            f"<product>\n{prod}\n</product>\n\n"
            'return a json array, one object per post: {"title": "...", '
            '"body": "...", "removal_risk": "what might get it removed in '
            'this subreddit and what to change if you want it to survive"}'
        )
        try:
            raw = llm.write(SYSTEM, prompt)
        except Exception:
            log.exception("post drafting failed for r/%s", sub)
            continue
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            log.warning("post drafting for r/%s returned no json", sub)
            continue
        try:
            drafts = json.loads(m.group(0))
        except json.JSONDecodeError:
            log.warning("post drafting for r/%s returned unparseable json", sub)
            continue
        for d in drafts[:count]:
            store.enqueue(
                kind="post",
                subreddit=sub,
                text=f"{d.get('title', '').strip()}\n\n{d.get('body', '').strip()}",
                target_permalink=f"https://www.reddit.com/r/{sub}/submit",
                removal_risk=d.get("removal_risk", ""),
            )
            queued += 1

    log.info("queued %d posts for this morning", queued)
    return queued


def posting_windows(cfg: Config, store: Store) -> dict[str, list[int]]:
    """Best UTC hours per subreddit, from when that community is active."""
    return {sub: store.active_hours(sub) for sub in cfg.subreddits}
