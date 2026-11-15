#!/usr/bin/env python3
"""Check every internal link and asset in dist/ points at a file that exists.

Run after build_site.py. Exits 1 (and blocks the deploy in GitHub Actions) on any broken link.
"""
from __future__ import annotations

import os
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

sys.path.insert(0, os.path.dirname(__file__))
from common import DIST_DIR, load_config, log  # noqa: E402


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key):
                self.found.append(a[key])


def target_exists(path: str) -> bool:
    p = DIST_DIR / unquote(path).lstrip("/")
    if path.endswith("/"):
        return (p / "index.html").exists()
    return p.exists() or (p / "index.html").exists()


def main() -> int:
    base = load_config()["base_path"]
    pages = list(DIST_DIR.rglob("*.html"))
    broken, checked = [], 0
    for page in pages:
        parser = Links()
        parser.feed(page.read_text(encoding="utf-8"))
        for link in parser.found:
            if link.startswith(("http://", "https://", "mailto:", "tel:", "data:", "#", "javascript:")):
                continue
            path = urlsplit(link).path
            if base and path.startswith(base):
                path = path[len(base):] or "/"
            if not path.startswith("/"):
                broken.append((page, link, "relative link"))
                continue
            checked += 1
            if not target_exists(path):
                broken.append((page, link, "missing"))
    for page, link, why in broken[:40]:
        log(f"BROKEN ({why}): {link}  in {page.relative_to(DIST_DIR)}")
    log(f"Checked {checked} internal links across {len(pages)} pages: {len(broken)} broken.")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
