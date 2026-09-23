#!/usr/bin/env bash
# Deterministic verification gate for wcao.
# Exit 0 = pass. Non-zero = agent must stay in the fix loop.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

fail=0

# ruff: advisory only. The repo carries ~196 pre-existing lint errors, so a
# hard gate here would block every task on unrelated legacy debt.
# Blocks once that backlog is cleared - flip `|| true` to `|| fail=1`.
echo "=== ruff (advisory) ==="
uv run --with ruff ruff check . --statistics || true

# pytest: hard gate.
echo "=== pytest ==="
uv run --with pytest pytest tests/ -q || fail=1

if [ "$fail" -ne 0 ]; then
  echo "VERIFICATION FAILED - task is not complete. Fix the errors above."
  exit 1
fi

echo "VERIFICATION PASSED"
