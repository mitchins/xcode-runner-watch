# Manifest schema

`latest/macos-latest.json` is a deterministic JSON document with this top-level shape:

The initial schema keeps scope narrow on purpose: it tracks the macOS runner plus the iPhone simulator/runtime environment. That keeps the published manifest useful for the common iOS/macOS build path without widening churn to every Apple platform on day one.

| Field | Type | Description |
| --- | --- | --- |
| `manifest_version` | integer | Schema version for the document format. |
| `observed_at` | string | UTC timestamp in RFC 3339 format for when the manifest was captured. |
| `runner_label` | string | Workflow runner label used for capture, for example `macos-latest`. |
| `system` | object | Host macOS metadata and `uname -srvm` output. |
| `xcode` | object | Selected Xcode path and `xcodebuild -version` output. |
| `swift` | object | `swift --version` output and parsed fields when available. |
| `sdks` | object | Version strings for `iphoneos`, `iphonesimulator`, and `macosx`. |
| `simulators` | object | Raw `simctl` JSON for runtimes, device types, and available devices. |

## `system`

| Field | Type | Description |
| --- | --- | --- |
| `product_name` | string | `sw_vers -productName` |
| `product_version` | string | `sw_vers -productVersion` |
| `build_version` | string | `sw_vers -buildVersion` |
| `uname` | string | `uname -srvm` |

## `xcode`

| Field | Type | Description |
| --- | --- | --- |
| `selected_path` | string | `xcode-select -p` |
| `xcodebuild_version` | object | Parsed and raw output of `xcodebuild -version` |

`xcodebuild_version` contains:

- `raw`
- `xcode`
- `build`

## `swift`

| Field | Type | Description |
| --- | --- | --- |
| `swift_version` | object | Parsed and raw output of `swift --version` |

`swift_version` contains:

- `raw`
- `version`
- `target`

## `sdks`

| Field | Type | Description |
| --- | --- | --- |
| `iphoneos` | string | `xcrun --sdk iphoneos --show-sdk-version` |
| `iphonesimulator` | string | `xcrun --sdk iphonesimulator --show-sdk-version` |
| `macosx` | string | `xcrun --sdk macosx --show-sdk-version` |

## `simulators`

| Field | Type | Description |
| --- | --- | --- |
| `runtimes` | object | `xcrun simctl list runtimes --json` |
| `device_types` | object | `xcrun simctl list devicetypes --json` |
| `devices_available` | object | Stable projection of `xcrun simctl list devices available --json` |

## Change comparison

`observed_at` is intentionally excluded from change detection.

That means:

- the publisher workflow only commits when the environment itself changes
- downstream repositories can compare manifests semantically without daily churn from timestamps alone
