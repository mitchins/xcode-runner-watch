#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 MANIFEST_URL [BASELINE_PATH]" >&2
  exit 64
}

require_tool() {
  local tool="$1"
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing required tool: $tool" >&2
    exit 127
  fi
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage
fi

for tool in curl python3 diff cmp mktemp; do
  require_tool "$tool"
done

manifest_url="$1"
baseline_path="${2:-.ci/xcode-runner-baseline.json}"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

downloaded_manifest="$workdir/manifest.json"
curl -fsSL "$manifest_url" -o "$downloaded_manifest"

canonicalize() {
  local source_path="$1"
  local output_path="$2"

  SOURCE_PATH="$source_path" OUTPUT_PATH="$output_path" python3 - <<'PY'
import json
import os
from pathlib import Path


def canonical(value):
    if isinstance(value, dict):
        return {
            key: canonical(item)
            for key, item in sorted(value.items())
            if key != "observed_at"
        }
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


source_path = Path(os.environ["SOURCE_PATH"])
output_path = Path(os.environ["OUTPUT_PATH"])
document = json.loads(source_path.read_text(encoding="utf-8"))
output_path.write_text(
    json.dumps(canonical(document), indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

remote_canonical="$workdir/remote-canonical.json"
baseline_canonical="$workdir/baseline-canonical.json"
canonicalize "$downloaded_manifest" "$remote_canonical"

if [[ ! -f "$baseline_path" ]]; then
  echo "Changed: baseline file is missing at $baseline_path"
  echo
  cat "$remote_canonical"
  exit 10
fi

canonicalize "$baseline_path" "$baseline_canonical"

if cmp -s "$baseline_canonical" "$remote_canonical"; then
  echo "Unchanged: $baseline_path matches $manifest_url"
  exit 0
fi

echo "Changed: $baseline_path differs from $manifest_url"
echo
diff -u "$baseline_canonical" "$remote_canonical" || true
exit 10
