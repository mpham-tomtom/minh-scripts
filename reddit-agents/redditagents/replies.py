"""Agent two, step 9: the replies.

For each match scoring 4 or above, the writer model drafts a reply and
queues it on the dashboard with the direct link, ordered by how time
sensitive it is. The agent never posts - you click through and paste.
"""

from __future__ import annotations

import logging

from . import prompts, product, profiles
from .config import Config
from .llm import LLM
from .storage import Store

log = logging.getLogger(__name__)

SYSTEM = """\
you draft reddit replies that a human will review and post from their own
account. the reply must stand on its own as help. do not mention the
product. do not link anything. no marketing language, no exclamation marks,
and never start with 'great question'. write in the tone of the community
the reply is going to, per its profile. return only the reply text.
"""


def run(cfg: Config, store: Store, llm: LLM) -> int:
    matches = store.matches_needing_replies(min_score=4)
    done_permalinks = store.already_replied_permalinks()
    queued = 0

    for m in matches:
        if m["permalink"] in done_permalinks:
            store.log_skip(m["item_id"], "already replied in this thread")
            continue
        profile = profiles.read_profile(cfg, m["subreddit"])
        prod = product.ensure_product_file(cfg)
        prompt = (
            f"{prompts.STEP9_WRITE_REPLIES}\n\n"
            f"the subreddit profile for r/{m['subreddit']} (match its tone "
            f"section exactly):\n<profile>\n{profile}\n</profile>\n\n"
            f"the product file (for substance only - never mention it):\n"
            f"<product>\n{prod}\n</product>\n\n"
            f"the thing to reply to, by u/{m['author']} at {m['timestamp']}:\n"
            f"<target>\ntitle: {m['title']}\n{m['body']}\n</target>\n\n"
            "write the one reply for this target. return only the reply text."
        )
        try:
            text = llm.write(SYSTEM, prompt).strip()
        except Exception:
            log.exception("reply drafting failed for %s", m["item_id"])
            continue
        if not text:
            store.log_skip(m["item_id"], "writer returned nothing")
            continue
        store.enqueue(
            kind="reply",
            subreddit=m["subreddit"],
            text=text,
            target_permalink=m["permalink"],
            target_item_id=m["item_id"],
            time_sensitivity=m["timestamp"],
        )
        queued += 1

    if queued:
        log.info("queued %d replies", queued)
    return queued
