#!/usr/bin/env python3
"""Build the whole static site into dist/.

  python3 scripts/build_site.py            # normal build
  SITE_URL=https://example.com python3 scripts/build_site.py

Standard library only. If matplotlib is installed, share images are generated too.
If Node.js is installed, each calculator page gets a worked example computed by
assets/calc-core.js (the same code the browser runs).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import share_images  # noqa: E402
import summaries  # noqa: E402
from common import (ASSETS_DIR, CONTENT_DIR, DATA_DIR, DIST_DIR, EIA_FILE, ROOT, SEED_FILE, SOLAR_FILE, add_months,  # noqa: E402
                    esc, fmt_cents, fmt_int, fmt_money, load_config, load_json, load_states_meta, log,
                    month_name, month_short, ordinal, today)

EVERYDAY = [
    ("1,000 kWh", 1000, "a round reference amount"),
    ("Central air conditioner", 840, "3.5 kW running 8 hours a day for 30 days"),
    ("Space heater", 360, "1.5 kW running 8 hours a day for 30 days"),
    ("Electric car, 1,000 miles", 317.46, "3.5 miles per kWh with 10% charging losses"),
    ("Electric clothes dryer", 36, "3 kW, twelve one-hour loads"),
    ("LED TV", 15, "100 W for 5 hours a day for 30 days"),
]

LOGO_SVG = ('<svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#2B3846"/>'
            '<path d="M7 21a9 9 0 0 1 18 0" fill="none" stroke="#F4C21B" stroke-width="3" stroke-linecap="round"/>'
            '<path d="M16 21l5-7" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>'
            '<circle cx="16" cy="21" r="2.2" fill="#fff"/></svg>')


# ---------------------------------------------------------------- helpers
def pct_phrase(p, below="below", above="above", same="about the same as"):
    if p is None:
        return ""
    if abs(p) < 1:
        return same
    return f"{abs(p):.0f}% {below if p < 0 else above}"


def change_phrase(p):
    if p is None:
        return ""
    if abs(p) < 0.05:
        return "unchanged"
    return f"{'up' if p > 0 else 'down'} {abs(p):.1f}%"


def rank_phrase(rank, n):
    if rank == 1:
        return "the lowest price of all"
    if rank == n:
        return "the highest price of all"
    if rank <= (n + 1) // 2:
        return f"the {ordinal(rank)} lowest"
    return f"the {ordinal(n - rank + 1)} highest"


def jsonld(obj) -> str:
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def meter(price, unit="¢ per kWh", small=False, label=None):
    s = f"{price:.2f}"
    whole, dec = s.split(".")
    cells = "".join(f'<span class="d">{ch}</span>' for ch in whole)
    cells += '<span class="sep">.</span>' + "".join(f'<span class="d dec">{ch}</span>' for ch in dec)
    aria = esc(label or f"{s} cents per kilowatt-hour")
    return (f'<div class="meter{" meter-sm" if small else ""}" role="img" aria-label="{aria}">'
            f'<span class="meter-digits" aria-hidden="true">{cells}</span>'
            f'<span class="meter-unit" aria-hidden="true">{esc(unit)}</span></div>')


def lines_html(r: dict) -> str:
    h = '<dl class="lines">' + "".join(f'<div class="line"><dt>{esc(a)}</dt><dd>{esc(b)}</dd></div>' for a, b in r["lines"]) + "</dl>"
    h += f'<p class="total"><span>{esc(r["total"][0])}</span><strong>{esc(r["total"][1])}</strong></p>'
    if r.get("extra"):
        h += '<dl class="lines extra">' + "".join(f'<div class="line"><dt>{esc(a)}</dt><dd>{esc(b)}</dd></div>' for a, b in r["extra"]) + "</dl>"
    h += "".join(f'<p class="note">{esc(n)}</p>' for n in r.get("notes", []))
    return h


def trend_svg(series, us_series=None, name="", w=480, h=240):
    """Inline SVG line chart of monthly prices. series = [(period, cents), ...] ascending."""
    if len(series) < 2:
        return ""
    periods = sorted({p for p, _ in series} | {p for p, _ in (us_series or [])})
    periods = [p for p in periods if p >= series[0][0]]
    idx = {p: i for i, p in enumerate(periods)}
    vals = [v for _, v in series] + [v for p, v in (us_series or []) if p in idx]
    lo, hi = min(vals), max(vals)
    span = max(hi - lo, 0.5)
    lo, hi = lo - span * 0.12, hi + span * 0.12
    L, R, T, B = 46, 58, 12, 28
    pw, ph = w - L - R, h - T - B

    def X(p):
        return L + pw * idx[p] / max(len(periods) - 1, 1)

    def Y(v):
        return T + ph * (1 - (v - lo) / (hi - lo))

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{esc(name)}">']
    for frac in (0, 0.5, 1):
        v = lo + (hi - lo) * frac
        y = Y(v)
        parts.append(f'<line class="grid" x1="{L}" x2="{w - R}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text x="{L - 8}" y="{y + 4:.1f}" text-anchor="end">{v:.1f}¢</text>')
    for p in (periods[0], periods[len(periods) // 2], periods[-1]):
        parts.append(f'<text x="{X(p):.1f}" y="{h - 8}" text-anchor="middle">{month_short(p)}</text>')
    if us_series:
        pts = " ".join(f"{X(p):.1f},{Y(v):.1f}" for p, v in us_series if p in idx)
        parts.append(f'<polyline class="series-us" points="{pts}"/>')
    pts = " ".join(f"{X(p):.1f},{Y(v):.1f}" for p, v in series)
    parts.append(f'<polyline class="series" points="{pts}"/>')
    lp, lv = series[-1]
    parts.append(f'<circle class="pt" cx="{X(lp):.1f}" cy="{Y(lv):.1f}" r="5"/>')
    parts.append(f'<text class="label-strong" x="{X(lp) + 9:.1f}" y="{Y(lv) + 4:.1f}">{lv:.2f}¢</text>')
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- site
class Site:
    def __init__(self, cfg, S, calcs):
        self.cfg, self.S, self.calcs = cfg, S, calcs
        self.pages: list[tuple[str, str, float]] = []
        self.og: dict[str, str] = {}
        self.examples: dict = {}
        self.v = {}
        self.build_date = today().isoformat()
        # Date of the last hand-made change to texts and calculators. Used as <lastmod> for pages that do not
        # depend on EIA data, so the sitemap does not claim that every page changes every week.
        self.content_date = str(cfg.get("content_updated") or self.build_date)
        self.choice = (load_json(DATA_DIR / "electric_choice.json", {}) or {}).get("states", {})

    # urls
    def url(self, path: str) -> str:
        return self.cfg["base_path"] + path

    def abs(self, path: str) -> str:
        return self.cfg["site_url"] + path

    def state_url(self, s) -> str:
        return self.url(f"/electricity-rates/{s['slug']}/")

    # output
    def write(self, path: str, html: str, priority: float = 0.6, lastmod: str | None = None, sitemap=True):
        target = DIST_DIR / "404.html" if path == "/404.html" else DIST_DIR / path.strip("/") / "index.html"
        if path == "/":
            target = DIST_DIR / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        if sitemap:
            self.pages.append((path, lastmod or self.build_date, priority))

    def copy_assets(self):
        out = DIST_DIR / "assets"
        out.mkdir(parents=True, exist_ok=True)
        for f in ASSETS_DIR.iterdir():
            if f.is_file():
                shutil.copy2(f, out / f.name)
                self.v[f.name] = hashlib.sha1(f.read_bytes()).hexdigest()[:10]
        shutil.copy2(ASSETS_DIR / "favicon.svg", DIST_DIR / "favicon.svg")

    def asset(self, name: str) -> str:
        return self.url(f"/assets/{name}?v={self.v.get(name, '1')}")

    # pieces
    def ad(self, slot: str) -> str:
        code = (self.cfg.get("ads", {}).get("slots", {}) or {}).get(slot, "")
        return f'<div class="ad-slot">{code}</div>' if code.strip() else ""

    def partner(self, key: str, state=None) -> str:
        """A labeled partner (affiliate) button. Hidden until its url is filled in site.config.json."""
        P = self.cfg.get("partners", {}) or {}
        item = P.get(key) or {}
        url = ""
        if state:
            url = ((item.get("state_urls") or {}).get(state["code"]) or "").strip()
        url = url or (item.get("url") or "").strip()
        if not url.startswith("https://"):
            return ""
        label = (item.get("label") or "See offers").replace("{state}", state["name"] if state else "your state")
        note = P.get("disclosure") or "Partner link: we may earn a commission if you use it. It never changes the numbers on this page."
        return (f'<aside class="partner"><a class="btn" href="{esc(url)}" target="_blank" rel="sponsored nofollow noopener">{esc(label)}</a>'
                f'<p class="partner-note">{esc(note)}</p></aside>')

    def has_partners(self) -> bool:
        P = self.cfg.get("partners", {}) or {}
        for item in P.values():
            if isinstance(item, dict) and ((item.get("url") or "").startswith("https://")
                                           or any((u or "").startswith("https://") for u in (item.get("state_urls") or {}).values())):
                return True
        return False

    def choice_block(self, s) -> str:
        """States where homes can pick their electricity supplier: what that means and the regulator's own site."""
        c = self.choice.get(s["code"])
        if not c:
            return ""
        name, price = esc(s["name"]), fmt_cents(s["price"])
        link = f'<a href="{esc(c["url"])}" rel="noopener">{esc(c["site"])}</a>'
        if c["kind"] == "required":
            first = (f"In most of {name}, you have to. Homes in the areas open to competition must pick a retail electricity provider. "
                     "Areas served by city-owned utilities or electric cooperatives, such as Austin and San Antonio, have a single provider.")
        else:
            first = (f"Yes. {name} lets most homes buy the supply part of their electricity from a competing supplier "
                     "instead of the utility's default rate. Your local utility still delivers the power and sends the bill.")
        return (f'<h2>Can you choose your electricity supplier in {name}?</h2><p>{first}</p>'
                f'<p>Only the supply charge changes when you switch. The {price} average on this page covers supply and delivery together, for all homes. '
                f'Compare current offers on {link}, run by the {esc(c["by"])}. Before you sign, check the contract length, any monthly or '
                f'cancellation fee, and the rate after a fixed term ends.</p>{self.partner("electricity_plans", s)}')

    def crumbs(self, items) -> str:
        out = []
        for label, path in items:
            out.append(f'<a href="{self.url(path)}">{esc(label)}</a>' if path else f'<span aria-current="page">{esc(label)}</span>')
        return '<nav class="crumbs" aria-label="Breadcrumb">' + '<span aria-hidden="true">/</span>'.join(out) + "</nav>"

    def crumbs_ld(self, items):
        return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": label, **({"item": self.abs(path)} if path else {})}
            for i, (label, path) in enumerate(items, 1)]}

    def layout(self, *, path, title, description, body, crumbs=None, ld=None, og_key=None, scripts=(),
               data_json=None, og_type="website", nav=None):
        cfg = self.cfg
        canonical = self.abs(path)
        head = [
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{esc(title)}</title>",
            f'<meta name="description" content="{esc(description)}">',
            f'<link rel="canonical" href="{esc(canonical)}">' if path != "/404.html" else '<meta name="robots" content="noindex">',
            f'<meta property="og:type" content="{og_type}">',
            f'<meta property="og:site_name" content="{esc(cfg["site_name"])}">',
            f'<meta property="og:title" content="{esc(title)}">',
            f'<meta property="og:description" content="{esc(description)}">',
            f'<meta property="og:url" content="{esc(canonical)}">',
            '<meta name="theme-color" content="#1D2733">',
            f'<link rel="icon" href="{self.url("/favicon.svg")}" type="image/svg+xml">',
            '<link rel="preconnect" href="https://fonts.googleapis.com">',
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Public+Sans:wght@400;600;700&display=swap">',
            f'<link rel="stylesheet" href="{self.asset("style.css")}">',
        ]
        og = (self.og.get(og_key) if og_key else None) or self.og.get("default")
        if og:
            head += [f'<meta property="og:image" content="{esc(self.abs(og))}">',
                     '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
                     '<meta name="twitter:card" content="summary_large_image">']
        for key, name in (("google_site_verification", "google-site-verification"),
                          ("bing_site_verification", "msvalidate.01"), ("pinterest_domain_verify", "p:domain_verify")):
            if cfg.get(key):
                head.append(f'<meta name="{name}" content="{esc(cfg[key])}">')
        for tag in (cfg.get("site_verification", {}).get("meta_tags") or []):
            tag = str(tag).strip()
            if re.fullmatch(r"<meta\s[^<>]*>", tag, re.I):          # only a single <meta ...> tag is accepted
                head.append(tag)
        if cfg.get("ads", {}).get("head_html", "").strip():
            head.append(cfg["ads"]["head_html"])
        an = cfg.get("analytics", {})
        if an.get("ga4_id"):
            g = esc(an["ga4_id"])
            head.append(f'<script async src="https://www.googletagmanager.com/gtag/js?id={g}"></script>'
                        f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}"
                        f"gtag('js',new Date());gtag('config','{g}');</script>")
        for item in ([self.crumbs_ld(crumbs)] if crumbs else []) + (ld or []):
            head.append(jsonld(item))

        navlinks = [("Electricity rates", "/electricity-rates/", "Rates"), ("Calculators", "/calculators/", "Calculators"),
                    ("Monthly reports", "/reports/", "Reports"), ("How we calculate", "/methodology/", "Methods")]
        if self.S["mode"] != "live":
            navlinks = [n for n in navlinks if n[1] != "/reports/"]
        current = ' aria-current="page"'
        # Phones show the short label so the whole menu fits on one line; aria-label keeps the full name.
        nav_html = "".join(
            f'<a href="{self.url(p)}"{current if nav == p else ""} aria-label="{esc(lbl)}">'
            f'<span class="nav-long">{esc(lbl)}</span><span class="nav-short" aria-hidden="true">{esc(short)}</span></a>'
            for lbl, p, short in navlinks)

        tail = []
        if data_json is not None:
            tail.append('<script id="hcp-data" type="application/json">' + json.dumps(data_json, separators=(",", ":")).replace("</", "<\\/") + "</script>")
        for sname in scripts:
            tail.append(f'<script src="{self.asset(sname)}" defer></script>')
        if an.get("cloudflare_token"):
            tail.append(f"<script defer src=\"https://static.cloudflareinsights.com/beacon.min.js\" "
                        f"data-cf-beacon='{{\"token\": \"{esc(an['cloudflare_token'])}\"}}'></script>")

        year = today().year
        footer = (
            '<footer class="site-footer"><div class="wrap">'
            f'<nav aria-label="Site"><a href="{self.url("/about/")}">About</a><a href="{self.url("/methodology/")}">How we calculate</a>'
            f'<a href="{self.url("/privacy/")}">Privacy</a><a href="{self.url("/terms/")}">Terms</a><a href="{self.url("/contact/")}">Contact</a></nav>'
            f"<p>Electricity data: U.S. Energy Information Administration (public domain). Solar estimates: PVWatts, National Laboratory of the Rockies. "
            f"All figures are estimates for planning, not quotes or financial advice.</p>"
            f"<p>© {year} {esc(cfg.get('publisher_name', cfg['site_name']))}. Not affiliated with any government agency or utility.</p>"
            "</div></footer>"
        )
        return ("<!doctype html>\n" f'<html lang="{esc(cfg.get("language", "en-US"))}">\n<head>\n' + "\n".join(head) +
                "\n</head>\n<body>\n" '<a class="skip" href="#main">Skip to content</a>\n'
                f'<header class="site-header"><div class="wrap header-row"><a class="brand" href="{self.url("/")}">{LOGO_SVG}<span>{esc(cfg["site_name"])}</span></a>'
                f'<nav aria-label="Main">{nav_html}</nav></div></header>\n'
                f'<main id="main" class="wrap">\n{self.crumbs(crumbs) if crumbs else ""}\n{body}\n</main>\n{footer}\n' + "\n".join(tail) + "\n</body>\n</html>\n")

    def state_options(self, selected="US"):
        opts = [f'<option value="US"{" selected" if selected == "US" else ""}>U.S. average</option>']
        for s in self.S["states"]:
            opts.append(f'<option value="{s["code"]}"{" selected" if selected == s["code"] else ""}>{esc(s["name"])}</option>')
        return "".join(opts)

    def calc_data(self):
        us = self.S["us"]
        d = {"US": {"name": "U.S. average", "price": round(us["price"], 2), "kwh": round(us["avg_kwh"]), "solar": None}}
        for s in self.S["states"]:
            if s["price"]:
                d[s["code"]] = {"name": s["name"], "price": round(s["price"], 2),
                                "kwh": round(s["avg_kwh"]) if s["avg_kwh"] else None,
                                "solar": round(s["solar"]["per_kw"]) if s["solar"] else None}
        return d

    def default_values(self, calc):
        us = self.S["us"]
        vals = {}
        for f in calc["fields"]:
            if f["type"] == "state":
                continue
            v = f.get("default")
            if f.get("bind") == "price":
                v = round(us["price"], 2)
            elif f.get("bind") == "kwh":
                v = round(us["avg_kwh"])
            if f["type"] == "number":
                v = float(v) if v is not None else None   # optional fields (prices) start empty
            vals[f["id"]] = v
        return vals

    # ------------------------------------------------------------ calculators
    def field_html(self, calc, f, values):
        cid, fid = calc["id"], f["id"]
        dom = f"f-{cid}-{fid}"
        help_html = f'<p class="help" id="{dom}-h">{esc(f["help"])}</p>' if f.get("help") else ""
        described = f' aria-describedby="{dom}-h"' if f.get("help") else ""
        if f["type"] == "state":
            return (f'<div class="field"><label for="{dom}">{esc(f["label"])}</label>'
                    f'<select id="{dom}" name="state" data-role="state">{self.state_options()}</select></div>')
        if f["type"] == "select":
            opts = "".join(f'<option value="{esc(o["value"])}"{" selected" if o["value"] == f.get("default") else ""}>{esc(o["label"])}</option>' for o in f["options"])
            sets = f' data-sets="{esc(f["sets"])}"' if f.get("sets") else ""
            return (f'<div class="field"><label for="{dom}">{esc(f["label"])}</label>'
                    f'<select id="{dom}" name="{fid}"{sets}{described}>{opts}</select>{help_html}</div>')
        if f["type"] == "checkbox":
            checked = " checked" if f.get("default") else ""
            return f'<div class="field"><label class="check" for="{dom}"><input id="{dom}" type="checkbox" name="{fid}"{checked}> {esc(f["label"])}</label></div>'
        kind = f.get("kind")
        unit = esc(f.get("unit", "")) if not kind else esc({
            "length": "ft", "small": "in", "area": "ft²", "coverage": "ft²/gal", "density": "tons/yd³",
            "price_volume": "$ per yd³", "price_area": "$ per ft²", "price_liquid": "$ per gal"}[kind])
        attrs = [f'id="{dom}"', f'name="{fid}"', 'type="number"', 'inputmode="decimal"',
                 f'value="{values[fid]:g}"' if values.get(fid) is not None else 'placeholder="optional"']
        for a in ("min", "max", "step"):
            if a in f:
                attrs.append(f'{a}="{f[a]}"')
        if kind:
            attrs.append(f'data-kind="{kind}"')
        if f.get("bind"):
            attrs.append(f'data-bind="{f["bind"]}" data-default="{f["default"]}"')
        kind_attr = f' data-kind="{kind}"' if kind else ""
        unit_html = f'<span class="unit"{kind_attr}>{unit}</span>' if unit else ""
        only = f' data-only="{esc(f["only"])}"' if f.get("only") else ""   # shown in one unit system only
        return (f'<div class="field"{only}><label for="{dom}">{esc(f["label"])}</label>'
                f'<div class="input-unit"><input {" ".join(attrs)}{described}>{unit_html}</div>{help_html}</div>')

    def calc_page(self, calc):
        S, us = self.S, self.S["us"]
        path = f"/calculators/{calc['slug']}/"
        values = self.default_values(calc)
        fields = "".join(self.field_html(calc, f, values) for f in calc["fields"])
        units = ""
        if calc.get("units"):
            units = (f'<div class="field"><label for="u-{calc["id"]}">Units</label><select id="u-{calc["id"]}" name="units">'
                     '<option value="us">Feet and inches</option><option value="metric">Meters and centimeters</option></select></div>')
        ex = self.examples.get(calc["id"])
        example_html = lines_html(ex) if ex and "error" not in ex else '<p class="note">Enter your numbers to see the estimate.</p>'
        basis = f"Rates: EIA, {month_name(S['latest_period'])}" if calc["group"] == "energy" else "Estimate"
        how = "".join(f"<p>{esc(p)}</p>" for p in calc["how"])
        tips = "<ul>" + "".join(f"<li>{esc(t)}</li>" for t in calc["tips"]) + "</ul>"
        faqs = '<dl class="faq">' + "".join(f"<dt>{esc(q['q'])}</dt><dd>{esc(q['a'])}</dd>" for q in calc["faqs"]) + "</dl>"
        by_id = {c["id"]: c for c in self.calcs}
        related = '<ul class="calc-list">' + "".join(
            f'<li><a href="{self.url("/calculators/" + by_id[r]["slug"] + "/")}">{esc(by_id[r]["h1"])}</a><span>{esc(by_id[r]["short"])}</span></li>'
            for r in calc["related"] if r in by_id) + "</ul>"
        example_text = ""
        if ex and "error" not in ex:
            example_text = (f'<h2>Worked example</h2><p>With the starting values shown in the form'
                            f'{" (U.S. average price of " + fmt_cents(us["price"]) + " per kWh)" if calc["group"] == "energy" else ""}, '
                            f'the result is <strong>{esc(ex["total"][1])}</strong> ({esc(ex["total"][0].lower())}). Change any number and the estimate updates as you type.</p>')
        states_block = ""
        if calc["group"] == "energy":
            states_block = ('<h2>Prices by state</h2><p>Pick a state in the form above, or open its page for the full picture: '
                            'price history, average bill and what everyday appliances cost there.</p>' + self.states_grid())
        contractor_for = (self.cfg.get("partners", {}).get("contractor_quotes", {}) or {}).get("calculators") or \
            ["roofing", "flooring-tile", "drywall", "concrete", "paint"]
        partner = self.partner("solar_quotes") if calc["id"] == "solar-payback" else (
            self.partner("contractor_quotes") if calc["id"] in contractor_for else "")
        body = (f'<h1>{esc(calc["h1"])}</h1><p class="lede">{esc(calc["intro"])}</p>'
                f'<div class="calc-layout"><form class="calc" data-calc="{calc["id"]}" novalidate>{units}{fields}'
                '<noscript><p class="note">This calculator needs JavaScript. The result on the right is a worked example with the starting values.</p></noscript></form>'
                f'<div class="receipt"><div class="receipt-head"><strong>Your estimate</strong><span>{esc(basis)}</span></div>'
                f'<div data-receipt-for="{calc["id"]}" aria-live="polite">{example_html}</div></div></div>'
                f'{partner}{self.ad("in_content")}<h2>How it is calculated</h2>{how}{example_text}<h2>Tips</h2>{tips}'
                f'<h2>Questions</h2>{faqs}{states_block}<h2>Related calculators</h2>{related}{self.ad("bottom")}')
        ld = [{"@context": "https://schema.org", "@type": "WebApplication", "name": calc["h1"],
               "url": self.abs(path), "applicationCategory": "UtilitiesApplication", "operatingSystem": "Any",
               "description": calc["description"], "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}}]
        html = self.layout(path=path, title=calc["title"], description=calc["description"], body=body,
                           crumbs=[("Home", "/"), ("Calculators", "/calculators/"), (calc["h1"], None)],
                           ld=ld, og_key=f"calc:{calc['id']}", scripts=("calc-core.js", "site.js"),
                           data_json=self.calc_data() if calc["group"] == "energy" else None, nav="/calculators/")
        # Energy calculators load the newest rates, so they change when the data does.
        self.write(path, html, 0.8, lastmod=max(self.content_date, self.data_lastmod()) if calc["group"] == "energy" else self.content_date)

    def states_grid(self):
        return '<ul class="states-grid">' + "".join(
            f'<li><a href="{self.state_url(s)}">{esc(s["name"])}</a><span class="num">{fmt_cents(s["price"])}</span></li>'
            for s in self.S["states"] if s["price"]) + "</ul>"

    def calculators_index(self):
        def group(g):
            return '<ul class="calc-list">' + "".join(
                f'<li><a href="{self.url("/calculators/" + c["slug"] + "/")}">{esc(c["h1"])}</a><span>{esc(c["short"])}</span></li>'
                for c in self.calcs if c["group"] == g) + "</ul>"
        body = ('<h1>Home cost calculators</h1><p class="lede">Free calculators for running a home and planning projects. '
                'The energy tools load each state\'s latest official electricity price; the project tools work in feet or meters and turn quantities into a cost at your local price.</p>'
                f'<h2>Energy and bills</h2>{group("energy")}<h2>Home projects</h2>{group("projects")}')
        html = self.layout(path="/calculators/", title="Home Cost Calculators: Energy Bills and Project Materials",
                           description="Free calculators for electric bills, appliance running costs, EV charging, solar payback, and the quantity and cost of concrete, gravel, paint, drywall, flooring and roofing.",
                           body=body, crumbs=[("Home", "/"), ("Calculators", None)], nav="/calculators/")
        self.write("/calculators/", html, 0.8, lastmod=self.content_date)

    # ------------------------------------------------------------ states
    def state_page(self, s):
        S, us, n = self.S, self.S["us"], self.S["count"]
        path = f"/electricity-rates/{s['slug']}/"
        mname = month_name(s["period"])
        vs = pct_phrase(s["vs_us_pct"])
        first = (f"Homes in {s['name']} paid an average of <strong>{fmt_cents(s['price'])} per kWh</strong> in {mname}, "
                 f"{vs} the U.S. average of {fmt_cents(us['price'])}. That is {rank_phrase(s['rank'], n)} "
                 f"among the 50 states and D.C.")
        change = ""
        if s["change_pct"] is not None:
            cls = "up" if s["change_pct"] > 0 else "down"
            change = f' The price is <span class="{cls}">{change_phrase(s["change_pct"])}</span> {esc(s["change_label"])}.'
        bill_box = ""
        if s["avg_kwh"] and s["avg_bill"]:
            bill_box = (f'<div class="receipt"><div class="receipt-head"><strong>The average {esc(s["name"])} home</strong>'
                        f'<span>{esc(s["usage_basis"])}</span></div><dl class="lines">'
                        f'<div class="line"><dt>Electricity used per month</dt><dd>{fmt_int(s["avg_kwh"])} kWh</dd></div>'
                        f'<div class="line"><dt>U.S. average home</dt><dd>{fmt_int(us["avg_kwh"])} kWh</dd></div>'
                        f'<div class="line"><dt>Average monthly bill</dt><dd>{fmt_money(s["avg_bill"])}</dd></div>'
                        f'</dl><p class="total"><span>Same usage at the {esc(month_short(s["period"]))} price</span>'
                        f'<strong>{fmt_money(s["bill_now"])}</strong></p>'
                        f'<p class="note">Bills are revenue divided by customers, so they include the fixed charges and fees utilities collect.</p></div>')
        top = (f'<div class="state-top"><div><h1>{esc(s["name"])} electricity rates and average bill</h1>'
               f'<p class="muted">Residential price, {esc(mname)}</p>{meter(s["price"])}'
               f'<p>{first}{change}</p></div>{bill_box}</div>')

        chart = ""
        if len(s["trend"]) >= 6:
            us_tr = us["trend"]
            name = (f"Line chart: {s['name']} residential electricity price from {month_name(s['trend'][0][0])} to "
                    f"{month_name(s['trend'][-1][0])}, ending at {s['trend'][-1][1]:.2f} cents per kWh, with the U.S. average for comparison.")
            rows = "".join(f'<tr><td>{month_name(p)}</td><td class="r">{v:.2f}¢</td></tr>' for p, v in reversed(s["trend"][-24:]))
            chart = (f'<h2>Price over the last {len(s["trend"])} months</h2><figure class="chart">{trend_svg(s["trend"], us_tr, name)}'
                     f'<figcaption class="legend"><span><i></i>{esc(s["name"])}</span><span><i class="us"></i>U.S. average</span></figcaption></figure>'
                     f'<details><summary>Show the monthly numbers</summary><div class="table-wrap"><table class="data"><thead><tr><th>Month</th><th class="r">Price</th></tr></thead>'
                     f'<tbody>{rows}</tbody></table></div></details>')

        p = s["price"] / 100
        ev_rows = "".join(f'<tr><td>{esc(lbl)}<br><span class="small muted">{esc(note)}</span></td><td class="r">{fmt_int(k)} kWh</td>'
                          f'<td class="r">{fmt_money(k * p)}</td></tr>' for lbl, k, note in EVERYDAY)
        everyday = (f'<h2>What everyday things cost in {esc(s["name"])}</h2><p>At {fmt_cents(s["price"])} per kWh, before any fixed monthly charge:</p>'
                    f'<div class="table-wrap"><table class="data"><thead><tr><th>Item</th><th class="r">Energy</th><th class="r">Cost</th></tr></thead>'
                    f'<tbody>{ev_rows}</tbody></table></div>'
                    f'<p class="small muted">Thermostat-controlled appliances cycle on and off, so real use is often lower. '
                    f'<a href="{self.url("/calculators/appliance-energy-cost/")}?state={s["code"]}">Price your own appliance</a>.</p>')

        solar = ""
        if s["solar"]:
            pk = s["solar"]["per_kw"]
            solar = (f'<h2>Rooftop solar in {esc(s["name"])}</h2><p>A 1 kW rooftop system near {esc(s["solar"]["city"])} produces about '
                     f'<strong>{fmt_int(pk)} kWh a year</strong>, according to the NLR PVWatts model. At {esc(s["name"])}\'s average price that output is worth about '
                     f'{fmt_money(pk * p, 0)} a year per kW. A typical 7 kW system would make about {fmt_int(pk * 7)} kWh, worth about {fmt_money(pk * 7 * p, 0)} a year.</p>'
                     f'<p class="callout">The 30% federal tax credit for solar you buy (Section 25D) ended on December 31, 2025. '
                     f'<a href="{self.url("/calculators/solar-payback/")}?state={s["code"]}">Work out payback with your own quote</a>.</p>'
                     + self.partner("solar_quotes", s))

        peers = sorted([x for x in S["states"] if x["region"] == s["region"] and x["price"]], key=lambda x: x["price"])
        current_row = ' class="is-current"'
        peer_rows = "".join(
            f'<tr{current_row if x["code"] == s["code"] else ""}><td>'
            + (esc(x["name"]) if x["code"] == s["code"] else f'<a href="{self.state_url(x)}">{esc(x["name"])}</a>')
            + f'</td><td class="r">{fmt_cents(x["price"])}</td><td class="r">{fmt_money(x["avg_bill"], 0) if x["avg_bill"] else "-"}</td></tr>'
            for x in peers)
        region = (f'<h2>{esc(s["name"])} compared with the {esc(s["region"])}</h2><div class="table-wrap"><table class="data"><thead><tr>'
                  f'<th>State</th><th class="r">Price</th><th class="r">Average bill</th></tr></thead><tbody>{peer_rows}</tbody></table></div>')

        mini_calc = (f'<h2>Estimate your {esc(s["name"])} bill</h2>'
                     f'<div class="calc-layout"><form class="calc" data-calc="electric-bill" novalidate>'
                     f'<input type="hidden" name="state" value="{s["code"]}">'
                     f'<div class="field"><label for="m-kwh">Your monthly usage</label><div class="input-unit"><input id="m-kwh" name="kwh" type="number" inputmode="decimal" min="0" step="1" value="{round(s["avg_kwh"] or 900)}"><span class="unit">kWh</span></div></div>'
                     f'<div class="field"><label for="m-price">Price per kWh</label><div class="input-unit"><input id="m-price" name="price" type="number" inputmode="decimal" min="0" step="0.01" value="{s["price"]:.2f}"><span class="unit">¢</span></div></div>'
                     f'<div class="field"><label for="m-fixed">Fixed monthly charge</label><div class="input-unit"><input id="m-fixed" name="fixed" type="number" inputmode="decimal" min="0" step="0.01" value="0"><span class="unit">$</span></div>'
                     f'<p class="help">Check your bill for a customer or service charge.</p></div></form>'
                     f'<div class="receipt"><div class="receipt-head"><strong>Your estimate</strong><span>{esc(s["name"])}</span></div>'
                     f'<div data-receipt-for="electric-bill" aria-live="polite"><p class="note">Enter your usage to see the estimate.</p></div></div></div>')

        tools = ('<h2>Tools with ' + esc(s["name"]) + ' prices loaded</h2><ul class="calc-list">' + "".join(
            f'<li><a href="{self.url("/calculators/" + c["slug"] + "/")}?state={s["code"]}">{esc(c["h1"])}</a><span>{esc(c["short"])}</span></li>'
            for c in self.calcs if c["group"] == "energy") + "</ul>")
        sources = (f'<div class="sources"><p>Source: {esc(S["source_note"])}. '
                   f'Average bill and usage: {esc(s["usage_basis"])}, computed from EIA revenue, sales and customer counts.</p>'
                   + (f'<p>Solar: PVWatts v8 by the National Laboratory of the Rockies, 1 kW fixed roof system, 20° tilt, facing south, 14% losses.</p>' if s["solar"] else "")
                   + f'<p><a href="{self.url("/methodology/")}">How we calculate</a>. Page updated {esc(self.build_date)}.</p></div>')

        choice = self.choice_block(s)
        body = top + self.ad("top") + chart + choice + everyday + self.ad("in_content") + solar + mini_calc + tools + region + self.ad("bottom") + sources
        desc = (f"{s['name']} homes paid {fmt_cents(s['price'])} per kWh in {mname}, {vs} the U.S. average. "
                f"Average bill {fmt_money(s['avg_bill'], 0) if s['avg_bill'] else 'n/a'} a month. "
                + ("Trend, appliance costs and how to choose a supplier." if choice else "Trend, appliance costs and solar output."))
        trend_cov = f"{s['trend'][0][0]}/{s['trend'][-1][0]}" if s["trend"] else s["period"]
        ld = [{"@context": "https://schema.org", "@type": "Dataset",
               "name": f"{s['name']} residential electricity price and average bill",
               "description": f"Average residential electricity price, usage and bill in {s['name']}, from U.S. Energy Information Administration data.",
               "url": self.abs(path), "isAccessibleForFree": True,
               "creator": {"@type": "Organization", "name": "U.S. Energy Information Administration", "url": "https://www.eia.gov"},
               "license": "https://www.eia.gov/about/copyrights_reuse.php",
               "spatialCoverage": {"@type": "Place", "name": f"{s['name']}, United States"},
               "temporalCoverage": trend_cov,
               "variableMeasured": ["Average residential electricity price (cents per kWh)", "Average monthly usage (kWh)", "Average monthly bill (USD)"]}]
        html = self.layout(path=path, title=f"{s['name']} Electricity Rates and Average Bill ({month_short(s['period'])})",
                           description=desc, body=body,
                           crumbs=[("Home", "/"), ("Electricity rates", "/electricity-rates/"), (s["name"], None)],
                           ld=ld, og_key=f"state:{s['code']}", scripts=("calc-core.js", "site.js"), nav="/electricity-rates/",
                           og_type="article")
        self.write(path, html, 0.9, lastmod=self.data_lastmod())

    def dataset_ld(self, path, name, description, coverage):
        return {"@context": "https://schema.org", "@type": "Dataset", "name": name, "description": description,
                "url": self.abs(path), "isAccessibleForFree": True,
                "creator": {"@type": "Organization", "name": "U.S. Energy Information Administration", "url": "https://www.eia.gov"},
                "license": "https://www.eia.gov/about/copyrights_reuse.php",
                "spatialCoverage": {"@type": "Place", "name": "United States"}, "temporalCoverage": coverage,
                "variableMeasured": ["Average residential electricity price (cents per kWh)"]}

    def data_lastmod(self):
        fa = self.S.get("fetched_at")
        return fa[:10] if fa else self.build_date

    def rates_table(self, states, change=True):
        head = ('<thead><tr><th data-sort="text"><button type="button">State</button></th>'
                '<th class="r" data-sort="num" aria-sort="ascending"><button type="button">Price per kWh</button></th>'
                '<th class="r" data-sort="num"><button type="button">vs U.S.</button></th>'
                + ('<th class="r" data-sort="num"><button type="button">Change</button></th>' if change else "")
                + '<th class="r" data-sort="num"><button type="button">Usage</button></th>'
                '<th class="r" data-sort="num"><button type="button">Average bill</button></th></tr></thead>')
        rows = []
        for s in sorted(states, key=lambda x: (x["price"] or 999)):
            ch = s["change_pct"]
            rows.append(
                f'<tr><td data-v="{esc(s["name"])}"><a href="{self.state_url(s)}">{esc(s["name"])}</a></td>'
                f'<td class="r" data-v="{s["price"]:.2f}">{fmt_cents(s["price"])}</td>'
                f'<td class="r" data-v="{s["vs_us_pct"]:.1f}">{"+" if s["vs_us_pct"] > 0 else ""}{s["vs_us_pct"]:.0f}%</td>'
                + (f'<td class="r" data-v="{ch if ch is not None else ""}"><span class="{"up" if (ch or 0) > 0 else "down"}">{("+" if (ch or 0) > 0 else "") + f"{ch:.1f}%" if ch is not None else "-"}</span></td>' if change else "")
                + f'<td class="r" data-v="{s["avg_kwh"] or ""}">{fmt_int(s["avg_kwh"]) + " kWh" if s["avg_kwh"] else "-"}</td>'
                f'<td class="r" data-v="{s["avg_bill"] or ""}">{fmt_money(s["avg_bill"]) if s["avg_bill"] else "-"}</td></tr>')
        return f'<div class="table-wrap"><table class="data" data-sortable>{head}<tbody>{"".join(rows)}</tbody></table></div>'

    def rates_index(self):
        S, us = self.S, self.S["us"]
        priced = sorted([s for s in S["states"] if s["price"]], key=lambda s: s["price"])
        lo, hi = priced[0], priced[-1]
        m = month_name(S["latest_period"])
        change_label = S["states"][0]["change_label"]
        facts = (f'<div class="facts"><div><strong>{fmt_cents(us["price"])}</strong><span>U.S. average per kWh, {esc(m)}</span></div>'
                 f'<div><strong>{fmt_money(us["avg_bill"], 0)}</strong><span>U.S. average monthly bill ({esc(us["usage_basis"])})</span></div>'
                 f'<div><strong>{fmt_cents(lo["price"])} to {fmt_cents(hi["price"])}</strong><span>{esc(lo["name"])} to {esc(hi["name"])}</span></div></div>')
        chart = ""
        if len(us["trend"]) >= 6:
            chart = (f'<h2>U.S. average price</h2><figure class="chart">{trend_svg(us["trend"], None, "Line chart of the U.S. average residential electricity price by month")}'
                     '</figure>')
        choice_states = [s for s in sorted(S["states"], key=lambda x: x["name"]) if s["code"] in self.choice and s["price"]]
        choice_html = ""
        if choice_states:
            links = ", ".join(f'<a href="{self.state_url(s)}">{esc(s["name"])}</a>' for s in choice_states)
            choice_html = ('<h2>States where you can choose your supplier</h2><p>In these places most homes can buy the supply part of their '
                           f'electricity from a competing supplier, and in most of Texas they must: {links}. Each page links to the state '
                           'regulator\'s own comparison site. Everywhere else, your local utility is the only seller.</p>')
        body = (f'<h1>Electricity rates by state</h1><p class="lede">Average residential price per kWh in {esc(m)} for all 50 states and D.C., '
                f'with usage and bills. Data from the U.S. Energy Information Administration, refreshed when EIA publishes a new month.</p>'
                f'{facts}{self.ad("top")}<h2>All states, ranked</h2><p class="small muted">Select a column heading to sort. Change is {esc(change_label)}.</p>'
                f'{self.rates_table(priced)}{self.ad("in_content")}{chart}'
                '<h2>Why prices differ so much</h2><p>The price per kWh mostly reflects how a state\'s power is generated and delivered: fuel costs, '
                'grid and storm-hardening investment, and state policy. Bills also depend on how much electricity homes use, which climate and '
                'the share of homes heating with electricity drive. That is why some lower-price Southern states still have higher average bills.</p>'
                f'{choice_html}<div class="sources"><p>Source: {esc(S["source_note"])}. Public domain.</p><p><a href="{self.url("/methodology/")}">How we calculate</a>.</p></div>')
        html = self.layout(path="/electricity-rates/", title=f"Electricity Rates by State ({month_short(S['latest_period'])}): All 50 States Ranked",
                           description=f"Average residential electricity price per kWh for every state in {m}, with average usage and monthly bills. U.S. average: {fmt_cents(us['price'])}.",
                           body=body, crumbs=[("Home", "/"), ("Electricity rates", None)], og_key="rates",
                           ld=[self.dataset_ld("/electricity-rates/", f"Residential electricity prices by U.S. state, {m}",
                                               f"Average residential electricity price, usage and monthly bill for all 50 states and D.C. in {m}.",
                                               S["latest_period"])],
                           scripts=("site.js",), nav="/electricity-rates/")
        self.write("/electricity-rates/", html, 1.0, lastmod=self.data_lastmod())

    # ------------------------------------------------------------ monthly reports (live data only)
    def reports(self):
        eia = load_json(EIA_FILE)
        if not eia or self.S["mode"] != "live":
            return []
        states = eia["states"]
        names = {s["code"]: s for s in self.S["states"]}
        months = sorted({r["period"] for r in states.get("TX", [])}, reverse=True)
        made = []
        for mth in months[:6]:
            ya = add_months(mth, -12)
            rows = []
            for code, srows in states.items():
                if code not in names:
                    continue
                cur = next((r for r in srows if r["period"] == mth), None)
                old = next((r for r in srows if r["period"] == ya), None)
                if cur and old and cur["price"] and old["price"]:
                    rows.append((code, cur["price"], (cur["price"] - old["price"]) / old["price"] * 100))
            if len(rows) < 50:
                continue
            us_rows = states.get("US") or []
            usc = next((r for r in us_rows if r["period"] == mth), None)
            uso = next((r for r in us_rows if r["period"] == ya), None)
            if usc and uso and usc["price"] and uso["price"]:
                us_price, us_change = usc["price"], (usc["price"] - uso["price"]) / uso["price"] * 100
            else:
                us_price, us_change = None, None
            made.append(mth)
            self.report_page(mth, rows, us_price, us_change, names)
        if made:
            items = "".join(f'<li><a href="{self.url("/reports/" + m + "/")}">Electricity prices by state, {month_name(m)}</a></li>' for m in made)
            body = ('<h1>Monthly electricity price reports</h1><p class="lede">A new report each time the U.S. Energy Information Administration '
                    f'publishes another month of state data, usually about two months after the month ends.</p><ul>{items}</ul>')
            html = self.layout(path="/reports/", title="Monthly Electricity Price Reports by State | Home Cost Pulse",
                               description="Monthly reports on residential electricity prices in every U.S. state: biggest increases, biggest decreases and the full ranking.",
                               body=body, crumbs=[("Home", "/"), ("Monthly reports", None)], nav="/reports/")
            self.write("/reports/", html, 0.7, lastmod=self.data_lastmod())
        return made

    def report_page(self, mth, rows, us_price, us_change, names):
        path = f"/reports/{mth}/"
        m, ya = month_name(mth), month_name(add_months(mth, -12))
        ups = [r for r in sorted(rows, key=lambda r: -r[2]) if r[2] > 0][:5]
        downs = [r for r in sorted(rows, key=lambda r: r[2]) if r[2] < 0][:5]
        ranked = sorted(rows, key=lambda r: r[1])

        def bars(items, cls):
            if not items:
                return '<p class="muted">No state moved in this direction over the year.</p>'
            return f'<ol class="bars {cls}">' + "".join(
                f'<li><a href="{self.state_url(names[c])}">{esc(names[c]["name"])}</a><span class="bar" style="width:{max(abs(ch), 0.5) / max(abs(items[0][2]), 0.5) * 100:.0f}%"></span>'
                f'<span class="v">{"+" if ch > 0 else ""}{ch:.1f}%</span></li>' for c, p, ch in items) + "</ol>"

        lead = f"The average U.S. home paid {fmt_cents(us_price)} per kWh in {m}, {change_phrase(us_change)} from {ya}." if us_price else ""
        table_rows = "".join(
            f'<tr><td data-v="{i}">{i}</td><td data-v="{esc(names[c]["name"])}"><a href="{self.state_url(names[c])}">{esc(names[c]["name"])}</a></td>'
            f'<td class="r" data-v="{p:.2f}">{fmt_cents(p)}</td><td class="r" data-v="{ch:.2f}"><span class="{"up" if ch > 0 else "down"}">{"+" if ch > 0 else ""}{ch:.1f}%</span></td></tr>'
            for i, (c, p, ch) in enumerate(ranked, 1))
        body = (f'<h1>Electricity prices by state, {esc(m)}</h1><p class="lede">{esc(lead)} '
                f'Here is every state, from the cheapest to the most expensive, and where prices moved most over the year.</p>'
                f'<div class="facts"><div><strong>{fmt_cents(ranked[0][1])}</strong><span>Lowest: {esc(names[ranked[0][0]]["name"])}</span></div>'
                f'<div><strong>{fmt_cents(ranked[-1][1])}</strong><span>Highest: {esc(names[ranked[-1][0]]["name"])}</span></div>'
                f'<div><strong>{sum(1 for r in rows if r[2] > 0)} of {len(rows)}</strong><span>States with higher prices than in {esc(ya)}</span></div></div>'
                f'{self.ad("top")}<div class="split"><div><h2>Biggest increases</h2>{bars(ups, "high")}</div>'
                f'<div><h2>Biggest decreases</h2>{bars(downs, "low")}</div></div>'
                f'<h2>All states, {esc(m)}</h2><div class="table-wrap"><table class="data" data-sortable><thead><tr>'
                '<th data-sort="num" aria-sort="ascending"><button type="button">Rank</button></th><th data-sort="text"><button type="button">State</button></th>'
                '<th class="r" data-sort="num"><button type="button">Price</button></th><th class="r" data-sort="num"><button type="button">Change in a year</button></th>'
                f'</tr></thead><tbody>{table_rows}</tbody></table></div>{self.ad("bottom")}'
                f'<div class="sources"><p>Source: U.S. Energy Information Administration (EIA), residential retail sales, {esc(m)} and {esc(ya)}. '
                f'Monthly figures are preliminary and EIA may revise them.</p></div>')
        html = self.layout(path=path, title=f"Electricity Prices by State, {m}: Every State Ranked",
                           description=f"Residential electricity prices in all 50 states and D.C. for {m}: cheapest, most expensive and the biggest changes since {ya}.",
                           body=body, crumbs=[("Home", "/"), ("Monthly reports", "/reports/"), (m, None)], scripts=("site.js",),
                           ld=[self.dataset_ld(path, f"Residential electricity prices by U.S. state, {m}",
                                               f"Residential electricity price in every U.S. state for {m}, with the change since {ya}.", mth)],
                           og_key="rates", nav="/reports/", og_type="article")
        self.write(path, html, 0.7, lastmod=self.data_lastmod())

    # ------------------------------------------------------------ home + static pages
    def home(self, reports):
        S, us = self.S, self.S["us"]
        priced = sorted([s for s in S["states"] if s["price"]], key=lambda s: s["price"])
        maxp = priced[-1]["price"]

        def bars(items, cls):
            return f'<ol class="bars {cls}">' + "".join(
                f'<li><a href="{self.state_url(s)}">{esc(s["name"])}</a><span class="bar" style="width:{s["price"] / maxp * 100:.0f}%"></span>'
                f'<span class="v">{fmt_cents(s["price"])}</span></li>' for s in items) + "</ol>"

        options = "".join(f'<option value="{self.state_url(s)}">{esc(s["name"])}</option>' for s in S["states"])
        m = month_name(S["latest_period"])
        report_link = (f'<p><a href="{self.url("/reports/" + reports[0] + "/")}">Read the {esc(month_name(reports[0]))} report</a>: '
                       'biggest increases, biggest decreases and the full ranking.</p>') if reports else ""
        calc_lists = ""
        for g, title in (("energy", "Energy and bills"), ("projects", "Home projects")):
            calc_lists += f"<h3>{title}</h3>" + '<ul class="calc-list">' + "".join(
                f'<li><a href="{self.url("/calculators/" + c["slug"] + "/")}">{esc(c["h1"])}</a><span>{esc(c["short"])}</span></li>'
                for c in self.calcs if c["group"] == g) + "</ul>"
        body = (
            '<section class="hero"><div><h1>What does electricity cost where you live?</h1>'
            f'<p class="lede">Official prices for all 50 states and D.C., refreshed when the U.S. Energy Information Administration publishes a new month. '
            'Plus calculators for your bill, appliances, EV charging, solar and home projects.</p>'
            f'<form class="picker" id="state-picker" action="{self.url("/electricity-rates/")}"><label for="pick">Choose your state</label>'
            f'<select id="pick" name="s"><option value="">Select a state</option>{options}</select><button type="submit">Show prices</button></form></div>'
            f'<div class="reading"><p class="muted">U.S. average, {esc(m)}</p>{meter(us["price"])}'
            f'<p>The average home uses {fmt_int(us["avg_kwh"])} kWh a month and pays about {fmt_money(us["avg_bill"], 0)} '
            f'({esc(us["usage_basis"])}).</p></div></section>'
            f'{self.ad("top")}<div class="split"><div><h2>Lowest prices</h2>{bars(priced[:5], "low")}</div>'
            f'<div><h2>Highest prices</h2>{bars(list(reversed(priced[-5:])), "high")}</div></div>{report_link}'
            f'<h2>Calculators</h2>{calc_lists}{self.ad("in_content")}'
            f'<h2>Every state</h2>{self.states_grid()}'
            f'<p><a href="{self.url("/electricity-rates/")}">Compare all states in one table</a>, with usage, bills and changes.</p>'
            '<h2>Where the numbers come from</h2><p>Prices, usage and bills come from the U.S. Energy Information Administration, '
            'which collects them from utilities every month. Solar output comes from PVWatts, the model run by the National Laboratory of the Rockies. '
            f'Every formula is written out on the <a href="{self.url("/methodology/")}">How we calculate</a> page.</p>')
        ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": self.cfg["site_name"], "url": self.abs("/")},
              {"@context": "https://schema.org", "@type": "Organization", "name": self.cfg.get("publisher_name", self.cfg["site_name"]),
               "url": self.abs("/"), "logo": self.abs("/favicon.svg")}]
        html = self.layout(path="/", title=f"Electricity Rates by State and Cost Calculators | {self.cfg['site_name']}",
                           description=f"Official electricity prices for every U.S. state ({m}), average bills, and free calculators for appliances, EV charging, solar payback and home projects.",
                           body=body, ld=ld, og_key="home", scripts=("site.js",))
        self.write("/", html, 1.0, lastmod=self.data_lastmod())

    def static_pages(self):
        cfg, S = self.cfg, self.S
        pub, site, mail = cfg.get("publisher_name", cfg["site_name"]), cfg["site_name"], cfg.get("contact_email", "")
        form_key = (cfg.get("contact_form", {}) or {}).get("web3forms_access_key", "").strip()
        if form_key:  # visitors write through a form; no address is published
            reach = f'<a href="{self.url("/contact/")}">contact form</a>'
            contact_block = f"""
<form class="contact-form" action="https://api.web3forms.com/submit" method="post" data-contact-form>
<input type="hidden" name="access_key" value="{esc(form_key)}">
<input type="hidden" name="subject" value="[{esc(site)}] Contact form">
<input type="hidden" name="from_name" value="{esc(site)}">
<div class="cf-row">
<div class="field"><label for="cf-name">Your name <span class="opt">(optional)</span></label><input id="cf-name" name="name" type="text" autocomplete="name" maxlength="80"></div>
<div class="field"><label for="cf-email">Your email <span class="opt">(optional, so we can reply)</span></label><input id="cf-email" name="email" type="email" autocomplete="email" inputmode="email" maxlength="120"></div>
</div>
<div class="field"><label for="cf-topic">Subject</label><select id="cf-topic" name="topic">
<option value="correction">A number or calculation looks wrong</option><option value="idea">An idea for a new calculator</option>
<option value="problem">A problem with the site</option><option value="privacy">A privacy request</option><option value="other">Something else</option></select></div>
<div class="field"><label for="cf-message">Message</label>
<textarea id="cf-message" name="message" rows="7" minlength="10" maxlength="5000" required aria-describedby="cf-hint"></textarea>
<p id="cf-hint" class="hint">For a correction, tell us the page and the number you think is right.</p></div>
<input type="checkbox" name="botcheck" tabindex="-1" autocomplete="off" hidden>
<div class="cf-send"><button type="submit">Send the message</button><p class="cf-status" role="status" aria-live="polite" data-contact-status></p></div>
</form>"""
        else:
            reach = f'<a href="mailto:{esc(mail)}">{esc(mail)}</a>'
            contact_block = f'<p>Email: {reach}</p>'
        sol = S.get("solar_meta", {}).get("system", {})
        funding = "The site is free to use and may show advertising. Ads never change the numbers. "
        funding += ("Some buttons are partner links: if you use one, we may earn a commission at no cost to you. Each one is labeled where it appears, "
                    "and partners have no say over the data or the calculations." if self.has_partners()
                    else "If we ever add affiliate links, they will be labeled where they appear.")
        pages = {
            "/about/": ("About Home Cost Pulse", f"Who publishes {site}, where the data comes from and how the site is funded.", f"""
<h1>About {esc(site)}</h1>
<p class="lede">{esc(site)} answers one question for U.S. households: what will this cost me? It turns official public data into plain numbers and free calculators.</p>
<h2>Who we are</h2><p>{esc(site)} is published by {esc(pub)}, an independent developer studio that builds calculators and study tools. We are not a utility, an energy retailer or a government agency, and we are not paid by any of them.</p>
<h2>Where the numbers come from</h2><p>Electricity prices, usage and bills come from the U.S. Energy Information Administration (EIA). Solar output estimates come from PVWatts, run by the National Laboratory of the Rockies (formerly NREL). Project calculators use standard building rules of thumb, explained on each page.</p>
<h2>How the site is funded</h2><p>{funding}</p>
<h2>Corrections</h2><p>Found a mistake? Tell us through the {reach} and we will fix it.</p>"""),
            "/methodology/": ("How We Calculate", "Data sources, formulas and update schedule behind every number on the site.", f"""
<h1>How we calculate</h1>
<p class="lede">Every number on this site comes from a public source or a formula written out below.</p>
<h2>Electricity prices, usage and bills</h2>
<p>Source: U.S. Energy Information Administration (EIA), electricity retail sales, residential sector, by state and month (API route electricity/retail-sales). EIA collects these figures from utilities and publishes them in its Electric Power Monthly, usually about two months after the month ends. This site checks for new data every week and rebuilds when EIA publishes a new month.</p>
<ul><li>Price (cents per kWh) is EIA's average price: total residential revenue divided by kWh sold. It therefore includes delivery charges and fees that utilities bill per kWh.</li>
<li>Average monthly usage = residential kWh sold ÷ number of residential customers, averaged over the latest 12 months.</li>
<li>Average monthly bill = residential revenue ÷ number of residential customers, averaged over the same 12 months. It includes fixed charges collected through rates; local taxes may be excluded.</li>
<li>Change is the price compared with the same month a year earlier.</li></ul>
<p>Monthly figures are preliminary and EIA revises them; when it does, the site picks up the revision on the next weekly check.</p>
<h2>Solar output</h2><p>Source: PVWatts v8 by the National Laboratory of the Rockies (formerly NREL), for one large city per state, using a fixed roof-mounted system facing south ({esc(sol.get("azimuth", 180))}° azimuth) at a {esc(sol.get("tilt", 20))}° tilt with {esc(sol.get("losses", 14))}% system losses and standard modules. Your roof's direction, shading and tilt change the result.</p>
<h2>Calculators</h2><p>Each calculator page explains its own formula. The math runs in your browser; nothing you type is sent anywhere. Project calculators only show a cost when you type a price yourself: the site does not guess material prices.</p>
<h2>Choosing a supplier</h2><p>Some state pages explain that homes there can choose their electricity supplier. That list follows the U.S. Energy Information Administration's description of retail choice and is reviewed by hand, and each page links to the state regulator's own site. Rules differ by utility, so confirm with yours.</p>
<h2>What these numbers are not</h2><p>They are averages and estimates for planning. They are not a quote, a bill, or financial, tax or legal advice. Your utility's tariff and your installer's or contractor's quote are the final word.</p>"""),
            "/privacy/": ("Privacy Policy", f"How {site} handles calculator inputs, analytics, cookies, advertising and the contact form, and how to make a privacy request.", f"""
<h1>Privacy policy</h1><p class="lede">Last updated {esc(self.content_date)}.</p>
<h2>What you type into calculators</h2><p>Calculator inputs are processed in your browser. We do not receive or store them.</p>
<h2>Analytics</h2><p>We may use privacy-friendly analytics (such as Cloudflare Web Analytics) or Google Analytics to count visits and see which pages are useful. These tools collect technical data such as pages viewed, approximate location from your IP address, device and browser type.</p>
<h2>Advertising</h2><p>We may show ads from third-party networks. These partners may use cookies or similar technologies to show ads and measure them, including ads based on your interests. You can control interest-based ads through your browser settings and, where available, the consent message shown on this site. Google's use of advertising cookies is explained at <a href="https://policies.google.com/technologies/ads">policies.google.com/technologies/ads</a>.</p>
<h2>Fonts</h2><p>Pages load fonts from Google Fonts, which receives your IP address to deliver them.</p>
<h2>Children</h2><p>This site is not directed to children under 13 and we do not knowingly collect their data.</p>
<h2>Your choices and rights</h2><p>Depending on where you live (for example California, the EU or the UK), you may have rights to access, delete or opt out of the sale or sharing of personal data. Use the {reach} to make a request.</p>
<h2>Contact form</h2><p>Messages sent through the contact form are delivered to us by Web3Forms, a form service. We use what you write, and your email address if you give one, only to answer you.</p>
<h2>Contact</h2><p>{esc(pub)}, through the {reach}.</p>"""),
            "/terms/": ("Terms of Use", f"Terms for using {site}: estimates and public statistics for general information, not quotes, bills or professional advice.", f"""
<h1>Terms of use</h1><p class="lede">Last updated {esc(self.content_date)}.</p>
<p>{esc(site)} provides estimates and public statistics for general information. They are not quotes, bills, or financial, tax, legal or engineering advice. Always confirm prices with your utility and get professional quotes before you buy or build.</p>
<p>We work to keep the data accurate and current but provide the site "as is", without warranties of any kind. We are not liable for decisions made using it.</p>
<p>Government data on this site (EIA and NLR) is public domain and credited to its source. The site's design, text and code belong to {esc(pub)}.</p>
<p>We may change these terms; the date above shows the latest version.</p>"""),
            "/contact/": ("Contact", f"Contact {site} with a question, a correction or an idea for a new calculator. Use the form; no account is needed.", f"""
<h1>Contact</h1><p class="lede">Questions, corrections or ideas for a new calculator are welcome.</p>
{contact_block}
<p>We cannot help with your utility account or bill disputes; please contact your utility for those.</p>"""),
        }
        for path, (title, desc, body) in pages.items():
            name = title if path != "/methodology/" else "How we calculate"
            html = self.layout(path=path, title=f"{title} | {site}", description=desc, body=body,
                               crumbs=[("Home", "/"), (name, None)], nav=path if path == "/methodology/" else None,
                               scripts=("site.js",) if path == "/contact/" else ())
            self.write(path, html, 0.3, lastmod=self.content_date)
        html = self.layout(path="/404.html", title=f"Page not found | {site}", description="This page does not exist.",
                           body=f'<h1>Page not found</h1><p class="lede">The address may be mistyped, or the page has moved.</p>'
                                f'<p><a href="{self.url("/electricity-rates/")}">See electricity rates by state</a> or '
                                f'<a href="{self.url("/calculators/")}">browse the calculators</a>.</p>')
        self.write("/404.html", html, sitemap=False)

    # ------------------------------------------------------------ technical files
    def technical_files(self):
        cfg = self.cfg
        urls = "".join(f"<url><loc>{esc(self.abs(p))}</loc><lastmod>{lm}</lastmod><priority>{pr:.1f}</priority></url>"
                       for p, lm, pr in sorted(self.pages))
        (DIST_DIR / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                              f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n', encoding="utf-8")
        (DIST_DIR / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {self.abs('/sitemap.xml')}\n", encoding="utf-8")
        lines = cfg.get("ads", {}).get("ads_txt_lines") or []
        if lines:
            (DIST_DIR / "ads.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for name, body in (cfg.get("site_verification", {}).get("files") or {}).items():
            if re.fullmatch(r"[A-Za-z0-9._-]+\.(txt|html)", name or ""):   # a plain file at the site root, nothing else
                (DIST_DIR / name).write_text(str(body), encoding="utf-8")
        key = cfg.get("indexnow_key", "")
        if key:
            (DIST_DIR / f"{key}.txt").write_text(key, encoding="utf-8")
        (DIST_DIR / ".nojekyll").write_text("", encoding="utf-8")

    # ------------------------------------------------------------ examples via node
    def compute_examples(self):
        node = shutil.which("node")
        if not node:
            log("Node.js not found: calculator pages will build without worked examples.")
            return
        jobs = [{"id": c["id"], "units": "us", "values": self.default_values(c)} for c in self.calcs]
        try:
            res = subprocess.run([node, str(ROOT / "scripts" / "calc_examples.js")], input=json.dumps({"jobs": jobs}),
                                 capture_output=True, text=True, timeout=60, check=True)
            self.examples = json.loads(res.stdout)
        except Exception as e:  # noqa: BLE001
            log(f"Worked examples skipped: {e}")


def main() -> int:
    cfg = load_config()
    meta = load_states_meta()
    S = summaries.build(meta, load_json(EIA_FILE), load_json(SEED_FILE), load_json(SOLAR_FILE))
    calcs = load_json(CONTENT_DIR / "calculators.json")["calculators"]
    log(f"Mode: {S['mode']}. Latest month: {S['latest_period']}. Solar data: {'yes' if S['has_solar'] else 'no'}.")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True)
    site = Site(cfg, S, calcs)
    site.copy_assets()
    site.compute_examples()

    if share_images.available() and os.environ.get("SKIP_IMAGES") != "1":
        try:
            site.og = share_images.generate(DIST_DIR, S, calcs, cfg)
            log(f"Share images: {len(site.og)} Open Graph images plus Pinterest pins.")
        except Exception as e:  # noqa: BLE001
            log(f"Share images skipped: {e}")
    else:
        log("matplotlib not installed (or SKIP_IMAGES=1): building without share images.")

    reports = site.reports()
    site.home(reports)
    site.rates_index()
    for s in S["states"]:
        if s["price"]:
            site.state_page(s)
    site.calculators_index()
    for c in calcs:
        site.calc_page(c)
    site.static_pages()
    site.technical_files()
    log(f"Built {len(site.pages)} pages into {DIST_DIR.relative_to(ROOT)}/ ({len(reports)} monthly reports).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
