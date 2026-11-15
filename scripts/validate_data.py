#!/usr/bin/env python3
"""Sanity-check the data before anything is built or published.

A failed check exits with code 1, which stops the GitHub Actions run: the live site keeps
serving the last good version instead of publishing wrong numbers.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import (EIA_FILE, SEED_FILE, SOLAR_FILE, add_months, gh_warning, load_json,  # noqa: E402
                    load_states_meta, log, parse_period, today)


def check_eia(data: dict, codes: list[str]) -> list[str]:
    errors = []
    latest = data.get("latest_period", "")
    try:
        parse_period(latest)
    except Exception:  # noqa: BLE001
        return [f"latest_period is not YYYY-MM: {latest!r}"]

    t = today()
    age = (t.year * 12 + t.month) - (parse_period(latest)[0] * 12 + parse_period(latest)[1])
    if age > 6:
        gh_warning(f"EIA latest month {latest} is {age} months old. EIA normally lags about 2 to 3 months.")

    states = data.get("states", {})
    missing = [c for c in codes if not any(r["period"] == latest and r["price"] is not None for r in states.get(c, []))]
    if len(missing) > 1:
        errors.append(f"{len(missing)} jurisdictions have no price for {latest}: {', '.join(missing)}")

    for c in codes + ["US"]:
        rows = states.get(c, [])
        for r in rows[:13]:
            p, cust, sales, rev = r["price"], r["customers"], r["sales"], r["revenue"]
            if p is not None and not (4 <= p <= 90):
                errors.append(f"{c} {r['period']}: price {p} cents/kWh is outside 4-90")
            if cust and sales:
                usage = sales * 1e6 / cust
                if not (80 <= usage <= 3500):
                    errors.append(f"{c} {r['period']}: usage {usage:.0f} kWh/customer is outside 80-3500")
            if cust and rev:
                bill = rev * 1e6 / cust
                if not (15 <= bill <= 700):
                    errors.append(f"{c} {r['period']}: bill ${bill:.0f}/customer is outside 15-700")
        if c != "US" and rows and len(rows) < 13:
            gh_warning(f"{c} has only {len(rows)} months of data; year-over-year change will be hidden.")
    year_ago = add_months(latest, -12)
    if not any(r["period"] == year_ago for r in states.get("TX", [])):
        gh_warning("No year-ago month in the data; change-over-the-year figures will be hidden.")
    return errors


def check_solar(data: dict) -> list[str]:
    errors = []
    for code, s in data.get("states", {}).items():
        v = s.get("ac_annual_per_kw")
        if v is None or not (500 <= v <= 2400):
            errors.append(f"solar {code}: {v} kWh per kW per year is outside 500-2400")
    return errors


def main() -> int:
    codes = [s["code"] for s in load_states_meta()]
    errors: list[str] = []

    eia = load_json(EIA_FILE)
    if eia:
        errors += check_eia(eia, codes)
        log(f"Checked {EIA_FILE.name}: latest month {eia.get('latest_period')}.")
    else:
        seed = load_json(SEED_FILE)
        if not seed or len([c for c in codes if c in seed.get("states", {})]) < 51:
            errors.append("No EIA data file and the seed file is missing or incomplete.")
        else:
            gh_warning("Building from the seed data (July 2026). Add the EIA_API_KEY secret for monthly updates.")

    solar = load_json(SOLAR_FILE)
    if solar:
        errors += check_solar(solar)
        log(f"Checked {SOLAR_FILE.name}: {len(solar.get('states', {}))} states.")

    if errors:
        for e in errors[:50]:
            log(f"DATA ERROR: {e}")
        log(f"{len(errors)} problem(s). Nothing will be published.")
        return 1
    log("Data checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
