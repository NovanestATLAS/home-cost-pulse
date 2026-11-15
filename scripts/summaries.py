"""Turn raw EIA / PVWatts data into one summary per state (and the U.S.).

Live mode uses data/eia_residential_monthly.json (monthly series from the EIA API).
Seed mode uses data/seed/eia_seed_2026-07.json until the API key is set.
"""
from __future__ import annotations

from common import add_months, month_name


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _row_for(rows, period):
    for r in rows:
        if r["period"] == period:
            return r
    return None


def _trailing(rows, latest, n=12):
    want = {add_months(latest, -i) for i in range(n)}
    return [r for r in rows if r["period"] in want]


def _usage_bill(rows):
    """Average monthly kWh and bill per customer over the given rows."""
    usage, bills = [], []
    for r in rows:
        if r["customers"] and r["sales"] is not None:
            usage.append(r["sales"] * 1e6 / r["customers"])
        if r["customers"] and r["revenue"] is not None:
            bills.append(r["revenue"] * 1e6 / r["customers"])
    if len(usage) < 9 or len(bills) < 9:
        return None, None
    return _avg(usage), _avg(bills)


def _aggregate_us(states: dict) -> list[dict]:
    """Build a national series from the 51 jurisdictions if EIA's 'US' rows are missing."""
    by_period: dict[str, dict] = {}
    for code, rows in states.items():
        if code == "US":
            continue
        for r in rows:
            agg = by_period.setdefault(r["period"], {"revenue": 0.0, "sales": 0.0, "customers": 0.0, "n": 0})
            if r["revenue"] is not None and r["sales"] and r["customers"]:
                agg["revenue"] += r["revenue"]
                agg["sales"] += r["sales"]
                agg["customers"] += r["customers"]
                agg["n"] += 1
    out = []
    for p, a in by_period.items():
        if a["n"] >= 50 and a["sales"]:
            out.append({"period": p, "price": a["revenue"] / a["sales"] * 100, "revenue": a["revenue"],
                        "sales": a["sales"], "customers": a["customers"]})
    return sorted(out, key=lambda r: r["period"], reverse=True)


def build(meta: list[dict], eia: dict | None, seed: dict, solar: dict | None) -> dict:
    by_meta = {m["code"]: m for m in meta}
    solar_states = (solar or {}).get("states", {})
    out_states = []

    if eia and eia.get("states"):
        mode = "live"
        latest = eia["latest_period"]
        states = eia["states"]
        us_rows = states.get("US") or _aggregate_us(states)
        basis = f"12 months to {month_name(latest)}"
        prev_label = f"{month_name(add_months(latest, -12))}"

        def summarise(code, rows, name, extra):
            rows = sorted(rows, key=lambda r: r["period"], reverse=True)
            cur = _row_for(rows, latest) or next((r for r in rows if r["price"] is not None), None)
            price = cur["price"] if cur else None
            ya = _row_for(rows, add_months(cur["period"], -12)) if cur else None
            yoy = ((price - ya["price"]) / ya["price"] * 100) if (ya and ya["price"] and price) else None
            kwh, bill = _usage_bill(_trailing(rows, cur["period"] if cur else latest))
            use_basis = basis
            if kwh is None and code in seed["states"]:
                kwh, bill = seed["states"][code]["avg_kwh"], seed["states"][code]["bill_annual"]
                use_basis = "2025 average"
            trend = [(r["period"], r["price"]) for r in sorted(rows, key=lambda r: r["period"]) if r["price"] is not None][-36:]
            return dict(code=code, name=name, price=price, period=cur["period"] if cur else latest,
                        prev_price=ya["price"] if ya else None, change_pct=yoy, change_label=f"vs {prev_label}",
                        avg_kwh=kwh, avg_bill=bill, usage_basis=use_basis, trend=trend, **extra)

        us = summarise("US", us_rows, "United States", {})
        for code, m in by_meta.items():
            out_states.append(summarise(code, states.get(code, []), m["name"], {}))
        source_note = (f"U.S. Energy Information Administration (EIA), residential retail sales, "
                       f"latest month {month_name(latest)}")
        fetched_at = eia.get("fetched_at")
    else:
        mode = "seed"
        latest = seed["period_latest"]
        basis = "2025 average"

        def summarise_seed(code, name):
            s = seed["states"][code]
            change = (s["price_latest"] - s["price_annual"]) / s["price_annual"] * 100
            return dict(code=code, name=name, price=s["price_latest"], period=latest, prev_price=s["price_annual"],
                        change_pct=change, change_label="vs the 2025 average", avg_kwh=s["avg_kwh"],
                        avg_bill=s["bill_annual"], usage_basis=basis, trend=[])

        us = summarise_seed("US", "United States")
        for code, m in by_meta.items():
            out_states.append(summarise_seed(code, m["name"]))
        source_note = ("U.S. Energy Information Administration (EIA): 2025 annual residential data and "
                       f"Electric Power Monthly Table 5.6.A ({month_name(latest)})")
        fetched_at = None

    # enrich, rank and compare
    for s in out_states:
        m = by_meta[s["code"]]
        s.update(slug=m["slug"], region=m["region"], city=m["city"])
        s["vs_us_pct"] = (s["price"] - us["price"]) / us["price"] * 100 if s["price"] and us["price"] else None
        s["bill_now"] = s["avg_kwh"] * s["price"] / 100 if s["avg_kwh"] and s["price"] else None
        sol = solar_states.get(s["code"])
        s["solar"] = ({"per_kw": sol["ac_annual_per_kw"], "monthly": sol.get("ac_monthly_per_kw", []),
                       "cf": sol.get("capacity_factor"), "city": sol.get("city", m["city"])} if sol else None)
    priced = sorted([s for s in out_states if s["price"]], key=lambda s: (s["price"], s["name"]))
    for i, s in enumerate(priced, 1):
        s["rank"] = i
    billed = sorted([s for s in out_states if s["avg_bill"]], key=lambda s: (s["avg_bill"], s["name"]))
    for i, s in enumerate(billed, 1):
        s["rank_bill"] = i
    us["bill_now"] = us["avg_kwh"] * us["price"] / 100 if us["avg_kwh"] and us["price"] else None
    us["solar"] = None

    out_states.sort(key=lambda s: s["name"])
    return {
        "mode": mode,
        "latest_period": latest,
        "usage_basis": basis,
        "source_note": source_note,
        "fetched_at": fetched_at,
        "us": us,
        "states": out_states,
        "by_code": {s["code"]: s for s in out_states},
        "count": len(out_states),
        "has_trend": any(len(s["trend"]) >= 6 for s in out_states),
        "has_solar": bool(solar_states),
        "solar_meta": {k: v for k, v in (solar or {}).items() if k != "states"},
    }
