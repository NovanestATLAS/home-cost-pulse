#!/usr/bin/env python3
"""Fetch monthly residential electricity data for every state from the EIA API v2.

Route:  https://api.eia.gov/v2/electricity/retail-sales/data/
Data:   price (cents/kWh), revenue (million $), sales (million kWh), customers (count)
Facet:  sectorid = RES (residential)
Key:    free, from https://www.eia.gov/opendata/register.php  ->  env EIA_API_KEY

Writes data/eia_residential_monthly.json. EIA data is public domain
(https://www.eia.gov/about/copyrights_reuse.php); credit "Source: U.S. Energy Information Administration".

Usage:  python3 scripts/fetch_eia.py [--months 36]
Exit codes: 0 ok or skipped (no key), 1 fetch/parse failure (existing data file is left untouched).
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(__file__))
from common import (EIA_FILE, add_months, gh_warning, http_get_json, load_config, load_json,  # noqa: E402
                    load_states_meta, log, save_json, to_float, today, utc_now_iso)

API = "https://api.eia.gov/v2/electricity/retail-sales/data/"
PAGE = 5000  # EIA's JSON row limit per request


def build_params(key: str, start: str, offset: int) -> list[tuple[str, str]]:
    return [
        ("api_key", key),
        ("frequency", "monthly"),
        ("data[0]", "price"),
        ("data[1]", "revenue"),
        ("data[2]", "sales"),
        ("data[3]", "customers"),
        ("facets[sectorid][]", "RES"),
        ("start", start),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "desc"),
        ("offset", str(offset)),
        ("length", str(PAGE)),
    ]


def fetch_rows(key: str, start: str) -> list[dict]:
    rows, offset, total = [], 0, None
    while True:
        url = API + "?" + urllib.parse.urlencode(build_params(key, start, offset))
        payload = http_get_json(url)
        if "error" in payload:
            raise RuntimeError(f"EIA error: {payload.get('error')}")
        resp = payload.get("response", {})
        for w in payload.get("warnings", []) or resp.get("warnings", []) or []:
            log(f"EIA warning: {w}")
        batch = resp.get("data", [])
        total = int(resp.get("total", len(batch)) or 0)
        rows.extend(batch)
        offset += len(batch)
        if not batch or offset >= total:
            break
    log(f"EIA returned {len(rows)} rows (total reported: {total}).")
    return rows


def parse_rows(rows: list[dict], wanted: set[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        code = str(r.get("stateid", "")).upper()
        if code not in wanted:
            continue  # skips census regions such as "MAT" or "PACC"
        if str(r.get("sectorid", "RES")).upper() != "RES":
            continue
        period = str(r.get("period", ""))
        if len(period) != 7:
            continue
        out.setdefault(code, []).append({
            "period": period,
            "price": to_float(r.get("price")),
            "revenue": to_float(r.get("revenue")),
            "sales": to_float(r.get("sales")),
            "customers": to_float(r.get("customers")),
        })
    for code in out:
        # newest first, one row per month
        seen, uniq = set(), []
        for row in sorted(out[code], key=lambda x: x["period"], reverse=True):
            if row["period"] not in seen:
                seen.add(row["period"])
                uniq.append(row)
        out[code] = uniq
    return out


def latest_common_period(states: dict[str, list[dict]], codes: list[str]) -> str | None:
    """Newest month for which at least 50 of the 51 jurisdictions have a price."""
    counts: dict[str, int] = {}
    for c in codes:
        for row in states.get(c, []):
            if row["price"] is not None:
                counts[row["period"]] = counts.get(row["period"], 0) + 1
    good = [p for p, n in counts.items() if n >= 50]
    return max(good) if good else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=None, help="months of history to keep")
    args = ap.parse_args()

    key = os.environ.get("EIA_API_KEY", "").strip()
    if not key:
        gh_warning("EIA_API_KEY is not set: skipping the EIA fetch. The site will build from the seed data.")
        return 0

    cfg = load_config()
    months = args.months or int(cfg.get("data", {}).get("eia_months_to_fetch", 36))
    codes = [s["code"] for s in load_states_meta()]
    wanted = set(codes) | {"US"}

    t = today()
    start = add_months(f"{t.year:04d}-{t.month:02d}", -(months + 3))
    try:
        rows = fetch_rows(key, start)
        states = parse_rows(rows, wanted)
    except Exception as e:  # noqa: BLE001
        log(f"EIA fetch failed: {e}")
        return 1

    latest = latest_common_period(states, codes)
    if not latest:
        log("EIA data had no month with prices for at least 50 states. Keeping the previous file.")
        return 1

    # Trim to the requested history, counted back from the latest complete month.
    cutoff = add_months(latest, -(months - 1))
    for c in list(states):
        states[c] = [r for r in states[c] if cutoff <= r["period"] <= latest]

    prev = load_json(EIA_FILE, {})
    data = {
        "source": "U.S. Energy Information Administration (EIA), API v2 route electricity/retail-sales, residential sector",
        "source_url": "https://www.eia.gov/electricity/data/browser/",
        "license": "Public domain (U.S. government work). Credit: Source: U.S. Energy Information Administration.",
        "units": {"price": "cents per kWh", "revenue": "million dollars", "sales": "million kWh", "customers": "count"},
        "fetched_at": utc_now_iso(),
        "latest_period": latest,
        "months": months,
        "states": {c: states[c] for c in sorted(states)},
    }
    if prev.get("states") == data["states"]:
        # Leave the file untouched so the workflow makes no commit and no redeploy.
        log(f"EIA data unchanged (latest month {latest}). Nothing to save.")
        return 0
    save_json(EIA_FILE, data)
    log(f"Saved {EIA_FILE.name}: NEW DATA, latest month {latest}, {len(states)} jurisdictions "
        f"(previous latest: {prev.get('latest_period', 'none')}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
