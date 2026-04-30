# SPDX-License-Identifier: Apache-2.0
"""Conservative checks for public-ledger privacy and secret leaks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from no_meta_standing_ledger.models import canonical_json


@dataclass(frozen=True)
class PrivacyFinding:
    path: str
    rule: str
    message: str


_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "windows-absolute-path",
        re.compile(r"\b[A-Za-z]:\\(?:Users|Documents and Settings|Windows|Temp)\\[^\s\"']+"),
        "Windows absolute or local system path detected",
    ),
    (
        "posix-home-path",
        re.compile(r"(?<![A-Za-z0-9_])/(?:Users|home)/[A-Za-z0-9._-]+/[^\s\"']*"),
        "POSIX home-directory path detected",
    ),
    (
        "file-uri",
        re.compile(r"\bfile://", re.IGNORECASE),
        "local file URI detected",
    ),
    (
        "private-key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "private key material detected",
    ),
    (
        "env-assignment",
        re.compile(
            r"(?m)^\s*[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|CREDENTIAL)"
            r"[A-Z0-9_]*\s*=\s*['\"]?[^'\"\s]{8,}"
        ),
        "secret-bearing environment assignment detected",
    ),
    (
        "secret-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|token|secret|password|passwd|credential)\b\s*[:=]\s*"
            r"['\"]?[A-Za-z0-9_./+=-]{12,}"
        ),
        "secret-like assignment detected",
    ),
)


def scan_text(text: str, *, path: str = "$") -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    for rule, pattern, message in _RULES:
        if pattern.search(text):
            findings.append(PrivacyFinding(path=path, rule=rule, message=message))
    return findings


def scan_value(value: Any, *, path: str = "$") -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    if isinstance(value, str):
        findings.extend(scan_text(value, path=path))
    elif isinstance(value, dict):
        for key, item in value.items():
            findings.extend(scan_value(item, path=f"{path}.{key}"))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            findings.extend(scan_value(item, path=f"{path}[{index}]"))
    return findings


def assert_public_value(value: Any, *, context: str) -> None:
    findings = scan_value(value)
    if findings:
        formatted = "; ".join(f"{item.path}:{item.rule}" for item in findings)
        raise ValueError(f"{context} contains non-public or secret-like data: {formatted}")


def scan_jsonl_file(path: Path) -> list[PrivacyFinding]:
    findings: list[PrivacyFinding] = []
    if not path.exists():
        return findings
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        findings.extend(scan_text(line, path=f"{path}:{line_number}"))
        try:
            findings.extend(scan_value(json.loads(line), path=f"{path}:{line_number}"))
        except json.JSONDecodeError:
            findings.append(
                PrivacyFinding(
                    path=f"{path}:{line_number}",
                    rule="json-invalid",
                    message="line is not valid JSON",
                )
            )
    return findings


def public_canonical(value: Any) -> str:
    """Return a canonical string suitable for privacy-safe diagnostics."""

    return canonical_json(value)
