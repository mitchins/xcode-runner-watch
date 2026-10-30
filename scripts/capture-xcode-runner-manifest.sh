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

for sdk in iphoneos iphonesimulator macosx; do
  xcrun --sdk "$sdk" --show-sdk-version >"$workdir/sdk-$sdk-version.txt"
  xcrun --sdk "$sdk" --show-sdk-path >"$workdir/sdk-$sdk-path.txt"
done

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
PYTHONPATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" \
python3 - <<'PY'
import json
import os
import plistlib
from datetime import datetime, timezone
from pathlib import Path

from manifest_fields import capture_swift_version, capture_xcode_version


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value):
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [canonical(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
    return value


def sdk_build(path: Path):
    settings = path / "SDKSettings.plist"
    if not settings.is_file():
        return None
    with settings.open("rb") as source:
        return plistlib.load(source).get("ProductBuildVersion")


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

sdks = {}
for sdk in ("iphoneos", "iphonesimulator", "macosx"):
    sdk_path = Path(read_text(workdir / f"sdk-{sdk}-path.txt"))
    sdks[sdk] = {
        "version": read_text(workdir / f"sdk-{sdk}-version.txt"),
        "build": sdk_build(sdk_path),
    }

manifest = canonical(
    {
        "manifest_version": 2,
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
            "xcodebuild_version": capture_xcode_version(read_text(workdir / "xcodebuild-version.txt")),
        },
        "swift": {
            "swift_version": capture_swift_version(read_text(workdir / "swift-version.txt")),
        },
        "sdks": sdks,
        "simulators": {
            "runtimes": read_json(workdir / "simctl-runtimes.json"),
            "device_types": read_json(workdir / "simctl-devicetypes.json"),
            "devices_available": sanitized_devices,
        },
    }
)

output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
