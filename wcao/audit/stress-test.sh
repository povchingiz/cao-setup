#!/usr/bin/env bash
# Auto-generated stress-test harness for cao-setup
set -u

export ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
echo "=== Starting Aggressive Stress Test on $(basename "$ROOT") ==="
passed=0; failed=0

test_assert() {
  local desc="$1"; shift
  echo -n "[TEST] $desc... "
  if "$@" >/dev/null 2>&1; then
    echo "PASS"; passed=$((passed+1))
  else
    echo "FAIL"; failed=$((failed+1))
  fi
}

echo "Phase 1: Input fuzzing & boundary flags..."
for cmd in cao-doctor cao-tokens cao-limits cao-monitor cao-aggressive cao-plan cao-memory; do
  if command -v "$cmd" >/dev/null 2>&1; then
    test_assert "$cmd rejects unknown flags gracefully" bash -c "! $cmd --invalid-fuzz-flag-test-xyz"
    test_assert "$cmd responds to --help cleanly" $cmd --help
  fi
done

echo "Phase 2: Concurrency burst (5 parallel invocations)..."
if command -v cao-limits >/dev/null 2>&1; then
  test_assert "Concurrent cao-limits --json execution" bash -c '
    for i in {1..5}; do cao-limits --json >/dev/null & done; wait
  '
fi
if command -v cao-tokens >/dev/null 2>&1; then
  test_assert "Concurrent cao-tokens --since 7d execution" bash -c '
    for i in {1..5}; do cao-tokens --since 7d >/dev/null & done; wait
  '
fi

echo "Phase 3: Python syntax & compilation stress..."
test_assert "AST compilation of all python files in repo" bash -c '
  find "$ROOT" -name "*.py" -not -path "*/.*" -exec python3 -m py_compile {} +
'

echo "=================================================="
echo "Stress Test Complete: $passed passed, $failed failed."
if [ "$failed" -gt 0 ]; then exit 1; else exit 0; fi

