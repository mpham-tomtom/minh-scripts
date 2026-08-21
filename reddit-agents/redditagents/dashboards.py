"""Step 12: the dashboards. Two of them, one per agent, updated each morning,
plain and on one page each.

- finding.html: what's coming up this week ranked by frequency with real
  quotes underneath, and what changed in the subreddit profiles
- selling.html: everything ready to send (full text, copy button, direct
  link, sorted by time sensitivity), what's already been sent, and account
  health

If something happens that doesn't fit either page, it gets a section rather
than being left out (the account_health table feeds that).
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import posts as posts_mod
from . import profiles
from .config import Config
from .storage import Store

log = logging.getLogger(__name__)

STYLE = """
body { font-family: -apple-system, system-ui, sans-serif; max-width: 860px;
       margin: 2rem auto; padding: 0 1rem; line-height: 1.5; color: #1a1a1a;
       background: #fdfdfc; }
h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 2rem;
     border-bottom: 1px solid #ddd; padding-bottom: .3rem; }
.card { border: 1px solid #ddd; border-radius: 6px; padding: .8rem 1rem;
        margin: .8rem 0; background: #fff; }
.card pre { white-space: pre-wrap; font-family: inherit; margin: .5rem 0; }
.meta { color: #666; font-size: .85rem; }
.risk { color: #8a5a00; font-size: .9rem; margin-top: .4rem; }
button { cursor: pointer; padding: .25rem .7rem; border: 1px solid #bbb;
         border-radius: 4px; background: #f4f4f4; }
a { color: #0b5cad; }
blockquote { border-left: 3px solid #ccc; margin: .4rem 0; padding-left: .8rem;
             color: #444; }
"""

COPY_JS = """
function copyText(id) {
  navigator.clipboard.writeText(document.getElementById(id).innerText)
    .then(() => { event.target.textContent = 'copied'; });
}
"""


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{STYLE}</style>"
        f"<script>{COPY_JS}</script></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<p class='meta'>updated {datetime.now(timezone.utc).isoformat(timespec='minutes')}</p>"
        f"{body}</body></html>"
    )


def _e(text: str) -> str:
    return html.escape(text or "")


# ---- dashboard one: finding the product ----

def _profile_changes(cfg: Config, days: int = 7) -> str:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    out = []
    for sub in cfg.subreddits:
        text = profiles.read_profile(cfg, sub)
        m = re.search(r"## update log\n(.*)", text, re.S | re.I)
        if not m:
            continue
        recent = [
            line for line in m.group(1).strip().splitlines()
            if (d := re.search(r"(\d{4}-\d{2}-\d{2})", line)) and d.group(1) >= cutoff
        ]
        if recent:
            out.append(f"<h3>r/{_e(sub)}</h3><ul>"
                       + "".join(f"<li>{_e(l.lstrip('- '))}</li>" for l in recent)
                       + "</ul>")
    return "".join(out) or "<p class='meta'>no profile changes this week</p>"


def render_finding(cfg: Config, store: Store) -> Path:
    body = ["<h2>what's coming up in the subreddits this week</h2>"]
    latest = store.latest_analysis("problems")
    if latest:
        body.append(f"<div class='card'><pre>{_e(latest['text'])}</pre>"
                    f"<p class='meta'>analysis from {_e(latest['created_at'])}</p></div>")
    else:
        body.append("<p class='meta'>no problem analysis yet - it runs weekly, "
                    "or run it now with: python -m redditagents analyze-problems</p>")

    week = store.recent_items(days=7)
    counts: dict[str, int] = {}
    for r in week:
        counts[r["subreddit"]] = counts.get(r["subreddit"], 0) + 1
    body.append("<h2>volume this week</h2><ul>")
    for sub, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        body.append(f"<li>r/{_e(sub)}: {n} items</li>")
    body.append("</ul>")

    body.append("<h2>what changed in the subreddit profiles</h2>")
    body.append(_profile_changes(cfg))

    niches = store.latest_analysis("niches")
    if niches:
        body.append("<h2>latest niche analysis</h2>")
        body.append(f"<div class='card'><pre>{_e(niches['text'])}</pre></div>")

    out = cfg.dashboards_dir / "finding.html"
    out.write_text(_page("finding the product", "".join(body)))
    return out


# ---- dashboard two: selling ----

def render_selling(cfg: Config, store: Store) -> Path:
    body = ["<h2>ready to send</h2>"]
    queued = store.queued()
    if not queued:
        body.append("<p class='meta'>nothing queued right now</p>")
    for i, q in enumerate(queued):
        text_id = f"q{q['id']}"
        label = "reply to" if q["kind"] == "reply" else "submit at"
        body.append(
            f"<div class='card'>"
            f"<div class='meta'>{_e(q['kind'])} for r/{_e(q['subreddit'])} "
            f"&middot; queued {_e(q['created_at'])}"
            + (f" &middot; thread from {_e(q['time_sensitivity'])}" if q["time_sensitivity"] else "")
            + f"</div>"
            f"<pre id='{text_id}'>{_e(q['text'])}</pre>"
            + (f"<div class='risk'>removal risk: {_e(q['removal_risk'])}</div>"
               if q["removal_risk"] else "")
            + f"<button onclick=\"copyText('{text_id}')\">copy</button> "
            f"<a href='{_e(q['target_permalink'])}' target='_blank'>{label} thread &rarr;</a>"
            f"</div>"
        )

    body.append("<h2>already sent</h2>")
    sent = store.sent()
    if not sent:
        body.append("<p class='meta'>nothing marked sent yet - after posting, run: "
                    "python -m redditagents mark-sent &lt;id&gt;</p>")
    body.append("<ul>")
    for s in sent:
        body.append(
            f"<li class='meta'>{_e(s['resolved_at'])} &middot; {_e(s['kind'])} in "
            f"r/{_e(s['subreddit'])} &middot; "
            f"<a href='{_e(s['target_permalink'])}' target='_blank'>thread</a></li>"
        )
    body.append("</ul>")

    body.append("<h2>account health</h2>")
    notes = store.health_notes()
    if not notes:
        body.append("<p class='meta'>no removals or rule changes logged</p>")
    body.append("<ul>")
    for n in notes:
        body.append(f"<li class='meta'>{_e(n['logged_at'])}: {_e(n['note'])}</li>")
    body.append("</ul>")

    windows = posts_mod.posting_windows(cfg, store)
    body.append("<h2>posting windows (utc, from when each community is active)</h2><ul>")
    for sub, hours in windows.items():
        hh = ", ".join(f"{h:02d}:00" for h in hours) or "not enough data yet"
        body.append(f"<li class='meta'>r/{_e(sub)}: {hh}</li>")
    body.append("</ul>")

    out = cfg.dashboards_dir / "selling.html"
    out.write_text(_page("selling", "".join(body)))
    return out


def render_index(cfg: Config) -> Path:
    out = cfg.dashboards_dir / "index.html"
    out.write_text(_page(
        "reddit agents",
        "<ul><li><a href='finding.html'>finding the product</a></li>"
        "<li><a href='selling.html'>selling</a></li></ul>",
    ))
    return out


def render_all(cfg: Config, store: Store) -> None:
    render_finding(cfg, store)
    render_selling(cfg, store)
    render_index(cfg)
    log.info("dashboards updated in %s", cfg.dashboards_dir)
