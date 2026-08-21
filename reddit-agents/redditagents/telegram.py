"""Telegram notifications. The agent messages you; it never posts anywhere."""

from __future__ import annotations

import logging

import requests

from .config import Config

log = logging.getLogger(__name__)


def send(cfg: Config, text: str) -> bool:
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        log.info("telegram not configured, would have sent: %s", text)
        return False
    resp = requests.post(
        f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage",
        json={"chat_id": cfg.telegram_chat_id, "text": text,
              "disable_web_page_preview": True},
        timeout=30,
    )
    if not resp.ok:
        log.error("telegram send failed: %s", resp.text)
    return resp.ok
