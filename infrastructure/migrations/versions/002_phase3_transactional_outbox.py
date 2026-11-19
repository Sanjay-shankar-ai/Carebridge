"""002_phase3_transactional_outbox

Revision ID: 002_phase3
Revises: 001_phase1
Create Date: 2026-11-20 02:15:00 UTC

Phase 3 Migration:
- Extends notifications table with transactional outbox delivery tracking:
  * status ('pending', 'processing', 'delivered', 'failed', 'dead_letter')
  * retry_count
  * max_retries
  * last_error
  * next_attempt_at
  * processing_started_at
  * delivered_at
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "002_phase3"
down_revision: Union[str, None] = "001_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "notifications" in existing_tables:
        existing_cols = [c["name"] for c in inspector.get_columns("notifications")]
        with op.batch_alter_table("notifications") as batch_op:
            if "status" not in existing_cols:
                batch_op.add_column(
                    sa.Column("status", sa.String(length=32), nullable=False, server_default="delivered")
                )
            if "retry_count" not in existing_cols:
                batch_op.add_column(
                    sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")
                )
            if "max_retries" not in existing_cols:
                batch_op.add_column(
                    sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3")
                )
            if "last_error" not in existing_cols:
                batch_op.add_column(
                    sa.Column("last_error", sa.Text(), nullable=True)
                )
            if "next_attempt_at" not in existing_cols:
                batch_op.add_column(
                    sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True)
                )
            if "processing_started_at" not in existing_cols:
                batch_op.add_column(
                    sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True)
                )
            if "delivered_at" not in existing_cols:
                batch_op.add_column(
                    sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True)
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "notifications" in existing_tables:
        existing_cols = [c["name"] for c in inspector.get_columns("notifications")]
        with op.batch_alter_table("notifications") as batch_op:
            if "delivered_at" in existing_cols:
                batch_op.drop_column("delivered_at")
            if "processing_started_at" in existing_cols:
                batch_op.drop_column("processing_started_at")
            if "next_attempt_at" in existing_cols:
                batch_op.drop_column("next_attempt_at")
            if "last_error" in existing_cols:
                batch_op.drop_column("last_error")
            if "max_retries" in existing_cols:
                batch_op.drop_column("max_retries")
            if "retry_count" in existing_cols:
                batch_op.drop_column("retry_count")
            if "status" in existing_cols:
                batch_op.drop_column("status")
