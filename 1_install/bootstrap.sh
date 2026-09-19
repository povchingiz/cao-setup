#!/usr/bin/env bash
#
# CAO bootstrap — provision the cli-agent-orchestrator multi-agent setup on a
# fresh macOS or Ubuntu/Linux machine. Idempotent: safe to re-run.
#
# What it does:
#   1. Ensures prerequisites (node/npm, uv, tmux, python3).
#   2. Installs CAO (cli-agent-orchestrator) from git via uv.
#   3. Installs worker CLIs via npm (claude, codex, opencode) + agy (Antigravity).
#   4. Copies agent profiles + configs into place and registers them.
#   5. Patches pyte (Antigravity ANSI crash fix).
#   6. Skips Antigravity onboarding; neutralizes codex startup hooks.
#   7. Optionally installs the dev-kodeks Claude Code rules layer.
#   8. Prints the remaining INTERACTIVE steps (logins) you must do by hand.
#
# Usage:
#   cp .env.example .env         # fill LOCAL_API_KEY
#   ./bootstrap.sh               # base setup
#   ./bootstrap.sh --inherit-mcp # also copy your ~/.claude.json MCP into workers
#   ./bootstrap.sh --with-kodeks # also install dev-kodeks (rules + skills)
#   ./bootstrap.sh --with-kodeks --with-guard-hook  # also activate guard-env hook
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"   # repo root (this script lives in 1_install/)
CONFIGURE="$REPO/2_configure"
APPLY="$REPO/3_apply"
WITH_KODEKS=0
WITH_GUARD_HOOK=0
INHERIT_MCP=0
for a in "$@"; do
  case "$a" in
    --with-kodeks)     WITH_KODEKS=1 ;;
    --with-guard-hook) WITH_GUARD_HOOK=1; WITH_KODEKS=1 ;;
    --inherit-mcp)     INHERIT_MCP=1 ;;
    *) echo "unknown flag: $a" >&2; exit 1 ;;
  esac
done

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }

# --- platform detection ------------------------------------------------------
OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="mac" ;;
  Linux)  PLATFORM="linux" ;;
  *) warn "Unsupported OS: $OS"; exit 1 ;;
esac
ok "platform: $PLATFORM"

# pkg install helper (brew on mac, apt on linux)
pkg_install() {
  # $@ = package names (same on both where possible)
  if [ "$PLATFORM" = "mac" ]; then
    command -v brew >/dev/null 2>&1 || { warn "Homebrew required on macOS: https://brew.sh"; exit 1; }
    brew install "$@" || true
  else
    if command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update -y && sudo apt-get install -y "$@" || true
    else
      warn "No apt-get; install manually: $*"
    fi
  fi
}

export PATH="$HOME/.local/bin:$PATH"

# --- 0. .env (LOCAL_API_KEY) -------------------------------------------------
if [ -f "$REPO/.env" ]; then
  set -a; . "$REPO/.env"; set +a
  ok ".env loaded"
else
  warn "No .env — copy .env.example to .env and set LOCAL_API_KEY (bulk-worker endpoint key)."
fi

# --- 1. Prerequisites --------------------------------------------------------
log "Ensuring prerequisites (python3, tmux, node/npm, curl, git)..."
command -v python3 >/dev/null 2>&1 || pkg_install python3
command -v tmux    >/dev/null 2>&1 || pkg_install tmux
command -v git     >/dev/null 2>&1 || pkg_install git
command -v curl    >/dev/null 2>&1 || pkg_install curl
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  if [ "$PLATFORM" = "mac" ]; then pkg_install node; else pkg_install nodejs npm; fi
fi
command -v node >/dev/null 2>&1 && ok "node: $(node --version)"

# uv
if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv..."; curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
ok "uv: $(uv --version)"

# --- 2. CAO ------------------------------------------------------------------
log "Installing / updating cli-agent-orchestrator..."
uv tool install --force "git+https://github.com/awslabs/cli-agent-orchestrator.git@main"
ok "cao: $(cao -V 2>&1 | head -1)"

# --- 3. Worker CLIs (npm everywhere; agy via official installer) -------------
log "Installing worker CLIs via npm..."
npm i -g @anthropic-ai/claude-code@latest || warn "claude install failed"
npm i -g @openai/codex@latest             || warn "codex install failed"
npm i -g --allow-scripts=opencode-ai opencode-ai@latest || warn "opencode install failed"
# Antigravity (agy) — official cross-platform installer -> ~/.local/bin/agy
if ! command -v agy >/dev/null 2>&1; then
  log "Installing Antigravity CLI (agy)..."
  curl -fsSL https://antigravity.google/cli/install.sh | bash || warn "agy install failed"
fi
hash -r || true

# --- 4. Render config into the live store ------------------------------------
mkdir -p "$HOME/.config/cao" "$HOME/.aws/opencode"
CAO_PY="$HOME/.local/share/uv/tools/cli-agent-orchestrator/bin/python"
# Pick a tomllib-capable interpreter once, reuse it (also usable with a heredoc).
if [ -x "$CAO_PY" ] && "$CAO_PY" -c 'import tomllib' 2>/dev/null; then PY="$CAO_PY"
elif python3 -c 'import tomllib' 2>/dev/null; then PY="python3"
else PY=""; fi
py_run() {  # run a repo python script with a tomllib-capable interpreter
  if [ -n "$PY" ]; then "$PY" "$@"
  else
    warn "No Python with tomllib (3.11+) — cannot render. CAO ships 3.14; its install above must have failed."
    exit 1
  fi
}

# inherit MCP FIRST (it edits the tracked prompts), so the render below picks up
# the added servers when it writes the fully-rendered profiles to the live store.
if [ "$INHERIT_MCP" = "1" ]; then
  log "Inheriting your existing Claude MCP servers into the workers..."
  warn "Copies ~/.claude.json global mcpServers into worker profiles. Review any"
  warn "server carrying a token in its env before committing the profiles."
  py_run "$APPLY/inherit_mcp.py"
  # Also register the same MCP servers directly with every engine's own CLI
  # (codex/opencode/agy/copilot), so the shared tools reach all of them.
  log "Broadcasting MCP servers to every engine (codex/opencode/agy/copilot)..."
  py_run "$APPLY/inherit_all.py" || warn "inherit_all had issues — check output above"
fi

log "Rendering settings + opencode + profiles from cao.config.toml..."
py_run "$APPLY/render_config.py"
mkdir -p "$HOME/.aws/cli-agent-orchestrator/agent_store"

log "Installing cao-run launcher + cao-doctor + cao-stop + cao-tokens..."
mkdir -p "$HOME/.local/bin"
# SYMLINK (not copy) so edits to run/*.sh in this repo take effect immediately —
# a copy goes stale the moment you change the script here. Re-running bootstrap
# refreshes a stale copy or wrong link; `ln -sfn` replaces whatever is there.
for tool in cao-run cao-doctor cao-stop cao-tokens cao-plugins cao-limits; do
  ln -sfn "$REPO/run/$tool" "$HOME/.local/bin/$tool"
  chmod +x "$REPO/run/$tool"
done

# Persist ~/.local/bin on PATH for FUTURE shells, so the tools stay found after
# you close this terminal (this script's own `export PATH` is session-only).
# Idempotent: only appends if no rc file already puts ~/.local/bin on PATH.
persist_path() {
  local line='export PATH="$HOME/.local/bin:$PATH"'
  local rc
  case "${SHELL##*/}" in
    zsh)  rc="$HOME/.zshrc" ;;
    bash) rc="$HOME/.bashrc" ;;
    *)    rc="$HOME/.profile" ;;
  esac
  # Already handled by any common rc? then do nothing.
  for f in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.profile" "$HOME/.zprofile"; do
    [ -f "$f" ] && grep -q '\.local/bin' "$f" 2>/dev/null && return 0
  done
  printf '\n# Added by cao-setup bootstrap — cao-run/cao-tokens/etc live here\n%s\n' "$line" >> "$rc"
  warn "Added ~/.local/bin to PATH in $rc — open a new shell or 'source $rc'."
}
persist_path

# Persist LOCAL_API_KEY where cao-run always looks.
if [ -n "${LOCAL_API_KEY:-}" ]; then
  mkdir -p "$HOME/.config/cao"
  ( umask 077; printf 'LOCAL_API_KEY=%s\n' "$LOCAL_API_KEY" > "$HOME/.config/cao/cao.env" )
  chmod 600 "$HOME/.config/cao/cao.env"
  ok "LOCAL_API_KEY persisted to ~/.config/cao/cao.env (chmod 600)"
fi

log "Initializing CAO database + registering profiles..."
cao init >/dev/null 2>&1 || true
# Register exactly the profiles the config lists (single source of truth), so a
# renamed/added worker doesn't need this line edited.
CFG="$REPO/2_configure/cao.config.local.toml"; [ -f "$CFG" ] || CFG="$REPO/2_configure/cao.config.toml"
PROFILES="$("$PY" - "$CFG" <<'PYEOF'
import sys, tomllib
print(" ".join(tomllib.load(open(sys.argv[1],"rb")).get("profiles",{}).get("register",[])))
PYEOF
)"
for p in $PROFILES; do
  cao install "$HOME/.aws/cli-agent-orchestrator/agent_store/$p.md" >/dev/null 2>&1 \
    && ok "registered $p" || warn "failed to register $p"
done

# --- 5. pyte patch (Antigravity crash) --------------------------------------
log "Patching pyte (Antigravity private-SGR crash)..."
python3 "$HERE/patch_pyte.py" || warn "pyte patch failed — antigravity may crash the server"

# --- 6. Antigravity onboarding skip + codex hooks neutralize -----------------
log "Skipping Antigravity onboarding wizard..."
ONB="$HOME/.gemini/antigravity-cli/cache/onboarding.json"
mkdir -p "$(dirname "$ONB")" 2>/dev/null || true
printf '{\n  "consumerOnboardingComplete": true,\n  "enterpriseOnboardingComplete": true,\n  "onboardingComplete": true\n}\n' > "$ONB" 2>/dev/null \
  && ok "onboarding.json set" || warn "could not write onboarding.json (agy not installed yet?)"

log "Neutralizing codex startup hooks..."
HOOKS="$HOME/.codex/hooks.json"
mkdir -p "$HOME/.codex"
[ -f "$HOOKS" ] && cp "$HOOKS" "$HOOKS.bak"
printf '{\n  "hooks": {}\n}\n' > "$HOOKS"
ok "codex hooks emptied"

# --- 7. dev-kodeks (optional) ------------------------------------------------
if [ "$WITH_KODEKS" = "1" ]; then
  warn "dev-kodeks is GLOBAL: it symlinks into ~/.claude/ and affects EVERY"
  warn "Claude Code session on this machine — all your repos AND CAO workers"
  warn "(claude_worker/supervisor). It changes Claude's default behavior"
  warn "(planning discipline, when it pauses). See the README dev-kodeks section."
  log "Installing dev-kodeks (Claude Code development standard)..."
  KODEKS_DIR="$HOME/dev-kodeks"
  if [ -d "$KODEKS_DIR/.git" ]; then
    git -C "$KODEKS_DIR" pull --ff-only || warn "dev-kodeks pull failed"
  else
    git clone https://github.com/povchingiz/dev-kodeks.git "$KODEKS_DIR" || warn "dev-kodeks clone failed"
  fi
  [ -x "$KODEKS_DIR/install.sh" ] && "$KODEKS_DIR/install.sh" || warn "dev-kodeks install.sh failed"

  if [ "$WITH_GUARD_HOOK" = "1" ]; then
    log "Activating guard-env PreToolUse hook in ~/.claude/settings.json..."
    warn "guard-env blocks git push/pull/reset etc. This affects CAO workers too."
    SETTINGS="$HOME/.claude/settings.json"
    mkdir -p "$HOME/.claude"
    [ -f "$SETTINGS" ] && cp "$SETTINGS" "$SETTINGS.bak"
    python3 - "$SETTINGS" "$KODEKS_DIR/hooks/guard-env.sh" <<'PY'
import json, sys, os
settings_path, hook_cmd = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(settings_path):
    try:
        with open(settings_path) as f: data = json.load(f)
    except Exception: data = {}
hooks = data.setdefault("hooks", {})
pre = hooks.setdefault("PreToolUse", [])
entry = {"matcher": "Bash", "hooks": [{"type": "command", "command": hook_cmd, "timeout": 5}]}
if not any(json.dumps(e, sort_keys=True) == json.dumps(entry, sort_keys=True) for e in pre):
    pre.append(entry)
with open(settings_path, "w") as f: json.dump(data, f, indent=2)
print("guard-env hook written to", settings_path)
PY
    ok "guard-env hook activated (backup at settings.json.bak)"
  else
    warn "guard-env hook NOT activated. To enable later, add its PreToolUse block"
    warn "to ~/.claude/settings.json (see dev-kodeks/install.sh output)."
  fi
fi

# --- 8. Interactive steps ----------------------------------------------------
cat <<'EOF'

============================================================
  BOOTSTRAP DONE. Remaining INTERACTIVE steps (by hand):
============================================================

1. Claude Code login:      claude   (follow /login on first use)
2. Codex login (ChatGPT):  codex login
3. Antigravity (agy):      agy      (Google sign-in if prompted)
4. bulk worker:         needs LOCAL_API_KEY in .env (already persisted
                           to ~/.config/cao/cao.env if you set it).

Then run:  cao-run

All four workers (claude / opencode / codex / antigravity) callable from the
supervisor. Re-run this script after any `cao update` (re-applies pyte patch).
EOF
