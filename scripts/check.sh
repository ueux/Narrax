#!/usr/bin/env bash
# Run every NarraX quality gate and exit non-zero if any fails.
# The production build (`pnpm build`) is excluded because it is slow; run it separately.
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend="$root/backend"
frontend="$root/frontend"

failures=0

gate() {
  local label="$1" dir="$2"
  shift 2
  printf '==> %s\n' "$label"
  if (cd "$dir" && "$@"); then
    printf '    ok\n'
  else
    printf '    FAILED\n' >&2
    failures=$((failures + 1))
  fi
}

py=""
for candidate in "$backend/.venv/bin/python" "$backend/.venv/Scripts/python.exe"; do
  if [[ -x "$candidate" ]]; then py="$candidate"; break; fi
done
if [[ -z "$py" ]]; then
  echo "Backend virtualenv not found. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

gate 'backend: ruff lint'   "$backend" "$py" -m ruff check .
gate 'backend: ruff format' "$backend" "$py" -m ruff format --check .
gate 'backend: mypy'        "$backend" "$py" -m mypy app
gate 'backend: pytest'      "$backend" "$py" -m pytest

gate 'frontend: typecheck'  "$frontend" pnpm typecheck
gate 'frontend: lint'       "$frontend" pnpm lint

if (( failures > 0 )); then
  printf '\n%d gate(s) failed.\n' "$failures" >&2
  exit 1
fi
printf '\nAll gates passed.\n'
