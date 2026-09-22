"""cao_token_master — Proactive Token & Quota Awareness Loop (CAO v2).

Monitors rate-limit ceilings via cao_limits and file-context sizes, proactively
adjusting task engines, models, and execution scopes before quota exhaustion occurs.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from run.cao_limits import ClaudeLimits, get_claude_limits

DEFAULT_HIGH_WATERMARK = 0.80  # 80% utilization threshold for proactive swap
LARGE_FILE_COUNT_THRESHOLD = 5
LARGE_CONTEXT_TOKEN_THRESHOLD = 25000  # estimated tokens


@dataclass
class TokenMasterDecision:
    """Outcome of TokenMaster task evaluation."""

    original_engine: str
    selected_engine: str
    selected_model: Optional[str] = None
    swapped: bool = False
    reason: str = ""
    notices: List[str] = field(default_factory=list)


class TokenMaster:
    """Evaluates task execution constraints against live quota ceilings and context size."""

    def __init__(
        self,
        high_watermark: float = DEFAULT_HIGH_WATERMARK,
        fallback_engine: str = "coder_worker",
        fallback_model: Optional[str] = None,
        reasoning_fallback: str = "hermes_worker",
        large_context_engine: str = "analyst_worker",
        initial_blocked_engines: Optional[List[str]] = None,
    ):
        self.high_watermark = high_watermark
        self.fallback_engine = fallback_engine
        self.fallback_model = fallback_model
        self.reasoning_fallback = reasoning_fallback
        self.large_context_engine = large_context_engine
        import time
        self._time = time
        # Map: engine_name -> (unblock_unix_timestamp, reason)
        self.blocked_engines: Dict[str, Tuple[float, str]] = {}
        if initial_blocked_engines:
            for eng in initial_blocked_engines:
                self.mark_engine_blocked(eng, duration_seconds=86400, reason="User configured quota exhaustion")

    def mark_engine_blocked(
        self, engine: str, duration_seconds: float = 3600.0, reason: str = "quota/429 rate limit"
    ) -> None:
        """Mark an engine as blocked for duration_seconds so subsequent tasks skip it proactively."""
        unblock_time = self._time.time() + duration_seconds
        self.blocked_engines[engine] = (unblock_time, reason)

    def is_engine_blocked(self, engine: str) -> Tuple[bool, str]:
        """Check if an engine is currently in a cooling-off block."""
        if engine in self.blocked_engines:
            unblock_time, reason = self.blocked_engines[engine]
            if self._time.time() < unblock_time:
                remaining = int(unblock_time - self._time.time())
                return True, f"{reason} (cooling off, {remaining}s remaining)"
            del self.blocked_engines[engine]
        return False, ""

    def get_claude_quota_state(self) -> Optional[ClaudeLimits]:
        """Fetch current Claude limits on disk."""
        try:
            return get_claude_limits()
        except Exception:
            return None

    def estimate_file_tokens(self, files: List[str], repo_root: Path) -> int:
        """Estimate token count for a list of files (~4 chars per token)."""
        total_chars = 0
        for f in files:
            p = repo_root / f if not Path(f).is_absolute() else Path(f)
            if p.exists() and p.is_file():
                try:
                    total_chars += p.stat().st_size
                except OSError:
                    pass
        return total_chars // 4

    def evaluate_task(
        self,
        task: dict,
        repo_root: Optional[Path] = None,
        claude_limits_override: Optional[ClaudeLimits] = None,
    ) -> TokenMasterDecision:
        """Evaluate a task before dispatch and adjust engine or add advisories."""
        engine = task.get("engine", "coder_worker")
        model = task.get("model")
        files = task.get("files", [])
        notices: List[str] = []

        limits = (
            claude_limits_override
            if claude_limits_override is not None
            else self.get_claude_quota_state()
        )

        # 0. Check if engine is in a known cooling-off / blocked state (Codex, AGY, or Claude)
        is_blocked, blocked_reason = self.is_engine_blocked(engine)
        if is_blocked:
            target_engine = (
                self.reasoning_fallback
                if engine in ("claude_worker", "claude_code", "architect")
                else self.fallback_engine
            )
            return TokenMasterDecision(
                original_engine=engine,
                selected_engine=target_engine,
                selected_model=self.fallback_model,
                swapped=True,
                reason=f"Proactive quota swap: {engine} is currently blocked ({blocked_reason})",
                notices=notices,
            )

        # 1. Context Size / Large File Set Check
        if repo_root and files:
            est_tokens = self.estimate_file_tokens(files, repo_root)
            if (
                len(files) >= LARGE_FILE_COUNT_THRESHOLD
                or est_tokens >= LARGE_CONTEXT_TOKEN_THRESHOLD
            ):
                notices.append(
                    f"TokenMaster: Large context detected ({len(files)} files, ~{est_tokens} tokens). "
                    f"Recommend slicing task or consulting {self.large_context_engine} (Gemini huge-context)."
                )

        # 2. Proactive Quota Check for Claude Engine
        is_claude_task = engine in ("claude_worker", "claude_code", "architect")
        if is_claude_task and limits is not None:
            util = 0.0
            if limits.five_hour:
                util = max(util, limits.five_hour.utilization)
            if limits.seven_day:
                util = max(util, limits.seven_day.utilization)

            if limits.is_blocked():
                # Proactive swap: Claude is actively blocked
                target_engine = self.reasoning_fallback or self.fallback_engine
                reason = f"Proactive quota swap: Claude rate limit blocked (resets at {limits.blocked_resets_at})"
                return TokenMasterDecision(
                    original_engine=engine,
                    selected_engine=target_engine,
                    selected_model=self.fallback_model,
                    swapped=True,
                    reason=reason,
                    notices=notices,
                )

            if util >= self.high_watermark or limits.is_near_limit():
                # Proactive swap: Quota utilization exceeds safety watermark
                target_engine = self.reasoning_fallback or self.fallback_engine
                reason = f"Proactive quota swap: Claude utilization at {int(util * 100)}% (watermark {int(self.high_watermark * 100)}%)"
                return TokenMasterDecision(
                    original_engine=engine,
                    selected_engine=target_engine,
                    selected_model=self.fallback_model,
                    swapped=True,
                    reason=reason,
                    notices=notices,
                )

        return TokenMasterDecision(
            original_engine=engine,
            selected_engine=engine,
            selected_model=model,
            swapped=False,
            reason="Within quota safety limits",
            notices=notices,
        )
