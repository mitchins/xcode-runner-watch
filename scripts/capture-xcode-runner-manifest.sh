#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: RUNNER_LABEL=<label> $0 OUTPUT_PATH" >&2
  exit 64
}

require_tool() {
  local tool="$1"
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 127
  fi
}

if [[ $# -ne 1 ]]; then
  usage
fi

if [[ -z "${RUNNER_LABEL:-}" ]]; then
  echo "RUNNER_LABEL must be set" >&2
  exit 64
fi

for tool in python3 xcode-select xcodebuild swift xcrun sw_vers uname mktemp; do
  require_tool "$tool"
done

output_path="$1"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

xcodebuild -version >"$workdir/xcodebuild-version.txt" 2>&1
swift --version >"$workdir/swift-version.txt" 2>&1
xcrun --sdk iphoneos --show-sdk-version >"$workdir/sdk-iphoneos.txt"
xcrun --sdk iphonesimulator --show-sdk-version >"$workdir/sdk-iphonesimulator.txt"
xcrun --sdk macosx --show-sdk-version >"$workdir/sdk-macosx.txt"
xcrun simctl list runtimes --json >"$workdir/simctl-runtimes.json"
xcrun simctl list devicetypes --json >"$workdir/simctl-devicetypes.json"
xcrun simctl list devices available --json >"$workdir/simctl-devices-available.json"

RUNNER_LABEL="$RUNNER_LABEL" \
OUTPUT_PATH="$output_path" \
WORKDIR="$workdir" \
SELECTED_XCODE_PATH="$(xcode-select -p)" \
UNAME_OUTPUT="$(uname -srvm)" \
MACOS_PRODUCT_NAME="$(sw_vers -productName)" \
MACOS_PRODUCT_VERSION="$(sw_vers -productVersion)" \
MACOS_BUILD_VERSION="$(sw_vers -buildVersion)" \
python3 - <<'PY'
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value):
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [canonical(item) for item in value]
        return sorted(
            items,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    return value


def capture_xcode_version(raw: str) -> dict:
    xcode_match = re.search(r"^Xcode\s+(.+)$", raw, re.MULTILINE)
    build_match = re.search(r"^Build version\s+(.+)$", raw, re.MULTILINE)
    return {
        "raw": raw,
        "xcode": xcode_match.group(1) if xcode_match else None,
        "build": build_match.group(1) if build_match else None,
    }


def capture_swift_version(raw: str) -> dict:
    version_match = re.search(r"^Swift version\s+(.+)$", raw, re.MULTILINE)
    target_match = re.search(r"^Target:\s+(.+)$", raw, re.MULTILINE)
    return {
        "raw": raw,
        "version": version_match.group(1) if version_match else None,
        "target": target_match.group(1) if target_match else None,
    }


workdir = Path(os.environ["WORKDIR"])
output_path = Path(os.environ["OUTPUT_PATH"])
devices_available = read_json(workdir / "simctl-devices-available.json")
sanitized_devices = {
    runtime: [
        {
            "name": device.get("name"),
            "deviceTypeIdentifier": device.get("deviceTypeIdentifier"),
            "isAvailable": device.get("isAvailable"),
        }
        for device in devices
    ]
    for runtime, devices in sorted(devices_available.get("devices", {}).items())
}

manifest = canonical(
    {
        "manifest_version": 1,
        "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runner_label": os.environ["RUNNER_LABEL"],
        "system": {
            "build_version": os.environ["MACOS_BUILD_VERSION"],
            "product_name": os.environ["MACOS_PRODUCT_NAME"],
            "product_version": os.environ["MACOS_PRODUCT_VERSION"],
            "uname": os.environ["UNAME_OUTPUT"],
        },
        "xcode": {
            "selected_path": os.environ["SELECTED_XCODE_PATH"],
            "xcodebuild_version": capture_xcode_version(
                read_text(workdir / "xcodebuild-version.txt")
            ),
        },
        "swift": {
            "swift_version": capture_swift_version(
                read_text(workdir / "swift-version.txt")
            ),
        },
        "sdks": {
            "iphoneos": read_text(workdir / "sdk-iphoneos.txt"),
            "iphonesimulator": read_text(workdir / "sdk-iphonesimulator.txt"),
            "macosx": read_text(workdir / "sdk-macosx.txt"),
        },
        "simulators": {
            "runtimes": read_json(workdir / "simctl-runtimes.json"),
            "device_types": read_json(workdir / "simctl-devicetypes.json"),
            "devices_available": sanitized_devices,
        },
    }
)

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
