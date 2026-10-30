# Manifest schema

`latest/macos-latest.json` is a deterministic JSON document with this top-level shape:

The manifest tracks the selected macOS runner toolchain, Apple SDKs, and installed simulator runtimes. Simulator device inventories remain available for diagnostics, but device churn does not trigger a release.

| Field | Type | Description |
| --- | --- | --- |
| `manifest_version` | integer | Schema version for the document format. |
| `observed_at` | string | UTC timestamp in RFC 3339 format for when the manifest was captured. |
| `runner_label` | string | Workflow runner label used for capture, for example `macos-latest`. |
| `system` | object | Host macOS metadata and `uname -srvm` output. |
| `xcode` | object | Selected Xcode path and `xcodebuild -version` output. |
| `swift` | object | `swift --version` output and parsed fields when available. |
| `sdks` | object | Version and build values for `iphoneos`, `iphonesimulator`, and `macosx`. |
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
| `selected_path` | string | `xcode-select -p` (diagnostic only; ignored for change alerts) |
| `xcodebuild_version` | object | Parsed and raw output of `xcodebuild -version` |

`xcodebuild_version` contains `raw`, `xcode`, and `build`.

## `swift`

| Field | Type | Description |
| --- | --- | --- |
| `swift_version` | object | Parsed and raw output of `swift --version` |

`swift_version` contains `raw`, `version`, and `target`. The parser accepts both `Apple Swift version ...` and `Swift version ...` output.

## `sdks`

Each SDK entry is an object with a `version` string from `xcrun --show-sdk-version` and a `build` value from `ProductBuildVersion` in that SDK's `SDKSettings.plist` (nullable if the setting is absent).

Manifest version 2 stores SDK entries as objects. The change detector continues to read version 1 manifests, which stored SDK entries as strings.

## Simulator runtimes

The release comparison uses each runtime's identifier, version, build version, and availability. It ignores `lastUsage`, bundle paths, devices, and device types. Runtime additions, removals, version/build updates, and availability changes are reported.

## Change comparison and notifications

The publisher compares only the fields listed above for alerts. It ignores `observed_at`, selected Xcode paths, host `uname`, device UUID/state changes, and simulator device-type inventory churn. The initial baseline is committed without a release. Unchanged captures are silent.

A change release is created before the latest manifest commit. Its tag includes the current baseline commit and incoming semantic snapshot hash, so a retry of an interrupted publication reuses the same release while a later rollback from a new baseline gets a new tag. GitHub Release notifications require the user to enable Releases in repository watch/custom notification settings.

The separate `latest/last-successful-health.txt` timestamp is excluded from the manifest and comparison. It is updated no more often than every 28 days after a successful check. This may help with scheduled-workflow inactivity, but GitHub does not guarantee that a bot commit resets the inactivity timer. Check the Actions page and re-enable the schedule if GitHub disables it.
