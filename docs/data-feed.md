# JSON feed and freshness

The committed manifest is the canonical data source for this page and for downstream consumers.

## Current feed

The mutable `main` endpoint is:

```text
https://raw.githubusercontent.com/mitchins/xcode-runner-watch/main/latest/macos-latest.json
```

This repository path was checked on GitHub. The page reads the same URL directly; there is no second copy or backend. The endpoint may be briefly cached by the browser or GitHub's raw-content delivery. Use a commit-pinned URL when a build must be reproducible:

```text
https://raw.githubusercontent.com/mitchins/xcode-runner-watch/<commit-sha>/latest/macos-latest.json
```

Replace `<commit-sha>` with the commit that contains the snapshot you want. A commit URL is immutable, while the `main` URL follows the latest manifest update.

## What the timestamps mean

`observed_at` is when the data in that manifest was captured. The publisher commits a new manifest only when tracked environment values change or when a quiet schema/data migration refreshes older fields. Therefore this timestamp can remain old across successful unchanged nightly checks.

The page separately queries the public GitHub Actions run history and labels the newest successful scheduled run on `main` as the **latest successful scheduled check**. If that API query fails, the page says check status is unavailable; it does not substitute `observed_at` or the monthly health timestamp.

`latest/last-successful-health.txt` is only a monthly inactivity-retention mitigation. It is not a nightly check record and does not establish how fresh the runner snapshot is. GitHub does not guarantee that such a commit resets scheduled-workflow inactivity.

## History

Meaningful changes are published as GitHub Releases with old and new values and a link to the successful capture run. The page reads those releases for its history section, so it does not maintain a duplicate event log. Failed or retried release publication reuses the same tag for the same persisted manifest baseline; genuine reversions start from a new manifest revision and retain a distinct release entry.
