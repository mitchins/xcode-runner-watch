#!/usr/bin/env bash
# Publish one allowlisted document through a normal, exact-head squash merge.
set -euo pipefail
kind="${1:?manifest or health required}"
case "$kind" in
  manifest) path="latest/macos-latest.json"; branch="bot/macos-latest-manifest" ;;
  health) path="latest/last-successful-health.txt"; branch="bot/macos-latest-health" ;;
  *) echo 'Unsupported publication kind' >&2; exit 64 ;;
esac

git add -- "$path"
if git diff --cached --quiet -- "$path"; then
  exit 0
fi
# Never fold another document into this PR, even if a caller staged it.
if [[ "$(git diff --cached --name-only)" != "$path" ]]; then
  echo 'Unexpected staged paths' >&2
  exit 1
fi
# Refresh main between manifest and health publication, including after squash.
git fetch origin main
git checkout -B "$branch" origin/main
base="$(git rev-parse HEAD)"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "Update macos-latest $kind"
head="$(git rev-parse HEAD)"
python3 scripts/validate_manifest_publication.py "$path" --kind "$kind"
gh auth setup-git
git push --force-with-lease origin "HEAD:refs/heads/$branch"
pr="$(gh pr list --repo "$GITHUB_REPOSITORY" --base main --head "$branch" --state open --json number --jq '.[0].number // empty')"
if [[ -z "$pr" ]]; then
  pr="$(gh pr create --repo "$GITHUB_REPOSITORY" --base main --head "$branch" \
    --title "Update macos-latest $kind" --body "Automated runner $kind publication. Only $path may change.")"
  pr="${pr##*/}"
fi
python3 scripts/validate_manifest_publication.py "$path" "$pr" "$head" --kind "$kind" --base "$base"
gh api --method PUT "repos/$GITHUB_REPOSITORY/pulls/$pr/merge" \
  -f sha="$head" -f merge_method=squash --jq 'if .merged then .sha else error(.message) end'
