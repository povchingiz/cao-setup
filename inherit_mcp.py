#!/usr/bin/env python3
"""Inherit the user's existing Claude MCP servers into CAO workers.

Whatever MCP servers a user already has in ~/.claude.json (global `mcpServers`)
can be handed to CAO's workers, so an orchestrated agent gets the same tools the
user's own Claude session has. CAO writes each profile's `mcpServers` block into
that engine's native config at `cao install`, so this works for every worker
provider (claude, codex, opencode, antigravity, ...), not just Claude.

What it does:
  * Reads global `mcpServers` from ~/.claude.json (the standard place a user's
    MCP servers live). Skips CAO's own `cao-mcp-server`.
  * Merges them into the chosen worker profiles' frontmatter `mcpServers` block,
    without touching the prompt body or `cao-mcp-server`.
  * You then run `cao install` on those profiles (apply.sh does this) to push
    them into each engine's config.

Scope (kept deliberately simple):
  * Source is ~/.claude.json global `mcpServers` only. Plugin-provided MCP
    (~/.claude/plugins/.../.mcp.json) and per-project MCP are NOT auto-read —
    enabled-state and per-plugin config make them unreliable to inherit blindly.
    Add those by hand to cao.config-side profiles if you want them.

Usage:
    python3 inherit_mcp.py                      # into all workers (default set)
    python3 inherit_mcp.py claude_worker jcode_worker
    python3 inherit_mcp.py --list               # just show what would be inherited
    python3 inherit_mcp.py --dry-run            # show plan, write nothing

Secrets: server definitions are copied verbatim. If one carries a token in its
`env`, that token lands in the profile file — review before committing. Prefer
servers that read their own env var. This script warns if it copies an `env`.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = HERE / "agent_store"
CLAUDE_JSON = Path.home() / ".claude.json"

DEFAULT_WORKERS = ["claude_worker", "jcode_worker", "codex_worker", "antigravity_worker"]
SKIP = {"cao-mcp-server"}


def read_user_mcp() -> dict:
    if not CLAUDE_JSON.exists():
        return {}
    try:
        d = json.load(open(CLAUDE_JSON))
    except Exception as e:
        print(f"WARN: could not parse {CLAUDE_JSON}: {e}", file=sys.stderr)
        return {}
    servers = d.get("mcpServers", {}) or {}
    return {k: v for k, v in servers.items() if k not in SKIP}


def to_yaml_block(servers: dict, indent="  ") -> str:
    """Render an mcpServers dict as YAML lines (excluding the `mcpServers:` key).
    Handles the common stdio shape: type/command/args/env."""
    out = []
    for name, cfg in servers.items():
        out.append(f"{indent}{name}:")
        for key in ("type", "command"):
            if key in cfg:
                out.append(f"{indent}  {key}: {json.dumps(cfg[key])}")
        if cfg.get("args"):
            out.append(f"{indent}  args:")
            for a in cfg["args"]:
                out.append(f"{indent}    - {json.dumps(a)}")
        if cfg.get("env"):
            out.append(f"{indent}  env:")
            for k, v in cfg["env"].items():
                out.append(f"{indent}    {k}: {json.dumps(v)}")
    return "\n".join(out)


def inject(md: Path, servers: dict) -> bool:
    """Merge servers into the profile's frontmatter mcpServers block.
    Leaves cao-mcp-server and the prompt body intact. Returns True if changed."""
    text = md.read_text()
    if not text.startswith("---\n"):
        print(f"  WARN {md.name}: no frontmatter, skipped")
        return False
    end = text.index("\n---", 4)
    fm, rest = text[4:end], text[end:]

    if "mcpServers:" not in fm:
        print(f"  WARN {md.name}: no mcpServers block, skipped (add one first)")
        return False

    # Which of the requested servers are already present in this profile?
    to_add = {n: c for n, c in servers.items() if f"\n  {n}:" not in "\n" + fm}
    if not to_add:
        print(f"  {md.name}: already has {list(servers)} — nothing to add")
        return False

    block = to_yaml_block(to_add)
    lines = fm.rstrip("\n").split("\n")
    # find the mcpServers: line, insert new servers right after it
    idx = next(i for i, ln in enumerate(lines) if ln.strip() == "mcpServers:")
    lines[idx + 1:idx + 1] = block.split("\n")
    md.write_text("---\n" + "\n".join(lines) + rest)
    print(f"  {md.name}: added {list(to_add)}")
    return True


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    workers = args or DEFAULT_WORKERS

    servers = read_user_mcp()
    if not servers:
        print("No inheritable MCP servers found in ~/.claude.json (global mcpServers).")
        return 0

    print(f"Found {len(servers)} user MCP server(s): {', '.join(servers)}")
    for name, cfg in servers.items():
        if cfg.get("env"):
            print(f"  NOTE: '{name}' carries an env block — review before committing "
                  f"(may contain a token).")

    if "--list" in flags:
        for name, cfg in servers.items():
            print(f"\n[{name}]\n{json.dumps(cfg, indent=2)}")
        return 0

    if "--dry-run" in flags:
        print(f"\nWould inject into: {', '.join(workers)} (no files written).")
        return 0

    changed = False
    for w in workers:
        md = STORE / f"{w}.md"
        if not md.exists():
            print(f"  WARN {w}: {md.name} not found, skipped")
            continue
        changed |= inject(md, servers)

    if changed:
        print("\nDone. Run ./apply.sh to push these into the live engine configs.")
    else:
        print("\nNo changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
