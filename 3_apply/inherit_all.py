#!/usr/bin/env python3
"""Propagate your Claude MCP servers to EVERY engine cao drives.

`inherit_mcp.py` copies your `~/.claude.json` MCP servers into cao worker
*profiles* (so cao writes them into each engine's config at install). This
script does the complementary thing at the ENGINE level: it registers the same
MCP servers directly with each CLI's own `mcp add`, so codex / opencode /
antigravity(agy) / copilot all expose the same tools (lean-ctx, symdex, …) that
Claude has — whether or not they're launched through cao.

Why both exist:
  * MCP is a cross-engine protocol — every engine here has an `mcp add`, so MCP
    tools CAN reach all of them. This script is the one-shot that does it.
  * Skills and plugins are NOT MCP. They're per-CLI instruction folders:
      - Claude Code + Copilot read `.claude/skills/` (Copilot reads it natively).
      - codex / opencode read `AGENTS.md`; gemini reads `GEMINI.md`.
    A plugin ships a manifest per engine (CLAUDE.md / AGENTS.md / GEMINI.md /
    .skill), so "one skill for every engine" isn't a single switch — see the
    README "Sharing skills & plugins" section. This script handles MCP only.

Source: `~/.claude.json` global `mcpServers` (same as inherit_mcp.py). A server
whose `env` carries a secret is copied verbatim into that engine's config — the
script warns so you can review.

Usage:
    python3 inherit_all.py                 # add all source MCP to every engine
    python3 inherit_all.py --list          # show what would be added, per engine
    python3 inherit_all.py --dry-run       # print the commands, run nothing
    python3 inherit_all.py codex copilot   # only these engines
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CLAUDE_JSON = Path.home() / ".claude.json"
SKIP = {"cao-mcp-server"}  # cao manages its own server per worker

# Each engine: the binary to check, and a function building the `mcp add` argv
# for a stdio server (name, command, args). Syntaxes differ slightly per CLI.
def _codex(name, cmd, args):
    return ["codex", "mcp", "add", name, "--", cmd, *args]

def _opencode(name, cmd, args):
    return ["opencode", "mcp", "add", name, "--", cmd, *args]

def _copilot(name, cmd, args):
    return ["copilot", "mcp", "add", name, "--", cmd, *args]

def _agy(name, cmd, args):
    # agy: `agy mcp add <name> <command> [args...]` (no `--` separator)
    return ["agy", "mcp", "add", name, cmd, *args]

ENGINES = {
    "codex": ("codex", _codex),
    "opencode": ("opencode", _opencode),
    "antigravity": ("agy", _agy),
    "copilot": ("copilot", _copilot),
}


def read_source():
    if not CLAUDE_JSON.exists():
        return {}
    try:
        d = json.load(open(CLAUDE_JSON))
    except Exception as e:
        sys.exit(f"ERROR: cannot parse {CLAUDE_JSON}: {e}")
    servers = d.get("mcpServers", {}) or {}
    return {k: v for k, v in servers.items() if k not in SKIP}


def main(argv):
    flags = {a for a in argv if a.startswith("--")}
    picked = [a for a in argv if not a.startswith("--")]
    engines = {k: v for k, v in ENGINES.items() if not picked or k in picked}

    servers = read_source()
    if not servers:
        print("No inheritable MCP servers in ~/.claude.json global mcpServers.")
        return 0

    print(f"Source MCP servers: {', '.join(servers)}")
    for name, cfg in servers.items():
        if cfg.get("env"):
            print(f"  NOTE: '{name}' carries an env block — review before sharing "
                  f"(it will be written into each engine's config).")

    if "--list" in flags:
        for ename in engines:
            binname = ENGINES[ename][0]
            have = "" if shutil.which(binname) else "  (binary missing — skipped)"
            print(f"\n[{ename}]{have}")
            for name in servers:
                print(f"  + {name}")
        return 0

    dry = "--dry-run" in flags
    for ename, (binname, build) in engines.items():
        if not shutil.which(binname):
            print(f"[{ename}] {binname} not installed — skipped")
            continue
        for name, cfg in servers.items():
            cmd = cfg.get("command")
            if not cmd:
                print(f"[{ename}] {name}: no stdio command in source — skipped")
                continue
            argv_add = build(name, cmd, cfg.get("args", []) or [])
            if dry:
                print("  " + " ".join(argv_add))
                continue
            r = subprocess.run(argv_add, capture_output=True, text=True)
            ok = r.returncode == 0
            # idempotent: some CLIs error if the server already exists — treat
            # "already exists" as success.
            blob = (r.stdout + r.stderr).lower()
            if ok or "already" in blob or "exists" in blob:
                print(f"[{ename}] {name}: ok")
            else:
                print(f"[{ename}] {name}: FAILED — {r.stderr.strip()[:120]}")

    if not dry:
        print("\nDone. Each engine's own `mcp list` will now show the shared servers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
