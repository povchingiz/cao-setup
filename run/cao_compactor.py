"""cao_compactor — Turn/Token Estimator and Pre-Emptive State Compactor.

Follows the Hermes 50% Rule: When conversation history / tool outputs exceed
50% of the active context window, compacts verbose logs and terminal stdout into
a structured state diff while strictly preserving the root goal, task DAG,
and wcao/design/ contracts.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any


DEFAULT_CONTEXT_WINDOW = 200_000
DEFAULT_COMPACTION_THRESHOLD = 0.50
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Fast, dependency-free token estimator (~4 chars per token)."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class CompactorState:
    turn_count: int = 0
    estimated_tokens: int = 0
    compaction_count: int = 0
    last_compacted_at: Optional[str] = None


class ContextCompactor:
    """Monitors turns/tokens and generates compact state representations."""

    def __init__(
        self,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
        threshold_ratio: float = DEFAULT_COMPACTION_THRESHOLD,
        turn_threshold: int = 30,
    ):
        self.context_window = context_window
        self.threshold_ratio = threshold_ratio
        self.turn_threshold = turn_threshold
        self.state = CompactorState()

    def record_turn(self, output_text: str = "") -> CompactorState:
        """Record a turn and add its estimated tokens."""
        self.state.turn_count += 1
        tokens = estimate_tokens(output_text)
        self.state.estimated_tokens += tokens
        return self.state

    def should_compact(self) -> bool:
        """Return True if estimated tokens or turn count exceeds the threshold."""
        token_limit = int(self.context_window * self.threshold_ratio)
        if self.state.estimated_tokens >= token_limit:
            return True
        if self.turn_threshold > 0 and self.state.turn_count >= self.turn_threshold:
            return True
        return False

    def compact(
        self,
        root_goal: str,
        tasks: List[Dict[str, Any]],
        worker_outputs: Optional[List[str]] = None,
        design_contracts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Compact logs and worker outputs into a structured summary state."""
        now_iso = datetime.now(timezone.utc).isoformat()
        worker_outputs = worker_outputs or []
        design_contracts = design_contracts or []

        # Summarize task progress
        done_tasks = [t["id"] for t in tasks if t.get("status") == "done"]
        running_tasks = [t["id"] for t in tasks if t.get("status") == "running"]
        pending_tasks = [t["id"] for t in tasks if t.get("status") == "pending"]

        # Summarize worker outputs to avoid unbounded token accumulation
        output_summaries = []
        for out in worker_outputs:
            trimmed = out.strip()
            if len(trimmed) > 200:
                trimmed = trimmed[:100] + " ... [truncated] ... " + trimmed[-80:]
            if trimmed:
                output_summaries.append(trimmed)

        compacted = {
            "root_goal": root_goal,
            "tasks_summary": {
                "total": len(tasks),
                "done": len(done_tasks),
                "running": len(running_tasks),
                "pending": len(pending_tasks),
                "done_ids": done_tasks,
                "running_ids": running_tasks,
                "pending_ids": pending_tasks,
            },
            "design_contracts": design_contracts,
            "recent_output_diffs": output_summaries[-5:],  # Keep only recent diffs
            "compacted_at": now_iso,
            "pre_compaction_tokens": self.state.estimated_tokens,
            "pre_compaction_turns": self.state.turn_count,
        }

        # Reset turn/token counts after compaction
        self.state.compaction_count += 1
        self.state.last_compacted_at = now_iso
        self.state.estimated_tokens = estimate_tokens(str(compacted))
        self.state.turn_count = 0

        return compacted

    def render_markdown_checkpoint(self, compacted: Dict[str, Any]) -> str:
        """Render compacted state into a Markdown section for wcao/plans/now.md."""
        ts = compacted["tasks_summary"]
        diffs = "\n".join(f"- {d}" for d in compacted.get("recent_output_diffs", [])) or "- No recent worker logs."
        contracts = "\n".join(f"- {c}" for c in compacted.get("design_contracts", [])) or "- None specified."

        return f"""## Context Compaction Checkpoint ({compacted['compacted_at']})
- **Goal:** {compacted['root_goal']}
- **Task Status:** {ts['done']}/{ts['total']} complete ({ts['running']} running, {ts['pending']} pending)
- **Completed Tasks:** {', '.join(ts['done_ids']) or 'None'}
- **Active Contracts:**
{contracts}
- **Recent Worker State Diff:**
{diffs}
"""

    def checkpoint_to_now_md(self, now_md_path: Path, compacted: Dict[str, Any]) -> None:
        """Append or update compaction checkpoint in now.md."""
        if not now_md_path.exists():
            return
        content = now_md_path.read_text(encoding="utf-8")
        section = self.render_markdown_checkpoint(compacted)
        # If there's an existing compaction checkpoint, update it; otherwise append
        marker = "## Context Compaction Checkpoint"
        if marker in content:
            # Replace previous checkpoint section
            parts = content.split(marker)
            # Find next header if any
            rest = parts[1]
            next_header = rest.find("\n## ")
            if next_header != -1:
                content = parts[0].rstrip() + "\n\n" + section.strip() + "\n\n## " + rest[next_header + 4:]
            else:
                content = parts[0].rstrip() + "\n\n" + section.strip() + "\n"
        else:
            content = content.rstrip() + "\n\n" + section.strip() + "\n"

        now_md_path.write_text(content, encoding="utf-8")
