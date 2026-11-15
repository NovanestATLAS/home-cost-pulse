#!/usr/bin/env python3
"""One command to refresh all data, then check it.

  EIA_API_KEY=... NLR_API_KEY=... python3 scripts/update_data.py

Missing keys are skipped with a warning, so the site can still build from what is on disk.
Exit code 1 means the data checks failed and nothing should be published.
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script: str, *args: str) -> int:
    print(f"\n== {script} {' '.join(args)}", flush=True)
    return subprocess.call([sys.executable, os.path.join(HERE, script), *args])


def main() -> int:
    eia = run("fetch_eia.py")
    solar = run("fetch_pvwatts.py", *sys.argv[1:])
    if eia or solar:
        print("A fetch failed; the previous data files were kept.", flush=True)
    return run("validate_data.py")


if __name__ == "__main__":
    sys.exit(main())
