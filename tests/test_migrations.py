"""An old database (created by the original create_all code) must migrate without data loss."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import config.database as dbconf

ROOT = Path(dbconf.__file__).resolve().parent.parent


def _index(engine, name):
    return {i["name"]: i for i in inspect(engine).get_indexes("attendance_records")}[name]


def test_legacy_database_is_migrated_and_keeps_rows(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.attributes["engine"] = engine
    command.upgrade(cfg, "0001_baseline")
    with engine.begin() as c:
        c.execute(text("DROP TABLE alembic_version"))  # now looks exactly like a create_all() database
        for uid in ("0001", "0001", "0002"):          # includes a duplicate, like real old data
            c.execute(text("INSERT INTO attendance_records (no,dn,uid,name,date_time,status,action,apb,job_code) "
                           "VALUES (1,1,:u,'Demo','2025/07/01 09:47:00',0,1,0,0)"), {"u": uid})

    monkeypatch.setattr(dbconf, "engine", engine)
    dbconf.run_migrations()

    with engine.connect() as c:
        rows = c.execute(text("SELECT uid, punch_at FROM attendance_records")).fetchall()
    assert len(rows) == 3 and all(r[1] is not None for r in rows)
    # Duplicates present -> index is non-unique and nothing was deleted.
    assert not _index(engine, "ix_attendance_uid_punch")["unique"]


def test_fresh_database_gets_unique_index():
    assert _index(dbconf.engine, "ix_attendance_uid_punch")["unique"]
