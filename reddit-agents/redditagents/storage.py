"""SQLite storage. Store everything so you build up history rather than only
looking at what's live."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .reddit_rss import FeedItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,             -- post | comment
    subreddit TEXT NOT NULL,
    title TEXT,
    author TEXT,
    body TEXT,
    permalink TEXT,
    timestamp TEXT,                 -- ISO 8601 from the feed
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_sub_time ON items (subreddit, timestamp);

CREATE TABLE IF NOT EXISTS matches (
    item_id TEXT PRIMARY KEY REFERENCES items (item_id),
    score INTEGER NOT NULL,         -- 1 to 5, how directly it relates
    looking_now INTEGER NOT NULL,   -- 1 if clearly looking for a solution right now
    reason TEXT,
    matched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,             -- reply | post
    subreddit TEXT NOT NULL,
    target_permalink TEXT,          -- the comment/thread to reply to, or the submit page
    target_item_id TEXT,
    text TEXT NOT NULL,
    removal_risk TEXT,              -- posts only: what might get it removed and what to change
    time_sensitivity TEXT,          -- ISO timestamp of the thread it answers, newest first
    status TEXT NOT NULL DEFAULT 'queued',  -- queued | sent | skipped
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS skip_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT,
    reason TEXT NOT NULL,
    logged_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note TEXT NOT NULL,             -- removals, rule changes, anything that doesn't fit
    logged_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
    job TEXT PRIMARY KEY,
    last_run TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,             -- niches | problems
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- items ----

    def save_items(self, items: list[FeedItem]) -> int:
        """Insert new items; returns how many were actually new."""
        cur = self.conn.executemany(
            "INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (i.item_id, i.kind, i.subreddit, i.title, i.author, i.body,
                 i.permalink, i.timestamp, _now())
                for i in items
            ],
        )
        self.conn.commit()
        return cur.rowcount

    def recent_items(self, days: int, subreddit: str | None = None,
                     limit: int = 5000) -> list[sqlite3.Row]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        q = "SELECT * FROM items WHERE timestamp >= ?"
        args: list = [cutoff]
        if subreddit:
            q += " AND subreddit = ?"
            args.append(subreddit)
        q += " ORDER BY timestamp DESC LIMIT ?"
        args.append(limit)
        return self.conn.execute(q, args).fetchall()

    def unmatched_items(self, days: int = 31, limit: int = 200) -> list[sqlite3.Row]:
        """Items not yet scored. Anything older than a month is ignored."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return self.conn.execute(
            """SELECT i.* FROM items i
               LEFT JOIN matches m ON m.item_id = i.item_id
               WHERE m.item_id IS NULL AND i.timestamp >= ?
               ORDER BY i.timestamp DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()

    # ---- matches ----

    def save_match(self, item_id: str, score: int, looking_now: bool, reason: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO matches VALUES (?,?,?,?,?)",
            (item_id, score, int(looking_now), reason, _now()),
        )
        self.conn.commit()

    def matches_needing_replies(self, min_score: int = 4) -> list[sqlite3.Row]:
        """Matches scoring 4 or above with no queued/sent reply yet."""
        return self.conn.execute(
            """SELECT i.*, m.score, m.looking_now, m.reason FROM matches m
               JOIN items i ON i.item_id = m.item_id
               LEFT JOIN queue q ON q.target_item_id = m.item_id AND q.kind = 'reply'
               WHERE m.score >= ? AND q.id IS NULL
               ORDER BY i.timestamp DESC""",
            (min_score,),
        ).fetchall()

    # ---- queue ----

    def enqueue(self, kind: str, subreddit: str, text: str,
                target_permalink: str = "", target_item_id: str = "",
                removal_risk: str = "", time_sensitivity: str = "") -> None:
        self.conn.execute(
            """INSERT INTO queue (kind, subreddit, target_permalink, target_item_id,
                                  text, removal_risk, time_sensitivity, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (kind, subreddit, target_permalink, target_item_id, text,
             removal_risk, time_sensitivity, _now()),
        )
        self.conn.commit()

    def queued(self, kind: str | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM queue WHERE status = 'queued'"
        args: list = []
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        # a thread from an hour ago goes above one from yesterday
        q += " ORDER BY time_sensitivity DESC, created_at DESC"
        return self.conn.execute(q, args).fetchall()

    def sent(self, limit: int = 100) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM queue WHERE status = 'sent' ORDER BY resolved_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def mark(self, queue_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE queue SET status = ?, resolved_at = ? WHERE id = ?",
            (status, _now(), queue_id),
        )
        self.conn.commit()

    def already_replied_permalinks(self) -> set[str]:
        """So you don't do the same thread twice."""
        rows = self.conn.execute(
            "SELECT target_permalink FROM queue WHERE status = 'sent'"
        ).fetchall()
        return {r["target_permalink"] for r in rows}

    def stale_queued_replies(self, hours: int) -> list[sqlite3.Row]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        return self.conn.execute(
            "SELECT * FROM queue WHERE status='queued' AND kind='reply' AND created_at < ?",
            (cutoff,),
        ).fetchall()

    # ---- logs ----

    def log_skip(self, item_id: str, reason: str) -> None:
        self.conn.execute(
            "INSERT INTO skip_log (item_id, reason, logged_at) VALUES (?,?,?)",
            (item_id, reason, _now()),
        )
        self.conn.commit()

    def log_health(self, note: str) -> None:
        self.conn.execute(
            "INSERT INTO account_health (note, logged_at) VALUES (?,?)", (note, _now())
        )
        self.conn.commit()

    def health_notes(self, limit: int = 50) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM account_health ORDER BY logged_at DESC LIMIT ?", (limit,)
        ).fetchall()

    # ---- analyses ----

    def save_analysis(self, kind: str, text: str) -> None:
        self.conn.execute(
            "INSERT INTO analyses (kind, text, created_at) VALUES (?,?,?)",
            (kind, text, _now()),
        )
        self.conn.commit()

    def latest_analysis(self, kind: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM analyses WHERE kind = ? ORDER BY created_at DESC LIMIT 1",
            (kind,),
        ).fetchone()

    # ---- scheduler bookkeeping ----

    def last_run(self, job: str) -> datetime | None:
        row = self.conn.execute(
            "SELECT last_run FROM job_runs WHERE job = ?", (job,)
        ).fetchone()
        return datetime.fromisoformat(row["last_run"]) if row else None

    def mark_run(self, job: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO job_runs VALUES (?,?)", (job, _now())
        )
        self.conn.commit()

    # ---- posting windows, computed from the data itself ----

    def active_hours(self, subreddit: str) -> list[int]:
        """The three UTC hours this community is most active in, from history."""
        rows = self.conn.execute(
            """SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS h, COUNT(*) AS n
               FROM items WHERE subreddit = ? GROUP BY h ORDER BY n DESC LIMIT 3""",
            (subreddit,),
        ).fetchall()
        return [r["h"] for r in rows]
