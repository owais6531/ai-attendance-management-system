"""Add a real punch timestamp and the duplicate-check index.

- Adds ``attendance_records.punch_at`` and fills it from the old text column.
- Adds an index on (uid, punch_at). It is UNIQUE when the existing data has no
  duplicate punches; otherwise it is a normal index and a warning is logged.
  No rows are ever deleted by this migration.

Revision ID: 0002_punch_at
"""
import logging
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision = "0002_punch_at"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0002")
FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M")


def _parse(value):
    for fmt in FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt)
        except ValueError:
            continue
    return None


def upgrade():
    bind = op.get_bind()
    with op.batch_alter_table("attendance_records") as batch:
        batch.add_column(sa.Column("punch_at", sa.DateTime, nullable=True))

    records = sa.table(
        "attendance_records",
        sa.column("id", sa.Integer),
        sa.column("date_time", sa.String),
        sa.column("punch_at", sa.DateTime),
    )
    rows = bind.execute(sa.select(records.c.id, records.c.date_time)).fetchall()
    unparsed = 0
    for row_id, text_value in rows:
        parsed = _parse(text_value)
        if parsed is None:
            unparsed += 1
            continue
        bind.execute(records.update().where(records.c.id == row_id).values(punch_at=parsed))
    if unparsed:
        log.warning("%s existing rows have an unreadable date_time; punch_at left empty", unparsed)

    duplicate_groups = bind.execute(sa.text(
        "SELECT COUNT(*) FROM (SELECT uid, punch_at FROM attendance_records "
        "WHERE punch_at IS NOT NULL GROUP BY uid, punch_at HAVING COUNT(*) > 1) d"
    )).scalar()
    if duplicate_groups:
        log.warning(
            "%s duplicate punch groups already exist; creating a NON-unique index. "
            "New uploads are still de-duplicated by the app. "
            "Run scripts/find_duplicates.py to review them.", duplicate_groups,
        )
    op.create_index("ix_attendance_uid_punch", "attendance_records", ["uid", "punch_at"],
                    unique=not duplicate_groups)
    op.create_index("ix_attendance_records_batch_id", "attendance_records", ["batch_id"])


def downgrade():
    op.drop_index("ix_attendance_records_batch_id", table_name="attendance_records")
    op.drop_index("ix_attendance_uid_punch", table_name="attendance_records")
    with op.batch_alter_table("attendance_records") as batch:
        batch.drop_column("punch_at")
