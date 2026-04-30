# SPDX-License-Identifier: Apache-2.0
"""Evidence payload construction with privacy-preserving defaults."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from no_meta_standing_ledger.models import JsonDict
from no_meta_standing_ledger.privacy import assert_public_value

DEFAULT_MAX_INCLUDE_BYTES = 65536


def evidence_payload_from_file(
    path: Path,
    *,
    content_type: str | None = None,
    include_content: bool = False,
    max_include_bytes: int = DEFAULT_MAX_INCLUDE_BYTES,
    support: bool = True,
) -> JsonDict:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    guessed_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    payload: JsonDict = {
        "artifact_id": f"sha256:{digest}",
        "sha256": digest,
        "size": len(data),
        "content_type": guessed_type,
        "support": support,
    }
    if include_content:
        if max_include_bytes < 0:
            raise ValueError("max_include_bytes must be non-negative")
        if len(data) > max_include_bytes:
            raise ValueError(
                "embedded evidence content exceeds max_include_bytes; "
                "record hash metadata or raise the explicit limit"
            )
        text = data.decode("utf-8")
        assert_public_value(text, context="embedded evidence content")
        payload["content"] = text
    return payload


def evidence_payload_from_uri(
    uri: str,
    *,
    sha256: str | None,
    size: int | None,
    content_type: str | None = None,
    support: bool = True,
) -> JsonDict:
    parsed = urlparse(uri)
    if parsed.scheme not in {"http", "https", "doi"}:
        raise ValueError("public evidence URI must use http, https, or doi")
    payload: JsonDict = {
        "public_uri": uri,
        "content_type": content_type or "application/octet-stream",
        "support": support,
    }
    if sha256 is not None:
        _validate_sha256(sha256)
        payload["sha256"] = sha256.lower()
        payload["artifact_id"] = f"sha256:{sha256.lower()}"
    if size is not None:
        if size < 0:
            raise ValueError("evidence size must be non-negative")
        payload["size"] = size
    assert_public_value(payload, context="evidence URI payload")
    return payload


def _validate_sha256(value: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise ValueError("sha256 must be a 64-character hex digest")
