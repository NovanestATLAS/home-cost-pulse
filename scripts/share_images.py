"""Social share images (Open Graph 1200×630) and Pinterest pins (1000×1500).

Generated at build time with matplotlib when it is installed (the GitHub workflow installs it).
If matplotlib is missing the site still builds; pages simply have no og:image.
"""
from __future__ import annotations

from pathlib import Path

from common import fmt_int, fmt_money, month_name

INK, PAPER, VOLT, MUTED, WIRE, LOW, HIGH = "#1D2733", "#F2F4F3", "#F4C21B", "#4A5664", "#1F5FA8", "#1D7357", "#B3261E"


def available() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


class Canvas:
    """Tiny pixel-coordinate helper over a matplotlib figure (origin at top left)."""

    def __init__(self, w: int, h: int):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch, Rectangle
        self.plt, self.Rect, self.Fancy = plt, Rectangle, FancyBboxPatch
        self.w, self.h = w, h
        self.fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
        self.fig.patch.set_facecolor(PAPER)

    def _fx(self, x): return x / self.w
    def _fy(self, y): return 1 - y / self.h

    def rect(self, x, y, w, h, color, rounded=0.0):
        if rounded:
            p = self.Fancy((self._fx(x), self._fy(y + h)), w / self.w, h / self.h,
                           boxstyle=f"round,pad=0,rounding_size={rounded / self.w}",
                           transform=self.fig.transFigure, facecolor=color, edgecolor="none")
        else:
            p = self.Rect((self._fx(x), self._fy(y + h)), w / self.w, h / self.h,
                          transform=self.fig.transFigure, facecolor=color, edgecolor="none")
        self.fig.add_artist(p)

    def text(self, x, y, s, size, color=INK, weight="normal", ha="left", va="top"):
        self.fig.text(self._fx(x), self._fy(y), s, fontsize=size * 0.72, color=color, weight=weight,
                      ha=ha, va=va, family="DejaVu Sans")

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(path, dpi=100, facecolor=PAPER)
        self.plt.close(self.fig)


def _meter_cells(c: Canvas, x, y, price, cell_w, cell_h, size):
    """Draw price digits; digits after the decimal point get the yellow cells."""
    s = f"{price:.2f}"
    cx, after = x, False
    for ch in s:
        if ch == ".":
            c.text(cx + 4, y + cell_h, ".", size, INK, "bold", va="bottom")
            cx += int(cell_w * 0.35)
            after = True
            continue
        c.rect(cx, y, cell_w, cell_h, VOLT if after else INK, rounded=6)
        c.text(cx + cell_w / 2, y + cell_h / 2 + 2, ch, size, INK if after else "#FFFFFF", "bold", ha="center", va="center")
        cx += cell_w + 8
    return cx


def _header(c: Canvas, site: str, domain: str):
    c.rect(0, 0, c.w, 64, INK)
    c.rect(28, 20, 24, 24, VOLT, rounded=5)
    c.text(64, 32, site, 26, "#FFFFFF", "bold", va="center")
    c.text(c.w - 28, 32, domain, 20, "#DCE3EA", ha="right", va="center")


def state_og(c_path: Path, s: dict, us: dict, site: str, domain: str):
    c = Canvas(1200, 630)
    _header(c, site, domain)
    c.text(60, 108, f"{s['name']} electricity price", 50, INK, "bold")
    end = _meter_cells(c, 60, 196, s["price"], 92, 132, 84)
    c.text(end + 16, 312, "¢ per kWh", 34, MUTED, "bold", va="bottom")
    vs = s.get("vs_us_pct")
    line = f"{month_name(s['period'])}. "
    if vs is not None:
        line += f"{abs(vs):.0f}% {'below' if vs < 0 else 'above'} the U.S. average of {us['price']:.2f}¢."
    c.text(60, 372, line, 28, INK)
    if s.get("avg_bill"):
        c.text(60, 422, f"Average home: {fmt_int(s['avg_kwh'])} kWh and {fmt_money(s['avg_bill'], 0)} a month ({s['usage_basis']}).", 26, MUTED)
    c.text(60, 580, "Source: U.S. Energy Information Administration", 22, MUTED)
    c.save(c_path)


def state_pin(c_path: Path, s: dict, site: str, domain: str):
    c = Canvas(1000, 1500)
    _header(c, site, domain)
    c.text(70, 130, "What electricity costs", 58, INK, "bold")
    c.text(70, 205, f"in {s['name']}", 58, INK, "bold")
    end = _meter_cells(c, 70, 320, s["price"], 104, 150, 96)
    c.text(end + 14, 470, "¢/kWh", 38, MUTED, "bold", va="bottom")
    c.text(70, 520, month_name(s["period"]), 30, MUTED)
    p = s["price"] / 100
    rows = [
        ("1,000 kWh", 1000 * p),
        ("Central AC, 8 h a day for a month", 840 * p),
        ("Space heater, 8 h a day for a month", 360 * p),
        ("1,000 miles in an EV", 317.46 * p),
        ("Electric dryer, 12 loads", 36 * p),
    ]
    y = 640
    for label, cost in rows:
        c.rect(70, y + 70, 860, 2, "#C9D1D8")
        c.text(70, y + 18, label, 30, INK)
        c.text(930, y + 18, fmt_money(cost), 34, INK, "bold", ha="right")
        y += 104
    c.text(70, 1300, "Estimates at the state's average residential price.", 24, MUTED)
    c.text(70, 1340, "Source: U.S. Energy Information Administration.", 24, MUTED)
    c.rect(0, 1410, 1000, 90, VOLT)
    c.text(500, 1455, f"Check your bill: {domain}", 34, INK, "bold", ha="center", va="center")
    c.save(c_path)


def simple_og(c_path: Path, title: str, subtitle: str, site: str, domain: str, price: float | None = None):
    c = Canvas(1200, 630)
    _header(c, site, domain)
    c.text(60, 120, title, 54, INK, "bold")
    c.text(60, 200, subtitle, 30, MUTED)
    if price:
        end = _meter_cells(c, 60, 300, price, 84, 120, 76)
        c.text(end + 14, 404, "¢ per kWh, U.S. average", 30, MUTED, "bold", va="bottom")
    c.save(c_path)


def generate(dist: Path, S: dict, calcs: list[dict], cfg: dict) -> dict[str, str]:
    """Writes images into dist/og and dist/pins. Returns page-key -> URL path of its og image."""
    site = cfg.get("site_name", "Home Cost Pulse")
    domain = cfg.get("site_url", "").replace("https://", "").replace("http://", "").rstrip("/") or "homecostpulse.com"
    us = S["us"]
    out: dict[str, str] = {}
    simple_og(dist / "og" / "home.png", "What electricity costs where you live",
              f"Official prices for 50 states and D.C., {month_name(S['latest_period'])}", site, domain, us["price"])
    out["home"] = "/og/home.png"
    simple_og(dist / "og" / "rates.png", "Electricity rates by state",
              f"Average residential price, {month_name(S['latest_period'])}", site, domain, us["price"])
    out["rates"] = "/og/rates.png"
    for s in S["states"]:
        if not s.get("price"):
            continue
        state_og(dist / "og" / f"{s['slug']}.png", s, us, site, domain)
        state_pin(dist / "pins" / f"{s['slug']}.png", s, site, domain)
        out[f"state:{s['code']}"] = f"/og/{s['slug']}.png"
    for calc in calcs:
        simple_og(dist / "og" / f"calc-{calc['id']}.png", calc["h1"], calc["short"], site, domain)
        out[f"calc:{calc['id']}"] = f"/og/calc-{calc['id']}.png"
    return out
