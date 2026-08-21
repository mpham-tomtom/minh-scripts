"""Step 13: the schedule.

- every 30 minutes: pull new posts and comments from the subreddits
- through the day: find new matches and queue replies for them
- every night: update the subreddit profiles from that day's activity
- every morning: draft five posts, queue them, and update both dashboards
- weekly: run the problem analysis and report what's changed

Each morning you get a telegram message with what's waiting and a link to
the dashboard. You also get pinged when a posting window opens for a
subreddit that has a post queued, and when a queued reply is about to go
stale.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from . import analysis, dashboards, matcher, posts, profiles, replies, telegram
from .config import Config
from .llm import LLM
from .reddit_rss import RateLimiter, RedditRSS
from .storage import Store

log = logging.getLogger(__name__)


def pull(cfg: Config, store: Store, rss: RedditRSS) -> int:
    """Pull new posts and comments from every subreddit and store them."""
    new = 0
    for sub in cfg.subreddits:
        try:
            new += store.save_items(rss.posts(sub))
            new += store.save_items(rss.comments(sub))
        except Exception:
            log.exception("pull failed for r/%s", sub)
    # tell me how much you're pulling and flag it if you're getting close
    # to the rate limit: 2 requests per subreddit per 30 minutes
    per_hour = len(cfg.subreddits) * 4
    log.info("pull done: %d new items stored (%d rss requests/hour at this "
             "subreddit count, limit is ~60)", new, per_hour)
    if per_hour > 45:
        telegram.send(cfg, f"heads up: {len(cfg.subreddits)} subreddits means "
                           f"~{per_hour} rss requests an hour, close to the "
                           f"~60/hour limit. drop some or slow the pull.")
    return new


def _due(store: Store, job: str, every: timedelta) -> bool:
    last = store.last_run(job)
    return last is None or datetime.now(timezone.utc) - last >= every


def _due_daily_at(store: Store, job: str, hour: int, now: datetime) -> bool:
    if now.hour != hour:
        return False
    last = store.last_run(job)
    return last is None or last.date() < now.date()


def morning(cfg: Config, store: Store, llm: LLM) -> None:
    posts.run(cfg, store, llm)
    dashboards.render_all(cfg, store)
    queued_replies = len(store.queued("reply"))
    queued_posts = len(store.queued("post"))
    url = cfg.dashboard_url or str(cfg.dashboards_dir / "index.html")
    telegram.send(
        cfg,
        f"morning. waiting for you: {queued_replies} replies and "
        f"{queued_posts} posts queued.\ndashboard: {url}",
    )


def run_forever(cfg: Config) -> None:
    store = Store(cfg.db_path)
    llm = LLM(cfg)
    rss = RedditRSS(RateLimiter(cfg.rss_min_seconds_between_requests))
    sched = cfg.schedule
    log.info("scheduler running for %s", [f"r/{s}" for s in cfg.subreddits])

    while True:
        now = datetime.now(timezone.utc)
        try:
            # every 30 minutes: pull, then match and queue replies on what's new
            if _due(store, "pull", timedelta(minutes=sched.pull_every_minutes)):
                pull(cfg, store, rss)
                store.mark_run("pull")
                if matcher.run(cfg, store, llm):
                    replies.run(cfg, store, llm)
                    dashboards.render_all(cfg, store)

            # every night: update the subreddit profiles from the day's activity
            if _due_daily_at(store, "nightly_profiles",
                             sched.nightly_profile_update_hour, now):
                for sub in cfg.subreddits:
                    try:
                        profiles.nightly_update(cfg, store, llm, sub)
                    except Exception:
                        log.exception("profile update failed for r/%s", sub)
                store.mark_run("nightly_profiles")

            # every morning: draft five posts, queue them, update both dashboards
            if _due_daily_at(store, "morning", sched.morning_hour, now):
                morning(cfg, store, llm)
                store.mark_run("morning")

            # weekly: the problem analysis, and what's changed
            if (now.weekday() == sched.weekly_analysis_weekday
                    and _due(store, "weekly_problems", timedelta(days=6))
                    and now.hour >= sched.weekly_analysis_hour):
                result = analysis.find_problems(cfg, store, llm)
                dashboards.render_all(cfg, store)
                telegram.send(cfg, "weekly problem analysis is done. "
                                   "what people are asking for:\n\n" + result[:3500])
                store.mark_run("weekly_problems")

            # ping when a posting window opens for a subreddit with a post queued
            queued_post_subs = {q["subreddit"] for q in store.queued("post")}
            for sub in queued_post_subs:
                if now.hour in store.active_hours(sub):
                    job = f"window_ping_{sub}_{now.date()}_{now.hour}"
                    if store.last_run(job) is None:
                        telegram.send(cfg, f"posting window open for r/{sub} "
                                           f"and you have a post queued for it.")
                        store.mark_run(job)

            # ping when a queued reply is about to go stale
            stale = store.stale_queued_replies(sched.reply_stale_after_hours)
            if stale and _due(store, "stale_ping", timedelta(hours=6)):
                telegram.send(cfg, f"{len(stale)} queued replies are older than "
                                   f"{sched.reply_stale_after_hours}h and about "
                                   f"to go stale. post or skip them.")
                store.mark_run("stale_ping")

        except Exception:
            log.exception("scheduler tick failed")

        time.sleep(60)
