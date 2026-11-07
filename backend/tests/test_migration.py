"""
CarbonLedger AI — Migration Upgrade & Downgrade Tests
=====================================================
Verifies that Alembic migrations upgrade to head and downgrade to base cleanly.
"""

from __future__ import annotations

import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from alembic import command
from alembic.config import Config


@pytest.fixture(scope="module")
def alembic_config():
    ini_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg = Config(ini_path)
    # Use dedicated test migration sqlite database
    test_db = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_alembic_cycle.db"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{test_db}")
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"

    yield cfg, test_db

    # Teardown
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass


def test_alembic_upgrade_head(alembic_config):
    """Verify that all migrations apply cleanly to head."""
    cfg, test_db = alembic_config
    command.upgrade(cfg, "head")
    assert os.path.exists(test_db), "Database file was not created by migration"


def test_alembic_downgrade_base(alembic_config):
    """Verify that all migrations can be cleanly rolled back to base."""
    cfg, _ = alembic_config
    command.downgrade(cfg, "base")


def test_alembic_reupgrade_head(alembic_config):
    """Verify that re-applying migrations after rollback works without collision."""
    cfg, _ = alembic_config
    command.upgrade(cfg, "head")
