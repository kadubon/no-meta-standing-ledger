# SPDX-License-Identifier: Apache-2.0
"""Scan repository text files for common local path and secret leaks."""

from __future__ import annotations

import sys
from pathlib import Path

from no_meta_standing_ledger.privacy import scan_text

SKIP_DIRS = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "tests",
}
SKIP_FILES = {
    Path("src/no_meta_standing_ledger/privacy.py"),
}
TEXT_SUFFIXES = {
    ".cff",
    ".cfg",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}


def main() -> int:
    findings: list[str] = []
    for path in Path.cwd().rglob("*"):
        relative = path.relative_to(Path.cwd())
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        if relative in SKIP_FILES:
            continue
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for item in scan_text(text, path=str(path)):
            findings.append(f"{item.path}: {item.rule}: {item.message}")
    if findings:
        print("secret scan findings:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
