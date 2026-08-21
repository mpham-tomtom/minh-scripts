"""Model routing. Running one model for all of it is how the cost gets away
from you, so each role gets the model the post assigns it:

- orchestrator (claude opus 5): decides the order of things, runs the
  niche/problem analyses
- matcher (claude haiku): reads the pulled items and does the matching
- writer (claude sonnet): posts, replies and subreddit profiles
- volume_reader (gemini 2.5 flash): reading at volume, e.g. a few thousand
  comments to find patterns
- builder (kimi k3): the landing page and the dashboard shell

Gemini and Kimi are optional - if their API keys aren't set, their roles
fall back to the Claude models so the system still runs end to end.
"""

from __future__ import annotations

import logging

import anthropic
import requests

from .config import Config

log = logging.getLogger(__name__)


class LLM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = anthropic.Anthropic()

    # ---- claude ----

    def _claude(self, model: str, system: str, prompt: str,
                max_tokens: int = 16000) -> str:
        response = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            details = response.stop_details.explanation if response.stop_details else ""
            raise RuntimeError(f"model refused: {details}")
        return "".join(b.text for b in response.content if b.type == "text")

    def _claude_long(self, model: str, system: str, prompt: str,
                     max_tokens: int = 64000) -> str:
        """Streaming variant for long outputs like the guide."""
        with self.client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            response = stream.get_final_message()
        if response.stop_reason == "refusal":
            details = response.stop_details.explanation if response.stop_details else ""
            raise RuntimeError(f"model refused: {details}")
        return "".join(b.text for b in response.content if b.type == "text")

    # ---- roles ----

    def orchestrate(self, system: str, prompt: str) -> str:
        return self._claude(self.cfg.models.orchestrator, system, prompt)

    def match(self, system: str, prompt: str, max_tokens: int = 4000) -> str:
        return self._claude(self.cfg.models.matcher, system, prompt, max_tokens)

    def write(self, system: str, prompt: str) -> str:
        return self._claude(self.cfg.models.writer, system, prompt)

    def write_long(self, system: str, prompt: str) -> str:
        return self._claude_long(self.cfg.models.writer, system, prompt)

    def read_volume(self, system: str, prompt: str) -> str:
        """Gemini 2.5 flash when a key is set, otherwise the matcher model."""
        if self.cfg.gemini_api_key:
            try:
                return self._gemini(system, prompt)
            except Exception:
                log.exception("gemini call failed, falling back to claude")
        return self._claude(self.cfg.models.matcher, system, prompt)

    def build(self, system: str, prompt: str) -> str:
        """Kimi when a key is set, otherwise the writer model."""
        if self.cfg.moonshot_api_key:
            try:
                return self._kimi(system, prompt)
            except Exception:
                log.exception("kimi call failed, falling back to claude")
        return self._claude_long(self.cfg.models.writer, system, prompt)

    # ---- non-anthropic providers ----

    def _gemini(self, system: str, prompt: str) -> str:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.cfg.models.volume_reader}:generateContent",
            headers={"x-goog-api-key": self.cfg.gemini_api_key},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            },
            timeout=300,
        )
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)

    def _kimi(self, system: str, prompt: str) -> str:
        resp = requests.post(
            "https://api.moonshot.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.cfg.moonshot_api_key}"},
            json={
                "model": self.cfg.models.builder,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=600,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
