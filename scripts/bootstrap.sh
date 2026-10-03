#!/usr/bin/env bash
# Bootstrap a fresh NarraX checkout: database, backend, frontend.
# Idempotent - safe to re-run. Requires: python3, docker, pnpm.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend="$root/backend"
frontend="$root/frontend"

step() { printf '\n==> %s\n' "$1"; }

step 'Checking prerequisites'
python_cmd=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then python_cmd="$candidate"; break; fi
done
[[ -n "$python_cmd" ]] || { echo "python3 not found on PATH" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "docker not found on PATH" >&2; exit 1; }

step 'Starting PostgreSQL + pgvector (docker compose)'
(cd "$root" && docker compose up -d)

step 'Backend: virtual environment'
cd "$backend"
[[ -d .venv ]] || "$python_cmd" -m venv .venv
py="$backend/.venv/bin/python"
[[ -x "$py" ]] || { echo "virtualenv interpreter not found" >&2; exit 1; }

step 'Backend: installing dependencies (editable + dev + db-test extras)'
"$py" -m pip install --upgrade pip
"$py" -m pip install -e '.[dev,db-test]'

if [[ -f .env ]]; then
  echo "    backend/.env already exists - left unchanged"
else
  cp "$root/.env.example" .env
  echo "    created backend/.env from .env.example (review the values)"
fi

step 'Backend: applying migrations'
"$py" -m alembic upgrade head

step 'Frontend: pnpm install'
command -v pnpm >/dev/null 2>&1 || { echo "pnpm not found on PATH" >&2; exit 1; }
(cd "$frontend" && pnpm install)

printf '\nBootstrap complete.\n'
printf 'Next steps:\n'
printf '  ./scripts/check.sh                                               # quality gates\n'
printf '  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload\n'
printf '  cd frontend && pnpm dev\n'
printf '  Open http://localhost:8000/docs and http://localhost:3000\n'
