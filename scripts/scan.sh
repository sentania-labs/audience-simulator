#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
git ls-files -z --cached --others --exclude-standard | tar --null -T - -cf - | tar -xf - -C "$scratch"
gitleaks dir "$scratch" --redact --no-banner --verbose
actionlint
