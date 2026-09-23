# Codebase Navigation & Integrity Protocol

## SymDex & AST Rules (Strict Read-Before-Write)

1. **Navigation Only**: Use SymDex tools (`search_symbols`, `get_file_outline`, `search_routes`, `get_callers`, `get_callees`) exclusively for discovery, locating files, and understanding repo topology.
2. **No Blind Edits**: NEVER generate code, apply patches, or write diffs based solely on AST outlines or symbol signatures.
3. **Full Read Mandatory**: Before modifying any function or file, inspect the full raw file or function block via `ctx_read(path, mode="full")` or an equivalent view tool. All local formatting, implicit side effects, types, and comments must be loaded into context.
4. **Fallback**: If the SymDex index is stale or missing, fall back immediately to standard project search (`ctx_search` / `grep` / `rg` / file listing).

## Output Integrity (lean-ctx)

Never suppress, compress, or truncate:

- Test runner output: `pytest`, `npm test`, `cargo test`, `go test`, `uv run ... pytest`
- Typecheckers and linters: `tsc`, `mypy`, `pyright`, `ruff`, `eslint`
- Runtime tracebacks — the full stack trace to the last line

Compression is allowed only for trivial commands: `git status`, directory listings, long asset lists, package manager chatter.

## Verification

A task is complete ONLY when the test and typecheck commands exit with code 0.
Never hand control back or claim success while a verification command is failing — stay in the fix loop.
