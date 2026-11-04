import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Throwaway SQLite database for the whole test run; never the dev/live DB.
_TMP = tempfile.mkdtemp(prefix="attendance-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["API_KEY"] = ""  # set before dotenv loads, so a key in a local .env is ignored

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from config.database import engine, run_migrations  # noqa: E402
from main import app  # noqa: E402

run_migrations()


@pytest.fixture(autouse=True)
def clean_db():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM attendance_records"))
        conn.execute(text("DELETE FROM upload_batches"))
    yield


@pytest.fixture
def client():
    return TestClient(app)


HEADER = "No,DN,UID,Name,Status,Action,APB,JobCode,DateTime\n"


@pytest.fixture
def make_csv():
    def _make(*rows: str) -> bytes:
        return (HEADER + "\n".join(rows) + "\n").encode("utf-8")
    return _make
