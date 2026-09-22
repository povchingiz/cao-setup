"""cao_plan — Autonomous Goal Decomposer and DAG Plan Generator.

Decomposes a North-Star objective into a Directed Acyclic Graph (DAG) of
discrete, file-bounded tasks, verifies DAG validity (no cycles), applies
TokenMaster engine routing, and saves to wcao/tasks.json.
"""
import argparse
import graphlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Add repo root to sys.path
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from run.cao_auto import find_repo_root
from run.cao_token_master import TokenMaster


def extract_goal_from_now_md(now_file: Path) -> str:
    """Extract the active North Star goal from wcao/plans/now.md."""
    if not now_file.exists():
        return ""
    content = now_file.read_text(encoding="utf-8")
    # Search for Goal, Objective, or Active Plan section
    match = re.search(r"(?:##?\s*(?:North Star|Goal|Objective|Active Plan)[^\n]*\n)([\s\S]*?)(?=\n##|\Z)", content, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return content.splitlines()[0].strip("# ") if content.strip() else ""


def validate_dag(tasks: List[dict]) -> Tuple[bool, str]:
    """Verify that every task dependency exists and there are no cycles."""
    task_ids = {t["id"] for t in tasks}
    graph: Dict[str, Set[str]] = {}

    for t in tasks:
        tid = t.get("id")
        if not tid:
            return False, "Task missing 'id' field"
        deps = t.get("depends_on", [])
        for d in deps:
            if d not in task_ids:
                return False, f"Task '{tid}' depends on non-existent task '{d}'"
        graph[tid] = set(deps)

    # Check for cycles using TopologicalSorter
    try:
        ts = graphlib.TopologicalSorter(graph)
        ts.prepare()
        return True, "DAG is valid and acyclic"
    except graphlib.CycleError as exc:
        return False, f"Cycle detected in task dependencies: {exc}"


def decompose_goal(
    goal: str,
    repo_root: Path,
    token_master: Optional[TokenMaster] = None,
) -> List[dict]:
    """Decompose a high-level goal into a validated DAG of tasks.

    Creates standard architectural phases:
    1. Schema / Contract specification (hermes_worker / claude_worker)
    2. Core Implementation (coder_worker)
    3. Unit & Integration Test Suite (antigravity_worker / coder_worker)
    4. Documentation & Verification
    """
    tm = token_master or TokenMaster()

    # Determine project type
    is_python = (repo_root / "pyproject.toml").exists() or (repo_root / "setup.py").exists()
    is_node = (repo_root / "package.json").exists()

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", goal.strip().lower())[:30].strip("_") or "feature"

    # Task 1: Architecture & Interface Design
    t1_decision = tm.evaluate_task({"engine": "claude_worker"}, repo_root=repo_root)
    arch_engine = t1_decision.selected_engine

    tasks = [
        {
            "id": f"task_01_{slug}_arch",
            "title": f"Design interface contracts and schema for {goal[:50]}",
            "status": "pending",
            "engine": arch_engine,
            "depends_on": [],
            "files": [f"wcao/design/{slug}.mmd"],
            "detail": f"Analyze requirements for '{goal}'. Write Mermaid sequence and state diagrams to wcao/design/{slug}.mmd defining interfaces, input/output schemas, and error cases.",
        },
        {
            "id": f"task_02_{slug}_impl",
            "title": f"Implement core logic for {goal[:50]}",
            "status": "pending",
            "engine": "coder_worker",
            "depends_on": [f"task_01_{slug}_arch"],
            "files": [f"run/cao_{slug}.py" if is_python else f"src/{slug}.ts"],
            "detail": f"Implement the core logic fulfilling the architecture contract in wcao/design/{slug}.mmd. Ensure clean, type-annotated code with error handling.",
        },
        {
            "id": f"task_03_{slug}_tests",
            "title": f"Write comprehensive unit test suite for {goal[:50]}",
            "status": "pending",
            "engine": "coder_worker",
            "depends_on": [f"task_02_{slug}_impl"],
            "files": [f"tests/test_{slug}.py" if is_python else f"tests/{slug}.test.ts"],
            "detail": f"Write unit and edge-case tests in tests/ covering normal paths, error conditions, and boundary values for {goal}.",
        },
        {
            "id": f"task_04_{slug}_verify",
            "title": f"Verification, documentation, and audit gate for {goal[:50]}",
            "status": "pending",
            "engine": "antigravity_worker",
            "depends_on": [f"task_03_{slug}_tests"],
            "files": ["README.md", "wcao/plans/now.md"],
            "detail": f"Update README.md and wcao/plans/now.md documenting {goal}. Run the full test suite and verify 0 blockers.",
        },
    ]

    valid, msg = validate_dag(tasks)
    if not valid:
        raise ValueError(f"Generated invalid DAG: {msg}")

    return tasks


def save_plan(
    tasks: List[dict],
    goal: str,
    repo_root: Path,
) -> Path:
    """Save the tasks into wcao/tasks.json and update wcao/plans/now.md."""
    wcao = repo_root / "wcao"
    wcao.mkdir(parents=True, exist_ok=True)
    plans_dir = wcao / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    tasks_file = wcao / "tasks.json"
    tasks_file.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")

    # Update now.md
    now_file = plans_dir / "now.md"
    now_content = f"""# now.md — Active Plan & Goal

> **Active Goal:** {goal}
> **Generated:** {datetime.now(timezone.utc).isoformat()[:19]} UTC
> **Autonomous Queue:** [`wcao/tasks.json`](../tasks.json) ({len(tasks)} tasks)

## Planned Tasks
"""
    for t in tasks:
        now_content += f"- [ ] **`{t['id']}`** ({t['engine']}): {t['title']}\n"

    now_file.write_text(now_content, encoding="utf-8")
    return tasks_file


def main():
    parser = argparse.ArgumentParser(description="Autonomous Goal Decomposer and DAG Planner (CAO)")
    parser.add_argument("goal", nargs="?", help="High-level goal description. If omitted, reads from wcao/plans/now.md")
    parser.add_argument("--json", action="store_true", help="Print plan as JSON to stdout")
    parser.add_argument("--dry-run", action="store_true", help="Plan without writing to disk")
    args = parser.parse_args()

    repo_root = find_repo_root(Path.cwd())
    wcao = repo_root / "wcao"

    goal = args.goal
    if not goal:
        now_md = wcao / "plans" / "now.md"
        goal = extract_goal_from_now_md(now_md)

    if not goal:
        sys.exit("Error: No goal provided and wcao/plans/now.md has no defined goal.\nUsage: cao-plan 'Your goal here'")

    print(f"==> Decomposing goal: '{goal}'")
    tm = TokenMaster()
    tasks = decompose_goal(goal, repo_root=repo_root, token_master=tm)

    if args.json:
        print(json.dumps(tasks, indent=2))
        return

    print(f"Generated {len(tasks)} DAG tasks:")
    for t in tasks:
        deps = f" (depends on: {', '.join(t['depends_on'])})" if t['depends_on'] else ""
        print(f"  [{t['engine']}] {t['id']}: {t['title']}{deps}")

    if not args.dry_run:
        target = save_plan(tasks, goal, repo_root)
        print(f"\n✓ Saved DAG to {target.relative_to(repo_root)} and updated wcao/plans/now.md")
        print(f"Run autonomously with:\n  uv run python run/cao_auto.py --tasks {target}")


if __name__ == "__main__":
    main()
