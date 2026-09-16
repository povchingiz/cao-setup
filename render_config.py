#!/usr/bin/env python3
"""Render cao.config.toml into all the real config files CAO reads.

Single source of truth -> generated targets:
  * ~/.config/cao/settings.json          (orchestrator block)
  * ~/.aws/opencode/opencode.json        (nitec provider + models + default,
                                           MCP + agent tool-gating preserved)
  * agent_store/<worker>.md frontmatter  (provider:/model: only — the prompt
                                           body below the frontmatter is NEVER
                                           touched)

Secrets are never rendered: the endpoint api key stays as {env:LOCAL_API_KEY}.
Run via apply.sh (which picks a Python with tomllib and copies the .md files
into ~/.aws first, then calls `cao install`).
"""
import json
import os
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("ERROR: need Python 3.11+ (tomllib). Run through apply.sh.")

HERE = Path(__file__).resolve().parent
HOME = Path.home()
CFG = HERE / "cao.config.toml"


def load():
    with open(CFG, "rb") as f:
        return tomllib.load(f)


def render_settings(c):
    o = c["orchestrator"]
    out = {
        "orchestrator": {
            "default_supervisor": o["default_supervisor"],
            "default_provider": o["default_provider"],
            "worktree_isolation": o["worktree_isolation"],
            "max_concurrent_workers": o["max_concurrent_workers"],
            "server_port": o["server_port"],
        },
        "providers": {"default": o["default_provider"]},
    }
    # write to the repo copy AND the live location
    (HERE / "config" / "settings.json").write_text(json.dumps(out, indent=2) + "\n")
    live = HOME / ".config" / "cao" / "settings.json"
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(json.dumps(out, indent=2) + "\n")
    print(f"  settings.json      -> {live}")


def render_opencode(c):
    ep = c["endpoint"]
    name = ep["name"]
    models = {m: {"name": m.split("/")[-1].replace("-", " ")} for m in ep["models"]}
    out = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            name: {
                "npm": "@ai-sdk/openai-compatible",
                "name": f"{name.capitalize()} Local",
                "options": {
                    "baseURL": ep["base_url"],
                    "apiKey": "{env:LOCAL_API_KEY}",
                },
                "models": models,
            }
        },
        "model": f"{name}/{ep['default_model']}",
        "mcp": {
            "cao-mcp-server": {
                "type": "local",
                "command": [str(HOME / ".local" / "bin" / "cao-mcp-server")],
                "enabled": True,
            }
        },
        "tools": {"cao-mcp-server*": False},
        "agent": {"jcode_worker": {"tools": {"cao-mcp-server*": True}}},
    }
    (HERE / "config" / "opencode.json").write_text(json.dumps(out, indent=2) + "\n")
    live = HOME / ".aws" / "opencode" / "opencode.json"
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(json.dumps(out, indent=2) + "\n")
    print(f"  opencode.json      -> {live}")


def set_frontmatter_key(md_path: Path, key: str, value: str):
    """Set/replace a top-level scalar `key: value` in the YAML frontmatter,
    leaving the prompt body untouched. Inserts after `role:` if missing."""
    text = md_path.read_text()
    if not text.startswith("---\n"):
        print(f"  WARN {md_path.name}: no frontmatter, skipped")
        return
    end = text.index("\n---", 4)
    fm, body = text[4:end], text[end:]
    lines = fm.split("\n")
    new_line = f'{key}: "{value}"'
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"{key}:") and not ln.startswith((" ", "\t")):
            lines[i] = new_line
            break
    else:
        # insert after role: (or provider:) to keep it a top-level key
        anchor = next((i for i, ln in enumerate(lines)
                       if ln.startswith(("role:", "provider:"))), len(lines) - 1)
        lines.insert(anchor + 1, new_line)
    md_path.write_text("---\n" + "\n".join(lines) + body)


def render_workers(c):
    endpoint = c["endpoint"]["name"]
    for wname, w in c.get("workers", {}).items():
        md = HERE / "agent_store" / f"{wname}.md"
        if not md.exists():
            print(f"  WARN worker '{wname}' has no {md.name}, skipped")
            continue
        if "provider" in w:
            set_frontmatter_key(md, "provider", w["provider"])
        if w.get("model"):
            model = w["model"]
            if "/" not in model:  # bare model -> qualify with endpoint
                model = f"{endpoint}/{model}"
            elif not model.startswith(f"{endpoint}/"):
                model = f"{endpoint}/{model.split('/', 1)[-1]}" if model.count("/") >= 2 else f"{endpoint}/{model}"
            set_frontmatter_key(md, "model", model)
        print(f"  {wname:20s} provider={w.get('provider','-')} model={w.get('model','-')}")


def main():
    c = load()
    print("Rendering cao.config.toml ->")
    render_settings(c)
    render_opencode(c)
    render_workers(c)
    print("Done. (Prompt bodies in agent_store/*.md untouched.)")


if __name__ == "__main__":
    main()
