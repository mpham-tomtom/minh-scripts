"""Command line entry points. `run` is what Railway starts; everything else
is for driving the steps by hand."""

from __future__ import annotations

import argparse
import logging
import sys

from . import (analysis, dashboards, guide, matcher, posts, product, profiles,
               prompts, replies, scheduler, server, telegram)
from .config import load
from .llm import LLM
from .reddit_rss import RateLimiter, RedditRSS
from .storage import Store

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(prog="redditagents")
    parser.add_argument("--config", default=None, help="path to config.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run", help="serve dashboards and run the schedule (step 13)")
    sub.add_parser("test-rss", help="step 2: test the feeds and report the fields")
    sub.add_parser("test-telegram", help="step 1: confirm it can message you")
    sub.add_parser("pull", help="pull new posts and comments once")
    sub.add_parser("find-subreddits", help="step 2: which subreddits to monitor")
    sub.add_parser("update-profiles", help="step 3: nightly profile update, now")
    sub.add_parser("find-niches", help="step 4: agent one, finding the niche")
    sub.add_parser("analyze-problems", help="step 5: agent one, finding the product")
    g = sub.add_parser("build-guide", help="step 6: build the guide and landing page")
    g.add_argument("--problem", required=True)
    g.add_argument("--subreddit", required=True)
    g.add_argument("--price", default=None)
    sub.add_parser("init-product", help="step 7: create the product file to fill in")
    sub.add_parser("match", help="step 8: score collected items against the product")
    sub.add_parser("draft-replies", help="step 9: queue replies for matches at 4+")
    sub.add_parser("draft-posts", help="step 10: draft this morning's five posts")
    sub.add_parser("dashboards", help="step 12: regenerate both dashboards")
    ms = sub.add_parser("mark-sent", help="mark a queued item as posted by you")
    ms.add_argument("id", type=int)
    sk = sub.add_parser("mark-skipped", help="mark a queued item as skipped")
    sk.add_argument("id", type=int)
    h = sub.add_parser("log-health", help="log a removal or rule change")
    h.add_argument("note")

    args = parser.parse_args()
    cfg = load(args.config) if args.config else load()
    store = Store(cfg.db_path)

    if args.cmd == "run":
        server.serve(cfg)
    elif args.cmd == "test-rss":
        rss = RedditRSS(RateLimiter(cfg.rss_min_seconds_between_requests))
        print(rss.test(cfg.subreddits[0] if cfg.subreddits else "python"))
    elif args.cmd == "test-telegram":
        ok = telegram.send(cfg, "reddit agents can message you. setup confirmed.")
        print("sent" if ok else "not sent - set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return 0 if ok else 1
    elif args.cmd == "pull":
        rss = RedditRSS(RateLimiter(cfg.rss_min_seconds_between_requests))
        print(f"{scheduler.pull(cfg, store, rss)} new items")
    elif args.cmd == "find-subreddits":
        print(profiles.find_subreddits(cfg, LLM(cfg)))
    elif args.cmd == "update-profiles":
        llm = LLM(cfg)
        for s in cfg.subreddits:
            profiles.nightly_update(cfg, store, llm, s)
    elif args.cmd == "find-niches":
        print(analysis.find_niches(store, LLM(cfg)))
    elif args.cmd == "analyze-problems":
        print(analysis.find_problems(cfg, store, LLM(cfg)))
    elif args.cmd == "build-guide":
        llm = LLM(cfg)
        guide_path = guide.build_guide(cfg, llm, args.problem, args.subreddit)
        page = guide.build_landing_page(cfg, llm, args.problem, args.subreddit,
                                        args.price or cfg.price or "$29", guide_path)
        print(f"guide: {guide_path}\nlanding page: {page}\n"
              "deploy the page (railway static / any host), create the product "
              "on whop so the guide gets emailed on purchase, and replace "
              "WHOP_CHECKOUT_URL in the html with your checkout link.")
    elif args.cmd == "init-product":
        product.ensure_product_file(cfg)
        print(f"fill in {cfg.product_file}\n\n{prompts.STEP7_PRODUCT_FILE}")
    elif args.cmd == "match":
        print(f"{matcher.run(cfg, store, LLM(cfg))} new matches at 4+")
    elif args.cmd == "draft-replies":
        print(f"{replies.run(cfg, store, LLM(cfg))} replies queued")
    elif args.cmd == "draft-posts":
        print(f"{posts.run(cfg, store, LLM(cfg))} posts queued")
    elif args.cmd == "dashboards":
        dashboards.render_all(cfg, store)
        print(cfg.dashboards_dir / "index.html")
    elif args.cmd == "mark-sent":
        store.mark(args.id, "sent")
        dashboards.render_all(cfg, store)
    elif args.cmd == "mark-skipped":
        store.mark(args.id, "skipped")
        dashboards.render_all(cfg, store)
    elif args.cmd == "log-health":
        store.log_health(args.note)
        dashboards.render_all(cfg, store)
    return 0


if __name__ == "__main__":
    sys.exit(main())
