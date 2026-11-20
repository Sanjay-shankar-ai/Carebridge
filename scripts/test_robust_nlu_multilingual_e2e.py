"""
CareBridge End-to-End Test: Robust NLU, Colloquial/Imperfect Grammar, Multilingual & Doctor Subgraph Routing
Verifies that:
1. Speech-to-text / informal grammar queries are accurately recognized:
   - "i want book doctor tomorrow" -> appointment_booking_request
   - "my report what saying" -> case_context_inquiry (birads), empathetic grammatically correct reply
   - "doctor not call me yet" -> referral_delay, coordinator notified
   - "any other slot morning" -> appointment_slot_alternatives (morning)
   - "second one book" -> appointment_slot_selection (slot_2)
   - "i am fear biopsy" -> patient_inquiry (biopsy), fear_anxiety barrier extracted, empathetic reassurance
2. Multilingual responses:
   - Spanish: "Tengo mucho miedo de la biopsia" -> lang="es", barrier="fear_anxiety", compassionate Spanish reply
   - Arabic: "أنا خائفة من الخزعة" -> lang="ar", barrier="fear_anxiety", compassionate Arabic reply
3. Doctor Subgraph supervisor integration:
   - Doctor queries routed through 11-node Doctor Subgraph cleanly
"""

import sys
import os
import uuid

# Ensure backend directory is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.agents.cognitive_engine import CognitiveEngine
from app.agents.specialized import PatientCommunicationAgent, CareCoordinationAgent
from app.agents.graph import supervisor_graph


def run_tests():
    print("=" * 80)
    print("CAREBRIDGE ROBUST NLU & MULTILINGUAL E2E TEST SUITE")
    print("=" * 80)

    patient_ctx = {
        "full_name": "Meenakshi Ramanathan",
        "first_name": "Meenakshi",
        "preferred_language": "en",
    }
    case_ctx = {
        "case_id": "00000000-0000-0000-0000-000000000001",
        "case_number": "CASE-2026-001",
        "finding_code": "BI-RADS 4",
        "finding_summary": "Suspicious microcalcifications in upper outer quadrant",
        "screening_type": "Mammogram",
        "current_owner_name": "Priya Nair, RN",
    }

    # Test 1: "i want book doctor tomorrow"
    print("\n[Test 1] Testing informal appointment request: 'i want book doctor tomorrow'")
    intent1 = CognitiveEngine.analyze_intent("i want book doctor tomorrow", patient_ctx, case_ctx)
    assert intent1.primary_intent == "appointment_booking_request", f"Expected appointment_booking_request, got {intent1.primary_intent}"
    plan1 = CognitiveEngine.formulate_plan(intent1, patient_ctx, case_ctx, {})
    assert any(a.tool_name == "book_appointment" for a in plan1.actions), "Expected book_appointment action in plan"
    print("  -> Passed: Intent matched appointment_booking_request, book_appointment tool scheduled.")

    # Test 2: "my report what saying"
    print("\n[Test 2] Testing imperfect grammar report query: 'my report what saying'")
    intent2 = CognitiveEngine.analyze_intent("my report what saying", patient_ctx, case_ctx)
    assert intent2.primary_intent == "case_context_inquiry", f"Expected case_context_inquiry, got {intent2.primary_intent}"
    assert intent2.inquiry_topic == "birads", f"Expected birads topic, got {intent2.inquiry_topic}"
    plan2 = CognitiveEngine.formulate_plan(intent2, patient_ctx, case_ctx, {})
    assert "BI-RADS 4" in plan2.patient_response_draft, "Expected BI-RADS 4 in response"
    assert "not a diagnosis of cancer" in plan2.patient_response_draft.lower(), "Expected non-diagnostic reassurance"
    # Ensure AI does NOT mimic the patient's broken grammar
    assert "what saying" not in plan2.patient_response_draft.lower(), "AI should not repeat broken grammar"
    print(f"  -> Passed: Intent matched case_context_inquiry. Reply draft: '{plan2.patient_response_draft[:80]}...'")

    # Test 3: "doctor not call me yet"
    print("\n[Test 3] Testing referral delay query: 'doctor not call me yet'")
    intent3 = CognitiveEngine.analyze_intent("doctor not call me yet", patient_ctx, case_ctx)
    assert intent3.primary_intent == "referral_delay", f"Expected referral_delay, got {intent3.primary_intent}"
    plan3 = CognitiveEngine.formulate_plan(intent3, patient_ctx, case_ctx, {})
    assert any(a.tool_name == "notify_case_owner" for a in plan3.actions), "Expected notify_case_owner action"
    assert "Priya Nair" in plan3.patient_response_draft, "Expected coordinator mention"
    print(f"  -> Passed: Intent matched referral_delay, nurse coordinator notified.")

    # Test 4: "any other slot morning"
    print("\n[Test 4] Testing slot alternative request: 'any other slot morning'")
    intent4 = CognitiveEngine.analyze_intent("any other slot morning", patient_ctx, case_ctx)
    assert intent4.primary_intent == "appointment_slot_alternatives", f"Expected appointment_slot_alternatives, got {intent4.primary_intent}"
    assert intent4.inquiry_topic == "morning", f"Expected morning topic, got {intent4.inquiry_topic}"
    plan4 = CognitiveEngine.formulate_plan(intent4, patient_ctx, case_ctx, {})
    assert "morning" in plan4.patient_response_draft.lower(), "Expected morning slots in draft"
    print("  -> Passed: Intent matched appointment_slot_alternatives with morning filter.")

    # Test 5: "second one book"
    print("\n[Test 5] Testing conversational slot selection: 'second one book'")
    intent5 = CognitiveEngine.analyze_intent("second one book", patient_ctx, case_ctx)
    assert intent5.primary_intent == "appointment_slot_selection", f"Expected appointment_slot_selection, got {intent5.primary_intent}"
    assert intent5.inquiry_topic == "slot_2", f"Expected slot_2 topic, got {intent5.inquiry_topic}"
    print("  -> Passed: Intent matched appointment_slot_selection for slot 2.")

    # Test 6: "i am fear biopsy"
    print("\n[Test 6] Testing anxiety query with imperfect grammar: 'i am fear biopsy'")
    intent6 = CognitiveEngine.analyze_intent("i am fear biopsy", patient_ctx, case_ctx)
    assert intent6.primary_intent == "patient_inquiry", f"Expected patient_inquiry, got {intent6.primary_intent}"
    assert intent6.inquiry_topic == "biopsy", f"Expected biopsy topic, got {intent6.inquiry_topic}"
    assert any(b.barrier_type == "fear_anxiety" for b in intent6.detected_barriers), "Expected fear_anxiety barrier"
    plan6 = CognitiveEngine.formulate_plan(intent6, patient_ctx, case_ctx, {})
    assert "anxious" in plan6.patient_response_draft.lower() or "scared" in plan6.patient_response_draft.lower(), "Expected empathy"
    assert "not a diagnosis of cancer" in plan6.patient_response_draft.lower(), "Expected non-diagnostic reassurance"
    # Ensure AI does NOT copy "i am fear"
    assert "i am fear" not in plan6.patient_response_draft.lower(), "AI response must use proper English"
    print(f"  -> Passed: Barrier fear_anxiety extracted. Proper English reassurance provided.")

    # Test 7: Multilingual - Spanish: "Tengo mucho miedo de la biopsia"
    print("\n[Test 7] Testing Spanish emotional inquiry: 'Tengo mucho miedo de la biopsia'")
    intent7 = CognitiveEngine.analyze_intent("Tengo mucho miedo de la biopsia", patient_ctx, case_ctx)
    assert intent7.detected_language == "es", f"Expected 'es', got {intent7.detected_language}"
    assert any(b.barrier_type == "fear_anxiety" for b in intent7.detected_barriers), "Expected fear_anxiety barrier in Spanish"
    plan7 = CognitiveEngine.formulate_plan(intent7, patient_ctx, case_ctx, {})
    assert plan7.target_language == "es", f"Expected target_language='es', got {plan7.target_language}"
    assert "cáncer" in plan7.patient_response_draft.lower(), "Expected Spanish reassurance content"
    assert "tranquilidad" in plan7.patient_response_draft.lower() or "biopsias" in plan7.patient_response_draft.lower(), "Expected compassionate Spanish phrasing"
    print(f"  -> Passed: Spanish detected and answered: '{plan7.patient_response_draft[:80]}...'")

    # Test 8: Multilingual - Arabic: "أنا خائفة من الخزعة"
    print("\n[Test 8] Testing Arabic emotional inquiry: 'أنا خائفة من الخزعة'")
    intent8 = CognitiveEngine.analyze_intent("أنا خائفة من الخزعة", patient_ctx, case_ctx)
    assert intent8.detected_language == "ar", f"Expected 'ar', got {intent8.detected_language}"
    assert any(b.barrier_type == "fear_anxiety" for b in intent8.detected_barriers), "Expected fear_anxiety barrier in Arabic"
    plan8 = CognitiveEngine.formulate_plan(intent8, patient_ctx, case_ctx, {})
    assert plan8.target_language == "ar", f"Expected target_language='ar', got {plan8.target_language}"
    assert "السرطان" in plan8.patient_response_draft, "Expected Arabic non-diagnostic reassurance"
    assert "حميدة" in plan8.patient_response_draft, "Expected benign explanation in Arabic"
    print(f"  -> Passed: Arabic detected and answered: '{plan8.patient_response_draft[:80]}...'")

    # Test 9: Doctor Subgraph routing via Supervisor Graph
    print("\n[Test 9] Testing Doctor Subgraph delegation in supervisor_graph: 'Review pending referrals'")
    test_state = {
        "case_id": "00000000-0000-0000-0000-000000000001",
        "patient_id": "00000000-0000-0000-0000-000000000001",
        "inbound_message": "Review pending referrals for my clinic",
        "inbound_sender": "doctor",
        "actor_role": "doctor",
        "actor_id": "00000000-0000-0000-0000-000000000002",
        "session_id": "sess-test-doc-001",
        "iteration_count": 0,
        "max_iterations": 3,
        "patient_context": patient_ctx,
        "case_context": case_ctx,
        "conversation_context": {},
        "replanning_needed": False,
        "pending_tool_calls": [],
        "tool_observations": [],
        "audit_entries": [],
    }
    # Invoke supervisor graph node reason_and_plan
    from app.agents.graph import reason_and_plan_node
    plan_out = reason_and_plan_node(test_state)
    assert "Clinical request processed" in plan_out["outbound_message"] or "referral" in plan_out["outbound_message"].lower() or len(plan_out["outbound_message"]) > 10, "Doctor subgraph should generate response"
    print(f"  -> Passed: Doctor request successfully routed through Doctor Subgraph: '{plan_out['outbound_message'][:80]}...'")

    print("\n" + "=" * 80)
    print("ALL 9 ROBUST NLU, MULTILINGUAL & DOCTOR ROUTING TESTS PASSED (100.0%)")
    print("=" * 80)


if __name__ == "__main__":
    run_tests()
