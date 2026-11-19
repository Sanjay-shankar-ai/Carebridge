"""
CareBridge Fact vs Assumption Evaluator & Stalled Journey Detector (Phase 7)
Separates verified clinical and operational facts from working assumptions.
Detects stalled journeys and triggers patient clarification inquiries
when the underlying cause of a delay is unverified.
"""

import logging
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger("carebridge.recovery.evaluator")

# Keyword maps for detecting explicit patient-reported barriers
BARRIER_KEYWORD_PATTERNS = {
    "transportation": [
        "car", "ride", "drive", "bus", "train", "transit", "uber", "lyft", "distance",
        "far", "no way to get there", "transport", "transportation"
    ],
    "caregiver_family": [
        "daughter", "son", "mother", "father", "husband", "wife", "mom", "dad",
        "caregiver", "child", "children", "baby", "kid", "babysitter", "childcare",
        "family member", "take care of"
    ],
    "fear_anxiety": [
        "afraid", "scared", "fear", "anxious", "anxiety", "worried", "panic", "terrified",
        "nervous", "pain", "hurt", "dread", "frightened", "don't want to know"
    ],
    "financial": [
        "money", "cost", "afford", "expensive", "pay", "insurance", "copay", "co-pay",
        "bill", "deductible", "uninsured", "lost job", "financial"
    ],
    "scheduling_work": [
        "work", "job", "boss", "shift", "busy", "hours", "meeting", "conflict",
        "cannot take off", "no leave", "weekend", "evening", "reschedule"
    ],
    "medical_illness": [
        "sick", "fever", "covid", "cough", "hospital", "ill", "pain", "flu",
        "surgery", "infection"
    ]
}


class FactAssumptionEvaluator:
    """Evaluates multi-source context, detects dropoffs, and isolates facts from assumptions."""

    @classmethod
    def detect_stalled_journey(cls, context: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Determines whether the care journey is stalled across 7 deterministic dimensions.
        Returns: (is_stalled, list_of_stalled_signals)
        """
        signals = []

        case_hist = context.get("case_history", {})
        sla_ctx = context.get("sla_context", {})
        app_hist = context.get("appointment_history", {})
        prev_attempts = context.get("previous_communication_attempts", {})
        ref_status = context.get("referral_status", {})
        tasks = context.get("outstanding_tasks", {})

        # 1. Prolonged Case Inactivity (>= 5 days)
        days_inactive = sla_ctx.get("days_inactive", 0.0)
        if days_inactive >= 5.0:
            signals.append({
                "type": "case_inactivity",
                "severity": "high" if days_inactive >= 10.0 else "medium",
                "reason": f"Case has had no recorded activity for {days_inactive} days (threshold: 5 days)",
                "days_inactive": days_inactive
            })

        # 2. Missed Appointment (no-show)
        if app_hist.get("no_show_count", 0) > 0:
            signals.append({
                "type": "appointment_no_show",
                "severity": "high",
                "reason": f"Patient has {app_hist['no_show_count']} unrecovered no-show appointment(s)",
                "latest_appointment": app_hist.get("latest_appointment")
            })

        # 3. Cancelled Appointment without active rebooking
        if app_hist.get("cancelled_count", 0) > 0 and not app_hist.get("has_active_booked", False):
            signals.append({
                "type": "appointment_cancelled_unrebooked",
                "severity": "medium",
                "reason": "Appointment cancelled without an active rescheduled appointment in place"
            })

        # 4. Unacknowledged Outreach
        hours_unacknowledged = prev_attempts.get("hours_since_last_outreach")
        if (
            prev_attempts.get("outreach_count", 0) > 0
            and not prev_attempts.get("has_replied", False)
            and hours_unacknowledged is not None
            and hours_unacknowledged >= 24.0
        ):
            signals.append({
                "type": "unacknowledged_outreach",
                "severity": "high" if hours_unacknowledged >= 48.0 else "medium",
                "reason": f"Outreach unacknowledged for {round(hours_unacknowledged, 1)} hours (threshold: 24h)",
                "hours_unacknowledged": hours_unacknowledged
            })

        # 5. Stalled Specialist Referral
        if ref_status.get("is_stalled", False):
            signals.append({
                "type": "referral_stalled",
                "severity": "high",
                "reason": "Specialist referral pending clinic acceptance beyond the SLA window"
            })

        # 6. SLA Breach or Warning
        if sla_ctx.get("is_breached", False):
            signals.append({
                "type": "sla_breached",
                "severity": "critical",
                "reason": f"SLA deadline breached! Hours overdue: {abs(sla_ctx.get('hours_remaining', 0))}"
            })
        elif sla_ctx.get("is_warning", False):
            signals.append({
                "type": "sla_warning",
                "severity": "high",
                "reason": f"SLA deadline warning: only {sla_ctx.get('hours_remaining')} hours remaining"
            })

        # 7. Overdue Milestone Tasks
        if tasks.get("overdue_count", 0) > 0:
            signals.append({
                "type": "overdue_tasks",
                "severity": "medium",
                "reason": f"{tasks['overdue_count']} milestone coordination task(s) are overdue",
                "overdue_tasks": tasks.get("overdue_tasks", [])
            })

        # 8. Unowned Case
        if not case_hist.get("current_owner_id"):
            signals.append({
                "type": "unassigned_owner",
                "severity": "critical",
                "reason": "Case has no accountable Care Coordinator assigned"
            })

        is_stalled = len(signals) > 0
        return is_stalled, signals

    @classmethod
    def evaluate_facts_vs_assumptions(
        cls,
        context: Dict[str, Any],
        stalled_signals: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Distinguishes known facts from working assumptions:
        - Known facts: Verified system records and explicit statements directly from the patient.
        - Assumptions: Inferences or unverified hypotheses regarding why the patient missed care.

        Returns a dictionary:
        {
            "known_facts": List[Dict],
            "assumptions": List[Dict],
            "detected_barriers": List[str],
            "needs_clarification": bool,
            "clarification_reason": Optional[str]
        }
        """
        known_facts: List[Dict[str, Any]] = []
        assumptions: List[Dict[str, Any]] = []
        detected_barriers: List[str] = []

        conv_ctx = context.get("patient_conversations", {})
        patient_msgs = conv_ctx.get("messages", [])
        app_hist = context.get("appointment_history", {})
        case_hist = context.get("case_history", {})
        sla_ctx = context.get("sla_context", {})
        ref_status = context.get("referral_status", {})
        prev_attempts = context.get("previous_communication_attempts", {})
        patient_pref = context.get("patient_preferences", {})

        # -------------------------------------------------------------
        # STEP 1: Extract Operational Known Facts from Records
        # -------------------------------------------------------------
        if app_hist.get("no_show_count", 0) > 0:
            latest_app = app_hist.get("latest_appointment", {})
            known_facts.append({
                "category": "appointment",
                "fact": f"Patient has missed appointment (no-show) scheduled for {latest_app.get('scheduled_time')}",
                "source": "appointment_records",
                "confidence": 1.0
            })

        if app_hist.get("cancelled_count", 0) > 0:
            latest_app = app_hist.get("latest_appointment", {})
            reason = latest_app.get("cancellation_reason") or "unspecified"
            known_facts.append({
                "category": "appointment",
                "fact": f"Appointment cancelled. Documented reason: '{reason}'",
                "source": "appointment_records",
                "confidence": 1.0
            })

        if ref_status.get("is_stalled", False):
            known_facts.append({
                "category": "referral",
                "fact": "Specialist referral pending facility acceptance beyond 48 hours",
                "source": "referral_records",
                "confidence": 1.0
            })

        if prev_attempts.get("outreach_count", 0) > 0 and not prev_attempts.get("has_replied", False):
            hours = prev_attempts.get("hours_since_last_outreach")
            known_facts.append({
                "category": "outreach",
                "fact": f"Outreach sent {hours}h ago on channel '{prev_attempts.get('last_outreach_channel')}' has received no patient reply",
                "source": "communication_records",
                "confidence": 1.0
            })

        if sla_ctx.get("is_breached", False) or sla_ctx.get("is_warning", False):
            known_facts.append({
                "category": "sla",
                "fact": f"Case SLA status is '{sla_ctx.get('sla_status')}' with {sla_ctx.get('hours_remaining')} hours remaining",
                "source": "sla_monitor",
                "confidence": 1.0
            })

        # -------------------------------------------------------------
        # STEP 2: Extract Explicit Patient-Reported Barriers (Known Facts)
        # -------------------------------------------------------------
        explicit_barriers_found = []
        for msg in patient_msgs:
            if msg.get("sender") == "patient":
                content = (msg.get("content") or "").lower()
                for barrier, keywords in BARRIER_KEYWORD_PATTERNS.items():
                    matching_kw = [kw for kw in keywords if kw in content]
                    if matching_kw:
                        explicit_barriers_found.append({
                            "barrier": barrier,
                            "matching_keywords": matching_kw,
                            "quote": msg.get("content"),
                            "timestamp": msg.get("sent_at")
                        })
                        if barrier not in detected_barriers:
                            detected_barriers.append(barrier)

        for eb in explicit_barriers_found:
            known_facts.append({
                "category": "patient_reported_barrier",
                "fact": f"Patient explicitly communicated barrier: {eb['barrier']} ('{eb['quote']}')",
                "source": "patient_message",
                "quote": eb["quote"],
                "confidence": 1.0
            })

        # Check patient profile context for known barriers
        profile_barriers = patient_pref.get("profile_known_barriers", [])
        if profile_barriers:
            for pb in profile_barriers:
                known_facts.append({
                    "category": "patient_profile_barrier",
                    "fact": f"Pre-documented barrier in patient profile: '{pb}'",
                    "source": "patient_profile",
                    "confidence": 0.95
                })
                if pb not in detected_barriers:
                    detected_barriers.append(pb)

        # -------------------------------------------------------------
        # STEP 3: Identify Working Assumptions
        # -------------------------------------------------------------
        # An assumption occurs when an event occurred (like a no-show or unacknowledged SMS)
        # but the patient NEVER stated WHY it happened.
        has_unexplained_no_show = (
            app_hist.get("no_show_count", 0) > 0 and len(explicit_barriers_found) == 0
        )
        has_unexplained_unresponsive = (
            prev_attempts.get("outreach_count", 0) > 0
            and not prev_attempts.get("has_replied", False)
            and len(explicit_barriers_found) == 0
        )
        has_unexplained_cancellation = (
            app_hist.get("cancelled_count", 0) > 0
            and not app_hist.get("has_active_booked", False)
            and (not app_hist.get("latest_appointment", {}).get("cancellation_reason")
                 or app_hist.get("latest_appointment", {}).get("cancellation_reason") == "patient_request")
            and len(explicit_barriers_found) == 0
        )

        if has_unexplained_no_show:
            assumptions.append({
                "hypothesis": "Patient may have encountered an unrecorded barrier (e.g. transportation, acute illness, anxiety, or scheduling conflict)",
                "event": "appointment_no_show",
                "status": "unverified",
                "risk": "Assuming a specific barrier without patient input leads to ineffective recovery actions"
            })

        if has_unexplained_unresponsive:
            assumptions.append({
                "hypothesis": f"Patient may not have received message, prefers a different channel ({patient_pref.get('communication_channel')}), or has anxiety regarding screening results",
                "event": "unacknowledged_outreach",
                "status": "unverified",
                "risk": "Assuming patient is disengaged rather than experiencing barriers"
            })

        if has_unexplained_cancellation:
            assumptions.append({
                "hypothesis": "Patient cancelled appointment without documenting underlying cause",
                "event": "appointment_cancelled",
                "status": "unverified",
                "risk": "Rescheduling without addressing underlying barrier may cause repeated dropoff"
            })

        # -------------------------------------------------------------
        # STEP 4: Determine if Clarification is Needed
        # -------------------------------------------------------------
        # Clarification IS NEEDED if:
        # 1. An appointment was missed (no-show) or cancelled without an explicit reason from the patient.
        # 2. Prolonged inactivity exists with no known barrier or conversation.
        # Clarification IS NOT NEEDED if:
        # - The patient ALREADY gave an explicit reason (barrier is a Known Fact).
        # - The issue is purely administrative (e.g. referral stalled at clinic, unowned case) where patient is not at fault.
        needs_clarification = False
        clarification_reason = None

        if has_unexplained_no_show:
            needs_clarification = True
            clarification_reason = "Appointment missed without documented patient reason. Must inquire empathetically before assuming cause."
        elif has_unexplained_cancellation:
            needs_clarification = True
            clarification_reason = "Appointment cancelled without documented reason. Inquire if rescheduling or assistance is needed."
        elif has_unexplained_unresponsive and prev_attempts.get("hours_since_last_outreach", 0) >= 48.0:
            needs_clarification = True
            clarification_reason = "Outreach unacknowledged after 48h. Empathetic check-in on patient's preferred channel needed."
        elif len(detected_barriers) == 0 and sla_ctx.get("days_inactive", 0) >= 5.0 and not ref_status.get("is_stalled"):
            needs_clarification = True
            clarification_reason = "Case inactive >= 5 days with no known barrier. Inquire if patient needs coordination help."

        return {
            "known_facts": known_facts,
            "assumptions": assumptions,
            "detected_barriers": detected_barriers,
            "needs_clarification": needs_clarification,
            "clarification_reason": clarification_reason
        }
