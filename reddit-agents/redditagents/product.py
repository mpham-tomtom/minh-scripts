"""Step 7: agent two, learning the product.

The product file is the difference between an agent that sounds like you and
one that sounds like a bot. Spend an hour getting it right. The agent reads
this file and the relevant subreddit profile before writing any post, reply
or message.
"""

from __future__ import annotations

from .config import Config

TEMPLATE = """\
# product file

## what the product is and what it costs
(fill in)

## the exact problem it solves, written the way a buyer would describe it
(fill in)

## who it's for and who it isn't for
(fill in)

## the specific things it covers
(fill in)

## what it doesn't do, so the agent never overpromises on your behalf
(fill in)

## the objections people raise and the honest answer to each
(fill in)

## three real quotes from the monitored subreddits that describe the problem this solves
1. (quote, with permalink)
2. (quote, with permalink)
3. (quote, with permalink)
"""


def ensure_product_file(cfg: Config) -> str:
    if not cfg.product_file.exists():
        cfg.product_file.write_text(TEMPLATE)
    return cfg.product_file.read_text()


def is_filled_in(cfg: Config) -> bool:
    return "(fill in)" not in ensure_product_file(cfg)
