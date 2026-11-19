"""003_phase4_task_ownership

Revision ID: 003_phase4
Revises: 002_phase3
Create Date: 2026-11-20 02:40:00 UTC

Phase 4 Migration:
- Extends tasks table with operational task ownership and handoff attributes:
  * patient_id (UUID FK to patients.id ondelete CASCADE, indexed)
  * completed_by_id (String(128) tracking closing actor user/clinician ID)
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "003_phase4"
down_revision: Union[str, None] = "002_phase3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "tasks" in existing_tables:
        existing_cols = [c["name"] for c in inspector.get_columns("tasks")]
        with op.batch_alter_table("tasks") as batch_op:
            if "patient_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "patient_id",
                        sa.Uuid(as_uuid=True) if bind.dialect.name == "postgresql" else sa.CHAR(32),
                        sa.ForeignKey("patients.id", ondelete="CASCADE"),
                        nullable=True
                    )
                )
                batch_op.create_index("ix_tasks_patient_id", ["patient_id"])

            if "completed_by_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column("completed_by_id", sa.String(length=128), nullable=True)
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "tasks" in existing_tables:
        existing_cols = [c["name"] for c in inspector.get_columns("tasks")]
        with op.batch_alter_table("tasks") as batch_op:
            if "completed_by_id" in existing_cols:
                batch_op.drop_column("completed_by_id")
            if "patient_id" in existing_cols:
                try:
                    batch_op.drop_index("ix_tasks_patient_id")
                except Exception:
                    pass
                batch_op.drop_column("patient_id")
