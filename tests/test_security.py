# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest

from no_meta_standing_ledger.evidence import evidence_payload_from_file, evidence_payload_from_uri
from no_meta_standing_ledger.privacy import assert_public_value, scan_text


def test_privacy_scanner_detects_absolute_path() -> None:
    findings = scan_text(r"artifact was at C:\Users\alice\secret\data.json")

    assert findings
    assert findings[0].rule == "windows-absolute-path"


def test_public_value_rejects_secret_assignment() -> None:
    with pytest.raises(ValueError):
        assert_public_value({"note": "api_key = sk-test-1234567890abcdef"}, context="test")


def test_uri_evidence_rejects_file_uri() -> None:
    with pytest.raises(ValueError):
        evidence_payload_from_uri(
            "file:///tmp/private.json",
            sha256="a" * 64,
            size=1,
            content_type="application/json",
        )


def test_uri_evidence_payload_contains_no_local_path() -> None:
    payload = evidence_payload_from_uri(
        "https://example.org/evidence.json",
        sha256="a" * 64,
        size=10,
        content_type="application/json",
    )

    assert payload["artifact_id"] == f"sha256:{'a' * 64}"
    assert "path" not in payload


def test_file_evidence_include_content_has_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "large.txt"
    path.write_text("x" * 10, encoding="utf-8")

    with pytest.raises(ValueError, match="max_include_bytes"):
        evidence_payload_from_file(path, include_content=True, max_include_bytes=4)
