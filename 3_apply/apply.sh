#!/usr/bin/env bash
#
# apply.sh — push 2_configure (cao.config.toml + prompts/) into the live CAO.
# Run after editing 2_configure/cao.config.toml or any prompts/*.md.
#
# Steps:
#   1. Render cao.config.toml -> settings.json, opencode.json, worker frontmatter.
#   2. Copy 2_configure/prompts/*.md into ~/.aws/cli-agent-orchestrator/agent_store/.
#   3. Re-register every profile with `cao install`.
#   4. Offer to restart cao-server so changes take effect.
#
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # 3_apply/
REPO="$(cd "$HERE/.." && pwd)"                          # repo root
CONFIGURE="$REPO/2_configure"
log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

# Pick a Python with tomllib (3.11+). Prefer the CAO uv-tool venv python (3.14).
CAO_PY="$HOME/.local/share/uv/tools/cli-agent-orchestrator/bin/python"
if [ -x "$CAO_PY" ] && "$CAO_PY" -c 'import tomllib' 2>/dev/null; then
  PY="$CAO_PY"
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import tomllib' 2>/dev/null; then
  PY="python3"
else
  warn "No Python with tomllib (3.11+) found. Install CAO first (bootstrap.sh)."
  exit 1
fi

log "Rendering config with $PY..."
"$PY" "$HERE/render_config.py"

log "Copying agent profiles to live store..."
STORE="$HOME/.aws/cli-agent-orchestrator/agent_store"
mkdir -p "$STORE"
cp "$CONFIGURE"/prompts/*.md "$STORE/"
ok "profiles copied"

log "Re-registering profiles..."
# Read the register list from the toml via the same Python.
PROFILES="$("$PY" - "$CONFIGURE/cao.config.toml" <<'PYEOF'
import sys, tomllib
with open(sys.argv[1], "rb") as f: c = tomllib.load(f)
print(" ".join(c.get("profiles", {}).get("register", [])))
PYEOF
)"
for p in $PROFILES; do
  cao install "$STORE/$p.md" >/dev/null 2>&1 && ok "registered $p" || warn "failed: $p"
done

# Offer server restart so opencode.json / settings changes are picked up.
if nc -z 127.0.0.1 9889 >/dev/null 2>&1; then
  printf '\n'
  read -r -p "cao-server is running. Restart it to apply changes? [y/N] " ans
  case "${ans:-N}" in
    y|Y)
      log "Restarting cao-server..."
      pkill -f cao-server 2>/dev/null || true
      # Reload LOCAL_API_KEY from the canonical env file.
      for ENV_FILE in "$HOME/.config/cao/cao.env" "$REPO/.env"; do
        [ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; break; }
      done
      mkdir -p "$HOME/.cao/logs"
      LOCAL_API_KEY="${LOCAL_API_KEY:-}" nohup cao-server > "$HOME/.cao/logs/server.log" 2>&1 &
      for _ in $(seq 1 10); do nc -z 127.0.0.1 9889 >/dev/null 2>&1 && break; sleep 0.5; done
      command -v tmux >/dev/null 2>&1 && [ -n "${LOCAL_API_KEY:-}" ] && \
        tmux setenv -g LOCAL_API_KEY "$LOCAL_API_KEY" 2>/dev/null || true
      nc -z 127.0.0.1 9889 >/dev/null 2>&1 && ok "cao-server restarted" || warn "restart failed — check log"
      ;;
    *) warn "Not restarting. Changes apply on next cao-run (or restart manually)." ;;
  esac
else
  ok "cao-server not running — changes apply on next cao-run."
fi

echo
ok "apply done."
