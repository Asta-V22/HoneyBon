"""github import and tag reviews

Revision ID: b7e3c1d9a2f4
Revises: a494e82ef2a6
Create Date: 2026-10-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e3c1d9a2f4"
down_revision: str | None = "a494e82ef2a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENUM = {"native_enum": False, "length": 32}


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column(
            "kind",
            sa.Enum("full", "tags", name="reviewkind", **_ENUM),
            nullable=False,
            server_default="full",
        ),
    )
    op.add_column("submissions", sa.Column("import_job_id", sa.Uuid(), nullable=True))
    op.create_index("ix_submissions_import_job_id", "submissions", ["import_job_id"])
    op.create_foreign_key(
        "submissions_import_job_id_fkey",
        "submissions",
        "import_jobs",
        ["import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )

    status = sa.Enum(
        "pending", "running", "completed", "failed", "cancelled", name="importstatus", **_ENUM
    )
    for name, column in [
        ("imported", sa.Integer()),
        ("duplicates", sa.Integer()),
        ("analysis_total", sa.Integer()),
        ("analysis_done", sa.Integer()),
        ("analysis_failed", sa.Integer()),
    ]:
        op.add_column("import_jobs", sa.Column(name, column, nullable=False, server_default="0"))
    op.add_column("import_jobs", sa.Column("analysis_status", status, nullable=True))
    op.add_column(
        "import_jobs", sa.Column("analysis_provider", sa.String(length=32), nullable=True)
    )
    op.add_column("import_jobs", sa.Column("analysis_model", sa.String(length=100), nullable=True))
    op.add_column("import_jobs", sa.Column("analysis_error", sa.Text(), nullable=True))
    op.add_column(
        "import_jobs",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    for name in [
        "updated_at",
        "analysis_error",
        "analysis_model",
        "analysis_provider",
        "analysis_status",
        "analysis_failed",
        "analysis_done",
        "analysis_total",
        "duplicates",
        "imported",
    ]:
        op.drop_column("import_jobs", name)
    op.drop_constraint("submissions_import_job_id_fkey", "submissions", type_="foreignkey")
    op.drop_index("ix_submissions_import_job_id", table_name="submissions")
    op.drop_column("submissions", "import_job_id")
    op.drop_column("reviews", "kind")
