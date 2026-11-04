"""Flexible import: optional device columns, extra data, import profiles, AI usage log.

- The device columns (no, dn, status, action, apb, job_code) become optional, because
  a 2-column file has none of them. Existing values are untouched.
- ``extra`` keeps every unmapped column as JSON, so a 100-column file loses nothing.
- ``day_status`` holds a day mark with no clock time (P, A, Leave...).
- No rows are changed or deleted by this migration.

Revision ID: 0003_flexible_import
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_flexible_import"
down_revision = "0002_punch_at"
branch_labels = None
depends_on = None

OPTIONAL_NOW = ("no", "dn", "status", "action", "apb", "job_code")


def upgrade():
    with op.batch_alter_table("attendance_records") as batch:
        for column in OPTIONAL_NOW:
            batch.alter_column(column, existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("extra", sa.Text(), nullable=True))
        batch.add_column(sa.Column("day_status", sa.String(20), nullable=True))

    op.create_table(
        "import_profiles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("shape", sa.String(20), nullable=False),
        sa.Column("columns_json", sa.Text(), nullable=False),
        sa.Column("date_order", sa.String(3), nullable=False, server_default="DMY"),
        sa.Column("signature", sa.String(40), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("feature", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("ok", sa.Boolean, nullable=False),
        sa.Column("error", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    # Rows from files without device columns would violate NOT NULL, so the
    # columns stay nullable; only the additions are removed.
    op.drop_table("ai_usage")
    op.drop_table("import_profiles")
    with op.batch_alter_table("attendance_records") as batch:
        batch.drop_column("day_status")
        batch.drop_column("extra")
