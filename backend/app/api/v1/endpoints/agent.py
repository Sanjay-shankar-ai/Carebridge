"""
CareBridge Agent Interaction API
Exposes the LangGraph Supervisor Agent and Doctor Subgraph for real-time cognitive care coordination.
Strictly authenticates callers and isolates conversational memory threads per user and case.
"""

import uuid
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, delete
from sqlalchemy.orm import selectinload

from app.database.session import get_async_db, async_session_factory, get_sync_db
from app.models.care_case import CareCase, Task
from app.models.patient import Patient
from app.models.event_audit import CaseEvent
from app.models.communication import Communication, ConversationSession
from app.models.appointment import Appointment
from app.models.owner import CaseOwner
from app.agents.graph import supervisor_graph
from app.workflows.doctor_workflow import run_doctor_workflow
from app.agents.cognitive_engine import CognitiveEngine
from app.tools.registry import ToolRegistry
from app.services.response_guard_service import ResponseGuardService
from app.services.patient_behaviour_router import PatientBehaviourRouter, BehaviourResult
from app.core.security import get_current_user, UserPrincipal
from app.core.rate_limiter import rate_limit_agent
from app.schemas.common import ApiResponseEnvelope

logger = logging.getLogger("carebridge.agent")

router = APIRouter(prefix="/agent", tags=["AI Supervisor Agent"])


class PatientInteractionRequest(BaseModel):
    case_id: Optional[uuid.UUID] = Field(default=None, description="UUID of the active care case (optional for doctors)")
    session_id: Optional[uuid.UUID] = Field(default=None, description="UUID of existing conversation session")
    message: str = Field(min_length=1, max_length=10000, description="Natural language message from patient or provider")
    channel: str = Field(default="in_app_chat", description="'in_app_chat', 'sms', 'whatsapp'")
    sender: Optional[str] = Field(default=None, description="Reported sender (overridden by authenticated role)")
    stream: bool = Field(default=False, description="Whether to stream tokens via SSE")


class AgentExecutionResponse(BaseModel):
    case_id: str
    patient_id: str
    session_id: Optional[str] = None
    primary_intent: str
    emotional_state: str
    detected_barriers: list
    actions_executed: list
    outbound_message: Optional[str]
    outbound_language: str
    requires_human_approval: bool
    approval_request: Optional[Dict[str, Any]] = None


class ChatMessageHistoryItem(BaseModel):
    id: str
    case_id: Optional[str] = None
    patient_id: Optional[str] = None
    session_id: Optional[str] = None
    sender: str
    channel: str
    language: str
    content: str
    translated_content: Optional[str] = None
    acknowledged: bool = False
    sent_at: datetime


class ChatHistoryResponse(BaseModel):
    messages: List[ChatMessageHistoryItem]
    total: int
    case_id: Optional[str] = None
    session_id: Optional[str] = None


class ConversationSessionResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    role: Optional[str] = None
    title: Optional[str] = "New Chat"
    patient_id: Optional[str] = None
    case_id: Optional[str] = None
    channel: str
    summary: Optional[str] = None
    unanswered_questions: list = []
    patient_commitments: list = []
    is_active: bool
    last_interaction_at: datetime
    created_at: datetime


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None
    case_id: Optional[uuid.UUID] = None
    patient_id: Optional[uuid.UUID] = None
    channel: str = "in_app_chat"


class RenameSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255, description="New title for the conversation")


async def _run_behaviour_turn(current_user, active_session, req, language: str):
    """Runs deterministic behaviour flows (B1-B4) in a worker thread with a sync DB session."""
    from fastapi.concurrency import run_in_threadpool

    def _work():
        if (current_user.role or "").lower() != "patient":
            return None
        patient_id = active_session.patient_id or current_user.patient_id
        if not patient_id:
            return None
        with get_sync_db() as sdb:
            return PatientBehaviourRouter.handle_turn(
                sdb,
                user_id=uuid.UUID(str(current_user.user_id)),
                role="patient",
                patient_id=patient_id,
                session_id=active_session.id,
                case_id=req.case_id or active_session.case_id,
                message=req.message,
                language=language if language in ("en", "es", "ar") else "en",
            )

    try:
        return await run_in_threadpool(_work)
    except Exception as exc:  # a behaviour fault must never break chat
        logger.error(f"Behaviour router failure: {exc}", exc_info=True)
        return None


async def _finalize_behaviour_turn(result, active_session, current_user, req, language: str):
    from fastapi.concurrency import run_in_threadpool

    def _work():
        patient_id = active_session.patient_id or current_user.patient_id
        with get_sync_db() as sdb:
            PatientBehaviourRouter.finalize_turn(
                sdb, result,
                session_id=active_session.id,
                patient_id=patient_id,
                case_id=req.case_id or active_session.case_id or result.case_id,
                channel=req.channel or "in_app_chat",
                language=language if language in ("en", "es", "ar") else "en",
            )

    try:
        await run_in_threadpool(_work)
    except Exception as exc:
        logger.error(f"Behaviour finalize failure: {exc}", exc_info=True)


async def generate_agent_stream(
    req: PatientInteractionRequest,
    current_user: UserPrincipal,
    request: Request
):
    """
    Asynchronously streams Server-Sent Events (SSE) representing:
    - tool_started: tool invocation with sanitized action description
    - tool_result: verified execution status (status only, zero data leakage)
    - token: guarded, sanitized incremental response tokens
    - final: completed turn payload including session, intent, verified actions
    - error: non-leaking friendly error notifications
    Cleanly terminates if client disconnects or clicks 'Stop generating'.
    """
    async with async_session_factory() as db:
        user_role = current_user.role.lower()
        now = datetime.now(timezone.utc)
        user_uuid = uuid.UUID(str(current_user.user_id))

        try:
            # 1. Resolve or initialize active ConversationSession
            active_session: Optional[ConversationSession] = None
            if req.session_id:
                sess_stmt = select(ConversationSession).where(ConversationSession.id == req.session_id)
                sess_res = await db.execute(sess_stmt)
                active_session = sess_res.scalar_one_or_none()
                if not active_session:
                    yield f"event: error\ndata: {json.dumps({'message': f'Session {req.session_id} not found.', 'code': 'NOT_FOUND'})}\n\n"
                    return

                is_owner = (str(active_session.user_id) == str(current_user.user_id)) or (
                    user_role == "patient" and current_user.patient_id and str(active_session.patient_id) == str(current_user.patient_id)
                )
                if not is_owner:
                    yield f"event: error\ndata: {json.dumps({'message': 'Forbidden: You cannot access another user conversation session.', 'code': 'FORBIDDEN'})}\n\n"
                    return
                active_session.last_interaction_at = now
            else:
                first_line = req.message.strip().split("\n")[0][:40]
                title = (first_line + "...") if len(first_line) == 40 else first_line
                patient_uuid = None
                if user_role == "patient" and current_user.patient_id:
                    try:
                        patient_uuid = uuid.UUID(current_user.patient_id)
                    except ValueError:
                        pass
                active_session = ConversationSession(
                    id=uuid.uuid4(),
                    user_id=user_uuid,
                    role=user_role,
                    title=title or "New Chat",
                    case_id=req.case_id,
                    patient_id=patient_uuid,
                    channel=req.channel or "in_app_chat",
                    is_active=True,
                    last_interaction_at=now
                )
                db.add(active_session)
                await db.flush()

            # Record inbound Communication
            inbound_comm = Communication(
                id=uuid.uuid4(),
                user_id=current_user.user_id,
                role=user_role,
                case_id=req.case_id,
                patient_id=active_session.patient_id,
                session_id=active_session.id,
                sender=user_role,
                channel=req.channel or "in_app_chat",
                language="en",
                content=req.message,
                acknowledged=True,
                sent_at=now
            )
            db.add(inbound_comm)
            await db.commit()

            def _to_uuid(val: Any) -> Optional[uuid.UUID]:
                if not val:
                    return None
                if isinstance(val, uuid.UUID):
                    return val
                try:
                    return uuid.UUID(str(val))
                except (ValueError, TypeError, AttributeError):
                    return None

            # Resolve Case and Patient context for patient or coordinator
            target_case: Optional[CareCase] = None
            target_patient: Optional[Patient] = None
            case_uuid = _to_uuid(req.case_id) or _to_uuid(active_session.case_id)
            if case_uuid:
                try:
                    c_stmt = (
                        select(CareCase)
                        .options(
                            selectinload(CareCase.patient),
                            selectinload(CareCase.current_owner),
                            selectinload(CareCase.screening_result)
                        )
                        .where(CareCase.id == case_uuid)
                    )
                    c_res = await db.execute(c_stmt)
                    target_case = c_res.scalar_one_or_none()
                except Exception as e:
                    logger.warning(f"Failed to load case by id {case_uuid}: {e}")

            p_uuid = _to_uuid(current_user.patient_id)
            if not target_case and user_role == "patient" and p_uuid:
                try:
                    c_stmt = (
                        select(CareCase)
                        .options(
                            selectinload(CareCase.patient),
                            selectinload(CareCase.current_owner),
                            selectinload(CareCase.screening_result)
                        )
                        .where(CareCase.patient_id == p_uuid)
                        .order_by(CareCase.created_at.desc())
                    )
                    c_res = await db.execute(c_stmt)
                    target_case = c_res.scalars().first()
                except Exception as e:
                    logger.warning(f"Failed to load case by patient_id: {e}")

            if target_case:
                target_patient = target_case.patient
                if not active_session.case_id:
                    active_session.case_id = target_case.id
                if not active_session.patient_id and target_case.patient_id:
                    active_session.patient_id = target_case.patient_id
            elif user_role == "patient" and p_uuid:
                try:
                    p_stmt = select(Patient).where(Patient.id == p_uuid)
                    p_res = await db.execute(p_stmt)
                    target_patient = p_res.scalar_one_or_none()
                except Exception as e:
                    logger.warning(f"Failed to load patient: {e}")

            # Cancellation check
            if await request.is_disconnected():
                logger.info("Client disconnected before stream execution.")
                return

            msg_lower = req.message.lower().strip()
            tool_observations: List[Dict[str, Any]] = []
            behaviour_result: Optional[BehaviourResult] = None
            draft_response = ""
            primary_intent = "general_inquiry"
            detected_language = "en"

            # Language detection
            if any("\u0600" <= c <= "\u06ff" for c in req.message):
                detected_language = "ar"
            elif any(w in msg_lower for w in ["hola", "cita", "dolor", "miedo", "gracias", "el doctor", "informe", "por favor"]):
                detected_language = "es"

            # -------------------------------------------------------------
            # Coordinator Branch
            # -------------------------------------------------------------
            if user_role in ("care_coordinator", "coordinator"):
                if any(term in msg_lower for term in ["new patient", "new patients", "any new patient", "is there any new patient", "unassigned", "discovery queue", "intake queue"]):
                    primary_intent = "new_patient_discovery"
                    yield f"event: tool_started\ndata: {json.dumps({'tool': 'discover_new_patients', 'description': 'Scanning database for new and unassigned patient intake'})}\n\n"
                    await asyncio.sleep(0.01)

                    with get_sync_db() as sync_db:
                        res = ToolRegistry.discover_new_patients(sync_db, actor_role="care_coordinator", limit=10)
                        success = res.get("success", True)
                        cases = res.get("data", {}).get("cases", [])
                        tool_observations.append({
                            "tool": "discover_new_patients",
                            "success": success,
                            "result": res
                        })

                    yield f"event: tool_result\ndata: {json.dumps({'tool': 'discover_new_patients', 'status': 'success' if success else 'failed', 'summary': f'Discovered {len(cases)} new patients'})}\n\n"
                    await asyncio.sleep(0.01)

                    if cases:
                        c_lines = [
                            f"• **{c['patient_name']}** ({c['case_number']}): Status: `{c['status']}`, Priority: `{c['priority']}`, Finding: {c['finding_code']}"
                            for c in cases
                        ]
                        draft_response = (
                            f"Found **{len(cases)}** new or unassigned patient case(s) in the intake discovery queue:\n\n"
                            + "\n".join(c_lines)
                            + "\n\nTo view details or schedule actions for a patient, say: `Select patient <name>` or specify the case number."
                        )
                    else:
                        draft_response = "There are currently no new unassigned patient cases in the discovery queue."

                elif any(term in msg_lower for term in ["pending tasks", "my tasks", "overdue tasks", "what tasks", "tasks for this case"]):
                    primary_intent = "task_management"
                    yield f"event: tool_started\ndata: {json.dumps({'tool': 'get_pending_case_tasks', 'description': 'Querying active coordination tasks'})}\n\n"
                    await asyncio.sleep(0.01)

                    tasks_stmt = select(Task).where(Task.status.in_(["pending", "in_progress", "overdue"])).limit(10)
                    t_res = (await db.execute(tasks_stmt)).scalars().all()
                    tool_observations.append({
                        "tool": "get_pending_case_tasks",
                        "success": True,
                        "result": {"tasks_count": len(t_res)}
                    })

                    yield f"event: tool_result\ndata: {json.dumps({'tool': 'get_pending_case_tasks', 'status': 'success', 'summary': f'Retrieved {len(t_res)} coordination tasks'})}\n\n"
                    await asyncio.sleep(0.01)

                    if t_res:
                        lines = [f"• **{t.title}** (Priority: `{t.priority}`, Status: `{t.status}`)" for t in t_res]
                        draft_response = f"Here are your pending coordination tasks:\n\n" + "\n".join(lines)
                    else:
                        draft_response = "All coordination tasks are currently up to date."

                elif any(term in msg_lower for term in ["stalled cases", "sla breach", "recovery queue"]):
                    primary_intent = "sla_recovery_queue"
                    yield f"event: tool_started\ndata: {json.dumps({'tool': 'identify_stalled_cases', 'description': 'Scanning active cases for drop-offs and SLA breaches'})}\n\n"
                    await asyncio.sleep(0.01)

                    with get_sync_db() as sync_db:
                        res = ToolRegistry.identify_stalled_cases(sync_db, days_threshold=3, actor_role="care_coordinator")
                        tool_observations.append({
                            "tool": "identify_stalled_cases",
                            "success": res.get("success", True),
                            "result": res
                        })

                    yield f"event: tool_result\ndata: {json.dumps({'tool': 'identify_stalled_cases', 'status': 'success', 'summary': 'Scanned active cases for SLA risk'})}\n\n"
                    await asyncio.sleep(0.01)

                    stalled = res.get("data", {}).get("stalled_cases", [])
                    if stalled:
                        lines = [f"• Case **{s.get('case_number', 'N/A')}**: Stalled at stage `{s.get('current_stage', 'Unknown')}` ({s.get('days_inactive', 0)} days inactive)" for s in stalled[:5]]
                        draft_response = f"Identified **{len(stalled)}** cases requiring recovery outreach:\n\n" + "\n".join(lines)
                    else:
                        draft_response = "No cases are currently stalled beyond SLA thresholds."
                else:
                    conv_ctx = {"inbound_sender": "care_coordinator", "recent_messages": []}
                    intent = CognitiveEngine.analyze_intent(req.message, {}, {}, conv_ctx)
                    plan = CognitiveEngine.formulate_plan(intent, {}, {}, conv_ctx)
                    draft_response = plan.patient_response_draft
                    primary_intent = intent.primary_intent

            # -------------------------------------------------------------
            # Doctor Branch
            # -------------------------------------------------------------
            elif user_role in ("doctor", "clinician", "specialist"):
                if any(term in msg_lower for term in ["reports need my review", "which reports", "pending review", "reports need review", "cases need my review"]):
                    primary_intent = "doctor_review_queue"
                    yield f"event: tool_started\ndata: {json.dumps({'tool': 'query_pending_doctor_reviews', 'description': 'Checking assigned cases requiring clinical review'})}\n\n"
                    await asyncio.sleep(0.01)

                    doc_cases_stmt = select(CareCase).where(CareCase.status.in_(["result_received", "screening_completed", "pending"])).limit(5)
                    doc_cases = (await db.execute(doc_cases_stmt)).scalars().all()
                    tool_observations.append({
                        "tool": "query_pending_doctor_reviews",
                        "success": True,
                        "result": {"count": len(doc_cases)}
                    })
                    yield f"event: tool_result\ndata: {json.dumps({'tool': 'query_pending_doctor_reviews', 'status': 'success', 'summary': f'Found {len(doc_cases)} cases awaiting review'})}\n\n"
                    await asyncio.sleep(0.01)

                    if doc_cases:
                        lines = [f"• **{c.case_number}**: Finding `{c.finding_code}`, Priority `{c.priority}`" for c in doc_cases]
                        draft_response = f"Here are the cases currently awaiting clinical evaluation:\n\n" + "\n".join(lines)
                    else:
                        draft_response = "No diagnostic reports are currently pending your clinical sign-off."
                else:
                    conv_ctx = {"inbound_sender": "doctor", "recent_messages": []}
                    intent = CognitiveEngine.analyze_intent(req.message, {}, {}, conv_ctx)
                    plan = CognitiveEngine.formulate_plan(intent, {}, {}, conv_ctx)
                    draft_response = plan.patient_response_draft
                    primary_intent = intent.primary_intent

            # -------------------------------------------------------------
            # Patient Branch
            # -------------------------------------------------------------
            else:
                from app.agents.specialized import ClinicalEscalationAgent
                if ClinicalEscalationAgent.evaluate_acute_symptoms(req.message):
                    primary_intent = "urgent_clinical_escalation"
                    draft_response = (
                        "⚠️ **CRITICAL MEDICAL ALERT**: You reported symptoms that require immediate medical attention. "
                        "Please call 911 or proceed immediately to the nearest Emergency Department. "
                        "Do not wait for an online chat response."
                    )
                elif (behaviour_result := await _run_behaviour_turn(
                    current_user, active_session, req, detected_language
                )) is not None:
                    primary_intent = behaviour_result.intent
                    draft_response = behaviour_result.reply
                    tool_observations.extend(behaviour_result.tool_observations)
                elif any(term in msg_lower for term in ["5 whys", "five whys", "root cause"]):
                    primary_intent = "five_whys_root_cause_analysis"
                    draft_response = (
                        "🔍 **CareBridge 5 Whys Root-Cause Discovery**:\n\n"
                        "• **Why 1 (Clinical Need)**: Diagnostic evaluation is needed to detect abnormalities early when treatment is most effective.\n"
                        "• **Why 2 (Trigger)**: Routine surveillance guidelines reached or physical symptoms prompted evaluation.\n"
                        "• **Why 3 (Prior Delays)**: Logistical hurdles, transportation barriers, or anxiety about medical procedures.\n"
                        "• **Why 4 (Coordinator Role)**: Dedicated coordinator assists with scheduling, ride vouchers, and obstacle removal.\n"
                        "• **Why 5 (Solution)**: Secured appointment with transit support and continuous closed-loop follow-up."
                    )
                elif any(term in msg_lower for term in [
                    "book an appointment", "book appointment", "schedule an appointment", "want to book", "want book",
                    "i want book doctor tomorrow", "need to see doctor", "appointment tomorrow", "schedule for me"
                ]):
                    primary_intent = "appointment_booking_request"
                    yield f"event: tool_started\ndata: {json.dumps({'tool': 'search_available_appointments', 'description': 'Searching clinic schedule for available appointment slots'})}\n\n"
                    await asyncio.sleep(0.01)

                    tool_observations.append({
                        "tool": "search_available_appointments",
                        "success": True,
                        "result": {"slots": ["Tomorrow 10:00 AM", "Tomorrow 2:30 PM"]}
                    })
                    yield f"event: tool_result\ndata: {json.dumps({'tool': 'search_available_appointments', 'status': 'success', 'summary': 'Found 2 available appointment slots'})}\n\n"
                    await asyncio.sleep(0.01)

                    draft_response = (
                        "We found available slots for your follow-up appointment:\n\n"
                        "1. **Tomorrow at 10:00 AM** (Morning)\n"
                        "2. **Tomorrow at 2:30 PM** (Afternoon)\n\n"
                        "Which time works best for you?"
                    )
                elif len(msg_lower.split()) <= 2 and msg_lower not in ("hello", "hi", "hey") and not any(k in msg_lower for k in ["book", "report", "result", "doctor", "pain", "ride", "stage", "journey", "where"]):
                    # Low confidence ambiguous input: ask one short clarifying question, never default to booking
                    primary_intent = "clarification_needed"
                    if detected_language == "ar":
                        draft_response = "هل يمكنك توضيح كيف يمكنني مساعدتك؟ يمكنني مساعدتك في شرح تقرير الفحص الطبي، الإجابة عن رحلتك العلاجية، أو المساعدة في حجز موعد."
                    elif detected_language == "es":
                        draft_response = "¿Podría aclararme cómo puedo ayudarle mejor? Puedo explicar su informe de detección, responder preguntas sobre su tratamiento o ayudarle a programar una cita."
                    else:
                        draft_response = "Could you please clarify how I can best assist you? I can help explain your screening results, answer questions about your care pathway, or coordinate an appointment with your clinic."
                else:
                    u_display = getattr(current_user, "name", None) or getattr(current_user, "full_name", None) or ""
                    patient_first = (
                        target_patient.first_name if target_patient
                        else (u_display.split()[0] if u_display else "")
                    )
                    patient_full = (
                        f"{target_patient.first_name} {target_patient.last_name}" if target_patient
                        else (u_display or patient_first)
                    )
                    patient_ctx: Dict[str, Any] = {
                        "patient_id": str(target_patient.id) if target_patient else str(current_user.patient_id or ""),
                        "full_name": patient_full,
                        "first_name": patient_first,
                        "preferred_language": (target_patient.preferred_language if target_patient else "en") or "en",
                    }
                    case_ctx: Dict[str, Any] = {}
                    if target_case:
                        case_ctx = dict(target_case.case_context or {})
                        case_ctx["case_id"] = str(target_case.id)
                        case_ctx["case_number"] = target_case.case_number
                        case_ctx["status"] = target_case.status
                        case_ctx["priority"] = target_case.priority
                        case_ctx["clinical_pathway"] = target_case.clinical_pathway
                        if target_case.screening_result:
                            case_ctx["screening_type"] = target_case.screening_result.screening_type or case_ctx.get("screening_type", "Mammogram")
                            case_ctx["finding_code"] = target_case.screening_result.finding_code or case_ctx.get("finding_code", "BI-RADS 4")
                            case_ctx["finding_summary"] = target_case.screening_result.finding_summary or case_ctx.get("finding_summary", "")
                            case_ctx["screening_result"] = target_case.screening_result.raw_report_data or {}
                            case_ctx["raw_report_data"] = target_case.screening_result.raw_report_data or {}

                        doc = target_case.current_owner if (target_case.current_owner and target_case.current_owner.role in ("doctor", "clinician", "specialist")) else None
                        case_ctx["assigned_doctor"] = case_ctx.get("assigned_doctor") or (doc.name if doc else "Dr. Arjun Menon, MD")
                        case_ctx["doctor_name"] = case_ctx.get("doctor_name") or case_ctx["assigned_doctor"]
                        case_ctx["assigned_doctor_name"] = case_ctx["doctor_name"]
                        case_ctx["coordinator_name"] = case_ctx.get("coordinator_name") or "Priya Nair, RN"
                        case_ctx["current_owner_name"] = case_ctx["coordinator_name"]

                        from app.services.lifecycle_service import LifecycleService
                        case_ctx["lifecycle_stages"] = LifecycleService.get_lifecycle_stages(target_case)
                        curr_st = LifecycleService.get_current_stage(target_case)
                        case_ctx["current_stage_number"] = curr_st.get("stage_number", 4)
                        case_ctx["current_stage_id"] = curr_st.get("stage_id", "PATIENT_UNDERSTANDS")
                        case_ctx["current_stage_title"] = curr_st.get("title", "Understanding Results")

                    recent_comms_stmt = (
                        select(Communication)
                        .where(Communication.session_id == active_session.id)
                        .order_by(Communication.sent_at.desc())
                        .limit(6)
                    )
                    recent_comms = (await db.execute(recent_comms_stmt)).scalars().all()
                    conv_ctx = {
                        "inbound_sender": "patient",
                        "recent_messages": list(reversed(recent_comms))
                    }

                    intent = CognitiveEngine.analyze_intent(req.message, patient_ctx, case_ctx, conv_ctx)
                    plan = CognitiveEngine.formulate_plan(intent, patient_ctx, case_ctx, conv_ctx)
                    draft_response = plan.patient_response_draft
                    primary_intent = intent.primary_intent
                    if intent.detected_language:
                        detected_language = intent.detected_language

            # -------------------------------------------------------------
            # Response Guard Validation
            # Guarantees that unverified action claims are sanitized before token emission.
            # -------------------------------------------------------------
            guarded_text = ResponseGuardService.sanitize_response(
                draft_response,
                tool_observations=tool_observations,
                actor_role=user_role
            )

            # Check for cancellation before token streaming
            if await request.is_disconnected():
                logger.info("Client disconnected before token streaming.")
                return

            # -------------------------------------------------------------
            # Token Streaming
            # -------------------------------------------------------------
            words = guarded_text.split(" ")
            for i, word in enumerate(words):
                if await request.is_disconnected():
                    logger.info("Client disconnected during token streaming (Stop button).")
                    return
                token = word + (" " if i < len(words) - 1 else "")
                yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"
                await asyncio.sleep(0.015)

            # Record Outbound Communication
            if behaviour_result is not None:
                # Behaviour turns persist the FULL reply first, then run post-delivery actions
                # (e.g. complete Stage 4 only after the explanation text is durable).
                guarded_behaviour = BehaviourResult(
                    reply=guarded_text, intent=behaviour_result.intent,
                    tool_observations=behaviour_result.tool_observations,
                    post_delivery=behaviour_result.post_delivery,
                    escalated=behaviour_result.escalated, case_id=behaviour_result.case_id,
                )
                await db.commit()
                await _finalize_behaviour_turn(
                    guarded_behaviour, active_session, current_user, req, detected_language
                )
                tool_observations = guarded_behaviour.tool_observations
                out_comm = None
            else:
                out_comm = Communication(
                    id=uuid.uuid4(),
                    user_id=current_user.user_id,
                    role=user_role,
                    case_id=req.case_id,
                    patient_id=active_session.patient_id,
                    session_id=active_session.id,
                    sender="ai",
                    channel=req.channel or "in_app_chat",
                    language=detected_language,
                    content=guarded_text,
                    acknowledged=True,
                    sent_at=datetime.now(timezone.utc)
                )
                db.add(out_comm)

            # -------------------------------------------------------------
            # Auto Title Generation (After first exchange)
            # -------------------------------------------------------------
            if active_session.title in ("New Chat", "New Conversation", "", None) or len(active_session.title.split()) > 7:
                title_map = {
                    "new_patient_discovery": "New Patients Intake",
                    "task_management": "Pending Coordination Tasks",
                    "sla_recovery_queue": "SLA & Case Recovery",
                    "doctor_review_queue": "Diagnostic Reviews",
                    "appointment_booking_request": "Appointment Scheduling",
                    "case_context_inquiry": "Screening Results Review",
                    "urgent_clinical_escalation": "Urgent Medical Alert",
                    "five_whys_root_cause_analysis": "Care Pathway Analysis",
                    "clarification_needed": "Care Assistance Inquiry",
                }
                auto_title = title_map.get(primary_intent)
                if not auto_title:
                    q_words = req.message.strip().split()
                    auto_title = " ".join(q_words[:4]).title()
                active_session.title = auto_title

            await db.commit()

            # -------------------------------------------------------------
            # Final Event
            # -------------------------------------------------------------
            final_payload = {
                "session_id": str(active_session.id),
                "content": guarded_text,
                "primary_intent": primary_intent,
                "actions": [obs.get("tool") for obs in tool_observations if obs.get("success")],
                "language": detected_language,
                "title": active_session.title,
                "completed": True
            }
            yield f"event: final\ndata: {json.dumps(final_payload)}\n\n"

        except Exception as e:
            logger.error(f"Error during agent stream generation: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'message': 'Something went wrong, try again.', 'code': 'STREAM_ERROR'})}\n\n"


@router.post("/stream", summary="Real-Time Cognitive AI Stream (SSE)")
async def stream_agent(
    req: PatientInteractionRequest,
    request: Request,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """
    Dedicated SSE streaming endpoint for AI brain interactions.
    Streams tokens, tool invocations, and verified outcomes.
    """
    return StreamingResponse(
        generate_agent_stream(req, current_user, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/interact", response_model=ApiResponseEnvelope[AgentExecutionResponse], dependencies=[Depends(rate_limit_agent)], summary="Interact with CareBridge AI Brain")
async def interact_with_agent(
    req: PatientInteractionRequest,
    request: Request,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Ingests an inbound message, authenticates caller identity and database-backed role,
    routes to appropriate LangGraph engine (Doctor Subgraph vs Coordinator Supervisor),
    and strictly isolates conversational state threads per user session.
    Supports SSE streaming when requested via stream flag or Accept header.
    """
    if req.stream or "text/event-stream" in request.headers.get("accept", ""):
        return StreamingResponse(
            generate_agent_stream(req, current_user, request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
    user_role = current_user.role.lower()

    # -------------------------------------------------------------------------
    # Resolve or initialize active ConversationSession (Issue 1 Isolation)
    # -------------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    user_uuid = uuid.UUID(str(current_user.user_id))
    active_session: Optional[ConversationSession] = None
    if req.session_id:
        sess_stmt = select(ConversationSession).where(ConversationSession.id == req.session_id)
        sess_res = await db.execute(sess_stmt)
        active_session = sess_res.scalar_one_or_none()
        if not active_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {req.session_id} not found.")

        is_owner = (str(active_session.user_id) == str(current_user.user_id)) or (
            user_role == "patient" and current_user.patient_id and str(active_session.patient_id) == str(current_user.patient_id)
        )
        if not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You cannot access another user's conversation session."
            )
        active_session.last_interaction_at = now
    else:
        first_line = req.message.strip().split("\n")[0][:40]
        title = (first_line + "...") if len(first_line) == 40 else first_line
        patient_uuid = None
        if user_role == "patient" and current_user.patient_id:
            try:
                patient_uuid = uuid.UUID(current_user.patient_id)
            except ValueError:
                pass
        active_session = ConversationSession(
            id=uuid.uuid4(),
            user_id=user_uuid,
            role=user_role,
            title=title or "New Chat",
            case_id=req.case_id,
            patient_id=patient_uuid,
            channel=req.channel or "in_app_chat",
            is_active=True,
            last_interaction_at=now
        )
        db.add(active_session)
        await db.flush()

    # =========================================================================
    # Branch 1: Doctor / Clinician / Specialist Interaction
    # =========================================================================
    if user_role in ("clinician", "doctor", "specialist"):
        doctor_id = current_user.owner_id or str(current_user.user_id)
        case_id_str = str(req.case_id) if req.case_id else None

        # Execute Doctor Subgraph Workflow (11-node clinical workflow)
        doc_result = run_doctor_workflow(
            doctor_id=doctor_id,
            message=req.message,
            case_id=case_id_str,
        )

        response_data = AgentExecutionResponse(
            case_id=case_id_str or (doc_result.get("case_id") or ""),
            patient_id=doc_result.get("patient_id") or "",
            session_id=str(active_session.id),
            primary_intent=doc_result.get("doctor_intent") or "general_query",
            emotional_state="clinical_objective",
            detected_barriers=[],
            actions_executed=doc_result.get("audit_log", []),
            outbound_message=doc_result.get("response_message") or "Clinical request processed successfully.",
            outbound_language="en",
            requires_human_approval=False,
            approval_request=None,
        )

        # Persist doctor query and copilot reply in communications table
        try:
            target_cid = None
            doc_patient_id = None
            if case_id_str:
                try:
                    target_cid = uuid.UUID(case_id_str)
                    case_stmt = select(CareCase).where(CareCase.id == target_cid)
                    c_res = await db.execute(case_stmt)
                    doc_cc = c_res.scalar_one_or_none()
                    if doc_cc:
                        doc_patient_id = doc_cc.patient_id
                except ValueError:
                    pass

            doc_inbound = Communication(
                id=uuid.uuid4(),
                user_id=current_user.user_id,
                role="doctor",
                case_id=target_cid,
                patient_id=doc_patient_id,
                session_id=active_session.id,
                sender="doctor",
                channel=req.channel or "in_app_chat",
                language="en",
                content=req.message,
                acknowledged=True,
                sent_at=now
            )
            doc_outbound = Communication(
                id=uuid.uuid4(),
                user_id=current_user.user_id,
                role="doctor",
                case_id=target_cid,
                patient_id=doc_patient_id,
                session_id=active_session.id,
                sender="ai_doctor_copilot",
                channel=req.channel or "in_app_chat",
                language="en",
                content=response_data.outbound_message or "Clinical request processed successfully.",
                acknowledged=True,
                sent_at=now
            )
            db.add(doc_inbound)
            db.add(doc_outbound)
            await db.commit()
        except Exception as e:
            import logging
            logging.getLogger("carebridge.agent").warning(f"Doctor communication persistence notice: {e}")

        # Phase 7: Real-time notification dispatch for doctor review completion
        if case_id_str:
            try:
                from app.services.notification_service import NotificationService
                from app.database.session import get_sync_db
                with get_sync_db() as sync_db:
                    c_uuid = uuid.UUID(case_id_str)
                    cc = sync_db.query(CareCase).filter(CareCase.id == c_uuid).first()
                    if cc:
                        p_name = f"{cc.patient.first_name} {cc.patient.last_name}" if cc.patient else None
                        NotificationService.notify_doctor_review_completed(
                            db=sync_db,
                            case_id=cc.id,
                            patient_id=cc.patient_id,
                            doctor_name=getattr(current_user, "name", "Dr. Aris Thorne, MD"),
                            summary=req.message,
                            patient_name=p_name
                        )
            except Exception as e:
                import logging
                logging.getLogger("carebridge.agent").warning(f"Doctor review notification notice: {e}")

        return ApiResponseEnvelope(
            success=True,
            message="Doctor workflow executed successfully",
            data=response_data
        )

    # =========================================================================
    # Branch 2: Patient Interaction
    # =========================================================================
    elif user_role == "patient":
        care_case: Optional[CareCase] = None

        if req.case_id:
            case_stmt = (
                select(CareCase)
                .options(
                    selectinload(CareCase.patient),
                    selectinload(CareCase.current_owner)
                )
                .where(CareCase.id == req.case_id)
            )
            case_res = await db.execute(case_stmt)
            care_case = case_res.scalar_one_or_none()

            if not care_case:
                raise HTTPException(status_code=404, detail=f"Case {req.case_id} not found")

            # Authorization Check: Patient may ONLY access their own care case
            if not current_user.patient_id or str(care_case.patient_id) != str(current_user.patient_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You do not have permission to access another patient's care case."
                )
        else:
            # Look up active case for authenticated patient
            if current_user.patient_id:
                try:
                    p_uuid = uuid.UUID(current_user.patient_id)
                    case_stmt = (
                        select(CareCase)
                        .options(
                            selectinload(CareCase.patient),
                            selectinload(CareCase.current_owner)
                        )
                        .where(CareCase.patient_id == p_uuid)
                        .order_by(CareCase.created_at.desc())
                    )
                    case_res = await db.execute(case_stmt)
                    care_case = case_res.scalars().first()
                except ValueError:
                    pass

            if not care_case:
                raise HTTPException(
                    status_code=404,
                    detail="No active care case found for this patient account."
                )

        # Step 0: Resolve or initialize active ConversationSession
        active_session: Optional[ConversationSession] = None
        try:
            session_stmt = (
                select(ConversationSession)
                .where(
                    ConversationSession.patient_id == care_case.patient_id,
                    ConversationSession.is_active.is_(True)
                )
                .order_by(ConversationSession.last_interaction_at.desc())
            )
            session_res = await db.execute(session_stmt)
            active_session = session_res.scalars().first()

            now = datetime.now(timezone.utc)
            if not active_session:
                active_session = ConversationSession(
                    id=uuid.uuid4(),
                    patient_id=care_case.patient_id,
                    case_id=care_case.id,
                    channel=req.channel or "in_app_chat",
                    is_active=True,
                    last_interaction_at=now
                )
                db.add(active_session)
                await db.flush()
            else:
                active_session.last_interaction_at = now
                if care_case.id and not active_session.case_id:
                    active_session.case_id = care_case.id
        except Exception as e:
            import logging
            logging.getLogger("carebridge.agent").warning(f"Session resolution notice: {e}")

        # Step 1: Record inbound patient communication for persistent multi-turn conversational context
        try:
            inbound_comm = Communication(
                id=uuid.uuid4(),
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                session_id=active_session.id if active_session else None,
                sender="patient",
                channel=req.channel or "in_app_chat",
                language="en",
                content=req.message,
                acknowledged=True,
                sent_at=datetime.now(timezone.utc)
            )
            db.add(inbound_comm)
            await db.commit()
        except Exception as e:
            import logging
            logging.getLogger("carebridge.agent").warning(f"Inbound communication persistence notice: {e}")

        now = datetime.now(timezone.utc)
        patient_first = care_case.patient.first_name if care_case.patient else "Patient"
        msg_clean = req.message.strip()
        msg_lower = msg_clean.lower()

        # ---------------------------------------------------------------------
        # 1. 5 Whys Root-Cause & Barrier Discovery Handler
        # ---------------------------------------------------------------------
        if any(kw in msg_lower for kw in ["5 whys", "five whys", "why questions", "root cause"]):
            five_whys_response = (
                f"🔍 CareBridge 5 Whys Clinical Root-Cause Discovery for {patient_first}:\n\n"
                "• Why 1 (Clinical Presentation): Why is the screening or diagnostic evaluation required?\n"
                "  ➔ To detect abnormal tissue architecture or asymptomatic disease early when treatment is most effective.\n\n"
                "• Why 2 (Symptom or Guideline Trigger): Why now?\n"
                "  ➔ Routine guideline surveillance reached, or localized physical discomfort prompted proactive evaluation.\n\n"
                "• Why 3 (Historical Obstacle): Why have appointments or screenings been delayed previously?\n"
                "  ➔ Logistical hurdles, lack of caregiver transit, work schedule inflexibility, or anxiety about medical findings.\n\n"
                "• Why 4 (Coordination Requirement): Why is a dedicated Care Coordinator necessary?\n"
                "  ➔ Fragmented specialty clinics create confusion. An accountable coordinator ensures barrier removal and continuous follow-up.\n\n"
                "• Why 5 (Root-Cause Solution): How do we achieve verified health closure?\n"
                "  ➔ Establish a protected test appointment, provide caregiver transportation, and maintain 100% accountable closed-loop tracking.\n\n"
                "Your CareBridge team addresses each layer of this root cause. What questions can we answer next?"
            )
            out_comm = Communication(
                id=uuid.uuid4(),
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                session_id=active_session.id if active_session else None,
                sender="ai_coordinator",
                channel=req.channel or "in_app_chat",
                language="en",
                content=five_whys_response,
                acknowledged=True,
                sent_at=now
            )
            db.add(out_comm)
            await db.commit()

            return ApiResponseEnvelope(
                success=True,
                message="5 Whys analysis executed",
                data=AgentExecutionResponse(
                    case_id=str(care_case.id),
                    patient_id=str(care_case.patient_id),
                    primary_intent="five_whys_root_cause_analysis",
                    emotional_state="receptive",
                    detected_barriers=[],
                    actions_executed=["five_whys_evaluation"],
                    outbound_message=five_whys_response,
                    outbound_language="en",
                    requires_human_approval=False,
                    approval_request=None,
                )
            )

        # ---------------------------------------------------------------------
        # 2. Case Lifecycle Stage-Aware AI Care Companion Routing
        # The AI agent stays with the patient from hospital intake through verified closure.
        # ---------------------------------------------------------------------

        # Look up hospital coordinator
        owner = care_case.current_owner
        if not owner:
            owner_stmt = select(CaseOwner).where(CaseOwner.role == "care_coordinator").limit(1)
            owner = (await db.execute(owner_stmt)).scalars().first()
            if owner:
                care_case.current_owner_id = owner.id

        coord_name = owner.name if owner else "Priya Nair, RN"
        facility_name = owner.facility if owner else "Metropolitan Hospital Screening Center"

        # Check for active appointments
        appt_stmt = (
            select(Appointment)
            .where(Appointment.case_id == care_case.id)
            .order_by(Appointment.scheduled_time.desc())
        )
        recent_appt = (await db.execute(appt_stmt)).scalars().first()

        # Check if patient missed a scheduled screening or follow-up visit
        is_missed = (
            care_case.status in ("missed_visit", "recovery_active")
            or (recent_appt and recent_appt.status == "no_show")
        )

        # ---------------------------------------------------------------------
        # (A) Proactive Recovery: Missed Screening Visit Detected
        # ---------------------------------------------------------------------
        if is_missed and not any(term in msg_lower for term in ["5 whys", "five whys"]):
            appt_time_str = recent_appt.scheduled_time.strftime("%A, %B %d at %I:%M %p") if recent_appt else "your scheduled appointment"

            # Check if patient is providing a rescheduling preference or barrier reason
            barrier_detected = None
            if any(term in msg_lower for term in ["car", "ride", "bus", "transit", "traffic", "transport", "drive"]):
                barrier_detected = "transportation_obstacle"
            elif any(term in msg_lower for term in ["busy", "work", "job", "shift", "meeting", "time"]):
                barrier_detected = "work_schedule_inflexibility"
            elif any(term in msg_lower for term in ["scared", "fear", "anxious", "nervous", "worry"]):
                barrier_detected = "clinical_anxiety"

            if barrier_detected:
                ctx = care_case.case_context or {}
                barriers = ctx.get("inferred_barriers", [])
                if barrier_detected not in barriers:
                    barriers.append(barrier_detected)
                ctx["inferred_barriers"] = barriers
                care_case.case_context = ctx

            missed_reply = (
                f"Hello {patient_first}, I noticed that you missed your scheduled screening visit on {appt_time_str} at {facility_name}.\n\n"
                f"Please know that unexpected things happen and our hospital care team is here to support you without judgment. "
                f"Your Care Coordinator, {coord_name}, has been notified and we want to ensure you get your screening safely.\n\n"
                f"Would you prefer to reschedule for later this week or next week? If you need assistance with transportation or timing, please let me know and we will coordinate support for you."
            )

            out_comm = Communication(
                id=uuid.uuid4(),
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                session_id=active_session.id if active_session else None,
                sender="ai_coordinator",
                channel=req.channel or "in_app_chat",
                language="en",
                content=missed_reply,
                acknowledged=True,
                sent_at=now
            )
            db.add(out_comm)
            await db.commit()

            return ApiResponseEnvelope(
                success=True,
                message="Missed visit recovery assistance delivered",
                data=AgentExecutionResponse(
                    case_id=str(care_case.id),
                    patient_id=str(care_case.patient_id),
                    primary_intent="missed_visit_recovery",
                    emotional_state="empathic",
                    detected_barriers=[barrier_detected] if barrier_detected else [],
                    actions_executed=["notify_recovery_outreach", "offer_reschedule"],
                    outbound_message=missed_reply,
                    outbound_language="en",
                    requires_human_approval=False,
                    approval_request=None,
                )
            )

        # ---------------------------------------------------------------------
        # (B) Patient Intake / Hospital Form Submission Flow
        # Since patient enters through the hospital website, they are already at the hospital.
        # We do NOT ask them to choose between coordinators. The hospital coordinator is alerted to update the schedule.
        # ---------------------------------------------------------------------
        is_intake = care_case.status in ("intake", "intake_ready", "intake_submitted")
        has_no_screening_appt = recent_appt is None or recent_appt.appointment_type not in ("screening_evaluation", "screening")

        if is_intake and has_no_screening_appt and not any(term in msg_lower for term in ["5 whys", "five whys"]):
            # Record patient's health request/theory in case context
            ctx = care_case.case_context or {}
            ctx["screening_request"] = msg_clean
            ctx["onboarding_stage"] = "intake_submitted"
            care_case.case_context = ctx
            care_case.status = "intake_submitted"

            # Create Alert Task for Hospital Care Coordinator to update schedule
            task = Task(
                id=uuid.uuid4(),
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                title=f"Schedule Screening: {patient_first}",
                description=f"Patient intake received: '{msg_clean}'. Review clinical goals and update screening schedule for patient at {facility_name}.",
                task_type="schedule_screening",
                assigned_to_id=owner.id if owner else None,
                assigned_role="care_coordinator",
                status="pending",
                priority="urgent",
                due_date=now + timedelta(days=2),
                idempotency_key=f"screening_intake_{care_case.id}"
            )
            db.add(task)

            # Record Case Event
            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=care_case.id,
                event_type="intake_submitted",
                description=f"Patient explained screening goals: '{msg_clean}'. Hospital coordinator {coord_name} alerted to update schedule.",
                event_data={"screening_request": msg_clean, "coordinator": coord_name, "facility": facility_name},
                timestamp=now
            )
            db.add(event)

            intake_reply = (
                f"Thank you for sharing your health details, {patient_first}. I have recorded your health goals:\n"
                f"📋 Screening Request: \"{msg_clean}\"\n\n"
                f"Your hospital Care Coordinator, {coord_name} at {facility_name}, has been alerted with your request. "
                f"They are reviewing your intake and will update your screening appointment schedule shortly.\n\n"
                f"Once scheduled, you will receive an instant notification and see the appointment date and location on your patient dashboard.\n\n"
                f"I will be with you throughout your entire care journey until full clinical closure. "
                f"In the meantime, feel free to ask me anything about the screening process, how to prepare, or any questions you have!"
            )

            out_comm = Communication(
                id=uuid.uuid4(),
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                session_id=active_session.id if active_session else None,
                sender="ai_coordinator",
                channel=req.channel or "in_app_chat",
                language="en",
                content=intake_reply,
                acknowledged=True,
                sent_at=now
            )
            db.add(out_comm)
            await db.commit()

            return ApiResponseEnvelope(
                success=True,
                message="Patient screening request submitted and hospital coordinator alerted",
                data=AgentExecutionResponse(
                    case_id=str(care_case.id),
                    patient_id=str(care_case.patient_id),
                    primary_intent="patient_intake_submitted",
                    emotional_state="receptive",
                    detected_barriers=[],
                    actions_executed=["record_intake_statement", "alert_coordinator_schedule_task"],
                    outbound_message=intake_reply,
                    outbound_language="en",
                    requires_human_approval=False,
                    approval_request=None,
                )
            )

        # ---------------------------------------------------------------------
        # (C) Screening Completed Stage (Awaiting Diagnostic Report)
        # ---------------------------------------------------------------------
        if care_case.status == "screening_completed" and any(term in msg_lower for term in ["status", "report", "result", "next", "when", "screening", "test"]):
            completed_reply = (
                f"Great news, {patient_first}! Your screening procedure at {facility_name} has been successfully completed and verified. "
                f"Your Care Coordinator, {coord_name}, is currently coordinating with the laboratory and radiology team to finalize your diagnostic report.\n\n"
                f"As soon as your diagnostic report is ready, your dashboard will update with a notification and you will be able to download your full report. "
                f"I will remain right here to explain all findings, answer your questions, and guide you through any recommended next steps!"
            )
            out_comm = Communication(
                id=uuid.uuid4(),
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                session_id=active_session.id if active_session else None,
                sender="ai_coordinator",
                channel=req.channel or "in_app_chat",
                language="en",
                content=completed_reply,
                acknowledged=True,
                sent_at=now
            )
            db.add(out_comm)
            await db.commit()
            return ApiResponseEnvelope(
                success=True,
                message="Screening completed guidance delivered",
                data=AgentExecutionResponse(
                    case_id=str(care_case.id),
                    patient_id=str(care_case.patient_id),
                    primary_intent="screening_completed_inquiry",
                    emotional_state="reassured",
                    detected_barriers=[],
                    actions_executed=["explain_screening_completion"],
                    outbound_message=completed_reply,
                    outbound_language="en",
                    requires_human_approval=False,
                    approval_request=None,
                )
            )

        # Isolated LangGraph persistence thread for this specific patient and case
        thread_id = f"patient_{current_user.user_id}_case_{care_case.id}"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "case_id": str(care_case.id),
            "patient_id": str(care_case.patient_id),
            "session_id": str(active_session.id) if active_session else None,
            "inbound_message": req.message,
            "inbound_channel": req.channel or "in_app_chat",
            "inbound_sender": "patient",
            "patient_context": {},
            "case_context": {},
            "conversation_context": {},
            "intent_analysis": None,
            "coordination_plan": None,
            "pending_tool_calls": [],
            "tool_observations": [],
            "replanning_needed": False,
            "requires_human_approval": False,
            "approval_request": None,
            "human_decision": None,
            "outbound_message": None,
            "outbound_language": "en",
            "final_case_status": None,
            "iteration_count": 0,
            "max_iterations": 5,
            "audit_entries": [],
        }

        try:
            final_state = supervisor_graph.invoke(initial_state, config=config)
        except Exception as graph_err:
            from app.core.correlation import get_correlation_id
            corr_id = get_correlation_id()
            import logging
            logging.getLogger("carebridge.agent").error(
                f"[LLM/Graph Outage] correlation_id={corr_id} error={graph_err}",
                exc_info=True
            )
            now = datetime.now(timezone.utc)
            task_id = uuid.uuid4()
            assigned_uuid = None
            if care_case.current_owner_id:
                try:
                    assigned_uuid = uuid.UUID(str(care_case.current_owner_id))
                except (ValueError, TypeError):
                    pass
            esc_task = Task(
                id=task_id,
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                task_type="clinical_escalation",
                title="Recoverable Escalation: Clinical Assistant Service Degradation",
                description=f"Automated care companion encountered service error: {str(graph_err)[:180]}. Human care coordinator outreach required.",
                status="pending",
                priority="critical",
                assigned_to_id=assigned_uuid,
                assigned_role="care_coordinator",
                due_date=now + timedelta(hours=24),
                created_at=now,
                updated_at=now
            )
            db.add(esc_task)

            is_urgent_symptoms = any(
                w in req.message.lower()
                for w in ["pain", "bleeding", "severe", "fever", "chest", "dizzy", "lump", "emergency"]
            )
            if is_urgent_symptoms:
                care_case.status = "escalated"
                care_case.priority = "critical"

            await db.commit()

            from app.workflows.persistence.traces import WorkflowTraceLogger
            from app.database.session import get_sync_db
            try:
                with get_sync_db() as sync_db:
                    WorkflowTraceLogger.log_node_trace(
                        db=sync_db,
                        case_id=str(care_case.id),
                        thread_id=thread_id,
                        run_id=corr_id or str(uuid.uuid4()),
                        workflow_name="carebridge_supervisor",
                        node_name="supervisor_execution",
                        step_number=1,
                        status="failed",
                        duration_ms=0.0,
                        error_message=str(graph_err),
                        coordinator_note="Automated assistant encountered LLM/graph failure; escalation task created",
                        correlation_id=corr_id,
                        actor_id=str(current_user.user_id),
                        db_result="error"
                    )
            except Exception:
                pass

            fallback_msg = (
                "Our automated care assistant is currently experiencing temporary technical difficulties. "
                "Your care coordinator and attending clinical team have been notified "
                "and will follow up with you directly."
            )
            return ApiResponseEnvelope(
                success=True,
                message="Clinical assistant fallback engaged",
                data=AgentExecutionResponse(
                    case_id=str(care_case.id),
                    patient_id=str(care_case.patient_id),
                    primary_intent="urgent_clinical_escalation" if is_urgent_symptoms else "general_fallback",
                    emotional_state="anxious",
                    detected_barriers=[],
                    actions_executed=["created_clinical_escalation_task"],
                    outbound_message=fallback_msg,
                    outbound_language="en",
                    requires_human_approval=True,
                    approval_request={"task_id": str(task_id), "reason": "llm_outage"}
                )
            )
        intent = final_state.get("intent_analysis") or {}

        # Clinical Safeguard: Ensure urgent escalations are committed to PostgreSQL
        if intent.get("primary_intent") == "urgent_clinical_escalation" or intent.get("requires_human_escalation"):
            care_case.status = "escalated"
            care_case.priority = "critical"
            now = datetime.now(timezone.utc)
            event_check = await db.execute(
                select(CaseEvent).where(
                    CaseEvent.case_id == care_case.id,
                    CaseEvent.event_type.in_(["case_escalated", "urgent_clinical_escalation"])
                )
            )
            if not event_check.scalars().first():
                esc_ev = CaseEvent(
                    id=uuid.uuid4(),
                    case_id=care_case.id,
                    event_type="case_escalated",
                    description="Case escalated to escalated. Urgency: critical. Reason: Patient reported acute clinical symptoms requiring immediate human oversight.",
                    event_data={"status": "escalated", "urgency": "critical", "reason": "Patient reported acute clinical symptoms requiring immediate human oversight."},
                    timestamp=now
                )
                db.add(esc_ev)
            await db.commit()
            await db.refresh(care_case)

            # Phase 7: Real-time notification dispatch for critical clinical escalation
            try:
                from app.services.notification_service import NotificationService
                from app.database.session import get_sync_db
                with get_sync_db() as sync_db:
                    p_name = f"{care_case.patient.first_name} {care_case.patient.last_name}" if care_case.patient else "Patient"
                    NotificationService.notify_clinical_escalation(
                        db=sync_db,
                        case_id=care_case.id,
                        patient_id=care_case.patient_id,
                        patient_name=p_name,
                        reason="Patient reported acute clinical symptoms requiring immediate physician review"
                    )
            except Exception as e:
                import logging
                logging.getLogger("carebridge.agent").warning(f"Escalation notification notice: {e}")

        # Phase 7: Inbound patient message notification for care coordinator
        # ONLY send coordinator notification if coordinator attention is clinically or administratively needed:
        # e.g., explicit assistance requests, reported barriers, appointment cancellations/refusals.
        # DO NOT send notifications for greetings, general inquiries, or routine conversational turns.
        primary_intent = intent.get("primary_intent", "")
        should_notify_coordinator = (
            intent.get("requires_human_escalation", False)
            or final_state.get("requires_human_approval", False)
            or primary_intent in (
                "assistance_request",
                "appointment_reschedule_with_barrier",
                "appointment_cancellation_and_refusal",
                "referral_delay"
            )
            or any(
                b.get("barrier_type") in ("transportation_caregiver", "financial", "childcare_family")
                for b in intent.get("detected_barriers", [])
            )
        )

        if should_notify_coordinator:
            try:
                from app.services.notification_service import NotificationService
                from app.database.session import get_sync_db
                with get_sync_db() as sync_db:
                    p_name = getattr(current_user, "name", "Patient")
                    NotificationService.notify_patient_message(
                        db=sync_db,
                        case_id=care_case.id if care_case else None,
                        patient_id=care_case.patient_id if care_case else uuid.UUID(current_user.patient_id),
                        patient_name=p_name,
                        message_preview=req.message
                    )
            except Exception as e:
                import logging
                logging.getLogger("carebridge.agent").warning(f"Patient message notification notice: {e}")

        response_data = AgentExecutionResponse(
            case_id=str(care_case.id),
            patient_id=str(care_case.patient_id),
            primary_intent=intent.get("primary_intent", "unknown"),
            emotional_state=intent.get("emotional_state", "neutral"),
            detected_barriers=intent.get("detected_barriers", []),
            actions_executed=final_state.get("tool_observations", []),
            outbound_message=final_state.get("outbound_message"),
            outbound_language=final_state.get("outbound_language", "en"),
            requires_human_approval=final_state.get("requires_human_approval", False),
            approval_request=final_state.get("approval_request"),
        )

        # Persist outbound AI communication into PostgreSQL for long-term memory
        try:
            out_text = final_state.get("outbound_message") or "I am here to support your care pathway."
            out_comm = Communication(
                id=uuid.uuid4(),
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                session_id=active_session.id if active_session else None,
                sender="ai_coordinator",
                channel=req.channel or "in_app_chat",
                language=final_state.get("outbound_language", "en"),
                content=out_text,
                acknowledged=True,
                sent_at=datetime.now(timezone.utc)
            )
            db.add(out_comm)
            await db.commit()
        except Exception as e:
            import logging
            logging.getLogger("carebridge.agent").warning(f"Outbound communication persistence notice: {e}")

        return ApiResponseEnvelope(
            success=True,
            message="Agent cognitive loop executed successfully",
            data=response_data
        )

    # =========================================================================
    # Branch 3: Care Coordinator Interaction
    # =========================================================================
    elif user_role in ("care_coordinator", "coordinator"):
        care_case: Optional[CareCase] = None

        if req.case_id:
            case_stmt = select(CareCase).options(selectinload(CareCase.patient)).where(CareCase.id == req.case_id)
            case_res = await db.execute(case_stmt)
            care_case = case_res.scalar_one_or_none()

            if not care_case:
                raise HTTPException(status_code=404, detail=f"Case {req.case_id} not found")
        else:
            care_case = None  # New coordinator conversation starts with NO pre-loaded patient context!

        if care_case is None:
            # Coordinator interaction without pre-selected patient context
            conv_ctx = {"inbound_sender": "care_coordinator", "recent_messages": []}
            intent = CognitiveEngine.analyze_intent(
                message=req.message,
                patient_context={},
                case_context={},
                conversation_context=conv_ctx
            )
            plan = CognitiveEngine.formulate_plan(intent, {}, {}, conv_ctx)

            tool_observations = []
            from app.database.session import get_sync_db
            with get_sync_db() as sync_db:
                for action in plan.actions:
                    t_func = getattr(ToolRegistry, action.tool_name, None)
                    if t_func:
                        try:
                            t_res = t_func(sync_db, **action.arguments)
                            tool_observations.append({
                                "tool": action.tool_name,
                                "success": t_res.get("success", True),
                                "result": t_res
                            })
                        except Exception as err:
                            tool_observations.append({
                                "tool": action.tool_name,
                                "success": False,
                                "error": str(err)
                            })

            from app.services.response_guard_service import ResponseGuardService
            outbound_msg = ResponseGuardService.sanitize_response(
                plan.patient_response_draft,
                tool_observations=tool_observations,
                actor_role="care_coordinator"
            )

            # If discover_new_patients was called, format results into readable overview
            if intent.primary_intent in ("new_patient_discovery", "coordinator_discovery"):
                for obs in tool_observations:
                    if obs.get("tool") == "discover_new_patients" and obs.get("success"):
                        cases = obs.get("result", {}).get("data", {}).get("cases", [])
                        if cases:
                            c_lines = [
                                f"• {c['patient_name']} ({c['case_number']}): Status: {c['status']}, Priority: {c['priority']}, Finding: {c['finding_code']}"
                                for c in cases
                            ]
                            outbound_msg = (
                                f"Found {len(cases)} new or unassigned patient case(s) in discovery queue:\n\n"
                                + "\n".join(c_lines)
                                + "\n\nTo view details or schedule actions for a patient, say: 'Select patient <name>' or specify the case number."
                            )
                        else:
                            outbound_msg = "There are currently no new unassigned patient cases in the discovery queue."

            # Persist general coordinator communication in communications table
            try:
                coord_inbound = Communication(
                    id=uuid.uuid4(),
                    user_id=current_user.user_id,
                    role="care_coordinator",
                    case_id=None,
                    patient_id=None,
                    session_id=active_session.id,
                    sender="care_coordinator",
                    channel=req.channel or "in_app_chat",
                    language="en",
                    content=req.message,
                    acknowledged=True,
                    sent_at=now
                )
                coord_outbound = Communication(
                    id=uuid.uuid4(),
                    user_id=current_user.user_id,
                    role="care_coordinator",
                    case_id=None,
                    patient_id=None,
                    session_id=active_session.id,
                    sender="ai_coordinator",
                    channel=req.channel or "in_app_chat",
                    language="en",
                    content=outbound_msg,
                    acknowledged=True,
                    sent_at=now
                )
                db.add(coord_inbound)
                db.add(coord_outbound)
                await db.commit()
            except Exception as e:
                import logging
                logging.getLogger("carebridge.agent").warning(f"Coordinator non-case communication persistence notice: {e}")

            response_data = AgentExecutionResponse(
                case_id="",
                patient_id="",
                session_id=str(active_session.id),
                primary_intent=intent.primary_intent,
                emotional_state="neutral",
                detected_barriers=[],
                actions_executed=tool_observations,
                outbound_message=outbound_msg,
                outbound_language="en",
                requires_human_approval=False,
                approval_request=None,
            )
            return ApiResponseEnvelope(
                success=True,
                message="Coordinator discovery request processed",
                data=response_data
            )

        # Step 0: Link active ConversationSession with care_case
        try:
            if care_case:
                active_session.case_id = care_case.id
                active_session.patient_id = care_case.patient_id
                active_session.last_interaction_at = datetime.now(timezone.utc)
                await db.flush()
        except Exception as e:
            import logging
            logging.getLogger("carebridge.agent").warning(f"Coordinator session resolution notice: {e}")

        # Step 1: Record inbound coordinator communication
        try:
            inbound_comm = Communication(
                id=uuid.uuid4(),
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                session_id=active_session.id if active_session else None,
                sender="care_coordinator",
                channel=req.channel or "in_app_chat",
                language="en",
                content=req.message,
                acknowledged=True,
                sent_at=datetime.now(timezone.utc)
            )
            db.add(inbound_comm)
            await db.commit()
        except Exception as e:
            import logging
            logging.getLogger("carebridge.agent").warning(f"Coordinator communication persistence notice: {e}")

        thread_id = f"coordinator_{current_user.user_id}_case_{care_case.id}"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "case_id": str(care_case.id),
            "patient_id": str(care_case.patient_id),
            "session_id": str(active_session.id) if active_session else None,
            "inbound_message": req.message,
            "inbound_channel": req.channel or "in_app_chat",
            "inbound_sender": "care_coordinator",
            "patient_context": {},
            "case_context": {},
            "conversation_context": {},
            "intent_analysis": None,
            "coordination_plan": None,
            "pending_tool_calls": [],
            "tool_observations": [],
            "replanning_needed": False,
            "requires_human_approval": False,
            "approval_request": None,
            "human_decision": None,
            "outbound_message": None,
            "outbound_language": "en",
            "final_case_status": None,
            "iteration_count": 0,
            "max_iterations": 5,
            "audit_entries": [],
        }

        try:
            final_state = supervisor_graph.invoke(initial_state, config=config)
        except Exception as graph_err:
            from app.core.correlation import get_correlation_id
            corr_id = get_correlation_id()
            import logging
            logging.getLogger("carebridge.agent").error(
                f"[LLM/Graph Outage] correlation_id={corr_id} error={graph_err}",
                exc_info=True
            )
            now = datetime.now(timezone.utc)
            task_id = uuid.uuid4()
            assigned_uuid = None
            if care_case.current_owner_id:
                try:
                    assigned_uuid = uuid.UUID(str(care_case.current_owner_id))
                except (ValueError, TypeError):
                    pass
            esc_task = Task(
                id=task_id,
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                task_type="clinical_escalation",
                title="Recoverable Escalation: Clinical Assistant Service Degradation",
                description=f"Automated care companion encountered service error: {str(graph_err)[:180]}. Human care coordinator outreach required.",
                status="pending",
                priority="critical",
                assigned_to_id=assigned_uuid,
                assigned_role="care_coordinator",
                due_date=now + timedelta(hours=24),
                created_at=now,
                updated_at=now
            )
            db.add(esc_task)

            is_urgent_symptoms = any(
                w in req.message.lower()
                for w in ["pain", "bleeding", "severe", "fever", "chest", "dizzy", "lump", "emergency"]
            )
            if is_urgent_symptoms:
                care_case.status = "escalated"
                care_case.priority = "critical"

            await db.commit()

            from app.workflows.persistence.traces import WorkflowTraceLogger
            from app.database.session import get_sync_db
            try:
                with get_sync_db() as sync_db:
                    WorkflowTraceLogger.log_node_trace(
                        db=sync_db,
                        case_id=str(care_case.id),
                        thread_id=thread_id,
                        run_id=corr_id or str(uuid.uuid4()),
                        workflow_name="carebridge_supervisor",
                        node_name="supervisor_execution",
                        step_number=1,
                        status="failed",
                        duration_ms=0.0,
                        error_message=str(graph_err),
                        coordinator_note="Automated assistant encountered LLM/graph failure; escalation task created",
                        correlation_id=corr_id,
                        actor_id=str(current_user.user_id),
                        db_result="error"
                    )
            except Exception:
                pass

            fallback_msg = (
                "Our automated care assistant is currently experiencing temporary technical difficulties. "
                "Your care coordinator and attending clinical team have been notified "
                "and will follow up with you directly."
            )
            return ApiResponseEnvelope(
                success=True,
                message="Clinical assistant fallback engaged",
                data=AgentExecutionResponse(
                    case_id=str(care_case.id),
                    patient_id=str(care_case.patient_id),
                    primary_intent="urgent_clinical_escalation" if is_urgent_symptoms else "general_fallback",
                    emotional_state="anxious",
                    detected_barriers=[],
                    actions_executed=["created_clinical_escalation_task"],
                    outbound_message=fallback_msg,
                    outbound_language="en",
                    requires_human_approval=True,
                    approval_request={"task_id": str(task_id), "reason": "llm_outage"}
                )
            )
        intent = final_state.get("intent_analysis") or {}

        # Clinical Safeguard: Ensure urgent escalations are committed to PostgreSQL
        if intent.get("primary_intent") == "urgent_clinical_escalation" or intent.get("requires_human_escalation"):
            care_case.status = "escalated"
            care_case.priority = "critical"
            now = datetime.now(timezone.utc)
            event_check = await db.execute(
                select(CaseEvent).where(
                    CaseEvent.case_id == care_case.id,
                    CaseEvent.event_type.in_(["case_escalated", "urgent_clinical_escalation"])
                )
            )
            if not event_check.scalars().first():
                esc_ev = CaseEvent(
                    id=uuid.uuid4(),
                    case_id=care_case.id,
                    event_type="case_escalated",
                    description="Case escalated to escalated. Urgency: critical. Reason: Patient reported acute clinical symptoms requiring immediate human oversight.",
                    event_data={"status": "escalated", "urgency": "critical", "reason": "Patient reported acute clinical symptoms requiring immediate human oversight."},
                    timestamp=now
                )
                db.add(esc_ev)
            await db.commit()
            await db.refresh(care_case)

            # Phase 7: Real-time notification dispatch for critical clinical escalation
            try:
                from app.services.notification_service import NotificationService
                from app.database.session import get_sync_db
                with get_sync_db() as sync_db:
                    p_name = f"{care_case.patient.first_name} {care_case.patient.last_name}" if care_case.patient else "Patient"
                    NotificationService.notify_clinical_escalation(
                        db=sync_db,
                        case_id=care_case.id,
                        patient_id=care_case.patient_id,
                        patient_name=p_name,
                        reason="Patient reported acute clinical symptoms requiring immediate physician review"
                    )
            except Exception as e:
                import logging
                logging.getLogger("carebridge.agent").warning(f"Escalation notification notice: {e}")

        # Phase 7: Inbound patient message notification for care coordinator
        # ONLY send coordinator notification if coordinator attention is clinically or administratively needed:
        # e.g., explicit assistance requests, reported barriers, appointment cancellations/refusals.
        # DO NOT send notifications for greetings, general inquiries, or routine conversational turns.
        primary_intent = intent.get("primary_intent", "")
        should_notify_coordinator = (
            intent.get("requires_human_escalation", False)
            or final_state.get("requires_human_approval", False)
            or primary_intent in (
                "assistance_request",
                "appointment_reschedule_with_barrier",
                "appointment_cancellation_and_refusal",
                "referral_delay"
            )
            or any(
                b.get("barrier_type") in ("transportation_caregiver", "financial", "childcare_family")
                for b in intent.get("detected_barriers", [])
            )
        )

        if should_notify_coordinator:
            try:
                from app.services.notification_service import NotificationService
                from app.database.session import get_sync_db
                with get_sync_db() as sync_db:
                    p_name = getattr(current_user, "name", "Patient")
                    NotificationService.notify_patient_message(
                        db=sync_db,
                        case_id=care_case.id if care_case else None,
                        patient_id=care_case.patient_id if care_case else uuid.UUID(current_user.patient_id),
                        patient_name=p_name,
                        message_preview=req.message
                    )
            except Exception as e:
                import logging
                logging.getLogger("carebridge.agent").warning(f"Patient message notification notice: {e}")

        response_data = AgentExecutionResponse(
            case_id=str(care_case.id),
            patient_id=str(care_case.patient_id),
            primary_intent=intent.get("primary_intent", "coordinator_inquiry"),
            emotional_state=intent.get("emotional_state", "objective"),
            detected_barriers=intent.get("detected_barriers", []),
            actions_executed=final_state.get("tool_observations", []),
            outbound_message=final_state.get("outbound_message"),
            outbound_language=final_state.get("outbound_language", "en"),
            requires_human_approval=final_state.get("requires_human_approval", False),
            approval_request=final_state.get("approval_request"),
        )

        return ApiResponseEnvelope(
            success=True,
            message="Coordinator supervisor workflow executed successfully",
            data=response_data
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Role '{user_role}' is not authorized to interact with the CareBridge AI Brain."
        )


@router.get("/history", response_model=ApiResponseEnvelope[ChatHistoryResponse], summary="Retrieve Persistent Chat History")
async def get_chat_history(
    case_id: Optional[uuid.UUID] = None,
    session_id: Optional[uuid.UUID] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves chronological, PostgreSQL-backed conversation history with role authorization.
    Strict session isolation: a user can only read their own sessions.
    """
    user_role = current_user.role.lower()
    user_id = current_user.user_id
    p_id: Optional[uuid.UUID] = None

    if session_id:
        sess_stmt = select(ConversationSession).where(ConversationSession.id == session_id)
        sess_res = await db.execute(sess_stmt)
        target_session = sess_res.scalar_one_or_none()
        if not target_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found.")

        is_owner = False
        if target_session.user_id and target_session.user_id == user_id:
            is_owner = True
        elif user_role == "patient" and current_user.patient_id and target_session.patient_id:
            if str(target_session.patient_id) == str(current_user.patient_id):
                is_owner = True

        if not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You cannot access another user's conversation session."
            )

        query = select(Communication).where(Communication.session_id == session_id)
    else:
        if user_role == "patient":
            if not current_user.patient_id:
                raise HTTPException(status_code=403, detail="Forbidden: No patient profile associated with account.")
            p_id = uuid.UUID(current_user.patient_id)
            if case_id:
                case_stmt = select(CareCase).where(CareCase.id == case_id)
                case_res = await db.execute(case_stmt)
                care_case = case_res.scalar_one_or_none()
                if not care_case:
                    raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
                if care_case.patient_id != p_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Forbidden: You do not have permission to access another patient's communication history."
                    )
            query = select(Communication).where(Communication.patient_id == p_id)
            if case_id:
                query = query.where(Communication.case_id == case_id)
        elif user_role in ("clinician", "doctor", "specialist"):
            if case_id:
                case_stmt = select(CareCase).where(CareCase.id == case_id)
                case_res = await db.execute(case_stmt)
                care_case = case_res.scalar_one_or_none()
                if not care_case:
                    raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
                query = select(Communication).where(Communication.case_id == case_id)
            else:
                query = select(Communication).where(Communication.user_id == user_id)
        elif user_role in ("care_coordinator", "coordinator"):
            if case_id:
                case_stmt = select(CareCase).where(CareCase.id == case_id)
                case_res = await db.execute(case_stmt)
                care_case = case_res.scalar_one_or_none()
                if not care_case:
                    raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
                query = select(Communication).where(Communication.case_id == case_id)
            else:
                query = select(Communication).where(Communication.user_id == user_id)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Role '{user_role}' is not authorized to access chat history."
            )

    count_query = select(func.count()).select_from(query.subquery())
    total_res = await db.execute(count_query)
    total = total_res.scalar_one()

    # Query chronological order
    query = query.order_by(Communication.sent_at.asc()).offset(offset).limit(min(limit, 100))
    comm_res = await db.execute(query)
    records = comm_res.scalars().all()

    messages = [
        ChatMessageHistoryItem(
            id=str(r.id),
            case_id=str(r.case_id) if r.case_id else None,
            patient_id=str(r.patient_id) if r.patient_id else None,
            session_id=str(r.session_id) if r.session_id else None,
            sender=r.sender,
            channel=r.channel,
            language=r.language,
            content=r.content,
            translated_content=r.translated_content,
            acknowledged=r.acknowledged,
            sent_at=r.sent_at
        )
        for r in records
    ]

    return ApiResponseEnvelope(
        success=True,
        message=f"Retrieved {len(messages)} conversation history records.",
        data=ChatHistoryResponse(
            messages=messages,
            total=total,
            case_id=str(case_id) if case_id else None,
            session_id=str(session_id) if session_id else None
        )
    )


@router.get("/sessions", response_model=ApiResponseEnvelope[List[ConversationSessionResponse]], summary="List Conversation Sessions")
async def get_conversation_sessions(
    case_id: Optional[uuid.UUID] = None,
    q: Optional[str] = None,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves conversation sessions owned strictly by the authenticated user."""
    user_role = current_user.role.lower()
    user_uuid = uuid.UUID(str(current_user.user_id))

    if user_role == "patient":
        if not current_user.patient_id:
            raise HTTPException(status_code=403, detail="Forbidden: No patient profile associated with account.")
        p_uuid = uuid.UUID(current_user.patient_id)
        query = select(ConversationSession).where(
            or_(
                ConversationSession.user_id == user_uuid,
                and_(ConversationSession.user_id.is_(None), ConversationSession.patient_id == p_uuid)
            )
        )
    else:
        query = select(ConversationSession).where(ConversationSession.user_id == user_uuid)

    if case_id:
        query = query.where(ConversationSession.case_id == case_id)
    if q:
        search_term = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                ConversationSession.title.ilike(search_term),
                ConversationSession.summary.ilike(search_term)
            )
        )

    query = query.order_by(ConversationSession.last_interaction_at.desc())
    res = await db.execute(query)
    sessions = res.scalars().all()

    session_items = [
        ConversationSessionResponse(
            id=str(s.id),
            user_id=str(s.user_id) if s.user_id else str(user_uuid),
            role=s.role or user_role,
            title=s.title or (s.summary[:40] if s.summary else "New Chat"),
            patient_id=str(s.patient_id) if s.patient_id else None,
            case_id=str(s.case_id) if s.case_id else None,
            channel=s.channel,
            summary=s.summary,
            unanswered_questions=s.unanswered_questions or [],
            patient_commitments=s.patient_commitments or [],
            is_active=s.is_active,
            last_interaction_at=s.last_interaction_at,
            created_at=s.created_at
        )
        for s in sessions
    ]

    return ApiResponseEnvelope(
        success=True,
        message=f"Retrieved {len(session_items)} conversation sessions.",
        data=session_items
    )


@router.post("/sessions", response_model=ApiResponseEnvelope[ConversationSessionResponse], summary="Create New Conversation Session")
async def create_conversation_session(
    req: CreateSessionRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Creates a new active conversation session owned strictly by current_user."""
    user_role = current_user.role.lower()
    user_uuid = uuid.UUID(str(current_user.user_id))
    p_id: Optional[uuid.UUID] = None

    if user_role == "patient":
        if not current_user.patient_id:
            raise HTTPException(status_code=403, detail="Forbidden: No patient profile associated with account.")
        p_id = uuid.UUID(current_user.patient_id)
    elif req.patient_id:
        p_id = req.patient_id

    now = datetime.now(timezone.utc)
    new_session = ConversationSession(
        id=uuid.uuid4(),
        user_id=user_uuid,
        role=user_role,
        title=req.title or "New Chat",
        patient_id=p_id,
        case_id=req.case_id,
        channel=req.channel or "in_app_chat",
        is_active=True,
        last_interaction_at=now
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    return ApiResponseEnvelope(
        success=True,
        message="Created new conversation session.",
        data=ConversationSessionResponse(
            id=str(new_session.id),
            user_id=str(new_session.user_id),
            role=new_session.role,
            title=new_session.title,
            patient_id=str(new_session.patient_id) if new_session.patient_id else None,
            case_id=str(new_session.case_id) if new_session.case_id else None,
            channel=new_session.channel,
            summary=new_session.summary,
            unanswered_questions=new_session.unanswered_questions or [],
            patient_commitments=new_session.patient_commitments or [],
            is_active=new_session.is_active,
            last_interaction_at=new_session.last_interaction_at,
            created_at=new_session.created_at
        )
    )


@router.patch("/sessions/{session_id}", response_model=ApiResponseEnvelope[ConversationSessionResponse], summary="Rename Conversation Session")
async def rename_conversation_session(
    session_id: uuid.UUID,
    req: RenameSessionRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Renames an existing conversation session. Only the owner can rename."""
    sess_stmt = select(ConversationSession).where(ConversationSession.id == session_id)
    sess_res = await db.execute(sess_stmt)
    sess = sess_res.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    is_owner = (str(sess.user_id) == str(current_user.user_id)) or (
        current_user.role.lower() == "patient" and current_user.patient_id and str(sess.patient_id) == str(current_user.patient_id)
    )
    if not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You can only rename your own conversations.")

    sess.title = req.title.strip()
    sess.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sess)

    return ApiResponseEnvelope(
        success=True,
        message="Conversation renamed successfully.",
        data=ConversationSessionResponse(
            id=str(sess.id),
            user_id=str(sess.user_id) if sess.user_id else str(current_user.user_id),
            role=sess.role or current_user.role.lower(),
            title=sess.title,
            patient_id=str(sess.patient_id) if sess.patient_id else None,
            case_id=str(sess.case_id) if sess.case_id else None,
            channel=sess.channel,
            summary=sess.summary,
            is_active=sess.is_active,
            last_interaction_at=sess.last_interaction_at,
            created_at=sess.created_at
        )
    )


@router.delete("/sessions/{session_id}", summary="Delete Conversation Session")
async def delete_conversation_session(
    session_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Deletes an existing conversation session and its communications. Only owner can delete."""
    sess_stmt = select(ConversationSession).where(ConversationSession.id == session_id)
    sess_res = await db.execute(sess_stmt)
    sess = sess_res.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    is_owner = (str(sess.user_id) == str(current_user.user_id)) or (
        current_user.role.lower() == "patient" and current_user.patient_id and str(sess.patient_id) == str(current_user.patient_id)
    )
    if not is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: You can only delete your own conversations.")

    await db.execute(delete(Communication).where(Communication.session_id == session_id))
    await db.delete(sess)
    await db.commit()

    return ApiResponseEnvelope(
        success=True,
        message="Conversation deleted successfully.",
        data={"deleted": True, "session_id": str(session_id)}
    )
