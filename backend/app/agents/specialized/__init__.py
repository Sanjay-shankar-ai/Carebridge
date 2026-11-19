"""
CareBridge Specialized Agents
Modular intelligence modules dispatched by the central AI Supervisor:
1. PatientCommunicationAgent - Empathetic drafting, educational explanations, translation
2. CareCoordinationAgent - Scheduling, referrals, milestone tracking, coordinator ownership
3. RecoveryAgent - Missed appointments, barrier resolution playbooks, recovery tasks
4. ClinicalEscalationAgent - Deterministic emergency triage, doctor routing, audit trail
5. DoctorReviewAgent - Clinical case synthesis, physician decision capture, closure review
"""

from app.agents.specialized.patient_communication_agent import PatientCommunicationAgent
from app.agents.specialized.care_coordination_agent import CareCoordinationAgent
from app.agents.specialized.recovery_agent import RecoveryAgent
from app.agents.specialized.clinical_escalation_agent import ClinicalEscalationAgent
from app.agents.specialized.doctor_review_agent import DoctorReviewAgent

__all__ = [
    "PatientCommunicationAgent",
    "CareCoordinationAgent",
    "RecoveryAgent",
    "ClinicalEscalationAgent",
    "DoctorReviewAgent",
]
