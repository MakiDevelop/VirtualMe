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

public_question_pool='src/virtualme/data/question-pool.yaml'
if [[ ! -f "$public_question_pool" ]]; then
  printf 'Moat hygiene violation: packaged toy question pool is missing\n' >&2
  failed=1
else
  line_count="$(wc -l < "$public_question_pool" | tr -d '[:space:]')"
  if [[ "$line_count" -gt 80 ]]; then
    printf 'Moat hygiene violation: packaged question pool has %s lines (maximum 80)\n' \
      "$line_count" >&2
    failed=1
  fi

  # Structural allowlist: do not encode private question text or other moat fingerprints here.
  toy_question_count="$(
    grep -Ec '^[[:space:]]*-[[:space:]]+id:[[:space:]]+TOY-[0-9]{2}[[:space:]]*$' \
      "$public_question_pool" || true
  )"
  if [[ "$toy_question_count" -ne 8 ]]; then
    printf 'Moat hygiene violation: packaged pool must contain exactly 8 TOY-* questions\n' >&2
    failed=1
  fi
  if grep -E '^[[:space:]]*-[[:space:]]+id:' "$public_question_pool" \
    | grep -Ev '^[[:space:]]*-[[:space:]]+id:[[:space:]]+TOY-[0-9]{2}[[:space:]]*$' \
      >/dev/null; then
    printf 'Moat hygiene violation: packaged pool contains a non-TOY question id\n' >&2
    failed=1
  fi
  if grep -Eq '^[[:space:]]*(default_placeholders|rationale_probe):' "$public_question_pool"; then
    printf 'Moat hygiene violation: packaged pool contains private-pack schema features\n' >&2
    failed=1
  fi
fi

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi

printf 'Moat hygiene check passed.\n'
