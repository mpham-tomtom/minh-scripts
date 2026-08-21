"""Step 3: the subreddit profiles.

A subreddit is a group of people with a shared situation. The agent keeps a
written profile of each community and updates it every night from that day's
activity. That file is the thing to read every morning - everything
downstream reads from it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from . import prompts
from .config import Config
from .llm import LLM
from .storage import Store

log = logging.getLogger(__name__)

EMPTY_PROFILE = """\
# r/{subreddit}

## demographics
(nothing observed yet)

## psychographics
(nothing observed yet)

## the words they use
(nothing observed yet)

## what they've already tried and why it failed
(nothing observed yet)

## what gets upvoted and what gets buried
(nothing observed yet)

## the rules of the place
(nothing observed yet)

## tone
(nothing observed yet)

## update log
- {today}: profile created, no data yet
"""

SYSTEM = """\
you maintain a live markdown profile of a reddit community for someone who
reads it every morning. you work only from what people in the community
actually wrote. mark anything you're guessing. never invent quotes.
"""


def profile_path(cfg: Config, subreddit: str) -> Path:
    return cfg.profiles_dir / f"{subreddit}.md"


def read_profile(cfg: Config, subreddit: str) -> str:
    p = profile_path(cfg, subreddit)
    if not p.exists():
        today = datetime.now(timezone.utc).date().isoformat()
        p.write_text(EMPTY_PROFILE.format(subreddit=subreddit, today=today))
    return p.read_text()


def _format_items(rows) -> str:
    lines = []
    for r in rows:
        lines.append(
            f"[{r['kind']}] u/{r['author']} at {r['timestamp']}\n"
            f"title: {r['title']}\n{r['body']}\npermalink: {r['permalink']}\n"
        )
    return "\n---\n".join(lines)


def nightly_update(cfg: Config, store: Store, llm: LLM, subreddit: str) -> str:
    """Read that day's activity and update the file."""
    current = read_profile(cfg, subreddit)
    day = store.recent_items(days=1, subreddit=subreddit, limit=400)
    if not day:
        log.info("r/%s: no new activity today, profile unchanged", subreddit)
        return current

    prompt = (
        f"{prompts.STEP3_SUBREDDIT_PROFILES}\n"
        f"the subreddit is r/{subreddit}.\n\n"
        f"here is the current profile file:\n\n<profile>\n{current}\n</profile>\n\n"
        f"here is today's activity ({len(day)} items):\n\n"
        f"<activity>\n{_format_items(day)}\n</activity>\n\n"
        "return the full updated markdown file and nothing else."
    )
    updated = llm.write(SYSTEM, prompt).strip()
    if updated:
        profile_path(cfg, subreddit).write_text(updated + "\n")
        log.info("r/%s: profile updated from %d items", subreddit, len(day))
    return updated


def find_subreddits(cfg: Config, llm: LLM) -> str:
    """Step 2, if you don't know which subreddits: ask first."""
    prompt = prompts.STEP2_FIND_SUBREDDITS.format(
        product=cfg.product or "[product]", who=cfg.audience or "[who]"
    )
    return llm.orchestrate(
        "you advise on where an audience actually spends time on reddit. "
        "be specific and honest about what you are unsure of.",
        prompt,
    )
