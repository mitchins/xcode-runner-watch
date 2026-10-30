#!/usr/bin/env python3
"""Compare meaningful Xcode runner changes and render release notes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path, require_parsed: bool = True) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    validate_manifest(value, str(path), require_parsed=require_parsed)
    return value


def validate_manifest(manifest: dict[str, Any], source: str = "manifest", require_parsed: bool = True) -> None:
    required = ("runner_label", "system", "xcode", "swift", "sdks", "simulators")
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError(f"{source} is missing required fields: {', '.join(missing)}")
    if not isinstance(_value(manifest, "simulators", "runtimes", "runtimes"), list):
        raise ValueError(f"{source} has no simulator runtime list; refusing to report removals")
    if require_parsed and not _string(_value(manifest, "xcode", "xcodebuild_version", "xcode")):
        raise ValueError(f"{source} has no parsed Xcode version")
    if require_parsed and not _string(_value(manifest, "swift", "swift_version", "version")):
        raise ValueError(f"{source} has no parsed Swift version")
    for runtime in _value(manifest, "simulators", "runtimes", "runtimes"):
        if not isinstance(runtime, dict) or not _string(runtime.get("identifier")):
            raise ValueError(f"{source} contains a simulator runtime without an identifier")
    for sdk in ("iphoneos", "iphonesimulator", "macosx"):
        if _sdk(manifest, sdk)[0] is None:
            raise ValueError(f"{source} has no {sdk} SDK version")


def _value(value: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value


def _string(value: Any) -> str | None:
    return str(value) if value is not None and str(value).strip() else None


def _toolchain(manifest: dict[str, Any], name: str) -> str | None:
    if name == "xcode":
        version = _value(manifest, "xcode", "xcodebuild_version")
        if not isinstance(version, dict):
            return _string(version)
        xcode = _string(version.get("xcode"))
        if xcode is None:
            return None
        build = _string(version.get("build"))
        return " ".join(part for part in (xcode, f"(build {build})" if build else None) if part) or None
    version = _value(manifest, "swift", "swift_version")
    if not isinstance(version, dict):
        return _string(version)
    label = _string(version.get("version"))
    if label is None:
        return None
    target = _string(version.get("target"))
    return " — ".join(part for part in (label, target) if part) or None


def _sdk(manifest: dict[str, Any], sdk: str) -> tuple[str | None, str | None]:
    value = _value(manifest, "sdks", sdk)
    if isinstance(value, dict):
        return _string(value.get("version")), _string(value.get("build"))
    # Version 1 manifests stored SDK values as strings.
    return _string(value), None


def _runtime_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    runtimes = _value(manifest, "simulators", "runtimes", "runtimes")
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(runtimes, list):
        return result
    for runtime in runtimes:
        if not isinstance(runtime, dict):
            continue
        identifier = _string(runtime.get("identifier"))
        if not identifier:
            continue
        result[identifier] = {
            "version": _string(runtime.get("version")),
            "build": _string(runtime.get("buildversion", runtime.get("buildVersion"))),
            "available": runtime.get("isAvailable", runtime.get("available")),
        }
    return result


def _runtime_label(runtime: dict[str, Any]) -> str:
    label = runtime.get("version") or "unknown version"
    if runtime.get("build"):
        label += f" (build {runtime['build']})"
    availability = runtime.get("available")
    if availability is not None:
        label += "; available" if availability else "; unavailable"
    return label


def semantic_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []

    def compare(label: str, old: Any, new: Any) -> None:
        old_text, new_text = _string(old), _string(new)
        # A newly available field fills in the baseline; it is not evidence
        # that the runner changed. Both sides must report a value.
        if old_text is not None and new_text is not None and old_text != new_text:
            changes.append(
                {"label": label, "before": old_text, "after": new_text}
            )

    compare("Runner", before.get("runner_label"), after.get("runner_label"))
    compare("macOS version", _value(before, "system", "product_version"), _value(after, "system", "product_version"))
    compare("macOS build", _value(before, "system", "build_version"), _value(after, "system", "build_version"))
    compare("Xcode", _toolchain(before, "xcode"), _toolchain(after, "xcode"))
    compare("Swift", _toolchain(before, "swift"), _toolchain(after, "swift"))

    for sdk in ("iphoneos", "iphonesimulator", "macosx"):
        old_version, old_build = _sdk(before, sdk)
        new_version, new_build = _sdk(after, sdk)
        compare(f"{sdk} SDK version", old_version, new_version)
        compare(f"{sdk} SDK build", old_build, new_build)

    old_runtimes, new_runtimes = _runtime_map(before), _runtime_map(after)
    for identifier in sorted(old_runtimes.keys() | new_runtimes.keys()):
        old, new = old_runtimes.get(identifier), new_runtimes.get(identifier)
        if old is None:
            changes.append({"label": f"Simulator runtime added: {identifier}", "before": "absent", "after": _runtime_label(new or {})})
        elif new is None:
            changes.append({"label": f"Simulator runtime removed: {identifier}", "before": _runtime_label(old), "after": "absent"})
        else:
            changed_fields = [key for key in ("version", "build", "available") if old.get(key) is not None and new.get(key) is not None and old.get(key) != new.get(key)]
            if changed_fields:
                changes.append({"label": f"Simulator runtime changed: {identifier}", "before": _runtime_label(old), "after": _runtime_label(new)})
    return changes


def needs_baseline_refresh(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Quietly persist newly represented fields so later changes are observable."""
    if after.get("manifest_version", 1) > before.get("manifest_version", 1):
        return True

    if _value(before, "swift", "swift_version", "version") is None and _value(after, "swift", "swift_version", "version") is not None:
        return True
    for sdk in ("iphoneos", "iphonesimulator", "macosx"):
        if _sdk(before, sdk)[1] is None and _sdk(after, sdk)[1] is not None:
            return True
    old_runtimes, new_runtimes = _runtime_map(before), _runtime_map(after)
    for identifier in old_runtimes.keys() & new_runtimes.keys():
        if any(old_runtimes[identifier].get(key) is None and new_runtimes[identifier].get(key) is not None for key in ("version", "build", "available")):
            return True
    return False


def compare_manifests(baseline_exists: bool, before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, bool, list[dict[str, str]]]:
    if not baseline_exists:
        return False, False, []
    changes = semantic_changes(before, after)
    return bool(changes), needs_baseline_refresh(before, after), changes


def semantic_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Project only values used by change detection for retry-safe keys."""
    return {
        "runner_label": manifest.get("runner_label"),
        "system": {
            "product_version": _value(manifest, "system", "product_version"),
            "build_version": _value(manifest, "system", "build_version"),
        },
        "xcode": _toolchain(manifest, "xcode"),
        "swift": _toolchain(manifest, "swift"),
        "sdks": {sdk: _sdk(manifest, sdk) for sdk in ("iphoneos", "iphonesimulator", "macosx")},
        "runtimes": _runtime_map(manifest),
    }


def release_tag(baseline_revision: str, current: dict[str, Any]) -> str:
    payload = json.dumps(semantic_manifest(current), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"runner-change-{baseline_revision[:12]}-{digest}"


def release_notes(changes: list[dict[str, str]], run_url: str) -> str:
    lines = ["## macOS runner environment changed", "", "Changes detected:", ""]
    for change in changes:
        lines.append(f"- **{change['label']}:** `{change['before']}` → `{change['after']}`")
    lines.extend(["", f"Evidence: [successful capture workflow run]({run_url})", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--incoming", type=Path, required=True)
    parser.add_argument("--baseline-revision", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--release-notes", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    current = load(args.incoming)
    baseline_exists = args.baseline.exists()
    baseline = load(args.baseline, require_parsed=False) if baseline_exists else {}
    changed, refresh_baseline, changes = compare_manifests(baseline_exists, baseline, current)
    tag = release_tag(args.baseline_revision, current) if changed else ""
    report = {"baseline_exists": baseline_exists, "changed": changed, "refresh_baseline": refresh_baseline, "release_tag": tag, "changes": changes}
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.release_notes.write_text(release_notes(changes, args.run_url) if changed else "", encoding="utf-8")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"baseline_exists={str(baseline_exists).lower()}\n")
            output.write(f"changed={str(changed).lower()}\n")
            output.write(f"initialize={str(not baseline_exists).lower()}\n")
            output.write(f"refresh_baseline={str(refresh_baseline).lower()}\n")
            output.write(f"release_tag={tag}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
