#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

git switch main
git pull

git branch -D download-safe 2>/dev/null || true
git switch -c download-safe

git ls-files -z -- '*.py' '*.toml' '*.spec' |
while IFS= read -r -d '' f; do
    git mv -- "$f" "$f.txt"
done

git commit -m "Generate download-safe branch"
git push -u origin download-safe --force

git switch main
