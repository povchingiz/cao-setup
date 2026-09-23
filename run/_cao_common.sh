#!/usr/bin/env bash
# Shared helpers for the cao-* scripts. Source, don't execute:
#
#   . "$(dirname "$SELF")/_cao_common.sh"
#
# Everything here must work under `set -euo pipefail`.

# cao_resolve_self <path>
# Resolve a script path through any chain of symlinks and print the directory
# it really lives in. Lets cao-* find their siblings (and the repo) when they
# are invoked via a symlink in ~/.local/bin.
cao_resolve_self() {
  local self="$1"
  while [ -L "$self" ]; do
    local link
    link="$(readlink "$self")"
    case "$link" in
      /*) self="$link" ;;
      *)  self="$(cd "$(dirname "$self")" && pwd)/$link" ;;
    esac
  done
  cd "$(dirname "$self")" && pwd
}

# cao_load_env [run_dir]
# Load the first env file that actually defines LOCAL_API_KEY, and export
# everything it sets. Sets CAO_ENV_SOURCE to the file that supplied the key
# (or leaves it empty). Never prints the value.
#
# Search order - explicit override first, then repo-relative, then the shell's
# cwd, then the machine-wide config. Deliberately NOT a list of hardcoded home
# directories: the repo may be checked out anywhere, under any name.
cao_load_env() {
  local run_dir="${1:-}"
  local candidates=()

  [ -n "${CAO_ENV_FILE:-}" ] && candidates+=("$CAO_ENV_FILE")
  [ -n "$run_dir" ] && candidates+=("$run_dir/../.env")
  candidates+=("$PWD/.env" "$HOME/.config/cao/cao.env")

  CAO_ENV_SOURCE=""
  local f
  for f in "${candidates[@]}"; do
    [ -f "$f" ] || continue
    set -a
    # shellcheck disable=SC1090
    . "$f" 2>/dev/null || true
    set +a
    # Keep going until the key is actually present: an earlier file may exist
    # but define only unrelated settings.
    if [ -n "${LOCAL_API_KEY:-}" ]; then
      CAO_ENV_SOURCE="$f"
      break
    fi
  done
  export CAO_ENV_SOURCE
}

# cao_server_port [run_dir]
# Echo the configured orchestrator port, preferring cao.config.local.toml over
# the tracked cao.config.toml. Falls back to 9889.
cao_server_port() {
  local run_dir="${1:-}"
  local port=""
  if [ -n "${CAO_SERVER_PORT:-}" ]; then
    echo "$CAO_SERVER_PORT"
    return 0
  fi
  local cfg="$run_dir/../2_configure/cao.config.local.toml"
  [ -f "$cfg" ] || cfg="$run_dir/../2_configure/cao.config.toml"
  if [ -f "$cfg" ]; then
    port="$(python3 -c "
import sys, tomllib
try:
    cfg = tomllib.load(open(sys.argv[1], 'rb'))
    print(cfg.get('orchestrator', {}).get('server_port', 9889))
except Exception:
    print(9889)
" "$cfg" 2>/dev/null)" || port=""
  fi
  echo "${port:-9889}"
}
