import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_xcode_runner_manifest as compare
from manifest_fields import capture_swift_version


def manifest():
    return {
        "manifest_version": 2,
        "observed_at": "2026-10-01T00:00:00Z",
        "runner_label": "macos-latest",
        "system": {"product_version": "26.0", "build_version": "25A1", "uname": "noisy host string"},
        "xcode": {"selected_path": "/Applications/Xcode_26.app", "xcodebuild_version": {"xcode": "26.0", "build": "17A1", "raw": "Xcode 26.0"}},
        "swift": {"swift_version": {"version": "6.2", "target": "arm64-apple-macosx26.0", "raw": "Apple Swift version 6.2 (swiftlang-abc)"}},
        "sdks": {"iphoneos": {"version": "26.0", "build": "23A1"}, "iphonesimulator": {"version": "26.0", "build": "23A1"}, "macosx": {"version": "26.0", "build": "25A1"}},
        "simulators": {
            "runtimes": {"runtimes": [{"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-0", "version": "26.0", "buildversion": "23A1", "isAvailable": True, "lastUsage": "yesterday", "bundlePath": "/tmp/runtime"}]},
            "device_types": {"devicetypes": [{"identifier": "iPhone-noise", "name": "changed"}]},
            "devices_available": {"devices": {"runtime": [{"udid": "device-one", "state": "Booted"}]}},
        },
    }


class ManifestComparisonTests(unittest.TestCase):
    def test_ignores_observation_paths_host_and_device_churn(self):
        before, after = manifest(), manifest()
        after["observed_at"] = "2026-10-02T00:00:00Z"
        after["system"]["uname"] = "another host string"
        after["xcode"]["selected_path"] = "/Applications/Other-Xcode.app"
        after["simulators"]["runtimes"]["runtimes"][0]["lastUsage"] = "today"
        after["simulators"]["runtimes"]["runtimes"][0]["bundlePath"] = "/different/path"
        after["simulators"]["device_types"]["devicetypes"].append({"identifier": "new-device-type"})
        after["simulators"]["devices_available"]["devices"]["runtime"][0]["state"] = "Shutdown"
        self.assertEqual([], compare.semantic_changes(before, after))

    def test_detects_sdk_build_only_change(self):
        after = manifest()
        after["sdks"]["iphoneos"]["build"] = "23A2"
        self.assertEqual(
            [{"label": "iphoneos SDK build", "before": "23A1", "after": "23A2"}],
            compare.semantic_changes(manifest(), after),
        )

    def test_detects_runtime_add_remove_and_availability(self):
        before, after = manifest(), manifest()
        runtime_list = after["simulators"]["runtimes"]["runtimes"]
        runtime_list[0]["isAvailable"] = False
        runtime_list.append({"identifier": "com.apple.CoreSimulator.SimRuntime.iOS-27-0", "version": "27.0", "buildversion": "24A1", "isAvailable": True})
        changes = compare.semantic_changes(before, after)
        self.assertEqual(2, len(changes))
        self.assertIn("available", changes[0]["before"])
        self.assertIn("unavailable", changes[0]["after"])
        self.assertEqual("absent", changes[1]["before"])

    def test_detects_runtime_removal_and_toolchain_changes(self):
        before, after = manifest(), manifest()
        after["simulators"]["runtimes"]["runtimes"] = []
        after["swift"]["swift_version"]["version"] = "6.3"
        changes = compare.semantic_changes(before, after)
        self.assertEqual(2, len(changes))
        self.assertTrue(any(change["label"].startswith("Simulator runtime removed") for change in changes))
        self.assertTrue(any(change["label"] == "Swift" for change in changes))

    def test_supports_legacy_sdk_strings(self):
        before, after = manifest(), manifest()
        before["sdks"]["macosx"] = "26.0"
        after["sdks"]["macosx"] = "26.1"
        changes = compare.semantic_changes(before, after)
        macos_sdk = next(change for change in changes if change["label"] == "macosx SDK version")
        self.assertEqual("26.1", macos_sdk["after"])

    def test_first_baseline_has_no_change(self):
        changed, changes = compare.compare_manifests(False, {}, manifest())
        self.assertFalse(changed)
        self.assertEqual([], changes)

    def test_newly_parsed_swift_and_sdk_build_values_seed_without_alert(self):
        before, after = manifest(), manifest()
        before["swift"]["swift_version"]["version"] = None
        before["sdks"]["iphoneos"]["build"] = None
        after["swift"]["swift_version"]["version"] = "6.2 (swiftlang-abc)"
        self.assertEqual([], compare.semantic_changes(before, after))

    def test_invalid_capture_refuses_to_report_all_runtimes_removed(self):
        broken = manifest()
        del broken["simulators"]["runtimes"]["runtimes"]
        with self.assertRaisesRegex(ValueError, "refusing to report removals"):
            compare.validate_manifest(broken, "incoming")

    def test_release_key_is_stable_for_retry_and_new_for_rollback_base(self):
        current = manifest()
        self.assertEqual(compare.release_tag("a" * 40, current), compare.release_tag("a" * 40, copy.deepcopy(current)))
        self.assertNotEqual(compare.release_tag("a" * 40, current), compare.release_tag("b" * 40, current))

    def test_rollback_to_prior_sdk_state_has_a_distinct_release_key(self):
        original = manifest()
        updated = copy.deepcopy(original)
        updated["sdks"]["iphoneos"]["build"] = "23A2"
        self.assertTrue(compare.compare_manifests(True, original, updated)[0])
        self.assertTrue(compare.compare_manifests(True, updated, original)[0])
        forward = compare.release_tag("a" * 40, updated)
        rollback = compare.release_tag("b" * 40, original)
        self.assertNotEqual(forward, rollback)

    def test_release_notes_include_old_new_values_and_run_evidence(self):
        notes = compare.release_notes([{"label": "Swift", "before": "6.2", "after": "6.3"}], "https://github.com/example/run/1")
        self.assertIn("`6.2` → `6.3`", notes)
        self.assertIn("https://github.com/example/run/1", notes)

    def test_parses_apple_swift_version_output(self):
        result = capture_swift_version("Apple Swift version 6.2 (swiftlang-abc)\nTarget: arm64-apple-macosx26.0")
        self.assertEqual("6.2 (swiftlang-abc)", result["version"])
        self.assertEqual("arm64-apple-macosx26.0", result["target"])


if __name__ == "__main__":
    unittest.main()
