#!/usr/bin/env python3
"""Tell IndexNow search engines (Bing, Yandex, Seznam, Naver and others) which URLs changed.

Google does not use IndexNow; it reads sitemap.xml (submit it once in Search Console).
The key file /<key>.txt is written into dist/ by build_site.py from site.config.json.

Usage:
  python3 scripts/indexnow_ping.py                 # all URLs from dist/sitemap.xml
  python3 scripts/indexnow_ping.py --dry-run       # print what would be sent
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from common import DIST_DIR, load_config, log  # noqa: E402

ENDPOINT = "https://api.indexnow.org/indexnow"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    key, site = cfg.get("indexnow_key", ""), cfg["site_url"]
    if not key or not site or "github.io" in site:
        log("IndexNow skipped: needs indexnow_key and your own domain in site_url.")
        return 0
    sitemap = DIST_DIR / "sitemap.xml"
    if not sitemap.exists():
        log("IndexNow skipped: dist/sitemap.xml not found (run build_site.py first).")
        return 0
    urls = re.findall(r"<loc>([^<]+)</loc>", sitemap.read_text(encoding="utf-8"))[:10000]
    host = site.split("://", 1)[-1].split("/", 1)[0]
    body = {"host": host, "key": key, "keyLocation": f"{site}/{key}.txt", "urlList": urls}
    if args.dry_run:
        log(json.dumps({**body, "urlList": urls[:5] + ["..."]}, indent=1))
        return 0
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            log(f"IndexNow accepted {len(urls)} URLs (HTTP {resp.status}).")
    except urllib.error.HTTPError as e:
        # 403 = key file not reachable yet; 422 = URLs don't match the host. Neither should fail the deploy.
        log(f"IndexNow returned HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as e:
        log(f"IndexNow unreachable: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
