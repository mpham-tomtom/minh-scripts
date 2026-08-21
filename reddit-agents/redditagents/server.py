"""Serves the two dashboards. On Railway this binds to $PORT so the
dashboards get a public url; the scheduler runs in a background thread of
the same process so one service covers everything."""

from __future__ import annotations

import functools
import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import scheduler
from .config import Config

log = logging.getLogger(__name__)


def serve(cfg: Config, with_scheduler: bool = True) -> None:
    if with_scheduler:
        t = threading.Thread(target=scheduler.run_forever, args=(cfg,), daemon=True)
        t.start()

    port = int(os.environ.get("PORT", "8080"))
    handler = functools.partial(
        SimpleHTTPRequestHandler, directory=str(cfg.dashboards_dir)
    )
    log.info("dashboards at http://0.0.0.0:%d", port)
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()
