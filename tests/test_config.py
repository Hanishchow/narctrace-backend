"""
Tests for production-mode configuration guards.
"""
import subprocess
import sys


def test_production_mode_rejects_demo_key():
    """Server must refuse to start in production with the demo signing key."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "os.environ['NARCTRACE_ENV'] = 'production'; "
                "os.environ['EVIDENCE_SIGNING_KEY'] = 'local-demo-evidence-key'; "
                "from app.config import get_settings; get_settings()"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, "Expected non-zero exit when demo key used in production"
    assert "EVIDENCE_SIGNING_KEY" in result.stderr


def test_production_mode_accepts_custom_key():
    """Server must start normally in production when a real key is set."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "os.environ['NARCTRACE_ENV'] = 'production'; "
                "os.environ['EVIDENCE_SIGNING_KEY'] = 'real-strong-secret-key-for-testing'; "
                "from app.config import get_settings; s = get_settings(); print(s.is_production)"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Expected clean start with custom key; stderr: {result.stderr}"
    assert "True" in result.stdout


def test_development_mode_allows_demo_key():
    """Demo key must be fine in development (the default mode)."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "os.environ.pop('NARCTRACE_ENV', None); "
                "from app.config import get_settings; s = get_settings(); print(s.EVIDENCE_SIGNING_KEY)"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Expected clean start in dev mode; stderr: {result.stderr}"
    assert "local-demo-evidence-key" in result.stdout
