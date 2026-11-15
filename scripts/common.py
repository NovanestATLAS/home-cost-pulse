"""Shared helpers for the Home Cost Pulse pipeline. Standard library only."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DIST_DIR = ROOT / "dist"
ASSETS_DIR = ROOT / "assets"
CONTENT_DIR = ROOT / "content"

EIA_FILE = DATA_DIR / "eia_residential_monthly.json"
SOLAR_FILE = DATA_DIR / "solar_pvwatts.json"
SEED_FILE = DATA_DIR / "seed" / "eia_seed_2026-07.json"
META_FILE = DATA_DIR / "states_meta.json"
CONFIG_FILE = ROOT / "site.config.json"

USER_AGENT = "HomeCostPulse/1.0 (+https://github.com/; static site data pipeline)"


def log(msg: str) -> None:
    print(msg, flush=True)


def gh_warning(msg: str) -> None:
    """Prints a warning that GitHub Actions shows as an annotation."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{msg}", flush=True)
    else:
        print(f"WARNING: {msg}", flush=True)


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    """Atomic write so a failed run never leaves a half-written data file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    tmp.replace(path)


def load_config() -> dict:
    cfg = load_json(CONFIG_FILE, {})
    # Environment overrides (set by the GitHub Actions workflow).
    site_url = os.environ.get("SITE_URL", "").strip()
    if site_url:
        cfg["site_url"] = site_url
    cfg["site_url"] = cfg.get("site_url", "").rstrip("/")
    base = os.environ.get("BASE_PATH", cfg.get("base_path", "")).strip()
    cfg["base_path"] = ("/" + base.strip("/")) if base.strip("/") else ""
    return cfg


def load_states_meta() -> list[dict]:
    return load_json(META_FILE)["states"]


def http_get_json(url: str, timeout: int = 30, retries: int = 4, backoff: float = 2.0):
    """GET a JSON document with retries on rate limits and server errors."""
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            last_err = RuntimeError(f"HTTP {e.code} for {redact(url)}: {body}")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(backoff ** attempt)
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = RuntimeError(f"Request failed for {redact(url)}: {e}")
            if attempt < retries:
                time.sleep(backoff ** attempt)
                continue
            raise last_err
    raise last_err  # pragma: no cover


def redact(url: str) -> str:
    """Hide API keys in log output."""
    import re
    return re.sub(r"(api_key=)[^&]+", r"\1***", url)


def to_float(v):
    """EIA returns numbers as strings; blanks and symbols like 'NA' or '--' become None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s in ("", "NA", "--", "W", "*", "(s)", "null", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ---------- dates ----------
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def parse_period(p: str) -> tuple[int, int]:
    y, m = p.split("-")
    return int(y), int(m)


def add_months(p: str, n: int) -> str:
    y, m = parse_period(p)
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_name(p: str) -> str:
    y, m = parse_period(p)
    return f"{MONTHS[m - 1]} {y}"


def month_short(p: str) -> str:
    y, m = parse_period(p)
    return f"{MONTHS[m - 1][:3]} {y}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> date:
    return datetime.now(timezone.utc).date()


# ---------- formatting ----------
def fmt_int(n) -> str:
    return f"{n:,.0f}"


def fmt_money(n, d: int = 2) -> str:
    sign = "-" if n < 0 else ""
    return f"{sign}${abs(n):,.{d}f}"


def fmt_cents(n) -> str:
    return f"{n:.2f}¢"


def fmt_pct(n, d: int = 1) -> str:
    return f"{abs(n):.{d}f}%"


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def esc(s) -> str:
    return escape(str(s), quote=True)


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(code)
