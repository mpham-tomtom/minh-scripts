"""Agent one, step 6: building the guide and the landing page.

The guide is written by the writer model (that's where quality shows); the
landing page html is built by the builder model (kimi k3 when configured).
Output lands in the data dir; deploy notes are in the README. The landing
page carries a whop checkout link placeholder - checkout itself is set up
on whop and the link pasted in, because payment setup needs the human's
account anyway.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from . import prompts, profiles
from .config import Config
from .llm import LLM

log = logging.getLogger(__name__)

GUIDE_SYSTEM = """\
you write practical guides sold to people who described this exact problem
on reddit. write in the community's own language, taken from the profile
provided. no filler, no padding, no invented statistics or testimonials.
"""

PAGE_SYSTEM = """\
you build plain, honest, single-file landing pages. output one complete html
file and nothing else. inline all css. no external scripts. no fake
testimonials, no invented numbers, no 'join 2,000 readers' when there are
none. where the checkout link goes, use the literal placeholder
WHOP_CHECKOUT_URL so the owner can paste their whop link in.
"""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def build_guide(cfg: Config, llm: LLM, problem: str, subreddit: str) -> Path:
    profile = profiles.read_profile(cfg, subreddit)
    prompt = (
        prompts.STEP6_BUILD_GUIDE.format(problem=problem)
        + f"\nhere is the subreddit profile for r/{subreddit}:\n\n"
        + f"<profile>\n{profile}\n</profile>\n\n"
        + "return the guide as markdown."
    )
    guide_md = llm.write_long(GUIDE_SYSTEM, prompt)
    out = cfg.output_dir / f"guide-{_slug(problem)}.md"
    out.write_text(guide_md)
    log.info("guide written to %s (%d chars)", out, len(guide_md))
    return out


def build_landing_page(cfg: Config, llm: LLM, problem: str, subreddit: str,
                       price: str, guide_path: Path) -> Path:
    profile = profiles.read_profile(cfg, subreddit)
    guide_md = guide_path.read_text()
    prompt = (
        prompts.STEP6_BUILD_LANDING_PAGE.format(price=price)
        + f"\nthe problem: {problem}\n\n"
        + f"the subreddit profile (use its language section for the headline):\n"
        + f"<profile>\n{profile}\n</profile>\n\n"
        + "the table of contents of the guide, so 'what's inside' is specific:\n"
        + "<guide_headings>\n"
        + "\n".join(l for l in guide_md.splitlines() if l.startswith("#"))
        + "\n</guide_headings>"
    )
    page = llm.build(PAGE_SYSTEM, prompt)
    # models sometimes wrap the file in a code fence
    page = re.sub(r"^```[a-z]*\n|\n```$", "", page.strip())
    out = cfg.output_dir / f"landing-{_slug(problem)}.html"
    out.write_text(page)
    log.info("landing page written to %s", out)
    return out
