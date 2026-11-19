"""001_phase1_unified_lifecycle

Revision ID: 001_phase1
Revises: 
Create Date: 2026-11-20 01:35:00 UTC

Phase 1 Migration:
- Relational table for authoritative 14-stage lifecycle tracking (case_lifecycle_stages)
- Notification persistence table (notifications)
- Intelligent doctor assignment table (doctor_assignments)
- Appointment dual-confirmation, versioning, and idempotency columns
- Referral clinical rationale separation, patient decision tracking, and idempotency columns
- Task priority, completion role, and idempotency columns
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "001_phase1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    # 1. Create notifications table if missing
    if "notifications" not in existing_tables:
        op.create_table(
            "notifications",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("role", sa.String(length=64), nullable=False, index=True),
            sa.Column("event_type", sa.String(length=64), nullable=False, index=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("priority", sa.String(length=32), nullable=False, server_default="normal"),
            sa.Column("case_id", sa.Uuid(as_uuid=True), sa.ForeignKey("care_cases.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("patient_id", sa.Uuid(as_uuid=True), sa.ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("action_link", sa.String(length=255), nullable=True),
            sa.Column("idempotency_key", sa.String(length=255), nullable=True, unique=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        )

    # 2. Create doctor_assignments table if missing
    if "doctor_assignments" not in existing_tables:
        op.create_table(
            "doctor_assignments",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("case_id", sa.Uuid(as_uuid=True), sa.ForeignKey("care_cases.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("doctor_id", sa.Uuid(as_uuid=True), sa.ForeignKey("case_owners.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("status", sa.String(length=64), nullable=False, server_default="PENDING_DOCTOR_RESPONSE", index=True),
            sa.Column("specialty_matched", sa.String(length=128), nullable=False),
            sa.Column("subspecialty_matched", sa.String(length=128), nullable=True),
            sa.Column("urgency_level", sa.String(length=32), nullable=False, server_default="standard"),
            sa.Column("allocation_score", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("allocation_factors", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("assigned_by_role", sa.String(length=64), nullable=False, server_default="ai_allocation_agent"),
            sa.Column("assigned_by_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column("reassignment_reason", sa.Text(), nullable=True),
            sa.Column("deadline", sa.DateTime(timezone=True), nullable=False, index=True),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decline_reason", sa.Text(), nullable=True),
            sa.Column("escalated_to_coordinator_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("idempotency_key", sa.String(length=255), nullable=True, unique=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        )

    # 3. Create case_lifecycle_stages table if missing
    if "case_lifecycle_stages" not in existing_tables:
        op.create_table(
            "case_lifecycle_stages",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("case_id", sa.Uuid(as_uuid=True), sa.ForeignKey("care_cases.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("stage_number", sa.Integer(), nullable=False, index=True),
            sa.Column("stage_id", sa.String(length=64), nullable=False, index=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending", index=True),
            sa.Column("responsible_role", sa.String(length=64), nullable=False),
            sa.Column("responsible_id", sa.String(length=64), nullable=True),
            sa.Column("responsible_name", sa.String(length=255), nullable=True),
            sa.Column("evidence_type", sa.String(length=128), nullable=True, index=True),
            sa.Column("evidence_id", sa.String(length=128), nullable=True),
            sa.Column("evidence_data", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("patient_notification_sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.UniqueConstraint("case_id", "stage_number", name="uq_case_stage_number"),
        )

    # 4. Alter appointments table if it exists
    if "appointments" in existing_tables:
        with op.batch_alter_table("appointments") as batch_op:
            existing_cols = [c["name"] for c in inspector.get_columns("appointments")]
            if "version" not in existing_cols:
                batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
            if "doctor_confirmed" not in existing_cols:
                batch_op.add_column(sa.Column("doctor_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("0")))
            if "doctor_confirmed_at" not in existing_cols:
                batch_op.add_column(sa.Column("doctor_confirmed_at", sa.DateTime(timezone=True), nullable=True))
            if "doctor_confirmed_version" not in existing_cols:
                batch_op.add_column(sa.Column("doctor_confirmed_version", sa.Integer(), nullable=True))
            if "patient_confirmed" not in existing_cols:
                batch_op.add_column(sa.Column("patient_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("0")))
            if "patient_confirmed_at" not in existing_cols:
                batch_op.add_column(sa.Column("patient_confirmed_at", sa.DateTime(timezone=True), nullable=True))
            if "patient_confirmed_version" not in existing_cols:
                batch_op.add_column(sa.Column("patient_confirmed_version", sa.Integer(), nullable=True))
            if "proposed_by_role" not in existing_cols:
                batch_op.add_column(sa.Column("proposed_by_role", sa.String(length=64), nullable=True))
            if "proposed_by_id" not in existing_cols:
                batch_op.add_column(sa.Column("proposed_by_id", sa.String(length=64), nullable=True))
            if "idempotency_key" not in existing_cols:
                batch_op.add_column(sa.Column("idempotency_key", sa.String(length=255), nullable=True, unique=True))

    # 5. Alter referrals table if it exists
    if "referrals" in existing_tables:
        with op.batch_alter_table("referrals") as batch_op:
            existing_cols = [c["name"] for c in inspector.get_columns("referrals")]
            if "clinical_rationale" not in existing_cols:
                batch_op.add_column(sa.Column("clinical_rationale", sa.Text(), nullable=True))
            if "ai_educational_summary" not in existing_cols:
                batch_op.add_column(sa.Column("ai_educational_summary", sa.Text(), nullable=True))
            if "patient_decision" not in existing_cols:
                batch_op.add_column(sa.Column("patient_decision", sa.String(length=32), nullable=True))
            if "patient_decision_at" not in existing_cols:
                batch_op.add_column(sa.Column("patient_decision_at", sa.DateTime(timezone=True), nullable=True))
            if "patient_decision_notes" not in existing_cols:
                batch_op.add_column(sa.Column("patient_decision_notes", sa.Text(), nullable=True))
            if "idempotency_key" not in existing_cols:
                batch_op.add_column(sa.Column("idempotency_key", sa.String(length=255), nullable=True, unique=True))

    # 6. Alter tasks table if it exists
    if "tasks" in existing_tables:
        with op.batch_alter_table("tasks") as batch_op:
            existing_cols = [c["name"] for c in inspector.get_columns("tasks")]
            if "priority" not in existing_cols:
                batch_op.add_column(sa.Column("priority", sa.String(length=32), nullable=False, server_default="standard"))
            if "completed_by_role" not in existing_cols:
                batch_op.add_column(sa.Column("completed_by_role", sa.String(length=64), nullable=True))
            if "completion_evidence" not in existing_cols:
                batch_op.add_column(sa.Column("completion_evidence", sa.JSON(), nullable=True))
            if "idempotency_key" not in existing_cols:
                batch_op.add_column(sa.Column("idempotency_key", sa.String(length=255), nullable=True, unique=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    existing_tables = inspector.get_table_names()

    # Reverse alterations on tasks
    if "tasks" in existing_tables:
        existing_cols = [c["name"] for c in inspector.get_columns("tasks")]
        with op.batch_alter_table("tasks") as batch_op:
            if "idempotency_key" in existing_cols:
                batch_op.drop_column("idempotency_key")
            if "completion_evidence" in existing_cols:
                batch_op.drop_column("completion_evidence")
            if "completed_by_role" in existing_cols:
                batch_op.drop_column("completed_by_role")
            if "priority" in existing_cols:
                batch_op.drop_column("priority")

    # Reverse alterations on referrals
    if "referrals" in existing_tables:
        existing_cols = [c["name"] for c in inspector.get_columns("referrals")]
        with op.batch_alter_table("referrals") as batch_op:
            if "idempotency_key" in existing_cols:
                batch_op.drop_column("idempotency_key")
            if "patient_decision_notes" in existing_cols:
                batch_op.drop_column("patient_decision_notes")
            if "patient_decision_at" in existing_cols:
                batch_op.drop_column("patient_decision_at")
            if "patient_decision" in existing_cols:
                batch_op.drop_column("patient_decision")
            if "ai_educational_summary" in existing_cols:
                batch_op.drop_column("ai_educational_summary")
            if "clinical_rationale" in existing_cols:
                batch_op.drop_column("clinical_rationale")

    # Reverse alterations on appointments
    if "appointments" in existing_tables:
        existing_cols = [c["name"] for c in inspector.get_columns("appointments")]
        with op.batch_alter_table("appointments") as batch_op:
            if "idempotency_key" in existing_cols:
                batch_op.drop_column("idempotency_key")
            if "proposed_by_id" in existing_cols:
                batch_op.drop_column("proposed_by_id")
            if "proposed_by_role" in existing_cols:
                batch_op.drop_column("proposed_by_role")
            if "patient_confirmed_version" in existing_cols:
                batch_op.drop_column("patient_confirmed_version")
            if "patient_confirmed_at" in existing_cols:
                batch_op.drop_column("patient_confirmed_at")
            if "patient_confirmed" in existing_cols:
                batch_op.drop_column("patient_confirmed")
            if "doctor_confirmed_version" in existing_cols:
                batch_op.drop_column("doctor_confirmed_version")
            if "doctor_confirmed_at" in existing_cols:
                batch_op.drop_column("doctor_confirmed_at")
            if "doctor_confirmed" in existing_cols:
                batch_op.drop_column("doctor_confirmed")
            if "version" in existing_cols:
                batch_op.drop_column("version")

    # Drop created tables
    if "case_lifecycle_stages" in existing_tables:
        op.drop_table("case_lifecycle_stages")
    if "doctor_assignments" in existing_tables:
        op.drop_table("doctor_assignments")
    if "notifications" in existing_tables:
        op.drop_table("notifications")
