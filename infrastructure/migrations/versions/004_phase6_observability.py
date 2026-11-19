"""004_phase6_observability

Revision ID: 004_phase6
Revises: 003_phase4
Create Date: 2026-11-20 05:20:00 UTC

Phase 6 Migration: Observability, Traceability, and Failure Recovery
- Extends workflow_execution_traces with structured telemetry & attribution:
    * correlation_id (String 128, indexed)
    * workflow_id (String 128, indexed)
    * conversation_id (String 128, indexed)
    * actor_id (String 128, indexed)
    * role (String 64)
    * patient_id (UUID FK to patients.id ondelete SET NULL, indexed)
    * intent (String 128)
    * routing_decision (String 128)
    * selected_agent (String 128)
    * tool_name (String 128)
    * domain_action (String 128)
    * db_result (String 32, default 'ok')
    * event_id (String 128)
    * notification_id (String 128)
    * lifecycle_transition (String 128)
    * retry_count (Integer, default 0)
- Extends audit_logs with correlation & workflow tracking:
    * correlation_id (String 128, indexed)
    * workflow_id (String 128, indexed)
- Extends care_cases with optimistic concurrency versioning:
    * version (Integer, default 1, non-nullable)
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "004_phase6"
down_revision: Union[str, None] = "003_phase4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    # 1. workflow_execution_traces extensions
    if "workflow_execution_traces" in existing_tables:
        cols = [c["name"] for c in inspector.get_columns("workflow_execution_traces")]
        with op.batch_alter_table("workflow_execution_traces") as batch_op:
            if "correlation_id" not in cols:
                batch_op.add_column(sa.Column("correlation_id", sa.String(128), nullable=True))
                batch_op.create_index("ix_wet_correlation_id", ["correlation_id"])
            if "workflow_id" not in cols:
                batch_op.add_column(sa.Column("workflow_id", sa.String(128), nullable=True))
                batch_op.create_index("ix_wet_workflow_id", ["workflow_id"])
            if "conversation_id" not in cols:
                batch_op.add_column(sa.Column("conversation_id", sa.String(128), nullable=True))
                batch_op.create_index("ix_wet_conversation_id", ["conversation_id"])
            if "actor_id" not in cols:
                batch_op.add_column(sa.Column("actor_id", sa.String(128), nullable=True))
                batch_op.create_index("ix_wet_actor_id", ["actor_id"])
            if "role" not in cols:
                batch_op.add_column(sa.Column("role", sa.String(64), nullable=True))
            if "patient_id" not in cols:
                batch_op.add_column(
                    sa.Column(
                        "patient_id",
                        sa.Uuid(as_uuid=True) if bind.dialect.name == "postgresql" else sa.CHAR(32),
                        sa.ForeignKey("patients.id", ondelete="SET NULL"),
                        nullable=True
                    )
                )
                batch_op.create_index("ix_wet_patient_id", ["patient_id"])
            if "intent" not in cols:
                batch_op.add_column(sa.Column("intent", sa.String(128), nullable=True))
            if "routing_decision" not in cols:
                batch_op.add_column(sa.Column("routing_decision", sa.String(128), nullable=True))
            if "selected_agent" not in cols:
                batch_op.add_column(sa.Column("selected_agent", sa.String(128), nullable=True))
            if "tool_name" not in cols:
                batch_op.add_column(sa.Column("tool_name", sa.String(128), nullable=True))
            if "domain_action" not in cols:
                batch_op.add_column(sa.Column("domain_action", sa.String(128), nullable=True))
            if "db_result" not in cols:
                batch_op.add_column(sa.Column("db_result", sa.String(32), server_default="ok", nullable=True))
            if "event_id" not in cols:
                batch_op.add_column(sa.Column("event_id", sa.String(128), nullable=True))
            if "notification_id" not in cols:
                batch_op.add_column(sa.Column("notification_id", sa.String(128), nullable=True))
            if "lifecycle_transition" not in cols:
                batch_op.add_column(sa.Column("lifecycle_transition", sa.String(128), nullable=True))
            if "retry_count" not in cols:
                batch_op.add_column(sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False))

    # 2. audit_logs extensions
    if "audit_logs" in existing_tables:
        cols = [c["name"] for c in inspector.get_columns("audit_logs")]
        with op.batch_alter_table("audit_logs") as batch_op:
            if "correlation_id" not in cols:
                batch_op.add_column(sa.Column("correlation_id", sa.String(128), nullable=True))
                batch_op.create_index("ix_al_correlation_id", ["correlation_id"])
            if "workflow_id" not in cols:
                batch_op.add_column(sa.Column("workflow_id", sa.String(128), nullable=True))
                batch_op.create_index("ix_al_workflow_id", ["workflow_id"])

    # 3. care_cases extensions
    if "care_cases" in existing_tables:
        cols = [c["name"] for c in inspector.get_columns("care_cases")]
        with op.batch_alter_table("care_cases") as batch_op:
            if "version" not in cols:
                batch_op.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    if "care_cases" in existing_tables:
        cols = [c["name"] for c in inspector.get_columns("care_cases")]
        with op.batch_alter_table("care_cases") as batch_op:
            if "version" in cols:
                batch_op.drop_column("version")

    if "audit_logs" in existing_tables:
        cols = [c["name"] for c in inspector.get_columns("audit_logs")]
        with op.batch_alter_table("audit_logs") as batch_op:
            if "workflow_id" in cols:
                batch_op.drop_index("ix_al_workflow_id")
                batch_op.drop_column("workflow_id")
            if "correlation_id" in cols:
                batch_op.drop_index("ix_al_correlation_id")
                batch_op.drop_column("correlation_id")

    if "workflow_execution_traces" in existing_tables:
        cols = [c["name"] for c in inspector.get_columns("workflow_execution_traces")]
        with op.batch_alter_table("workflow_execution_traces") as batch_op:
            for col in [
                "retry_count", "lifecycle_transition", "notification_id", "event_id",
                "db_result", "domain_action", "tool_name", "selected_agent",
                "routing_decision", "intent", "role"
            ]:
                if col in cols:
                    batch_op.drop_column(col)
            if "patient_id" in cols:
                batch_op.drop_index("ix_wet_patient_id")
                batch_op.drop_column("patient_id")
            if "actor_id" in cols:
                batch_op.drop_index("ix_wet_actor_id")
                batch_op.drop_column("actor_id")
            if "conversation_id" in cols:
                batch_op.drop_index("ix_wet_conversation_id")
                batch_op.drop_column("conversation_id")
            if "workflow_id" in cols:
                batch_op.drop_index("ix_wet_workflow_id")
                batch_op.drop_column("workflow_id")
            if "correlation_id" in cols:
                batch_op.drop_index("ix_wet_correlation_id")
                batch_op.drop_column("correlation_id")
