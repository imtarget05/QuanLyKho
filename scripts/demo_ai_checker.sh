#!/usr/bin/env bash
# Reproduce the advisory-AI → human-checker demo on a disposable local PostgreSQL.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="$repo_dir/backend/.venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  echo "Missing backend/.venv/bin/python. Run: cd backend && poetry install --with dev" >&2
  exit 2
fi
for command in initdb pg_ctl createdb; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing $command (local PostgreSQL is required)." >&2
    exit 2
  fi
done

pg_dir="$(mktemp -d /tmp/quanlykho-ai-checker.XXXXXX)"
pg_port="$("$python_bin" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
cleanup() {
  pg_ctl -D "$pg_dir" -m immediate stop >/dev/null 2>&1 || true
  "$python_bin" - "$pg_dir" <<'PY'
from pathlib import Path
import shutil
import sys

path = Path(sys.argv[1]).resolve()
if path.parent != Path('/tmp').resolve() or not path.name.startswith('quanlykho-ai-checker.'):
    raise SystemExit('Refusing to remove an unexpected PostgreSQL data directory')
shutil.rmtree(path)
PY
}
trap cleanup EXIT

initdb -D "$pg_dir" -A trust --no-instructions >/dev/null
pg_ctl -D "$pg_dir" -o "-h 127.0.0.1 -p $pg_port" -l "$pg_dir/postgres.log" start >/dev/null
createdb -h 127.0.0.1 -p "$pg_port" bankops_test
export DATABASE_URL="postgresql+psycopg2://127.0.0.1:$pg_port/bankops_test"
export APP_ENV=demo
export DEMO_MODE=true

cd "$repo_dir/backend"
"$python_bin" -m alembic upgrade head
"$python_bin" -m app.seed
"$python_bin" -m pytest tests/test_portfolio_ai_checker_demo.py -q --disable-warnings
