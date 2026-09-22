import pytest
from pathlib import Path
from run.cao_compactor import ContextCompactor, estimate_tokens


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello") >= 1
    long_text = "a" * 400
    assert estimate_tokens(long_text) == 100


def test_compactor_threshold_trigger():
    # Model window 1000 tokens, 50% = 500 tokens
    compactor = ContextCompactor(context_window=1000, threshold_ratio=0.50, turn_threshold=10)
    assert not compactor.should_compact()

    # Add 400 tokens (1600 chars)
    compactor.record_turn("x" * 1600)
    assert not compactor.should_compact()

    # Add another 200 tokens (800 chars) -> 600 tokens total >= 500
    compactor.record_turn("x" * 800)
    assert compactor.should_compact()


def test_compactor_turn_threshold_trigger():
    compactor = ContextCompactor(context_window=100000, threshold_ratio=0.50, turn_threshold=3)
    compactor.record_turn("short")
    compactor.record_turn("short")
    assert not compactor.should_compact()
    compactor.record_turn("short")
    assert compactor.should_compact()


def test_compactor_compact_and_reset(tmp_path):
    compactor = ContextCompactor(context_window=1000, threshold_ratio=0.50, turn_threshold=5)
    compactor.record_turn("output" * 200)

    tasks = [
        {"id": "t1", "status": "done"},
        {"id": "t2", "status": "running"},
        {"id": "t3", "status": "pending"},
    ]
    worker_outputs = [
        "worker 1 finished tests successfully",
        "worker 2 " + ("detailed log output " * 50),
    ]
    contracts = ["wcao/design/architecture.md"]

    compacted = compactor.compact(
        root_goal="Implement Hermes memory",
        tasks=tasks,
        worker_outputs=worker_outputs,
        design_contracts=contracts,
    )

    assert compacted["root_goal"] == "Implement Hermes memory"
    assert compacted["tasks_summary"]["done"] == 1
    assert compacted["tasks_summary"]["running"] == 1
    assert compacted["tasks_summary"]["pending"] == 1
    assert compacted["design_contracts"] == contracts
    assert len(compacted["recent_output_diffs"]) == 2
    # Check truncation of long output
    assert "[truncated]" in compacted["recent_output_diffs"][1]

    # After compaction, turn count should be 0 and should_compact should be False
    assert compactor.state.turn_count == 0
    assert not compactor.should_compact()


def test_compactor_checkpoint_to_now_md(tmp_path):
    compactor = ContextCompactor()
    now_file = tmp_path / "now.md"
    now_file.write_text("# now.md\n\n## Immediate Tasks\n- Task 1\n")

    compacted = compactor.compact(
        root_goal="Testing checkpoint",
        tasks=[{"id": "t1", "status": "done"}],
        worker_outputs=["all tests pass"],
        design_contracts=["wcao/design/spec.md"],
    )

    compactor.checkpoint_to_now_md(now_file, compacted)
    content = now_file.read_text()
    assert "## Context Compaction Checkpoint" in content
    assert "Testing checkpoint" in content
    assert "wcao/design/spec.md" in content

    # Test re-compaction updates in place
    compacted2 = compactor.compact(
        root_goal="Testing checkpoint 2",
        tasks=[{"id": "t1", "status": "done"}, {"id": "t2", "status": "done"}],
        worker_outputs=["second wave finished"],
    )
    compactor.checkpoint_to_now_md(now_file, compacted2)
    updated_content = now_file.read_text()
    assert "Testing checkpoint 2" in updated_content
    # Should only have one checkpoint header
    assert updated_content.count("## Context Compaction Checkpoint") == 1
