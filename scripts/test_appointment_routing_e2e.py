"""
CareBridge Targeted Appointment Routing & Database Verification Test Suite
Tests:
- Patient messages triggering LangGraph Supervisor and CareCoordinationAgent:
  * "I want to book an appointment"
  * "Can you schedule an appointment for me?"
  * "I need to see a doctor"
  * "Book me an appointment tomorrow"
  * "I prefer a morning appointment"
  * "Can I get another available slot?"
  * Informal: "i want book doctor tomorrow", "any other slot morning", "second one book"
- Database persistence verification:
  * Appointments inserted in PostgreSQL
  * Tasks created for Care Coordinator
  * Case status transitions
  * Audit events logged
"""

import sys
import os
import uuid
from datetime import datetime, timezone, timedelta

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.database.session import get_sync_db
from app.models import Patient, CareCase, Task, Appointment, CaseEvent, AuditLog, User, ScreeningResult
from app.agents.cognitive_engine import CognitiveEngine
from app.agents.graph import supervisor_graph
from app.tools.registry import ToolRegistry, _parse_scheduled_datetime


def test_appointment_intents_and_routing():
    print("=" * 70)
    print("SUITE 1: Appointment Intent Analysis & Agent Routing")
    print("=" * 70)

    test_cases = [
        ("I want to book an appointment", "appointment_booking_request", "CareCoordinationAgent"),
        ("Can you schedule an appointment for me?", "appointment_booking_request", "CareCoordinationAgent"),
        ("I need to see a doctor", "appointment_booking_request", "CareCoordinationAgent"),
        ("Book me an appointment tomorrow", "appointment_booking_request", "CareCoordinationAgent"),
        ("I prefer a morning appointment", "appointment_slot_preference", "CareCoordinationAgent"),
        ("Can I get another available slot?", "appointment_slot_alternatives", "CareCoordinationAgent"),
        ("i want book doctor tomorrow", "appointment_booking_request", "CareCoordinationAgent"),
        ("any other slot morning", "appointment_slot_alternatives", "CareCoordinationAgent"),
        ("second one book", "appointment_slot_selection", "CareCoordinationAgent"),
    ]

    patient_ctx = {"full_name": "Sarah Jenkins", "preferred_language": "en"}
    case_ctx = {
        "case_id": str(uuid.uuid4()),
        "case_number": "CASE-APPT-001",
        "facility": "Clinic A - Women's Specialty Breast Center",
        "specialty": "Breast Oncology",
        "screening_type": "Mammogram",
        "finding_code": "BI-RADS 4"
    }

    all_passed = True
    for msg, expected_intent, expected_agent in test_cases:
        analysis = CognitiveEngine._offline_intent_analysis(msg, patient_ctx)
        plan = CognitiveEngine.formulate_plan(analysis, patient_ctx, case_ctx, {})
        
        intent_ok = analysis.primary_intent == expected_intent
        tools = [a.tool_name for a in plan.actions]
        has_coord_tools = any(t in tools for t in ["search_available_appointments", "book_appointment", "create_followup_task", "update_case_notes"])
        
        status = "PASS" if (intent_ok and has_coord_tools) else "FAIL"
        if status == "FAIL":
            all_passed = False
            
        print(f"[{status}] Message: \"{msg}\"")
        print(f"       -> Detected Intent: {analysis.primary_intent} (Expected: {expected_intent})")
        print(f"       -> Action Tools: {tools}")
        print(f"       -> Plan Goal: {plan.goal[:60]}...")
        assert intent_ok, f"Expected intent {expected_intent}, got {analysis.primary_intent}"

    assert all_passed, "All intent and routing tests must pass!"
    print("\n>>> SUITE 1 PASSED: 9/9 Appointment Intents & Routings Verified.\n")


def test_datetime_parser():
    print("=" * 70)
    print("SUITE 2: Datetime Parser Robustness")
    print("=" * 70)

    now = datetime.now(timezone.utc)
    cases = [
        ("2026-11-25T10:00:00Z", 2026, 11, 25, 10, 0),
        ("tomorrow at 10:00 AM", (now + timedelta(days=1)).year, (now + timedelta(days=1)).month, (now + timedelta(days=1)).day, 10, 0),
        ("Thursday at 2:00 PM", None, None, None, 14, 0),
        ("Tuesday at 10:30 AM", None, None, None, 10, 30),
        ("next Wednesday at 3:30 PM", None, None, None, 15, 30),
    ]

    for raw, exp_year, exp_month, exp_day, exp_hour, exp_min in cases:
        parsed = _parse_scheduled_datetime(raw)
        assert isinstance(parsed, datetime), f"Failed to parse {raw}"
        assert parsed.tzinfo is not None, f"Parsed datetime must be timezone-aware: {parsed}"
        if exp_year:
            assert parsed.year == exp_year
        if exp_month:
            assert parsed.month == exp_month
        if exp_day:
            assert parsed.day == exp_day
        if exp_hour is not None:
            assert parsed.hour == exp_hour, f"Expected hour {exp_hour}, got {parsed.hour} for {raw}"
        if exp_min is not None:
            assert parsed.minute == exp_min, f"Expected minute {exp_min}, got {parsed.minute} for {raw}"
        print(f"[PASS] Parsed \"{raw}\" -> {parsed.isoformat()}")

    print("\n>>> SUITE 2 PASSED: Robust relative & ISO datetime parsing verified.\n")


def test_database_appointment_booking_and_persistence():
    print("=" * 70)
    print("SUITE 3: PostgreSQL Database Verification: Appointment & Coordination Tasks")
    print("=" * 70)

    with get_sync_db() as db:
        # Create isolated synthetic patient, screening result, and case
        p_id = uuid.uuid4()
        c_id = uuid.uuid4()
        sr_id = uuid.uuid4()

        test_patient = Patient(
            id=p_id,
            first_name="TestSarah",
            last_name="AppointmentTester",
            mrn=f"MRN-APPT-{uuid.uuid4().hex[:6]}",
            date_of_birth=datetime(1982, 5, 12).date(),
            gender="female",
            phone="+15551234567",
            email=f"sarah.appt.{uuid.uuid4().hex[:4]}@example.com",
            preferred_language="en"
        )
        db.add(test_patient)

        test_screening = ScreeningResult(
            id=sr_id,
            patient_id=p_id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc) - timedelta(days=2),
            finding_code="BI-RADS 4",
            finding_summary="Suspicious abnormality detected requiring tissue diagnosis.",
            performing_facility="Clinic A - Women's Specialty Breast Center"
        )
        db.add(test_screening)

        test_case = CareCase(
            id=c_id,
            case_number=f"CASE-APPT-{uuid.uuid4().hex[:6]}",
            patient_id=p_id,
            screening_result_id=sr_id,
            status="referred",
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=14),
            case_context={"facility": "Clinic A - Women's Specialty Breast Center", "specialty": "Breast Oncology"}
        )
        db.add(test_case)
        db.commit()

        print(f"[SETUP] Created synthetic patient {test_patient.id} and case {test_case.id}")

        # Test 1: Patient says "Book me an appointment tomorrow" -> Supervisor execution
        print("\n--- Testing Supervisor with \"Book me an appointment tomorrow\" ---")
        initial_state = {
            "inbound_message": "Book me an appointment tomorrow",
            "patient_context": {
                "id": str(p_id),
                "full_name": "TestSarah AppointmentTester",
                "preferred_language": "en"
            },
            "case_context": {
                "case_id": str(c_id),
                "case_number": test_case.case_number,
                "facility": "Clinic A - Women's Specialty Breast Center",
                "specialty": "Breast Oncology",
                "finding_code": "BI-RADS 4"
            },
            "conversation_context": {},
            "case_id": str(c_id),
            "patient_id": str(p_id),
        }

        result = supervisor_graph.invoke(initial_state, config={"configurable": {"thread_id": str(c_id)}})
        print(f"Supervisor outbound message: {result.get('outbound_message')}")
        assert result.get("outbound_message"), "Outbound message must be generated"

        # Verify DB records
        db.refresh(test_case)
        print(f"Case status after booking request: {test_case.status}")
        assert test_case.status in ["appointment_booked", "appointment_scheduled", "appointment_proposed"], \
            f"Case status should reflect appointment progress, got: {test_case.status}"

        # Check Appointment record in DB
        appt = db.query(Appointment).filter(Appointment.case_id == c_id).first()
        assert appt is not None, "Appointment must be persisted in appointments table!"
        print(f"[DB VERIFIED] Appointment record found: ID={appt.id}, Status={appt.status}, Provider={appt.provider_name}, Time={appt.scheduled_time}")
        assert appt.facility == "Clinic A - Women's Specialty Breast Center"
        assert appt.patient_id == p_id

        # Check Task record in DB
        task = db.query(Task).filter(Task.case_id == c_id).first()
        assert task is not None, "Care Coordination task must be persisted in tasks table!"
        print(f"[DB VERIFIED] Task record found: ID={task.id}, Title='{task.title}', AssignedRole={task.assigned_role}")

        # Check AuditLog record in DB
        audit = db.query(AuditLog).filter(AuditLog.case_id == c_id, AuditLog.action == "BOOK_APPOINTMENT").first()
        assert audit is not None, "AuditLog for BOOK_APPOINTMENT must be persisted!"
        print(f"[DB VERIFIED] AuditLog record found: Action={audit.action}, Actor={audit.actor_id}, Rationale={audit.rationale}")

        # Test 2: Patient says "second one book" -> Select slot 2
        print("\n--- Testing Supervisor with \"second one book\" ---")
        c2_id = uuid.uuid4()
        sr2_id = uuid.uuid4()
        test_screening2 = ScreeningResult(
            id=sr2_id,
            patient_id=p_id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc) - timedelta(days=3),
            finding_code="BI-RADS 4",
            finding_summary="Suspicious abnormality requiring biopsy.",
            performing_facility="Clinic A - Women's Specialty Breast Center"
        )
        db.add(test_screening2)

        test_case2 = CareCase(
            id=c2_id,
            case_number=f"CASE-SLOT2-{uuid.uuid4().hex[:6]}",
            patient_id=p_id,
            screening_result_id=sr2_id,
            status="referred",
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=14),
            case_context={"facility": "Clinic A - Women's Specialty Breast Center", "specialty": "Breast Oncology"}
        )
        db.add(test_case2)
        db.commit()

        initial_state2 = {
            "inbound_message": "second one book",
            "patient_context": {
                "id": str(p_id),
                "full_name": "TestSarah AppointmentTester",
                "preferred_language": "en"
            },
            "case_context": {
                "case_id": str(c2_id),
                "case_number": test_case2.case_number,
                "facility": "Clinic A - Women's Specialty Breast Center",
                "specialty": "Breast Oncology",
                "finding_code": "BI-RADS 4"
            },
            "conversation_context": {},
            "case_id": str(c2_id),
            "patient_id": str(p_id),
        }

        result2 = supervisor_graph.invoke(initial_state2, config={"configurable": {"thread_id": str(c2_id)}})
        print(f"Supervisor outbound message: {result2.get('outbound_message')}")

        appt2 = db.query(Appointment).filter(Appointment.case_id == c2_id).first()
        assert appt2 is not None, "Appointment for slot selection must be persisted!"
        print(f"[DB VERIFIED] Slot 2 Appointment: ID={appt2.id}, Status={appt2.status}, Time={appt2.scheduled_time}")
        assert appt2.status == "booked"
        appt_utc = appt2.scheduled_time.astimezone(timezone.utc) if appt2.scheduled_time.tzinfo else appt2.scheduled_time
        assert appt_utc.hour == 14  # Thursday at 2:00 PM UTC

        # Clean up test artifacts
        db.query(Appointment).filter(Appointment.patient_id == p_id).delete()
        db.query(Task).filter(Task.case_id.in_([c_id, c2_id])).delete()
        db.query(AuditLog).filter(AuditLog.case_id.in_([c_id, c2_id])).delete()
        db.query(CareCase).filter(CareCase.patient_id == p_id).delete()
        db.query(Patient).filter(Patient.id == p_id).delete()
        db.commit()
        print("\n[CLEANUP] Successfully cleaned up isolated synthetic test records.")

    print("\n>>> SUITE 3 PASSED: Full PostgreSQL Persistence Verified for Appointments, Tasks, and Audit.\n")


if __name__ == "__main__":
    print("\n========================================================")
    print("CAREBRIDGE TARGETED APPOINTMENT SUITE: E2E VERIFICATION")
    print("========================================================\n")
    test_appointment_intents_and_routing()
    test_datetime_parser()
    test_database_appointment_booking_and_persistence()
    print("========================================================")
    print("ALL APPOINTMENT TESTS PASSED WITH 100% SUCCESS RATE!")
    print("========================================================\n")
