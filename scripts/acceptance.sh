#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
acceptance_url="${1:-http://localhost:8000}"
curl --fail --silent "$acceptance_url/api/config" | .venv/bin/python -c '
import json,sys
c=json.load(sys.stdin)
if c["mode"]=="mock" or c["missing"]:
    sys.exit("Acceptance blocked: real providers must be configured. Mock mode cannot pass.")
print("Configured provider hosts:", c["providers"])
print("Readiness does not establish actual account access or model support.")
'
cat docs/mvp-acceptance.md
printf '\nOpen %s and perform each checklist step using approved PowerPoint and live VCF Automation content.\n' "$acceptance_url"
for step in \
  'One named infrastructure architect configured' \
  'Natural spoken introduction and recognized speech' \
  'Question grounded in actual visible PowerPoint diagram' \
  'Changed live demo recognized with a grounded question' \
  'Earlier slide recalled accurately' \
  'Spoken and button interruptions stop stale audio' \
  'Native share stop, mute and output controls work' \
  'Ten-minute session and useful final transcript/summary' \
  'Timing and failures recorded from actual run'; do
  printf '\n%s. Type PASS or a failure description: ' "$step"
  IFS= read -r acceptance_result
  printf 'Result: %s\n' "$acceptance_result"
  if [[ "$acceptance_result" != PASS ]]; then
    printf 'Acceptance failed or incomplete at this step.\n'
    exit 1
  fi
done
printf '\nManual acceptance reported passed. Preserve the actual evidence and provider versions in docs/mvp-acceptance.md.\n'
