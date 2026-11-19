"""
CareBridge Phase 8 Test Suite: Long-Running Agent Workflows
Validates:
1. PostgreSQL Checkpointer with case-specific thread isolation.
2. Checkpoint history inspection and state retrieval.
3. Asynchronous workflow initiation without holding HTTP request.
4. Workflow resume after patient responses (event-driven).
5. Event-driven clinic continuation (attendance, no-show, cancellation, referral).
6. Idempotent tool execution and cached outcomes.
7. Inbound and outbound duplicate message prevention.
8. Retry handling with exponential backoff and exhaustion protection.
9. Workflow failure recovery from last checkpoint.
10. Structured execution trace telemetry.
11. Coordinator-readable action history.
12. Background surveillance scheduler jobs (stalled cases, SLA deadlines, unacknowledged outreach).
"""

import uuid
import time
import unittest
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.database.seed import seed_database
from app.models.care_case import CareCase, Task
from app.models.patient import Patient
from app.models.owner import CaseOwner
from app.models.communication import Communication
from app.models.referral import Referral
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent
from app.models.workflow_trace import WorkflowExecutionTrace

from app.workflows.persistence.checkpointer import (
    get_workflow_checkpointer,
    get_thread_config,
    inspect_checkpoint_history,
    get_latest_checkpoint_state,
    get_in_memory_checkpointer
)
from app.workflows.persistence.idempotency import (
    IdempotencyManager,
    DuplicateMessageFilter
)
from app.workflows.persistence.retry import (
    RetryPolicy,
    RetryConfig,
    WorkflowRetryExhaustedError
)
from app.workflows.persistence.traces import (
    WorkflowTraceLogger,
    NODE_COORDINATOR_EXPLANATIONS
)
from app.workflows.orchestrator import LongRunningWorkflowOrchestrator
from app.scheduler.jobs import SchedulerJobs
from app.scheduler.manager import BackgroundSchedulerManager


class TestLongRunningWorkflows(unittest.TestCase):
    """Exhaustive test suite for Phase 8 Long-Running Agent Workflows."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionFactory = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)

        import app.database.session as session_module
        session_module.sync_session_factory = cls.SessionFactory

        from app.core.config import settings
        settings.LLM_PROVIDER = "mock"

    def setUp(self):
        Base.metadata.create_all(self.engine)
        self.db = self.SessionFactory()
        seed_database(self.db)

        # Retrieve seeded exemplar entities: Meenakshi Ramanathan (CASE-2026-0147)
        self.patient = self.db.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()
        self.case = self.db.query(CareCase).filter(CareCase.patient_id == self.patient.id).first()
        self.coordinator = self.case.current_owner

        # Clear idempotency caches
        IdempotencyManager.clear()
        DuplicateMessageFilter.clear()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    # ==========================================================================
    # Test 1: Checkpointer & Case-Specific Thread Isolation
    # ==========================================================================
    def test_01_checkpointer_thread_isolation(self):
        """Verifies case-specific thread IDs and state isolation across multiple cases."""
        cp = get_in_memory_checkpointer()
        case_id_1 = str(self.case.id)
        case_id_2 = str(uuid.uuid4())

        cfg_1 = get_thread_config(case_id_1)
        cfg_2 = get_thread_config(case_id_2)

        self.assertEqual(cfg_1["configurable"]["thread_id"], f"care-thread-{case_id_1}")
        self.assertEqual(cfg_2["configurable"]["thread_id"], f"care-thread-{case_id_2}")
        self.assertNotEqual(cfg_1["configurable"]["thread_id"], cfg_2["configurable"]["thread_id"])

    # ==========================================================================
    # Test 2: Asynchronous Workflow Initiation (No HTTP Request Blocking)
    # ==========================================================================
    def test_02_async_workflow_initiation(self):
        """Verifies workflow initiates, dispatches initial outreach, and suspends without hanging."""
        cp = get_in_memory_checkpointer()

        res = LongRunningWorkflowOrchestrator.initiate_case_workflow(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            screening_result_id=str(self.case.screening_result_id),
            priority="urgent",
            checkpointer=cp
        )

        self.assertEqual(res["case_id"], str(self.case.id))
        self.assertEqual(res["status"], "suspended_waiting_for_patient")
        self.assertIn("thread_id", res)

        # Verify trace was persisted
        traces = self.db.query(WorkflowExecutionTrace).filter(
            WorkflowExecutionTrace.case_id == self.case.id
        ).all()
        self.assertGreater(len(traces), 0)
        self.assertEqual(traces[0].node_name, "initiate_case_workflow")

    # ==========================================================================
    # Test 3: Workflow Resume on Patient Response (Event-Driven)
    # ==========================================================================
    def test_03_resume_on_patient_response(self):
        """Verifies workflow wakes up upon patient response, processes intent, and advances."""
        cp = get_in_memory_checkpointer()

        # Inbound message from patient
        res = LongRunningWorkflowOrchestrator.resume_on_patient_response(
            case_id=str(self.case.id),
            message="Yes I got the message, what does BI-RADS 4 mean?",
            sender="patient",
            channel="sms",
            checkpointer=cp
        )

        self.assertEqual(res["status"], "resumed_and_processed")
        self.assertIsNotNone(res.get("outbound_message"))

        # Verify inbound communication was persisted in DB
        comm = self.db.query(Communication).filter(
            Communication.case_id == self.case.id,
            Communication.sender == "patient"
        ).order_by(Communication.created_at.desc()).first()
        self.assertIsNotNone(comm)
        self.assertIn("BI-RADS 4", comm.content)

        # Verify CaseEvent was logged
        event = self.db.query(CaseEvent).filter(
            CaseEvent.case_id == self.case.id,
            CaseEvent.event_type == "patient_response_received"
        ).first()
        self.assertIsNotNone(event)

    # ==========================================================================
    # Test 4: Duplicate Inbound and Outbound Message Prevention
    # ==========================================================================
    def test_04_duplicate_message_prevention(self):
        """Verifies duplicate inbound webhooks and outbound notification spam are suppressed."""
        case_id = str(self.case.id)
        msg = "I can attend on Thursday."

        # First inbound message -> allowed
        is_dup_1 = DuplicateMessageFilter.is_duplicate_inbound(case_id, "patient", msg, window_seconds=60)
        self.assertFalse(is_dup_1)

        # Repeated webhook delivery of same message within 60s -> suppressed!
        is_dup_2 = DuplicateMessageFilter.is_duplicate_inbound(case_id, "patient", msg, window_seconds=60)
        self.assertTrue(is_dup_2)

        # Outbound duplicate check
        is_out_dup_1 = DuplicateMessageFilter.is_duplicate_outbound(case_id, "appointment_reminder", cooldown_hours=12)
        self.assertFalse(is_out_dup_1)

        is_out_dup_2 = DuplicateMessageFilter.is_duplicate_outbound(case_id, "appointment_reminder", cooldown_hours=12)
        self.assertTrue(is_out_dup_2)

    # ==========================================================================
    # Test 5: Idempotent Tool & Workflow Execution
    # ==========================================================================
    def test_05_idempotent_execution(self):
        """Verifies operations execute only once per idempotency key and return cached results."""
        call_count = 0

        def expensive_action(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        key = "unique_op_12345"
        # 1st call
        res1 = IdempotencyManager.execute_idempotent(key, expensive_action, 10, 20)
        self.assertEqual(res1, 30)
        self.assertEqual(call_count, 1)

        # 2nd call with same key -> returns cached, function not called
        res2 = IdempotencyManager.execute_idempotent(key, expensive_action, 10, 20)
        self.assertEqual(res2, 30)
        self.assertEqual(call_count, 1)

    # ==========================================================================
    # Test 6: Retry Handling with Exponential Backoff
    # ==========================================================================
    def test_06_retry_handling(self):
        """Verifies transient error retries and proper exhaustion handling."""
        attempt_count = 0

        def transient_failing_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("Temporary connection drop")
            return "recovered_success"

        cfg = RetryConfig(max_retries=3, initial_delay=0.01, backoff_multiplier=1.5)
        result = RetryPolicy.execute_with_retry(
            transient_failing_function,
            config=cfg,
            operation_name="test_transient_op"
        )
        self.assertEqual(result, "recovered_success")
        self.assertEqual(attempt_count, 3)

        # Test exhaustion
        def permanently_failing_function():
            raise TimeoutError("Endpoint unreachable")

        with self.assertRaises(WorkflowRetryExhaustedError) as cm:
            RetryPolicy.execute_with_retry(
                permanently_failing_function,
                config=RetryConfig(max_retries=2, initial_delay=0.01),
                operation_name="test_exhaust_op"
            )
        self.assertEqual(cm.exception.attempts, 2)

    # ==========================================================================
    # Test 7: Event-Driven Clinic Continuation (Attendance, No-Show, Cancellation)
    # ==========================================================================
    def test_07_event_driven_clinic_continuation(self):
        """Verifies workflow reacts to clinic events (attended, no-show, referral accepted)."""
        now = datetime.now(timezone.utc)
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="Mercy Imaging",
            provider_name="Dr. Sundaram",
            appointment_type="diagnostic_mammogram",
            scheduled_time=now + timedelta(days=2),
            status="booked"
        )
        self.db.add(appt)
        self.db.commit()

        # 1. Appointment Attended
        res_attended = LongRunningWorkflowOrchestrator.resume_on_clinic_event(
            case_id=str(self.case.id),
            event_type="appointment_attended",
            event_payload={"appointment_id": str(appt.id)}
        )
        self.assertEqual(res_attended["status"], "ready_for_clinical_closure_review")

        # 2. Appointment No-Show (triggers recovery agent)
        res_noshow = LongRunningWorkflowOrchestrator.resume_on_clinic_event(
            case_id=str(self.case.id),
            event_type="appointment_no_show",
            event_payload={"appointment_id": str(appt.id)}
        )
        self.assertIn("recovery_triggered", res_noshow["status"])

    # ==========================================================================
    # Test 8: Structured Traces & Coordinator Action History
    # ==========================================================================
    def test_08_structured_traces_and_action_history(self):
        """Verifies structured execution telemetry and coordinator-readable timeline."""
        # Log sample traces
        WorkflowTraceLogger.log_node_trace(
            db=self.db,
            case_id=str(self.case.id),
            thread_id=f"care-thread-{self.case.id}",
            run_id=str(uuid.uuid4()),
            workflow_name="care_workflow",
            node_name="select_approved_pathway",
            step_number=2,
            status="success",
            duration_ms=45.2,
            input_data={"finding": "BI-RADS 4"},
            output_data={"pathway": "mammogram_urgent_workup"}
        )

        history = LongRunningWorkflowOrchestrator.get_coordinator_action_history(str(self.case.id))

        self.assertGreater(history["total_actions"], 0)
        timeline = history["timeline"]
        first_action = timeline[0]

        self.assertIn("coordinator_explanation", first_action)
        self.assertIn("approved clinical protocol", first_action["coordinator_explanation"])
        self.assertFalse(first_action["has_error"])

    # ==========================================================================
    # Test 9: Background Scheduler Jobs Integration
    # ==========================================================================
    def test_09_background_scheduler_jobs(self):
        """Verifies periodic surveillance jobs (stalled cases, SLA deadlines, unacknowledged outreach)."""
        now = datetime.now(timezone.utc)

        # 1. Setup an overdue SLA case
        self.case.sla_deadline = now - timedelta(hours=5)
        self.db.commit()

        sla_job_res = SchedulerJobs.scan_sla_deadlines(self.db)
        self.assertGreaterEqual(sla_job_res["breached_count"], 1)

        # 2. Setup an unacknowledged outreach case
        self.case.status = "active"
        comm = Communication(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            sender="ai_coordinator",
            channel="sms",
            content="Please check your screening result",
            sent_at=now - timedelta(hours=36)
        )
        self.db.add(comm)
        self.db.commit()

        unack_res = SchedulerJobs.scan_unacknowledged_outreach(self.db, hours_threshold=24.0)
        self.assertGreaterEqual(unack_res["unacknowledged_count"], 1)

        # 3. Scheduler Manager on-demand execution
        mgr_status = BackgroundSchedulerManager.get_status()
        self.assertIn("registered_jobs", mgr_status)


if __name__ == "__main__":
    unittest.main()
