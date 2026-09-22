"""Unit tests for run/cao_tamper.py — Anti-Test-Tampering Gate."""
from pathlib import Path
from unittest.mock import MagicMock, patch

from run.cao_tamper import detect_test_tampering, revert_test_tampering


def test_tamper_no_changes(tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        is_tampered, msg, files = detect_test_tampering(tmp_path)
        assert is_tampered is False
        assert msg == ""
        assert files == []


def test_tamper_deleted_assertion(tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    fake_diff = """--- a/tests/test_api.py
+++ b/tests/test_api.py
@@ -10,1 +10,0 @@
-    assert resp.status_code == 200
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_diff)
        is_tampered, msg, files = detect_test_tampering(tmp_path)
        assert is_tampered is True
        assert "Deleted test assertion" in msg
        assert "tests/test_api.py" in files


def test_tamper_dummy_assert_bypass(tmp_path: Path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    fake_diff = """--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -15,1 +15,1 @@
+    assert True
"""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=fake_diff)
        is_tampered, msg, files = detect_test_tampering(tmp_path)
        assert is_tampered is True
        assert "Inserted dummy assert True" in msg
        assert "tests/test_auth.py" in files


def test_revert_tampering(tmp_path: Path):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ok = revert_test_tampering(tmp_path, ["tests/test_api.py"])
        assert ok is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["git", "checkout", "--", "tests/test_api.py"]
