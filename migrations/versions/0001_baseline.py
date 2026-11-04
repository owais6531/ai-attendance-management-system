"""Baseline: schema as created by the original create_all() code.

Revision ID: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("no", sa.Integer, nullable=False),
        sa.Column("dn", sa.Integer, nullable=False),
        sa.Column("uid", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("date_time", sa.String(50), nullable=False),
        sa.Column("status", sa.Integer, nullable=False),
        sa.Column("action", sa.Integer, nullable=False),
        sa.Column("apb", sa.Integer, nullable=False),
        sa.Column("job_code", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("batch_id", sa.String(100), nullable=True),
        sa.Column("is_processed", sa.Boolean, nullable=True),
    )
    op.create_index("ix_attendance_records_id", "attendance_records", ["id"])
    op.create_table(
        "upload_batches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(100), nullable=False, unique=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("total_records", sa.Integer, nullable=True),
        sa.Column("successful_records", sa.Integer, nullable=True),
        sa.Column("failed_records", sa.Integer, nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_upload_batches_id", "upload_batches", ["id"])


def downgrade():
    op.drop_table("upload_batches")
    op.drop_table("attendance_records")
