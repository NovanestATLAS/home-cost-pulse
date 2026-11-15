"""Pipeline tests. Run with:  python3 -m unittest discover -s tests -v

No network access is needed: API responses are simulated in the documented EIA API v2 and
PVWatts v8 formats, and a full build runs in a temporary copy of the project.
The fake data below is for tests only and is never written into the real data/ folder.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_eia  # noqa: E402
import summaries  # noqa: E402
import validate_data  # noqa: E402
from common import add_months, load_json  # noqa: E402

META = load_json(ROOT / "data" / "states_meta.json")["states"]
SEED = load_json(ROOT / "data" / "seed" / "eia_seed_2026-07.json")
CODES = [s["code"] for s in META]


def fake_eia(latest="2026-08", months=36) -> dict:
    """Plausible monthly series shaped like fetch_eia.py output (TEST DATA ONLY)."""
    states = {}
    for code in CODES + ["US"]:
        sd = SEED["states"][code]
        customers = 1_000_000.0 if code != "US" else 145_000_000.0
        rows = []
        for i in range(months):
            p = add_months(latest, -i)
            season = 1 + 0.25 * math.sin((int(p[5:]) - 4) / 12 * 2 * math.pi)
            price = round(sd["price_latest"] * (1 - 0.003 * i), 2)
            kwh = sd["avg_kwh"] * season
            rows.append({"period": p, "price": price, "sales": kwh * customers / 1e6,
                         "revenue": kwh * customers * price / 100 / 1e6, "customers": customers})
        states[code] = rows
    return {"latest_period": latest, "months": months, "fetched_at": "2026-10-24T08:00:00+00:00", "states": states}


def fake_solar() -> dict:
    return {"fetched_at": "2026-10-24T08:00:00+00:00",
            "system": {"system_capacity": 1, "module_type": 0, "losses": 14, "array_type": 1, "tilt": 20, "azimuth": 180},
            "states": {s["code"]: {"city": s["city"], "ac_annual_per_kw": 1400.0, "ac_monthly_per_kw": [100.0] * 12,
                                   "solrad_annual": 4.8, "capacity_factor": 16.0} for s in META}}


class EiaParsing(unittest.TestCase):
    def test_query_parameters_match_eia_docs(self):
        q = urllib.parse.urlencode(fetch_eia.build_params("KEY", "2023-06", 0))
        self.assertIn("frequency=monthly", q)
        self.assertIn(urllib.parse.quote("facets[sectorid][]") + "=RES", q)
        self.assertIn(urllib.parse.quote("data[0]") + "=price", q)
        self.assertIn("length=5000", q)

    def test_strings_regions_and_duplicates(self):
        rows = [
            {"period": "2026-08", "stateid": "TX", "sectorid": "RES", "price": "15.9", "revenue": "4000.5", "sales": "25000", "customers": "12000000"},
            {"period": "2026-08", "stateid": "TX", "sectorid": "RES", "price": "15.9", "revenue": "4000.5", "sales": "25000", "customers": "12000000"},
            {"period": "2026-07", "stateid": "TX", "sectorid": "RES", "price": "NA", "revenue": None, "sales": "", "customers": "--"},
            {"period": "2026-08", "stateid": "WSC", "sectorid": "RES", "price": "14.0"},
            {"period": "2026-08", "stateid": "CA", "sectorid": "COM", "price": "25.0"},
        ]
        out = fetch_eia.parse_rows(rows, set(CODES) | {"US"})
        self.assertEqual(list(out), ["TX"])
        self.assertEqual([r["period"] for r in out["TX"]], ["2026-08", "2026-07"])
        self.assertEqual(out["TX"][0]["price"], 15.9)
        self.assertIsNone(out["TX"][1]["price"])
        self.assertIsNone(out["TX"][1]["customers"])

    def test_latest_common_period_needs_50_states(self):
        states = {c: [{"period": "2026-08", "price": 15.0}, {"period": "2026-07", "price": 15.0}] for c in CODES}
        for c in CODES[:5]:
            states[c] = [{"period": "2026-07", "price": 15.0}]
        self.assertEqual(fetch_eia.latest_common_period(states, CODES), "2026-07")


class Summaries(unittest.TestCase):
    def test_live_numbers_are_computed_from_revenue_sales_customers(self):
        eia = fake_eia()
        S = summaries.build(META, eia, SEED, fake_solar())
        self.assertEqual(S["mode"], "live")
        tx = S["by_code"]["TX"]
        rows = eia["states"]["TX"][:12]
        want_kwh = sum(r["sales"] * 1e6 / r["customers"] for r in rows) / 12
        want_bill = sum(r["revenue"] * 1e6 / r["customers"] for r in rows) / 12
        self.assertAlmostEqual(tx["avg_kwh"], want_kwh, places=6)
        self.assertAlmostEqual(tx["avg_bill"], want_bill, places=6)
        ya = eia["states"]["TX"][12]["price"]
        self.assertAlmostEqual(tx["change_pct"], (tx["price"] - ya) / ya * 100, places=6)
        self.assertEqual(len(tx["trend"]), 36)
        self.assertEqual(S["count"], 51)
        self.assertEqual(sorted(s["rank"] for s in S["states"]), list(range(1, 52)))

    def test_seed_mode(self):
        S = summaries.build(META, None, SEED, None)
        self.assertEqual(S["mode"], "seed")
        self.assertEqual(S["by_code"]["HI"]["rank"], 51)
        self.assertEqual(S["by_code"]["LA"]["rank"], 1)
        self.assertAlmostEqual(S["us"]["price"], 18.31)


class Validation(unittest.TestCase):
    def test_good_data_passes_and_bad_price_fails(self):
        eia = fake_eia()
        self.assertEqual(validate_data.check_eia(eia, CODES), [])
        eia["states"]["OH"][0]["price"] = 250.0
        self.assertTrue(any("OH" in e for e in validate_data.check_eia(eia, CODES)))

    def test_missing_states_fail(self):
        eia = fake_eia()
        for c in CODES[:3]:
            eia["states"][c] = eia["states"][c][1:]
        self.assertTrue(validate_data.check_eia(eia, CODES))

    def test_solar_bounds(self):
        bad = fake_solar()
        bad["states"]["AZ"]["ac_annual_per_kw"] = 9000
        self.assertTrue(validate_data.check_solar(bad))
        self.assertEqual(validate_data.check_solar(fake_solar()), [])


class FullBuild(unittest.TestCase):
    """Builds the site in a temporary copy of the project and checks the output."""

    def build(self, live: bool, partners: dict | None = None) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="hcp-"))
        dst = tmp / "site"
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("dist", ".git", "__pycache__", "*.zip"))
        if partners is not None:
            cfg = json.loads((dst / "site.config.json").read_text())
            cfg["partners"] = partners
            (dst / "site.config.json").write_text(json.dumps(cfg))
        for f in ("eia_residential_monthly.json", "solar_pvwatts.json"):
            (dst / "data" / f).unlink(missing_ok=True)
        if live:
            (dst / "data" / "eia_residential_monthly.json").write_text(json.dumps(fake_eia()))
            (dst / "data" / "solar_pvwatts.json").write_text(json.dumps(fake_solar()))
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "SKIP_IMAGES": "1", "SITE_URL": "https://example.test"}
        for script in ("validate_data.py", "build_site.py", "check_links.py"):
            r = subprocess.run([sys.executable, str(dst / "scripts" / script)], cwd=dst, env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{script} failed:\n{r.stdout}\n{r.stderr}")
        self.addCleanup(shutil.rmtree, tmp, True)
        return dst / "dist"

    def test_live_build(self):
        dist = self.build(live=True)
        tx = (dist / "electricity-rates" / "texas" / "index.html").read_text()
        self.assertIn("<svg viewBox", tx)
        self.assertIn("Rooftop solar in Texas", tx)
        self.assertIn("August 2026", tx)
        self.assertTrue((dist / "reports" / "2026-08" / "index.html").exists())
        self.assertIn("https://example.test/electricity-rates/texas/", (dist / "sitemap.xml").read_text())

    def test_seed_build(self):
        dist = self.build(live=False)
        self.assertEqual(len(list((dist / "electricity-rates").iterdir())), 52)  # 51 states + index.html
        home = (dist / "index.html").read_text()
        self.assertIn("July 2026", home)
        self.assertNotIn("/reports/", home)
        self.assertTrue((dist / "calculators" / "solar-payback" / "index.html").exists())

    def test_supplier_choice_cost_fields_and_no_partner_buttons_by_default(self):
        dist = self.build(live=False)
        tx = (dist / "electricity-rates" / "texas" / "index.html").read_text()
        oh = (dist / "electricity-rates" / "ohio" / "index.html").read_text()
        fl = (dist / "electricity-rates" / "florida" / "index.html").read_text()
        self.assertIn("Can you choose your electricity supplier in Texas?", tx)
        self.assertIn("https://www.powertochoose.org/", tx)
        self.assertIn("https://energychoice.ohio.gov/", oh)
        self.assertNotIn("choose your electricity supplier", fl)
        concrete = (dist / "calculators" / "concrete" / "index.html").read_text()
        self.assertIn('name="price_yard"', concrete)
        self.assertIn('placeholder="optional"', concrete)
        self.assertIn('data-only="us"', concrete)
        for page in (tx, concrete, (dist / "calculators" / "solar-payback" / "index.html").read_text()):
            self.assertNotIn('rel="sponsored', page)      # no affiliate button until a url is configured
        sitemap = (dist / "sitemap.xml").read_text()
        self.assertIn("<loc>https://example.test/terms/</loc><lastmod>2026-11-15</lastmod>", sitemap)

    def test_partner_buttons_appear_only_where_configured(self):
        dist = self.build(live=False, partners={
            "disclosure": "Partner link test.",
            "solar_quotes": {"url": "https://partner.test/solar", "label": "Compare solar quotes"},
            "electricity_plans": {"url": "", "label": "Compare plans in {state}", "state_urls": {"TX": "https://partner.test/tx"}},
            "contractor_quotes": {"url": "http://not-https.test", "label": "Get quotes"}})
        solar = (dist / "calculators" / "solar-payback" / "index.html").read_text()
        self.assertIn('href="https://partner.test/solar" target="_blank" rel="sponsored nofollow noopener"', solar)
        self.assertIn("Partner link test.", solar)
        tx = (dist / "electricity-rates" / "texas" / "index.html").read_text()
        self.assertIn("https://partner.test/tx", tx)
        self.assertIn("Compare plans in Texas", tx)
        self.assertNotIn("partner.test", (dist / "electricity-rates" / "ohio" / "index.html").read_text())
        self.assertNotIn("not-https.test", (dist / "calculators" / "roofing" / "index.html").read_text())
        self.assertIn("partner links", (dist / "about" / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
