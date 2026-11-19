"""
Phase 6 Migration: Add correlation_id and actor_id to traces and audit_logs.
"""

MIGRATION = {
    "description": "Phase 6: add correlation_id and actor_id to traces and audit_logs",
    "upgrade_sql": [
        "ALTER TABLE workflow_execution_traces ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(128)",
        "ALTER TABLE workflow_execution_traces ADD COLUMN IF NOT EXISTS actor_id VARCHAR(128)",
        "CREATE INDEX IF NOT EXISTS ix_wet_correlation_id ON workflow_execution_traces(correlation_id)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(128)",
        "CREATE INDEX IF NOT EXISTS ix_al_correlation_id ON audit_logs(correlation_id)",
    ],
    "downgrade_sql": [
        "ALTER TABLE workflow_execution_traces DROP COLUMN IF EXISTS correlation_id",
        "ALTER TABLE workflow_execution_traces DROP COLUMN IF EXISTS actor_id",
        "ALTER TABLE audit_logs DROP COLUMN IF EXISTS correlation_id",
    ]
}
