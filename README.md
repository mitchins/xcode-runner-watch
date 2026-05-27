# xcode-runner-watch

`xcode-runner-watch` publishes a stable JSON snapshot of the current `macos-latest` GitHub Actions Xcode and simulator environment.

The repository is meant for app and SDK teams that want an auditable baseline for:

- selected Xcode
- Swift toolchain version
- Apple SDK versions
- simulator runtimes, device types, and available devices

After the first successful run, the latest manifest is published at:

`https://raw.githubusercontent.com/mitchins/xcode-runner-watch/main/latest/macos-latest.json`

## Published manifest

The manifest includes:

- `runner_label`
- `observed_at`
- macOS product and build version plus `uname`
- selected Xcode path and `xcodebuild -version`
- `swift --version`
- SDK versions for `iphoneos`, `iphonesimulator`, and `macosx`
- `simctl` JSON for runtimes, device types, and available devices

The JSON is rendered deterministically. `observed_at` is included for traceability, but repository updates only happen when the meaningful environment data changes.

See [`docs/manifest-schema.md`](docs/manifest-schema.md) for the field-level schema.

## Repository automation

The publisher workflow lives at [`.github/workflows/publish-macos-latest.yml`](.github/workflows/publish-macos-latest.yml).

It:

1. runs nightly and on `workflow_dispatch`
2. captures the runner state with [`scripts/capture-xcode-runner-manifest.sh`](scripts/capture-xcode-runner-manifest.sh)
3. compares the new manifest with the committed one while ignoring `observed_at`
4. commits `latest/macos-latest.json` only when a meaningful change is detected

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