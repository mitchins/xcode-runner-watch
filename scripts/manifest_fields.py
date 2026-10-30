"""Small parsers shared by manifest capture and its unit tests."""

from __future__ import annotations

import re
from typing import Any


def capture_xcode_version(raw: str) -> dict[str, Any]:
    xcode_match = re.search(r"^Xcode\s+(.+)$", raw, re.MULTILINE)
    build_match = re.search(r"^Build version\s+(.+)$", raw, re.MULTILINE)
    return {
        "raw": raw,
        "xcode": xcode_match.group(1) if xcode_match else None,
        "build": build_match.group(1) if build_match else None,
    }


def capture_swift_version(raw: str) -> dict[str, Any]:
    # `swift --version` on current Apple toolchains starts with
    # "Apple Swift version", while some older versions omit "Apple".
    version_match = re.search(r"^(?:Apple\s+)?Swift version\s+(.+)$", raw, re.MULTILINE)
    target_match = re.search(r"^Target:\s+(.+)$", raw, re.MULTILINE)
    return {
        "raw": raw,
        "version": version_match.group(1) if version_match else None,
        "target": target_match.group(1) if target_match else None,
    }
