from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import urlsplit

USER_AGENT = "RadarShrinkflationPT/0.1 (projeto sem fins lucrativos; github.com/capebm/shrinkflation)"


BACKOFF = (5, 15, 45)  # seconds between attempts; overloaded public APIs answer 503 or 429


def get(url: str, *, retries: int = len(BACKOFF) + 1, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-PT,pt;q=0.9"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if (exc.code < 500 and exc.code != 429) or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(BACKOFF[min(attempt, len(BACKOFF) - 1)])
    raise RuntimeError("unreachable")


def get_json(url: str) -> dict:
    return json.loads(get(url))


_robots: dict[str, urllib.robotparser.RobotFileParser] = {}


def allowed(url: str) -> bool:
    """Respect robots.txt. An unreachable robots.txt counts as a refusal."""
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.parse(get(base + "/robots.txt", retries=1).splitlines())
        except Exception:
            rp.disallow_all = True
        _robots[base] = rp
    return _robots[base].can_fetch(USER_AGENT, url)
