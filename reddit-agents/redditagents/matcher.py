"""Agent two, step 8: finding the threads.

The matcher (claude haiku - high volume, low difficulty) scores every new
item 1 to 5 for how directly it relates to the problem the product solves,
and flags anyone clearly looking for a solution right now. Anything older
than a month is never considered; the storage layer filters that.
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
you score reddit posts and comments for how directly they describe a given
problem, whether or not they use the same words for it. you are strict: a 4
or 5 means the person is describing this exact problem. return only json.
"""

BATCH = 20


def _language_sections(cfg: Config, subreddits: list[str]) -> str:
    """The language section of each profile, so we catch the phrasings each
    community actually uses rather than only the obvious ones."""
    chunks = []
    for sub in subreddits:
        text = profiles.read_profile(cfg, sub)
        m = re.search(r"## the words they use\n(.*?)(\n## |\Z)", text, re.S)
        if m:
            chunks.append(f"r/{sub}:\n{m.group(1).strip()}")
    return "\n\n".join(chunks)


def _parse_json(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        log.warning("matcher returned unparseable json")
        return []


def run(cfg: Config, store: Store, llm: LLM) -> int:
    prod = product.ensure_product_file(cfg)
    if not product.is_filled_in(cfg):
        log.info("product file not filled in yet (%s) - matching skipped", cfg.product_file)
        return 0

    items = store.unmatched_items()
    if not items:
        return 0
    language = _language_sections(cfg, cfg.subreddits)
    matched = 0

    for start in range(0, len(items), BATCH):
        batch = items[start:start + BATCH]
        listing = "\n\n".join(
            f"id: {r['item_id']}\nsubreddit: r/{r['subreddit']}\n"
            f"when: {r['timestamp']}\ntitle: {r['title']}\n"
            f"text: {(r['body'] or '')[:600]}"
            for r in batch
        )
        prompt = (
            f"{prompts.STEP8_FIND_THREADS}\n\n"
            f"the product file:\n<product>\n{prod}\n</product>\n\n"
            f"language sections from the subreddit profiles:\n"
            f"<language>\n{language}\n</language>\n\n"
            f"the items to score:\n<items>\n{listing}\n</items>\n\n"
            'return a json array, one object per item: {"id": ..., "score": 1-5, '
            '"looking_now": true/false, "reason": "...", '
            '"skip_reason": "already answered well / would obviously be spam / '
            'not related" or null}'
        )
        for verdict in _parse_json(llm.match(SYSTEM, prompt)):
            item_id = verdict.get("id", "")
            score = int(verdict.get("score", 1))
            skip = verdict.get("skip_reason")
            store.save_match(item_id, score, bool(verdict.get("looking_now")),
                             verdict.get("reason", ""))
            if skip:
                store.log_skip(item_id, skip)
            elif score >= 4:
                matched += 1

    log.info("matcher scored %d items, %d new matches at 4+", len(items), matched)
    return matched
