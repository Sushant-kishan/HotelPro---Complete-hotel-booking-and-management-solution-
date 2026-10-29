"""
Pytest configuration for HotelPro test suite.
Configures an isolated SQLite database test_hotelpro.db and resets state per test run.
"""
import os
import pytest
from app.config import settings
from app.database import init_db, _local
from app.seed import seed_demo_data

@pytest.fixture(autouse=True, scope="session")
def setup_test_db():
    test_db = "test_hotelpro.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    
    settings.DATABASE_PATH = test_db
    if hasattr(_local, "conn"):
        _local.conn = None

    init_db()
    seed_demo_data()
    yield

    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None
    if os.path.exists(test_db):
        os.remove(test_db)

