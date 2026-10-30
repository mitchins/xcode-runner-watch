# xcode-runner-watch

`xcode-runner-watch` publishes a stable JSON snapshot of the current `macos-latest` GitHub Actions Xcode and simulator environment.

The repository is meant for app and SDK teams that want an auditable baseline for:

- selected Xcode
- Swift toolchain version
- Apple SDK versions and SDK build IDs
- installed simulator runtimes, versions, builds, and availability

After the first successful run, the latest manifest is published at:

`https://raw.githubusercontent.com/mitchins/xcode-runner-watch/main/latest/macos-latest.json`

## Published manifest

The manifest includes:

- `runner_label`
- `observed_at`
- macOS product and build version plus `uname`
- selected Xcode path and `xcodebuild -version`
- `swift --version`
- SDK versions and build IDs for `iphoneos`, `iphonesimulator`, and `macosx`
- `simctl` JSON for runtimes, device types, and available devices

The JSON is rendered deterministically. `observed_at` is included for traceability, but repository updates only happen when meaningful environment data changes, except for a separate monthly successful-check timestamp.

The change alert focuses on selected Xcode and Swift, macOS version/build, SDK version/build, and simulator runtime identifier/version/build/availability. It ignores temporary Xcode paths, host `uname`, device UUID/state churn, device-type inventory changes, runtime paths, and observation timestamps.

## Change notifications

The publisher creates a GitHub Release only when a meaningful change is detected after a baseline exists. Release notes list each added, removed, or changed value with before/after values and link to the successful capture run. The first baseline and unchanged runs do not create releases. The release is published before the manifest commit; retry-safe tags let a later run finish a failed commit without creating a duplicate release. A later transition back to an earlier SDK/runtime state uses a new baseline commit in its tag and creates a new release.

To receive these alerts through GitHub, enable **Releases** in this repository's watch/custom notification settings. This repository does not configure your personal notification subscriptions. Workflow failures continue to use GitHub Actions failure notifications.

The publisher also records `latest/last-successful-health.txt` at most once every 28 days. This is an inactivity-retention mitigation, not a guarantee: GitHub does not promise that a bot commit resets scheduled-workflow inactivity. If the schedule is disabled, re-enable it on the Actions workflow page.

## Repository automation

The publisher workflow lives at [`.github/workflows/publish-macos-latest.yml`](.github/workflows/publish-macos-latest.yml).

It:

1. runs nightly and on `workflow_dispatch`
2. captures the runner state with [`scripts/capture-xcode-runner-manifest.sh`](scripts/capture-xcode-runner-manifest.sh)
3. compares normalized toolchain, SDK, and runtime values with [`scripts/compare_xcode_runner_manifest.py`](scripts/compare_xcode_runner_manifest.py)
4. publishes a release for meaningful changes, then commits the manifest
5. records a separate monthly health timestamp

Pull requests run the manifest comparison unit tests via [`.github/workflows/test.yml`](.github/workflows/test.yml).

## Downstream usage

### 1. Seed a baseline in your app repository

```bash
mkdir -p .ci
curl -fsSL \
  https://raw.githubusercontent.com/mitchins/xcode-runner-watch/main/latest/macos-latest.json \
  -o .ci/xcode-runner-baseline.json
```

### 2. Copy the freshness checker

```bash
mkdir -p scripts
curl -fsSL \
  https://raw.githubusercontent.com/mitchins/xcode-runner-watch/main/examples/check-xcode-runner-freshness.sh \
  -o scripts/check-xcode-runner-freshness.sh
chmod +x scripts/check-xcode-runner-freshness.sh
```

Then run:

```bash
scripts/check-xcode-runner-freshness.sh \
  https://raw.githubusercontent.com/mitchins/xcode-runner-watch/main/latest/macos-latest.json \
  .ci/xcode-runner-baseline.json
```

Exit codes:

- `0`: unchanged
- `10`: changed

### 3. Copy the example downstream workflow

```bash
mkdir -p .github/workflows
curl -fsSL \
  https://raw.githubusercontent.com/mitchins/xcode-runner-watch/main/examples/downstream-sdk-watch.yml \
  -o .github/workflows/downstream-sdk-watch.yml
```

The example workflow:

- runs on `ubuntu-latest`
- downloads the published manifest
- updates `.ci/xcode-runner-baseline.json` when the manifest meaningfully changes
- opens or updates a pull request with `gh` and `GITHUB_TOKEN`

Set `MANIFEST_URL` in that workflow if you want to point at a fork or another branch.
