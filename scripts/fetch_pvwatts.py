#!/usr/bin/env python3
"""Fetch rooftop solar output per kW for one large city in every state from PVWatts v8.

PVWatts is run by the National Laboratory of the Rockies (NLR, formerly NREL).
Docs:  https://developer.nlr.gov/docs/solar/pvwatts/v8/
Key:   free, https://developer.nlr.gov/signup/  ->  env NLR_API_KEY (NREL_API_KEY also accepted; old keys still work)
Limit: 1,000 requests per hour. This script makes 51 and pauses between calls.

The result changes only when NLR updates its weather data, so it refreshes once a year
(site.config.json -> data.pvwatts_refresh_days) or when run with --force.

Usage:  python3 scripts/fetch_pvwatts.py [--force]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from common import (SOLAR_FILE, gh_warning, http_get_json, load_config, load_json,  # noqa: E402
                    load_states_meta, log, save_json, utc_now_iso)

HOSTS = ["https://developer.nlr.gov"]  # developer.nrel.gov stopped resolving on May 29, 2026; same API keys work here
PATH = "/api/pvwatts/v8.json"


def is_stale(days: int) -> bool:
    data = load_json(SOLAR_FILE)
    if not data or not data.get("states"):
        return True
    try:
        fetched = datetime.fromisoformat(data["fetched_at"])
    except (KeyError, ValueError):
        return True
    return (datetime.now(timezone.utc) - fetched).days >= days


def call(key: str, system: dict, lat: float, lon: float) -> dict:
    params = {"api_key": key, **system, "lat": lat, "lon": lon, "dataset": "nsrdb", "radius": 0, "timeframe": "monthly"}
    last = None
    for host in HOSTS:
        url = f"{host}{PATH}?{urllib.parse.urlencode(params)}"
        try:
            res = http_get_json(url, timeout=60)
        except RuntimeError as e:
            last = e
            continue
        if res.get("errors"):
            raise RuntimeError("; ".join(map(str, res["errors"])))
        return res
    raise last or RuntimeError("PVWatts unreachable")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    key = (os.environ.get("NLR_API_KEY") or os.environ.get("NREL_API_KEY") or "").strip()
    if not key:
        gh_warning("NLR_API_KEY is not set: skipping PVWatts. Solar sections stay hidden until it is added.")
        return 0

    cfg = load_config()
    days = int(cfg.get("data", {}).get("pvwatts_refresh_days", 365))
    if not args.force and not is_stale(days):
        log(f"PVWatts data is newer than {days} days. Skipping (use --force to refresh).")
        return 0

    system = cfg.get("data", {}).get("pvwatts_system", {
        "system_capacity": 1, "module_type": 0, "losses": 14, "array_type": 1, "tilt": 20, "azimuth": 180})
    states, failed = {}, []
    for s in load_states_meta():
        try:
            res = call(key, system, s["lat"], s["lon"])
            out = res.get("outputs", {})
            cap = float(system.get("system_capacity", 1)) or 1.0
            states[s["code"]] = {
                "city": s["city"],
                "lat": s["lat"],
                "lon": s["lon"],
                "ac_annual_per_kw": round(float(out["ac_annual"]) / cap, 1),
                "ac_monthly_per_kw": [round(float(x) / cap, 1) for x in out.get("ac_monthly", [])],
                "solrad_annual": round(float(out.get("solrad_annual", 0)), 2),
                "capacity_factor": round(float(out.get("capacity_factor", 0)), 2),
                "weather_data_source": res.get("station_info", {}).get("weather_data_source", ""),
            }
            log(f"{s['code']}: {states[s['code']]['ac_annual_per_kw']} kWh per kW per year ({s['city']})")
        except Exception as e:  # noqa: BLE001
            failed.append(s["code"])
            log(f"{s['code']}: failed ({e})")
        time.sleep(0.8)

    if len(states) < 40:
        log(f"Only {len(states)} states succeeded; keeping the previous solar file.")
        return 1
    prev = load_json(SOLAR_FILE, {}) or {}
    for code in failed:  # keep last year's value for any state that failed this time
        if code in prev.get("states", {}):
            states[code] = prev["states"][code]
    save_json(SOLAR_FILE, {
        "source": "PVWatts v8, National Laboratory of the Rockies (NLR, formerly NREL)",
        "source_url": "https://pvwatts.nlr.gov/",
        "fetched_at": utc_now_iso(),
        "system": system,
        "states": dict(sorted(states.items())),
    })
    log(f"Saved {SOLAR_FILE.name} for {len(states)} states. Failed: {', '.join(failed) or 'none'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
