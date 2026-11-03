"""Database connection.

Works with SQLite (default, zero setup), MySQL/MariaDB (typical shared hosting)
and PostgreSQL. Pick one with ``DATABASE_URL``; the legacy ``DB_*`` variables
still build a PostgreSQL URL when ``DB_PASSWORD`` is set.
"""
import logging
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_SQLITE_URL = "sqlite:///./data/attendance.db"


def resolve_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    password = os.getenv("DB_PASSWORD")
    if password:
        return "postgresql://{user}:{pw}@{host}:{port}/{name}".format(
            user=quote_plus(os.getenv("DB_USER", "postgres")),
            pw=quote_plus(password),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            name=os.getenv("DB_NAME", "attendanceapp"),
        )
    return DEFAULT_SQLITE_URL


def safe_url(url: str) -> str:
    """URL with the password hidden, for logs."""
    return make_url(url).render_as_string(hide_password=True)


def _make_engine(url: str):
    kwargs = {"echo": os.getenv("ECHO_SQL", "False").lower() == "true", "pool_pre_ping": True}
    if url.startswith("sqlite"):
        db_path = make_url(url).database
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_recycle"] = 300
    return create_engine(url, **kwargs)


DATABASE_URL = resolve_database_url()
engine = _make_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as e:  # noqa: BLE001 - report any driver error as "down"
        logger.warning("Database connection failed: %s", type(e).__name__)
        return False


def run_migrations() -> None:
    """Bring the schema up to date with Alembic.

    A database created by the old ``create_all`` code (tables present but no
    ``alembic_version``) is stamped at the baseline revision first, so its data
    is migrated instead of re-created.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.attributes["engine"] = engine

    tables = set(inspect(engine).get_table_names())
    if "attendance_records" in tables and "alembic_version" not in tables:
        logger.info("Existing pre-migration database found; stamping baseline")
        command.stamp(cfg, "0001_baseline")
    command.upgrade(cfg, "head")
