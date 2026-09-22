#!/usr/bin/env python3
"""Render cao.config.toml into all the real config files CAO reads.

Single source of truth -> generated targets:
  * ~/.config/cao/settings.json          (orchestrator block)
  * ~/.aws/opencode/opencode.json        (bulk provider + models + default,
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

HERE = Path(__file__).resolve().parent      # 3_apply/
REPO = HERE.parent                          # repo root
CONFIGURE = REPO / "2_configure"
GENERATED = REPO / ".generated"
HOME = Path.home()
# Prefer a private local config if present (gitignored) — this keeps your real
# endpoint/models out of the committed template. Fall back to the template.
CFG_LOCAL = CONFIGURE / "cao.config.local.toml"
CFG = CFG_LOCAL if CFG_LOCAL.exists() else CONFIGURE / "cao.config.toml"


def load():
    if not CFG.exists():
        sys.exit(f"ERROR: config not found: {CFG}\n"
                 "  Copy 2_configure/cao.config.toml and fill in your endpoint,\n"
                 "  or create cao.config.local.toml. See the README.")
    try:
        with open(CFG, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"ERROR: {CFG.name} is not valid TOML:\n  {e}\n"
                 "  Fix the syntax above and re-run ./apply.sh.")


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
    (GENERATED / "settings.json").write_text(json.dumps(out, indent=2) + "\n")
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
        "agent": {"opencode_worker": {"tools": {"cao-mcp-server*": True}}},
    }
    (GENERATED / "opencode.json").write_text(json.dumps(out, indent=2) + "\n")
    live = HOME / ".aws" / "opencode" / "opencode.json"
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_text(json.dumps(out, indent=2) + "\n")
    print(f"  opencode.json      -> {live}")


LIVE_STORE = HOME / ".aws" / "cli-agent-orchestrator" / "agent_store"


def _apply_frontmatter(text: str, edits: dict) -> str:
    """Return `text` with the given top-level frontmatter keys set. Prompt body
    is untouched. Keys not present are inserted after role:/provider:."""
    if not text.startswith("---\n"):
        return text
    end = text.index("\n---", 4)
    fm, body = text[4:end], text[end:]
    lines = fm.split("\n")
    for key, value in edits.items():
        new_line = f'{key}: "{value}"'
        for i, ln in enumerate(lines):
            if ln.strip().startswith(f"{key}:") and not ln.startswith((" ", "\t")):
                lines[i] = new_line
                break
        else:
            anchor = next((i for i, ln in enumerate(lines)
                           if ln.startswith(("role:", "provider:"))), len(lines) - 1)
            lines.insert(anchor + 1, new_line)
    return "---\n" + "\n".join(lines) + body


def render_workers(c):
    """Read each tracked prompt, apply provider/model from config, and write the
    result to the LIVE store — the tracked source in 2_configure/prompts is NEVER
    modified (so a private model id can't leak into the committed template)."""
    endpoint = c["endpoint"]["name"]
    LIVE_STORE.mkdir(parents=True, exist_ok=True)
    for wname, w in c.get("workers", {}).items():
        src = CONFIGURE / "prompts" / f"{wname}.md"
        if not src.exists():
            print(f"  WARN worker '{wname}' has no {src.name}, skipped")
            continue
        edits = {}
        if "provider" in w:
            edits["provider"] = w["provider"]
        if w.get("model"):
            model = w["model"]
            # The `<endpoint>/…` prefix is ONLY for the opencode bulk endpoint
            # (opencode resolves a model as "<provider>/<id>"). Every other engine
            # (codex, antigravity/gemini, copilot) names its models directly, so
            # writing a "nitec/…" prefix there would be a broken id. Prefix only
            # for opencode_cli, and don't double-prefix one already qualified.
            if w.get("provider") == "opencode_cli":
                if "/" not in model:
                    model = f"{endpoint}/{model}"
                elif not model.startswith(f"{endpoint}/"):
                    model = (f"{endpoint}/{model.split('/', 1)[-1]}"
                             if model.count("/") >= 2 else f"{endpoint}/{model}")
            edits["model"] = model
        (LIVE_STORE / f"{wname}.md").write_text(_apply_frontmatter(src.read_text(), edits))
        print(f"  {wname:20s} provider={w.get('provider','-')} model={w.get('model','-')} -> live store")


MAP_START = "<!-- AUTO-MAPPING START"
MAP_END = "<!-- AUTO-MAPPING END -->"


def render_supervisor_mapping(c):
    """Regenerate the supervisor's Worker Mapping table from [workers.*]
    aliases + focus, between the AUTO-MAPPING markers. Rest of the prompt
    (execution rules, division of labor) is left untouched."""
    sup = c.get("orchestrator", {}).get("default_supervisor", "code_supervisor")
    src = CONFIGURE / "prompts" / f"{sup}.md"
    if not src.exists():
        print(f"  WARN supervisor '{sup}' has no {src.name}, mapping skipped")
        return
    text = src.read_text()
    if MAP_START not in text or MAP_END not in text:
        print(f"  WARN {src.name}: no AUTO-MAPPING markers, mapping skipped")
        return

    rows = []
    for wname, w in c.get("workers", {}).items():
        aliases = w.get("aliases") or [wname.replace("_worker", "")]
        quoted = " / ".join(f'"{a}"' for a in aliases)
        focus = w.get("focus", "")
        rows.append(f"- {quoted} -> `{wname}` ({focus})")
    block = "\n".join(rows)

    start = text.index(MAP_START)
    line_end = text.index("\n", start) + 1        # keep the START marker line
    end = text.index(MAP_END)
    new = (
        text[:line_end]
        + block + "\n"
        + text[end:]
    )
    LIVE_STORE.mkdir(parents=True, exist_ok=True)
    (LIVE_STORE / f"{sup}.md").write_text(new)
    print(f"  supervisor mapping   -> live {sup}.md ({len(rows)} workers)")


def copy_remaining_profiles(c):
    """Copy any prompts that render_workers/mapping didn't already write to the
    live store (e.g. profiles registered but not in [workers.*])."""
    workers = set(c.get("workers", {}).keys())
    sup = c.get("orchestrator", {}).get("default_supervisor", "code_supervisor")
    handled = workers | {sup}
    LIVE_STORE.mkdir(parents=True, exist_ok=True)
    for src in (CONFIGURE / "prompts").glob("*.md"):
        if src.stem in handled:
            continue
        (LIVE_STORE / src.name).write_text(src.read_text())
        print(f"  {src.stem:20s} copied -> live store")


def prune_stale_profiles(c):
    """Delete live-store profiles that are no longer tracked in 2_configure —
    e.g. a worker that was renamed or removed. Without this, a renamed profile
    (opencode_worker -> coder_worker) leaves the old .md orphaned in the live
    store, and cao may still pick it up. Only prune files that have a tracked
    source name; never touch unrelated files."""
    tracked = {p.stem for p in (CONFIGURE / "prompts").glob("*.md")}
    if not LIVE_STORE.exists():
        return
    for live in LIVE_STORE.glob("*.md"):
        if live.stem not in tracked:
            live.unlink()
            print(f"  {live.stem:20s} pruned (no tracked source) <- live store")


KNOWN_PROVIDERS = {"claude_code", "opencode_cli", "codex", "antigravity_cli", "copilot_cli", "hermes_cli"}


def validate(c):
    """Fail early with a clear message on the config mistakes that would
    otherwise surface as a confusing cao error at launch time."""
    errs = []
    for section in ("orchestrator", "endpoint", "workers", "profiles"):
        if section not in c:
            errs.append(f"missing [{section}] section")
    if errs:
        sys.exit("ERROR: config problems:\n  - " + "\n  - ".join(errs))

    ep_models = set(c["endpoint"].get("models", []))
    reg = c.get("profiles", {}).get("register", [])
    sup = c.get("orchestrator", {}).get("default_supervisor", "code_supervisor")

    for wname, w in c.get("workers", {}).items():
        prov = w.get("provider")
        if prov not in KNOWN_PROVIDERS:
            errs.append(f"worker '{wname}': provider '{prov}' not one of {sorted(KNOWN_PROVIDERS)}")
        if wname not in reg:
            errs.append(f"worker '{wname}' is defined but not in [profiles].register")
        m = w.get("model")
        if m and prov == "opencode_cli":
            bare = m.split("/", 1)[-1] if m.count("/") >= 2 else m
            # accept both 'ns/model' and 'endpoint/ns/model'
            if m not in ep_models and bare not in ep_models and \
               "/".join(m.split("/")[1:]) not in ep_models:
                errs.append(f"worker '{wname}': model '{m}' not in [endpoint].models {sorted(ep_models)}")
    # every registered profile except the supervisor should have a prompt file
    for p in reg:
        if p == sup:
            continue
        if not (CONFIGURE / "prompts" / f"{p}.md").exists():
            errs.append(f"registered profile '{p}' has no prompts/{p}.md")
    if not (CONFIGURE / "prompts" / f"{sup}.md").exists():
        errs.append(f"supervisor '{sup}' has no prompts/{sup}.md")

    if errs:
        sys.exit("ERROR: config problems:\n  - " + "\n  - ".join(errs) +
                 "\n  Fix these in the config, then re-run ./apply.sh.")


def main():
    c = load()
    validate(c)
    print("Rendering cao.config.toml ->")
    render_settings(c)
    render_opencode(c)
    render_workers(c)
    render_supervisor_mapping(c)
    copy_remaining_profiles(c)
    prune_stale_profiles(c)
    print("Done. Tracked prompts untouched; live store fully rendered.")


if __name__ == "__main__":
    main()
