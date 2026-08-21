"""Agent one, steps 4 and 5: finding the niche, then finding the product.

The niche search starts from which kinds of people are desperate enough to
pay for an answer. The problem analysis looks at everything pulled in the
last 30 days for the same question asked over and over - that repetition is
the whole signal.
"""

from __future__ import annotations

import logging

from . import prompts
from .config import Config
from .llm import LLM
from .storage import Store

log = logging.getLogger(__name__)

NICHE_SYSTEM = """\
you research niches for someone deciding what to build and sell. urgency and
willingness to pay matter more than topic size. be explicit about niches
that should be skipped: anywhere selling would require credentials the
seller doesn't have, or where a wrong answer would hurt someone. name those
rather than quietly including them.
"""

PROBLEM_SYSTEM = """\
you analyse collected reddit posts and comments to find problems people
repeatedly ask about. quote real lines verbatim with their permalinks. never
invent a quote or inflate a count. if nothing in the data is worth building
for, say so instead of forcing something.
"""


def find_niches(store: Store, llm: LLM) -> str:
    """Step 4. Pick one, point the monitor at its subreddits, let it run a week."""
    result = llm.orchestrate(NICHE_SYSTEM, prompts.STEP4_FIND_NICHES)
    store.save_analysis("niches", result)
    return result


def _condense(rows) -> str:
    lines = []
    for r in rows:
        body = (r["body"] or "")[:400]
        lines.append(
            f"[{r['kind']}|r/{r['subreddit']}|{r['timestamp']}|{r['permalink']}] "
            f"{r['title']} :: {body}"
        )
    return "\n".join(lines)


def find_problems(cfg: Config, store: Store, llm: LLM) -> str:
    """Step 5, also the weekly analysis in step 13.

    The pattern-finding pass over the raw volume runs on the volume reader
    (gemini 2.5 flash by default); the orchestrator then ranks what came out.
    """
    rows = store.recent_items(days=30)
    if not rows:
        return "nothing collected in the last 30 days yet - let the monitor run first."

    condensed = llm.read_volume(
        PROBLEM_SYSTEM,
        "group the following reddit activity by the underlying problem being "
        "described. for each group: the problem in the words people used, a "
        "rough count, three verbatim quoted lines with permalinks, and what "
        "people said they'd already tried.\n\n" + _condense(rows),
    )
    result = llm.orchestrate(
        PROBLEM_SYSTEM,
        f"{prompts.STEP5_FIND_PROBLEMS}\n\nhere is the grouped activity from "
        f"the last 30 days ({len(rows)} items):\n\n{condensed}",
    )
    store.save_analysis("problems", result)
    return result
