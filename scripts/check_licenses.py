# SPDX-License-Identifier: Apache-2.0
"""Minimal runtime dependency license guard.

The package intentionally has no runtime dependencies. This script prevents
accidental introduction of copyleft runtime dependencies without review.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

BLOCKED_LICENSE_FAMILIES = ("gpl", "agpl", "lgpl", "mpl")


def main() -> int:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject.get("project", {}).get("dependencies", [])
    blocked = [
        dependency
        for dependency in dependencies
        if any(family in dependency.lower() for family in BLOCKED_LICENSE_FAMILIES)
    ]
    if blocked:
        print("blocked runtime dependencies require legal review:", file=sys.stderr)
        for dependency in blocked:
            print(f"- {dependency}", file=sys.stderr)
        return 1
    print("runtime dependency license allowlist passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

