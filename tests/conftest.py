"""
Shared pytest fixtures. Ensures STORE_BACKEND=local, an isolated temp SQLite DB / evidence
dir, and that the synthetic demo samples exist before any test runs. No network required.
"""
import os
import pytest

os.environ.setdefault("STORE_BACKEND", "local")

from app.demo_data import generate_all_demo_samples  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _demo_samples():
    generate_all_demo_samples(overwrite=False)
    yield


@pytest.fixture()
def local_store(tmp_path):
    """A LocalStore backed by an isolated temp DB + evidence dir."""
    from app.store.local import LocalStore
    return LocalStore(db_path=tmp_path / "evidence.db", evidence_dir=tmp_path / "evidence")
