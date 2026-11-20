"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  MessageSquare,
  Clock,
  CheckCircle2,
  Download,
  FileText,
  Info,
  Bell,
  AlertCircle,
  ChevronRight,
  User,
  Phone,
  Calendar,
  Activity,
} from "lucide-react";
import {
  fetchCases,
  fetchAppointments,
  fetchCaseLifecycle,
  downloadDiagnosticReport,
  explainReport,
  fetchPatientDashboard,
} from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import { CareCase, Appointment } from "../../types";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { LoadingState } from "../../components/ui/EmptyState";
import { useToast } from "../../components/ui/Toast";

// ─── Stage status helpers ───────────────────────────────────────────────────
const STAGE_NAMES: Record<number, string> = {
  1: "Screening Examination",
  2: "Diagnostic Report Generated",
  3: "Initial Patient Outreach",
  4: "AI Case-Aware Education & Understanding",
  5: "Attending Physician Clinical Review",
  6: "Clinical Confirmation & Next Steps",
  7: "Specialist Referral Initiated",
  8: "Referral Formally Accepted",
  9: "Appointment Scheduled & Confirmed",
  10: "Specialist Consultation Completed",
  11: "Active Treatment & Progress Monitoring",
  12: "Follow-Up Evaluation & Surveillance",
  13: "Care Documentation & Audit Complete",
  14: "Verified Clinical Closure Sign-Off",
};

const STAGE_OWNERS: Record<number, string> = {
  1: "Radiologist",
  2: "Radiologist",
  3: "Care Coordinator",
  4: "AI Coordinator",
  5: "Doctor",
  6: "Doctor",
  7: "Care Coordinator",
  8: "Doctor",
  9: "Care Coordinator",
  10: "Doctor",
  11: "Doctor",
  12: "Doctor",
  13: "Care Coordinator",
  14: "Doctor",
};

function resolveStageStatus(stageNum: number, currentStage: number, stage: any) {
  const raw = (stage?.status || "").toLowerCase();
  if (raw === "completed") return "COMPLETED";
  if (raw === "active" || raw === "in_progress") return "ACTIVE";
  if (raw === "pending") return "PENDING";
  if (currentStage <= 0) return "PENDING";
  if (stageNum < currentStage) return "COMPLETED";
  if (stageNum === currentStage) return "ACTIVE";
  return "PENDING";
}

function StageCard({
  stageNum,
  currentStage,
  stage,
  date,
}: {
  stageNum: number;
  currentStage: number;
  stage: any;
  date?: string;
}) {
  const status = resolveStageStatus(stageNum, currentStage, stage);
  const name = stage?.title || stage?.name || STAGE_NAMES[stageNum] || `Stage ${stageNum}`;
  const owner = stage?.owner || STAGE_OWNERS[stageNum] || "";
  const summary = stage?.summary || stage?.notes || "";
  const isActive = status === "ACTIVE";
  const isDone = status === "COMPLETED";

  return (
    <div
      className={`relative flex-shrink-0 w-[172px] rounded-xl border p-3 text-[11px] flex flex-col gap-1.5 transition-shadow ${
        isActive
          ? "border-[#0F766E] bg-white shadow-md ring-1 ring-[#0F766E]/20"
          : isDone
          ? "border-[#BBF7D0] bg-[#F0FDF4]"
          : "border-[#E2E8F0] bg-[#F8FAFC]"
      }`}
    >
      {/* Status badge row */}
      <div className="flex items-center justify-between">
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${
            isActive
              ? "bg-[#0F766E] text-white"
              : isDone
              ? "bg-[#DCFCE7] text-[#15803D]"
              : "bg-[#F1F5F9] text-[#64748B]"
          }`}
        >
          {isDone && <CheckCircle2 className="w-2.5 h-2.5" />}
          {status}
        </span>
        <span className="text-[9px] font-semibold text-[#94A3B8]">{stageNum}</span>
      </div>

      {/* Name */}
      <p className={`font-semibold leading-snug ${isActive ? "text-[#0F172A]" : isDone ? "text-[#166534]" : "text-[#334155]"}`}>
        {name}
      </p>

      {/* Summary */}
      {summary && (
        <p className="text-[10px] text-[#64748B] leading-relaxed line-clamp-2">{summary}</p>
      )}

      {/* Footer */}
      <div className="mt-auto pt-1 flex items-center justify-between border-t border-[#E2E8F0]/60">
        <span className="text-[9px] text-[#94A3B8]">{owner}</span>
        {date && <span className="text-[9px] text-[#94A3B8]">{date}</span>}
      </div>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────
export default function PatientDashboard() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [patientCase, setPatientCase] = useState<CareCase | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [lifecycleStages, setLifecycleStages] = useState<any[]>([]);
  const [lifecycleData, setLifecycleData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isExplainModalOpen, setIsExplainModalOpen] = useState(false);
  const [downloadingReport, setDownloadingReport] = useState(false);
  const [reportData, setReportData] = useState<any>(null);
  const [dashboardData, setDashboardData] = useState<any>(null);
  const [explanationData, setExplanationData] = useState<any>(null);
  const [explainingLoading, setExplainingLoading] = useState(false);

  const loadPatientData = async (silent = false) => {
    try {
      if (!silent && !patientCase && lifecycleStages.length === 0) {
        setLoading(true);
      }
      try {
        const dashRes = await fetchPatientDashboard();
        if (dashRes) {
          setDashboardData(dashRes);
          if (dashRes.current_case?.id) {
            setPatientCase({
              ...dashRes.current_case,
              patient_name: dashRes.profile?.name,
              patient_id: dashRes.profile?.id,
              screening_type: dashRes.screening?.screening_type,
              finding_code: dashRes.screening?.finding_code,
              finding_summary: dashRes.screening?.finding_summary,
              current_owner: dashRes.coordinator?.name || dashRes.doctor?.name || "Priya Nair, RN",
            });
          }
          if (dashRes.lifecycle?.stages) {
            setLifecycleStages(dashRes.lifecycle.stages);
            setLifecycleData(dashRes.lifecycle);
          }
          if (dashRes.appointments) setAppointments(dashRes.appointments);
          if (dashRes.reports?.length > 0) setReportData(dashRes.reports[0]);
          return;
        }
      } catch (e) {
        console.warn("Dashboard projection notice:", e);
      }

      const [casesRes, apptsRes] = await Promise.all([fetchCases(), fetchAppointments()]);
      if (casesRes?.length > 0) {
        const c = casesRes.find((c) => c.patient_id === user?.patient_id || c.id === user?.case_id) || casesRes[0];
        setPatientCase(c);
        try {
          const lc = await fetchCaseLifecycle(c.id);
          if (lc?.stages) { setLifecycleStages(lc.stages); setLifecycleData(lc); }
        } catch (e) { console.warn(e); }
      }
      if (apptsRes) setAppointments(apptsRes);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "CareBridge — Patient Care Pathway";
    loadPatientData(false);
    const handler = () => loadPatientData(true);
    window.addEventListener("carebridge:data_updated", handler);
    return () => window.removeEventListener("carebridge:data_updated", handler);
  }, [user]);

  const handleDownloadReport = async () => {
    if (!patientCase) return;
    setDownloadingReport(true);
    try {
      const res = await downloadDiagnosticReport(patientCase.id);
      setReportData(res);
      const blob = new Blob([res.report_document_text || "CareBridge Diagnostic Report"], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = res.filename || `CareBridge_Report_${patientCase.case_number}.txt`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      toast("Diagnostic report downloaded successfully.", "success");
    } catch (err: any) {
      toast("Could not download: " + (err.message || String(err)), "error");
    } finally {
      setDownloadingReport(false);
    }
  };

  const handleOpenExplanation = async () => {
    setIsExplainModalOpen(true);
    if (patientCase) {
      setExplainingLoading(true);
      try {
        const expRes = await explainReport(patientCase.id);
        if (expRes?.data) {
          setExplanationData(expRes.data);
          // Refetch patient dashboard & lifecycle so Stage 4 is immediately shown as completed
          await loadPatientData();
        }
      } catch (e) {
        console.warn("Report explanation fetch error:", e);
      } finally {
        setExplainingLoading(false);
      }
    }
    if (!reportData && patientCase) {
      try { const r = await downloadDiagnosticReport(patientCase.id); setReportData(r); } catch (e) { console.warn(e); }
    }
  };

  if (loading && !patientCase && lifecycleStages.length === 0) {
    return <div className="py-16"><LoadingState message="Loading your care pathway..." /></div>;
  }

  const patientFullName = user?.name || patientCase?.patient_name || "Patient";
  const caseNumber = patientCase?.case_number || "MRN-2026-0001";
  const coordinatorName = dashboardData?.coordinator?.name || "Priya Nair, RN";
  const doctorName = dashboardData?.doctor?.name || "Dr. Arjun Menon, MD";
  const findingCode = patientCase?.finding_code || "INTAKE-PENDING";
  const screeningType = patientCase?.screening_type || "Mammogram";

  // Build 14 stages, merging real data where available
  const stageList = Array.from({ length: 14 }, (_, i) => {
    const num = i + 1;
    const real = lifecycleStages.find((s) => s.stage_number === num || s.number === num || s.id === num);
    return { num, real };
  });

  const completedStagesCount = stageList.filter(({ real }) => (real?.status || "").toLowerCase() === "completed").length;
  const activeStageObj = stageList.find(({ real }) => ["active", "in_progress"].includes((real?.status || "").toLowerCase()));
  const currentStage =
    completedStagesCount === 0 && !activeStageObj
      ? 0
      : completedStagesCount === 14
      ? 14
      : activeStageObj?.num || lifecycleData?.current_stage_number || completedStagesCount + 1;
  const currentStageName =
    currentStage === 0
      ? "Awaiting Screening Intake"
      : currentStage === 14 && completedStagesCount === 14
      ? "Clinical Closure Verified"
      : STAGE_NAMES[currentStage] || `Stage ${currentStage}`;
  const isReportFinalized = completedStagesCount >= 2;

  const nextAppt =
    appointments.find((a) => ["booked", "confirmed", "CONFIRMED", "PENDING"].includes(a.status)) || appointments[0];

  return (
    <div className="space-y-5 pb-6">
      {/* ── Welcome Banner ──────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-[#E2E8F0] shadow-sm p-5 flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-[#0F172A] tracking-tight">
            Welcome back, {patientFullName}
          </h1>
          <p className="mt-1 text-sm text-[#475569] max-w-xl leading-relaxed">
            We are coordinating your closed-loop diagnostic pathway ({caseNumber}).
            You are supported every step of the way by Care Coordinator{" "}
            <strong className="text-[#0F172A]">{coordinatorName}</strong> and{" "}
            <strong className="text-[#0F172A]">{doctorName}</strong>.
          </p>
        </div>
        <div className="shrink-0">
          <Link href="/chat">
            <Button variant="primary" size="sm" leftIcon={<MessageSquare className="w-4 h-4" />}>
              Ask CareBridge AI
            </Button>
          </Link>
        </div>
      </div>

      {/* ── 14-Stage Care Journey (Above the Fold) ────────────────────────── */}
      <div className="bg-white rounded-xl border border-[#E2E8F0] shadow-sm p-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
          <div>
            <h2 className="font-bold text-base text-[#0F172A]">14-Stage Closed-Loop Care Journey</h2>
            <p className="text-xs text-[#64748B] mt-0.5">
              Stages complete only from persisted database evidence — from initial screening through verified clinical closure
            </p>
          </div>
          <div className="shrink-0 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#F0FDFA] border border-[#99F6E4]">
            <Info className="w-3.5 h-3.5 text-[#0F766E]" />
            <span className="text-xs font-semibold text-[#0F766E]">
              {completedStagesCount} of 14 Stages Complete • {currentStageName}
            </span>
          </div>
        </div>

        {/* Stage cards — row 1: stages 1–7, row 2: stages 8–14 */}
        <div className="space-y-3">
          <div className="flex gap-2.5 overflow-x-auto pb-1 no-scrollbar">
            {stageList.slice(0, 7).map(({ num, real }) => (
              <StageCard
                key={num}
                stageNum={num}
                currentStage={currentStage}
                stage={real}
                date={real?.completed_at ? new Date(real.completed_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : undefined}
              />
            ))}
          </div>
          <div className="flex gap-2.5 overflow-x-auto pb-1 no-scrollbar">
            {stageList.slice(7, 14).map(({ num, real }) => (
              <StageCard
                key={num}
                stageNum={num}
                currentStage={currentStage}
                stage={real}
                date={real?.completed_at ? new Date(real.completed_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : undefined}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ── Teal Notification Bar ────────────────────────────────────────── */}
      {isReportFinalized ? (
        <div className="rounded-xl border border-[#0D9488]/30 bg-[#F0FDFA] px-5 py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-[#0F766E] text-white flex items-center justify-center shrink-0">
              <Bell className="w-4 h-4" />
            </div>
            <div>
              <p className="font-semibold text-sm text-[#0F172A]">
                Screening Result Finalized: {findingCode} ({screeningType})
              </p>
              <p className="text-xs text-[#475569] mt-0.5">
                Click here to review your plain-language clinical explanation and download your official diagnostic report.
              </p>
            </div>
          </div>
          <button
            onClick={handleOpenExplanation}
            className="shrink-0 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#0F766E] text-white text-xs font-semibold hover:bg-[#115E59] transition cursor-pointer whitespace-nowrap"
          >
            <FileText className="w-3.5 h-3.5" />
            Explain &amp; Download
          </button>
        </div>
      ) : (
        <div className="rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] px-5 py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-[#0F766E]/10 text-[#0F766E] flex items-center justify-center shrink-0">
              <Bell className="w-4 h-4" />
            </div>
            <div>
              <p className="font-semibold text-sm text-[#0F172A]">
                {completedStagesCount === 0
                  ? "Care Pathway Ready — No Stages Completed Yet (0/14)"
                  : "Stage 1 Complete: Screening Procedure Performed — Awaiting Finalized Report"}
              </p>
              <p className="text-xs text-[#475569] mt-0.5">
                {completedStagesCount === 0
                  ? "Submit your screening request in CareBridge AI Chat to notify your Care Coordinator and begin Stage 1."
                  : "Your Care Coordinator is validating and finalizing your diagnostic report before Stage 2 completes."}
              </p>
            </div>
          </div>
          <Link href="/chat">
            <Button variant="secondary" size="sm" leftIcon={<MessageSquare className="w-3.5 h-3.5" />}>
              Open AI Companion
            </Button>
          </Link>
        </div>
      )}

      {/* ── Screening Result Card ─────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-[#E2E8F0] shadow-sm p-5">
        {/* Header row */}
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 mb-5">
          <div>
            <div className="flex items-center gap-1.5 mb-0.5">
              <FileText className="w-4 h-4 text-[#0F766E]" />
              <h2 className="font-semibold text-sm text-[#0F172A]">Recent Screening Result &amp; Clinical Context</h2>
            </div>
            <p className="text-xs text-[#64748B]">Performed at {screeningType}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleOpenExplanation}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#E2E8F0] text-xs font-medium text-[#475569] hover:border-[#0F766E] hover:text-[#0F766E] transition cursor-pointer"
            >
              <Info className="w-3.5 h-3.5" />
              Explain Result
            </button>
            <button
              onClick={handleDownloadReport}
              disabled={downloadingReport}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0F766E] text-white text-xs font-semibold hover:bg-[#115E59] transition disabled:opacity-60 cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              {downloadingReport ? "Downloading…" : "Download Report"}
            </button>
          </div>
        </div>

        {/* Two-column: left = data, right = info panel */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-5">
          {/* Left side */}
          <div className="space-y-4">
            {/* 3-column stats */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0]">
                <span className="text-[10px] text-[#64748B] block mb-1">Assessment Finding</span>
                <span className="font-bold text-sm text-[#0F172A] block">{findingCode}</span>
                <span className="text-[11px] text-[#0F766E]">Diagnostic Follow-up Advised</span>
              </div>
              <div className="p-3 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0]">
                <span className="text-[10px] text-[#64748B] block mb-1">Screening Modality</span>
                <span className="font-bold text-sm text-[#0F172A] block">{screeningType}</span>
                <span className="text-[11px] text-[#475569]">Bilateral Diagnostic Views</span>
              </div>
              <div className="p-3 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0]">
                <span className="text-[10px] text-[#64748B] block mb-1">Care Pathway SLA</span>
                <span className="font-bold text-sm text-[#0F172A] block">
                  {patientCase?.sla_deadline
                    ? new Date(patientCase.sla_deadline).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                    : "Within 14 Days"}
                </span>
                <span className="text-[11px] text-[#15803D]">Within Clinical Window</span>
              </div>
            </div>

            {/* Clinical summary */}
            <div className="p-3.5 rounded-lg bg-[#F1F5F9] border border-[#E2E8F0] text-xs text-[#334155] leading-relaxed">
              <strong className="text-[#0F172A]">Clinical Summary: </strong>
              {patientCase?.finding_summary ||
                "Patient registered in CareBridge hospital portal. Awaiting intake statement to schedule screening at Metropolitan Breast & Cancer Care Center."}
            </div>
          </div>

          {/* Right: Understanding panel */}
          <div className="p-4 rounded-lg bg-[#F0FDFA] border border-[#99F6E4] text-xs leading-relaxed">
            <div className="flex items-center gap-1.5 mb-2.5">
              <Info className="w-3.5 h-3.5 text-[#0F766E]" />
              <span className="font-semibold text-sm text-[#0F766E]">Understanding Your Finding</span>
            </div>
            <p className="text-[#134E4A] mb-2.5">
              A <strong>{findingCode}</strong> category indicates a finding that requires further evaluation. Importantly,{" "}
              <strong>70% to 80% of such biopsies turn out to be non-cancerous (benign).</strong>
            </p>
            <p className="text-[#134E4A]">
              Your Care Coordinator (<strong>{coordinatorName}</strong>) is proactively tracking your care pathway so you never face delays.
            </p>
          </div>
        </div>
      </div>

      {/* ── Next Appointment + Care Team row ─────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Next appointment */}
        <div className="bg-white rounded-xl border border-[#E2E8F0] shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Calendar className="w-4 h-4 text-[#0F766E]" />
              <span className="font-semibold text-sm text-[#0F172A]">Next Appointment</span>
            </div>
            {nextAppt && (
              <Badge variant="success">Confirmed</Badge>
            )}
          </div>
          {nextAppt ? (
            <div className="space-y-2 text-xs">
              <p className="font-semibold text-sm text-[#0F172A] capitalize">
                {nextAppt.appointment_type?.replace(/_/g, " ") || "Diagnostic Consultation"}
              </p>
              <p className="text-[#475569]">{nextAppt.facility || "Metropolitan Care Center"}</p>
              <div className="flex items-center gap-1.5 text-[#64748B]">
                <Clock className="w-3.5 h-3.5 text-[#0F766E]" />
                {nextAppt.scheduled_time
                  ? new Date(nextAppt.scheduled_time).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
                  : "Upcoming — date to be confirmed"}
              </div>
              <p className="text-[#475569]">
                Attending: <strong>{nextAppt.provider_name || "Dr. Aris Thorne"}</strong>
              </p>
            </div>
          ) : (
            <p className="text-xs text-[#64748B]">No upcoming appointments scheduled. Your care coordinator will notify you.</p>
          )}
          <div className="mt-4 pt-3 border-t border-[#E2E8F0]">
            <Link href="/chat" className="text-xs text-[#0F766E] font-semibold flex items-center gap-1 hover:underline">
              Questions about this visit? <ChevronRight className="w-3.5 h-3.5" />
            </Link>
          </div>
        </div>

        {/* Care team */}
        <div className="bg-white rounded-xl border border-[#E2E8F0] shadow-sm p-5">
          <div className="flex items-center gap-2 mb-3">
            <User className="w-4 h-4 text-[#0F766E]" />
            <span className="font-semibold text-sm text-[#0F172A]">Your Care Team</span>
          </div>
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0]">
              <div className="w-10 h-10 rounded-full bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center font-bold text-sm shrink-0">
                {coordinatorName.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-xs text-[#0F172A]">{coordinatorName}</p>
                <p className="text-[11px] text-[#475569]">Care Coordinator — Single point of contact</p>
                <p className="text-[11px] text-[#0F766E] flex items-center gap-1 mt-0.5">
                  <Phone className="w-3 h-3" /> Direct Line: +91-98765-43210
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 p-3 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0]">
              <div className="w-10 h-10 rounded-full bg-[#EFF6FF] text-[#2563EB] flex items-center justify-center font-bold text-sm shrink-0">
                AT
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-xs text-[#0F172A]">Dr. Aris Thorne, MD</p>
                <p className="text-[11px] text-[#475569]">Attending Physician — Diagnostic Oncology</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Explanation Modal ─────────────────────────────────────────────── */}
      <Modal isOpen={isExplainModalOpen} onClose={() => setIsExplainModalOpen(false)} title="Diagnostic Screening Result Explanation" size="lg">
        <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
          {explainingLoading ? (
            <div className="py-12 text-center">
              <LoadingState message="Translating medical findings into plain language with clinical care standards..." />
            </div>
          ) : explanationData ? (
            <div className="space-y-4">
              {/* Section 1: What your report says */}
              <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0]">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-xs font-bold text-[#0F766E] uppercase tracking-wider flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5" />
                    What your report says
                  </h3>
                  <Badge variant="warning">{findingCode}</Badge>
                </div>
                <div className="text-xs text-[#334155] whitespace-pre-line leading-relaxed space-y-1">
                  {explanationData.what_your_report_says}
                </div>
              </div>

              {/* Section 2: What these words mean */}
              <div className="p-4 rounded-xl bg-[#F0FDFA] border border-[#99F6E4]">
                <h3 className="text-xs font-bold text-[#0F766E] uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5" />
                  What these words mean (Reviewed Glossary)
                </h3>
                <div className="text-xs text-[#134E4A] whitespace-pre-line leading-relaxed">
                  {explanationData.what_these_words_mean}
                </div>
              </div>

              {/* Section 3: What your report recommends */}
              <div className="p-4 rounded-xl bg-[#FEF3C7]/70 border border-[#FDE68A]">
                <h3 className="text-xs font-bold text-[#92400E] uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5" />
                  What your report recommends
                </h3>
                <div className="text-xs text-[#78350F] whitespace-pre-line leading-relaxed">
                  {explanationData.what_your_report_recommends}
                </div>
              </div>

              {/* Section 4: What is not certain */}
              <div className="p-4 rounded-xl bg-[#EFF6FF] border border-[#BFDBFE]">
                <h3 className="text-xs font-bold text-[#1D4ED8] uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5" />
                  What is not certain
                </h3>
                <p className="text-xs text-[#1E40AF] leading-relaxed">
                  {explanationData.what_is_not_certain}
                </p>
              </div>

              {/* Section 5: Questions for your doctor */}
              <div className="p-4 rounded-xl bg-[#FAF5FF] border border-[#E9D5FF]">
                <h3 className="text-xs font-bold text-[#7E22CE] uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <MessageSquare className="w-3.5 h-3.5" />
                  Questions you may want to ask your doctor
                </h3>
                <div className="text-xs text-[#581C87] whitespace-pre-line leading-relaxed">
                  {explanationData.questions_for_doctor}
                </div>
              </div>

              {/* Section 6: Warm closing */}
              <div className="p-3.5 rounded-xl bg-[#F0FDF4] border border-[#BBF7D0] text-xs text-[#166534] font-medium leading-relaxed">
                {explanationData.warm_closing}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="p-4 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0]">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-semibold text-[#0F766E] uppercase tracking-wider">Assessment Finding</span>
                  <Badge variant="warning">{findingCode}</Badge>
                </div>
                <p className="text-xs text-[#475569] leading-relaxed">
                  {patientCase?.finding_summary || "Screening identified an area requiring confirmatory imaging and histology."}
                </p>
              </div>
            </div>
          )}

          {reportData && (
            <details className="space-y-1.5 pt-1">
              <summary className="text-[11px] font-semibold text-[#64748B] uppercase tracking-wider cursor-pointer hover:text-[#0F172A]">
                View Official Clinical Document Text (Original)
              </summary>
              <pre className="p-3 mt-1 rounded-lg bg-[#0F172A] text-[#F8FAFC] font-mono text-[11px] max-h-48 overflow-y-auto whitespace-pre-wrap leading-relaxed border border-[#334155]">
                {reportData.report_document_text}
              </pre>
            </details>
          )}

          <div className="pt-3 flex items-center justify-between gap-3 border-t border-[#E2E8F0]">
            <span className="text-[11px] text-[#64748B]">Coordinator: <strong>{coordinatorName}</strong></span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleDownloadReport}
                disabled={downloadingReport}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#0F766E] text-white text-xs font-semibold hover:bg-[#115E59] transition disabled:opacity-60 cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                {downloadingReport ? "Downloading…" : "Download Report"}
              </button>
              <button onClick={() => setIsExplainModalOpen(false)} className="px-3 py-2 rounded-lg border border-[#E2E8F0] text-xs text-[#64748B] hover:text-[#0F172A] transition cursor-pointer">
                Close
              </button>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
