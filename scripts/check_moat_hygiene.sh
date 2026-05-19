#!/usr/bin/env bash
set -euo pipefail

blocked_patterns=(
  '(^|/)bait_reaction\.py$'
  '(^|/)test_bait_reaction\.py$'
  '(^|/)question-pool-v2\.yaml$'
  '(^|/)domain-packs-v2\.yaml$'
  '(^|/)v2_loader\.py$'
  '(^|/)v2_schema\.py$'
  '(^|/)TRUNK\.md$'
  '(^|/)virtualme-domain-pack-8-fields\.md$'
  '(^|/)GEMINI\.md$'
  '(^|/)docs/design/'
  '(^|/)exports/'
  '(^|/)artifacts/'
  '(^|/)transcripts/'
  '(^|/)\.private/'
)

tracked="$(git ls-files)"
failed=0

for pattern in "${blocked_patterns[@]}"; do
  if printf '%s\n' "$tracked" | grep -E "$pattern" >/dev/null; then
    printf 'Moat hygiene violation: tracked file matches %s\n' "$pattern" >&2
    printf '%s\n' "$tracked" | grep -E "$pattern" >&2
    failed=1
  fi
done

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi

printf 'Moat hygiene check passed.\n'
