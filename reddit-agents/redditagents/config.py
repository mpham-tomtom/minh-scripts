"""Configuration for both agents.

Everything lives in one YAML file plus a few environment variables for
secrets. The data directory defaults to /data so a Railway volume mounted
there persists between runs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = os.environ.get("REDDIT_AGENTS_CONFIG", "config.yaml")


@dataclass
class Models:
    """Which model does what. From the post:

    - claude opus 5 orchestrates. it's what decides the order of things
    - claude haiku reads the feeds and does the matching. high volume, low difficulty
    - claude sonnet writes the posts and replies and maintains the subreddit
      profiles, because that's where the quality actually shows
    - gemini 2.5 flash handles anything that needs reading at volume
    - kimi k3 builds the landing page and the dashboard
    """

    orchestrator: str = "claude-opus-5"
    matcher: str = "claude-haiku-4-5"
    writer: str = "claude-sonnet-5"
    volume_reader: str = "gemini-2.5-flash"
    builder: str = "kimi-k3"


@dataclass
class Schedule:
    """From the post's step 13. Times are 24h local to the host."""

    pull_every_minutes: int = 30
    nightly_profile_update_hour: int = 2
    morning_hour: int = 7
    weekly_analysis_weekday: int = 0  # Monday
    weekly_analysis_hour: int = 8
    reply_stale_after_hours: int = 12


@dataclass
class Config:
    subreddits: list[str] = field(default_factory=list)
    data_dir: Path = Path(os.environ.get("REDDIT_AGENTS_DATA", "/data"))
    # the rate limit is about one request a minute from a single ip
    rss_min_seconds_between_requests: int = 60
    models: Models = field(default_factory=Models)
    schedule: Schedule = field(default_factory=Schedule)
    # agent two inputs
    product: str = ""  # short name, e.g. "a guide to X"
    audience: str = ""  # who it's for, used by the find-subreddits prompt
    price: str = ""  # e.g. "$29"
    # dashboard base url shown in telegram messages (the railway public url)
    dashboard_url: str = ""

    # secrets, from the environment only - never from the yaml file
    telegram_bot_token: str = field(
        default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", "")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", "")
    )
    gemini_api_key: str = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY", "")
    )
    moonshot_api_key: str = field(
        default_factory=lambda: os.environ.get("MOONSHOT_API_KEY", "")
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "reddit.db"

    @property
    def profiles_dir(self) -> Path:
        return self.data_dir / "profiles"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "output"

    @property
    def dashboards_dir(self) -> Path:
        return self.data_dir / "dashboards"

    @property
    def product_file(self) -> Path:
        return self.data_dir / "product.md"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.profiles_dir, self.output_dir, self.dashboards_dir):
            d.mkdir(parents=True, exist_ok=True)


def load(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    cfg = Config()
    p = Path(path)
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
        cfg.subreddits = [s.removeprefix("r/") for s in raw.get("subreddits", [])]
        if "data_dir" in raw:
            cfg.data_dir = Path(raw["data_dir"])
        cfg.rss_min_seconds_between_requests = raw.get(
            "rss_min_seconds_between_requests", cfg.rss_min_seconds_between_requests
        )
        for k, v in (raw.get("models") or {}).items():
            if hasattr(cfg.models, k):
                setattr(cfg.models, k, v)
        for k, v in (raw.get("schedule") or {}).items():
            if hasattr(cfg.schedule, k):
                setattr(cfg.schedule, k, v)
        cfg.product = raw.get("product", "")
        cfg.audience = raw.get("audience", "")
        cfg.price = raw.get("price", "")
        cfg.dashboard_url = raw.get("dashboard_url", "")
    cfg.ensure_dirs()
    return cfg
