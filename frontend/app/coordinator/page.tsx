"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  FolderGit2,
  RotateCcw,
  Clock,
  AlertTriangle,
  CheckCircle2,
  Users,
  Calendar,
  Share2,
  ArrowRight,
  Filter,
  ShieldAlert,
  ChevronRight,
  UserCheck,
  RefreshCw,
  Building,
  AlertCircle,
  FileText,
  Search,
  Activity,
  UserPlus,
  Stethoscope,
} from "lucide-react";
import {
  fetchCases,
  fetchRecoveryQueue,
  fetchAppointments,
  fetchReferrals,
  triggerRecoveryPlay,
  acceptReferral,
  uploadTestReport,
  scheduleScreening,
  completeScreening,
  recordMissedScreening,
  runDashboardConsistencyCheck,
} from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import { CareCase, RecoveryCase, Appointment, Referral } from "../../types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { EmptyState, LoadingState } from "@/components/ui/EmptyState";
import { Tabs } from "@/components/ui/Tabs";
import { KPICard } from "@/components/ui/KPICard";
import { Pagination } from "@/components/ui/Pagination";
import { useToast } from "@/components/ui/Toast";
import { ReportUploadModal } from "@/components/ReportUploadModal";

export default function CoordinatorDashboard() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [cases, setCases] = useState<CareCase[]>([]);
  const [recoveryCases, setRecoveryCases] = useState<RecoveryCase[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  // Filtering & Pagination
  const [filterStatus, setFilterStatus] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  const [recoveringId, setRecoveringId] = useState<string | null>(null);
  const [runningAudit, setRunningAudit] = useState(false);

  const handleRunConsistencyCheck = async () => {
    setRunningAudit(true);
    try {
      const res = await runDashboardConsistencyCheck(true);
      if (res.corrupted_count === 0) {
        toast(
          "Consistency Audit Passed: All patient cases and projections verified.",
          "success"
        );
      } else {
        const confirmRepair = confirm(
          `Detected ${res.corrupted_count} projection anomalies. Would you like to safely apply repairs and generate coordinator reconciliation tasks?`
        );
        if (confirmRepair) {
          const repairRes = await runDashboardConsistencyCheck(false);
          toast(
            `Repairs Applied: ${repairRes.repaired_count} projections repaired. Reconciliation tasks created.`,
            "success"
          );
          await loadData();
        }
      }
    } catch (err: any) {
      toast("Consistency check failed: " + (err.message || String(err)), "error");
    } finally {
      setRunningAudit(false);
    }
  };

  // Upload Test Report Modal State
  const [isReportModalOpen, setIsReportModalOpen] = useState(false);
  const [reportCaseId, setReportCaseId] = useState("");
  const [reportScreeningType, setReportScreeningType] = useState("Mammogram");
  const [reportDiseaseCondition, setReportDiseaseCondition] = useState("BI-RADS 4 Suspicious Mass");
  const [reportFindingCode, setReportFindingCode] = useState("BI-RADS-4");
  const [reportSummary, setReportSummary] = useState(
    "Focal architectural distortion with clustered microcalcifications in upper outer quadrant."
  );
  const [reportRecommendation, setReportRecommendation] = useState(
    "Targeted ultrasound and ultrasound-guided core needle tissue biopsy within 14 days."
  );
  const [reportUrgency, setReportUrgency] = useState("standard");
  const [reportFilename, setReportFilename] = useState("diagnostic_report_scan.pdf");
  const [isUploadingReport, setIsUploadingReport] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);

  // Schedule Screening Modal State
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
  const [scheduleCaseId, setScheduleCaseId] = useState("");
  const [schedulePatientName, setSchedulePatientName] = useState("");
  const [screeningDate, setScreeningDate] = useState("");
  const [screeningTime, setScreeningTime] = useState("10:00");
  const [screeningNotes, setScreeningNotes] = useState(
    "Routine hospital diagnostic screening protocol."
  );
  const [isScheduling, setIsScheduling] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  const handleOpenScheduleModal = (caseItem: CareCase) => {
    setScheduleCaseId(caseItem.id);
    setSchedulePatientName(caseItem.patient_name);
    const d = new Date();
    d.setDate(d.getDate() + 3);
    setScreeningDate(d.toISOString().split("T")[0]);
    setScreeningTime("10:00");
    setIsScheduleModalOpen(true);
  };

  const handleScheduleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!scheduleCaseId || !screeningDate) {
      toast("Please select a valid screening date.", "warning");
      return;
    }
    setIsScheduling(true);
    try {
      const scheduledIso = new Date(`${screeningDate}T${screeningTime || "10:00"}:00`).toISOString();
      await scheduleScreening(scheduleCaseId, {
        scheduled_time: scheduledIso,
        facility: coordinatorFacility,
        notes: screeningNotes,
      });
      setIsScheduleModalOpen(false);
      await loadData();
      toast(`Screening visit scheduled for ${screeningDate} at ${screeningTime}.`, "success");
    } catch (err: any) {
      toast("Failed to schedule screening: " + (err.message || String(err)), "error");
    } finally {
      setIsScheduling(false);
    }
  };

  const handleManualCompleteScreening = async (caseId: string, patientName: string) => {
    if (!confirm(`Confirm that ${patientName} has completed their screening procedure at the hospital?`)) {
      return;
    }
    setActionLoadingId(caseId);
    try {
      await completeScreening(caseId, {
        completion_notes: `Screening verified as completed by ${coordinatorName} at ${coordinatorFacility}. Findings under review.`,
      });
      await loadData();
      toast(`Screening for ${patientName} marked as completed. Diagnostic report upload ready.`, "success");
    } catch (err: any) {
      toast("Failed to complete screening: " + (err.message || String(err)), "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRecordMissedScreeningAction = async (caseId: string, patientName: string) => {
    const reason = prompt(
      `Enter reason for missed screening visit for ${patientName}:`,
      "Patient did not attend scheduled visit"
    );
    if (!reason) return;
    setActionLoadingId(caseId);
    try {
      await recordMissedScreening(caseId, { missed_reason: reason });
      await loadData();
      toast(`Missed visit recorded for ${patientName}. Recovery task activated.`, "warning");
    } catch (err: any) {
      toast("Failed to record missed visit: " + (err.message || String(err)), "error");
    } finally {
      setActionLoadingId(null);
    }
  };

  const coordinatorName = user?.name || "Priya Nair, RN";
  const coordinatorFacility = user?.facility || "Metropolitan Breast & Cancer Care Center";

  const loadData = async () => {
    try {
      setLoading(true);
      const [casesRes, recRes, apptsRes, refsRes] = await Promise.all([
        fetchCases(),
        fetchRecoveryQueue(),
        fetchAppointments(),
        fetchReferrals(),
      ]);
      setCases(casesRes || []);
      setRecoveryCases(recRes || []);
      setAppointments(apptsRes || []);
      setReferrals(refsRes || []);
    } catch (err) {
      console.error("Error loading coordinator dashboard:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "CareBridge — Care Coordination Command Center";
    loadData();

    const handleDataUpdated = () => {
      loadData();
    };

    if (typeof window !== "undefined") {
      window.addEventListener("carebridge:data_updated", handleDataUpdated);
    }

    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("carebridge:data_updated", handleDataUpdated);
      }
    };
  }, []);

  const handleTriggerRecovery = async (caseId: string) => {
    try {
      setRecoveringId(caseId);
      await triggerRecoveryPlay(caseId);
      await loadData();
      toast("Recovery playbook triggered successfully.", "success");
    } catch (err: any) {
      toast("Failed to trigger recovery: " + (err.message || String(err)), "error");
    } finally {
      setRecoveringId(null);
    }
  };

  const handleAcceptReferral = async (refId: string) => {
    try {
      await acceptReferral(refId, {
        receiving_provider_name: coordinatorFacility,
        acceptance_notes: "Referral formally accepted via Care Coordinator Hub.",
      });
      await loadData();
      toast("Referral formally accepted.", "success");
    } catch (err: any) {
      toast("Failed to accept referral: " + (err.message || String(err)), "error");
    }
  };

  const handleUploadTestReportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reportCaseId) {
      toast("Please select a patient care case.", "warning");
      return;
    }
    setIsUploadingReport(true);
    try {
      const res = await uploadTestReport(reportCaseId, {
        screening_type: reportScreeningType,
        disease_condition: reportDiseaseCondition,
        finding_code: reportFindingCode,
        finding_summary: reportSummary,
        clinical_recommendation: reportRecommendation,
        urgency_level: reportUrgency,
        report_filename: reportFilename,
      });
      setUploadResult(res);
      await loadData();
      toast("Test report uploaded and specialist matched.", "success");
    } catch (err: any) {
      toast("Upload failed: " + (err.message || String(err)), "error");
    } finally {
      setIsUploadingReport(false);
    }
  };

  const filteredCases = cases.filter((c) => {
    const matchesStatus = filterStatus === "all" ? true : c.status === filterStatus;
    const matchesSearch =
      c.patient_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.case_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.finding_code.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesStatus && matchesSearch;
  });

  const paginatedCases = filteredCases.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const escalatedCases = cases.filter((c) => c.status === "escalated" || c.priority === "critical");
  const stalledCount = cases.filter(
    (c) => c.status === "recovering" || c.sla_status === "warning" || c.sla_status === "breached"
  ).length;
  const closedCount = cases.filter(
    (c) => c.status === "closed" || c.status === "care_completed"
  ).length;

  const intakeCases = cases.filter(
    (c) => c.status === "intake" || c.status === "intake_ready" || c.status === "intake_submitted"
  );
  const screeningCases = cases.filter(
    (c) => c.status === "screening_scheduled" || c.status === "screening_completed"
  );
  const allocationCases = cases.filter(
    (c) =>
      c.status === "screening_completed" ||
      c.status === "result_generated" ||
      c.status === "result_received" ||
      c.status === "referred"
  );

  const formatSLARemaining = (deadlineStr: string): { text: string; isOverdue: boolean } => {
    if (!deadlineStr) return { text: "N/A", isOverdue: false };
    const deadline = new Date(deadlineStr).getTime();
    const now = new Date().getTime();
    const diffHours = Math.round((deadline - now) / (1000 * 60 * 60));

    if (diffHours < 0) {
      const overdueDays = Math.abs(Math.round(diffHours / 24));
      return { text: `${overdueDays}d Overdue`, isOverdue: true };
    }
    const days = Math.floor(diffHours / 24);
    const hrs = diffHours % 24;
    return { text: `${days}d ${hrs}h remaining`, isOverdue: false };
  };

  const tabs = [
    { id: "overview", label: "Overview", icon: <Activity className="w-4 h-4" /> },
    {
      id: "requirements",
      label: "New Requirements",
      badge: intakeCases.length > 0 ? intakeCases.length : undefined,
      icon: <UserPlus className="w-4 h-4" />,
    },
    {
      id: "screening",
      label: "Screening Orders",
      badge: screeningCases.length > 0 ? screeningCases.length : undefined,
      icon: <Calendar className="w-4 h-4" />,
    },
    {
      id: "allocation",
      label: "Doctor Allocation",
      badge: allocationCases.length > 0 ? allocationCases.length : undefined,
      icon: <Stethoscope className="w-4 h-4" />,
    },
    {
      id: "appointments",
      label: "Appointments & Referrals",
      badge: referrals.length,
      icon: <Share2 className="w-4 h-4" />,
    },
    {
      id: "recovery",
      label: "Recovery & SLA",
      badge: recoveryCases.length > 0 ? recoveryCases.length : undefined,
      badgeVariant: "warning" as const,
      icon: <RotateCcw className="w-4 h-4" />,
    },
    {
      id: "all_cases",
      label: "All Cases",
      badge: cases.length,
      icon: <FolderGit2 className="w-4 h-4" />,
    },
  ];

  if (loading) {
    return (
      <div className="py-16">
        <LoadingState message="Loading care coordination hub..." />
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-semibold mb-1.5">
            <UserCheck className="w-3.5 h-3.5" />
            Care Coordination Command Center
          </div>
          <h1 className="text-xl sm:text-2xl font-semibold text-[#0F172A] tracking-tight">
            Active Case Surveillance & Care Recovery
          </h1>
          <p className="text-xs sm:text-sm text-[#475569] mt-0.5">
            Accountable Coordinator: <span className="font-semibold text-[#0F172A]">{coordinatorName}</span> •{" "}
            {coordinatorFacility}
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="primary"
            size="sm"
            leftIcon={<FileText className="w-4 h-4" />}
            onClick={() => {
              if (cases.length > 0 && !reportCaseId) {
                setReportCaseId(cases[0].id);
              }
              setUploadResult(null);
              setIsReportModalOpen(true);
            }}
          >
            Upload Test Report
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRunConsistencyCheck}
            disabled={runningAudit}
            leftIcon={
              <ShieldAlert
                className={`w-4 h-4 ${runningAudit ? "animate-pulse text-[#B45309]" : "text-[#0F766E]"}`}
              />
            }
          >
            {runningAudit ? "Auditing..." : "Audit Projections"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={loadData}
            disabled={loading}
            leftIcon={<RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />}
            aria-label="Refresh data"
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* Doctor Handoff & Clinical Escalation Alert Banner */}
      {escalatedCases.length > 0 && (
        <Card padding="md" className="border-l-4 border-l-[#B45309] bg-[#FFFBEB]/70">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-[#B45309]" />
              <h3 className="font-semibold text-sm text-[#92400E]">
                Doctor Handoff Active: {escalatedCases.length} Escalated Case(s) Under Clinical Review
              </h3>
            </div>
            <Badge variant="warning">Handoff to Attending Physician</Badge>
          </div>
          <p className="text-xs text-[#78350F] leading-relaxed">
            These cases have been routed to Dr. Aris Thorne for evaluation. Care coordination will resume
            once physician recommendations are documented.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {escalatedCases.map((ec) => (
              <Link
                key={ec.id}
                href={`/cases/${ec.id}`}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-btn bg-white border border-[#FDE68A] text-xs font-semibold text-[#92400E] hover:bg-[#FEF3C7] transition"
              >
                <span>
                  {ec.patient_name} ({ec.case_number})
                </span>
                <ChevronRight className="w-3 h-3" />
              </Link>
            ))}
          </div>
        </Card>
      )}

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Tab 1: Overview */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* 4 Standardized KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              label="Total Active Cases"
              value={cases.length}
              subtitle="Full longitudinal tracking"
              icon={<FolderGit2 className="w-4 h-4" />}
            />
            <KPICard
              label="Stalled / At-Risk"
              value={stalledCount}
              subtitle="Requires coordinator recovery"
              badgeText="SLA Attention"
              badgeVariant="warning"
              icon={<AlertTriangle className="w-4 h-4 text-[#B45309]" />}
            />
            <KPICard
              label="Active Referrals"
              value={referrals.length}
              subtitle="48h SLA turnaround"
              icon={<Share2 className="w-4 h-4" />}
            />
            <KPICard
              label="Verified Closures"
              value={closedCount}
              subtitle="100% evidence confirmed"
              badgeText="Completed"
              badgeVariant="success"
              icon={<CheckCircle2 className="w-4 h-4 text-[#15803D]" />}
            />
          </div>

          {/* Quick Actions & Recent Stalled Journeys Summary */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <div className="lg:col-span-8 space-y-4">
              <Card padding="md">
                <CardHeader
                  title="Needs Your Action"
                  subtitle="Cases requiring scheduling, report verification, or recovery"
                  action={
                    <button
                      type="button"
                      onClick={() => setActiveTab("all_cases")}
                      className="text-xs font-semibold text-[#0F766E] hover:underline flex items-center gap-1 cursor-pointer"
                    >
                      <span>View All ({cases.length})</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  }
                />

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-[#F8FAFC] text-[#64748B] border-b border-[#E2E8F0]">
                      <tr>
                        <th className="py-2.5 px-4 font-semibold">Case / Patient</th>
                        <th className="py-2.5 px-3 font-semibold">Finding</th>
                        <th className="py-2.5 px-3 font-semibold">Status</th>
                        <th className="py-2.5 px-3 font-semibold">SLA</th>
                        <th className="py-2.5 px-4 font-semibold text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E2E8F0]">
                      {cases.slice(0, 5).map((c) => {
                        const sla = formatSLARemaining(c.sla_deadline);
                        return (
                          <tr key={c.id} className="hover:bg-[#F8FAFC] transition">
                            <td className="py-3 px-4">
                              <Link
                                href={`/cases/${c.id}`}
                                className="font-semibold text-[#0F172A] hover:text-[#0F766E] block"
                              >
                                {c.patient_name}
                              </Link>
                              <span className="text-[11px] font-mono text-[#64748B]">{c.case_number}</span>
                            </td>
                            <td className="py-3 px-3">
                              <span className="font-medium text-[#0F172A]">{c.finding_code}</span>
                            </td>
                            <td className="py-3 px-3">
                              <Badge
                                variant={
                                  c.status === "closed"
                                    ? "success"
                                    : c.status === "escalated"
                                    ? "error"
                                    : c.status === "recovering"
                                    ? "warning"
                                    : "neutral"
                                }
                              >
                                {c.status.replace(/_/g, " ")}
                              </Badge>
                            </td>
                            <td className="py-3 px-3">
                              <span
                                className={`text-[11px] font-medium ${
                                  sla.isOverdue ? "text-[#DC2626] font-semibold" : "text-[#0F766E]"
                                }`}
                              >
                                {sla.text}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-right">
                              <Link href={`/cases/${c.id}`}>
                                <Button size="sm" variant="secondary">
                                  Manage
                                </Button>
                              </Link>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>

            <div className="lg:col-span-4 space-y-4">
              <Card padding="md">
                <CardHeader
                  title="Stalled Care Radar"
                  subtitle="Top barrier detection alerts"
                  action={
                    <button
                      type="button"
                      onClick={() => setActiveTab("recovery")}
                      className="text-xs text-[#0F766E] hover:underline font-semibold cursor-pointer"
                    >
                      Recovery ({recoveryCases.length})
                    </button>
                  }
                />
                <div className="space-y-3">
                  {recoveryCases.slice(0, 3).map((rc) => (
                    <div
                      key={rc.case_id}
                      className="p-3 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-[#0F172A]">{rc.patient_name}</span>
                        <Badge variant="warning">{rc.priority}</Badge>
                      </div>
                      <p className="text-[11px] text-[#475569]">
                        Barrier: <strong>{rc.barriers_detected.join(", ") || "Missed Visit / Transport"}</strong>
                      </p>
                      <div className="pt-1 flex items-center justify-between text-[11px]">
                        <span className="text-[#0F766E] font-medium">{rc.active_playbook}</span>
                        <button
                          type="button"
                          onClick={() => handleTriggerRecovery(rc.case_id)}
                          disabled={recoveringId === rc.case_id}
                          className="px-2 py-0.5 rounded bg-[#E6F4F1] text-[#0F766E] font-semibold hover:bg-[#CCFBF1] cursor-pointer"
                        >
                          {recoveringId === rc.case_id ? "Running..." : "Trigger"}
                        </button>
                      </div>
                    </div>
                  ))}
                  {recoveryCases.length === 0 && (
                    <p className="text-xs text-[#64748B] text-center py-4">All care journeys progressing on schedule.</p>
                  )}
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: New Requirements (Intake) */}
      {activeTab === "requirements" && (
        <Card padding="md">
          <CardHeader
            title="New Patient Intake & Screening Requirements"
            subtitle="Patients awaiting diagnostic appointment scheduling"
            action={<Badge variant="info">{intakeCases.length} Pending</Badge>}
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8FAFC] text-[#64748B] border-b border-[#E2E8F0]">
                <tr>
                  <th className="py-2.5 px-4 font-semibold">Patient</th>
                  <th className="py-2.5 px-3 font-semibold">Screening Type</th>
                  <th className="py-2.5 px-3 font-semibold">Finding</th>
                  <th className="py-2.5 px-3 font-semibold">Priority</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {intakeCases.map((c) => (
                  <tr key={c.id} className="hover:bg-[#F8FAFC] transition">
                    <td className="py-3 px-4 font-semibold text-[#0F172A]">{c.patient_name}</td>
                    <td className="py-3 px-3 text-[#475569]">{c.screening_type || "Diagnostic Mammogram"}</td>
                    <td className="py-3 px-3 font-medium text-[#0F172A]">{c.finding_code}</td>
                    <td className="py-3 px-3">
                      <Badge variant={c.priority === "urgent" || c.priority === "critical" ? "error" : "neutral"}>
                        {c.priority}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        type="button"
                        onClick={() => handleOpenScheduleModal(c)}
                        className="px-2.5 py-1.5 rounded-btn bg-[#0F766E] text-white hover:bg-[#115E59] text-xs font-semibold cursor-pointer inline-flex items-center gap-1 shadow-2xs"
                      >
                        <Calendar className="w-3.5 h-3.5" />
                        <span>Schedule Screening</span>
                      </button>
                    </td>
                  </tr>
                ))}
                {intakeCases.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-xs text-[#64748B]">
                      No new intake cases requiring screening scheduling.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Tab 3: Screening Orders */}
      {activeTab === "screening" && (
        <Card padding="md">
          <CardHeader
            title="Screening Orders & Hospital Attendance"
            subtitle="Record attendance completion or missed appointments"
            action={<Badge variant="info">{screeningCases.length} Active</Badge>}
          />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8FAFC] text-[#64748B] border-b border-[#E2E8F0]">
                <tr>
                  <th className="py-2.5 px-4 font-semibold">Patient</th>
                  <th className="py-2.5 px-3 font-semibold">Modality</th>
                  <th className="py-2.5 px-3 font-semibold">Status</th>
                  <th className="py-2.5 px-4 font-semibold text-right">Record Outcome</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {screeningCases.map((c) => (
                  <tr key={c.id} className="hover:bg-[#F8FAFC] transition">
                    <td className="py-3 px-4">
                      <span className="font-semibold text-[#0F172A] block">{c.patient_name}</span>
                      <span className="text-[11px] font-mono text-[#64748B]">{c.case_number}</span>
                    </td>
                    <td className="py-3 px-3 text-[#475569]">{c.screening_type}</td>
                    <td className="py-3 px-3">
                      <Badge variant={c.status === "screening_completed" ? "success" : "info"}>
                        {c.status.replace(/_/g, " ")}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-right space-x-1.5">
                      {c.status === "screening_scheduled" && (
                        <>
                          <button
                            type="button"
                            onClick={() => handleManualCompleteScreening(c.id, c.patient_name)}
                            disabled={actionLoadingId === c.id}
                            className="px-2.5 py-1.5 rounded-btn bg-[#DCFCE7] text-[#14532D] hover:bg-[#BBF7D0] text-xs font-semibold cursor-pointer inline-flex items-center gap-1"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5 text-[#15803D]" />
                            <span>{actionLoadingId === c.id ? "Saving..." : "Completed"}</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleRecordMissedScreeningAction(c.id, c.patient_name)}
                            disabled={actionLoadingId === c.id}
                            className="px-2 py-1.5 rounded-btn text-[#B91C1C] hover:bg-[#FEE2E2] text-xs font-semibold cursor-pointer"
                          >
                            Missed Visit
                          </button>
                        </>
                      )}
                      {c.status === "screening_completed" && (
                        <button
                          type="button"
                          onClick={() => {
                            setReportCaseId(c.id);
                            setUploadResult(null);
                            setIsReportModalOpen(true);
                          }}
                          className="px-2.5 py-1.5 rounded-btn bg-[#E6F4F1] text-[#0F766E] hover:bg-[#CCFBF1] text-xs font-semibold cursor-pointer inline-flex items-center gap-1"
                        >
                          <FileText className="w-3.5 h-3.5" />
                          <span>Upload Report</span>
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {screeningCases.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-xs text-[#64748B]">
                      No active screening orders found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Tab 4: Doctor Allocation */}
      {activeTab === "allocation" && (
        <Card padding="md">
          <CardHeader
            title="Specialist Matching & Doctor Allocation"
            subtitle="Assign cases with verified diagnostic reports to attending oncologists"
            action={
              <Button
                variant="primary"
                size="sm"
                leftIcon={<FileText className="w-4 h-4" />}
                onClick={() => {
                  if (cases.length > 0 && !reportCaseId) setReportCaseId(cases[0].id);
                  setUploadResult(null);
                  setIsReportModalOpen(true);
                }}
              >
                Upload Findings & Match
              </Button>
            }
          />
          <div className="space-y-3">
            {allocationCases.map((c) => (
              <div
                key={c.id}
                className="p-3.5 rounded-card border border-[#E2E8F0] bg-[#F8FAFC] flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-[#0F172A]">{c.patient_name}</span>
                    <Badge variant="neutral">{c.finding_code}</Badge>
                    <Badge variant="info">{c.status.replace(/_/g, " ")}</Badge>
                  </div>
                  <p className="text-[#475569] mt-0.5">{c.finding_summary}</p>
                  <p className="text-[11px] text-[#64748B] mt-0.5">
                    Attending: <strong>{c.current_owner}</strong> • SLA Deadline:{" "}
                    {new Date(c.sla_deadline).toLocaleDateString()}
                  </p>
                </div>
                <div className="shrink-0 flex items-center gap-2">
                  <Link href={`/cases/${c.id}`}>
                    <Button size="sm" variant="secondary">
                      Review Case & Staging
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
            {allocationCases.length === 0 && (
              <div className="py-8 text-center text-xs text-[#64748B]">
                No cases awaiting doctor allocation.
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Tab 5: Appointments & Referrals */}
      {activeTab === "appointments" && (
        <div className="space-y-6">
          <Card padding="md">
            <CardHeader
              title="Cross-Facility Referrals (48h Acceptance SLA)"
              subtitle="Inter-facility specialist routing and acceptance tracking"
              action={<Badge variant="info">{referrals.length} Active</Badge>}
            />
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {referrals.map((ref) => (
                <div
                  key={ref.id}
                  className="p-3.5 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] text-xs space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs text-[#0F172A]">{ref.patient_name}</span>
                    <Badge variant={ref.status === "accepted" ? "success" : "info"}>{ref.status}</Badge>
                  </div>
                  <div className="text-[11px] text-[#475569] space-y-0.5">
                    <span className="block">
                      <strong>Specialty:</strong> {ref.specialty || "Breast Oncology"}
                    </span>
                    <span className="block">
                      <strong>Target:</strong> {ref.target_facility}
                    </span>
                    <span className="block">
                      <strong>Reason:</strong> {ref.reason_for_referral}
                    </span>
                  </div>
                  <div className="pt-2 border-t border-[#E2E8F0] flex items-center justify-between text-[11px]">
                    <span className="text-[#0F766E] font-medium">48h SLA</span>
                    <div className="flex items-center gap-2">
                      {ref.status !== "accepted" && (
                        <button
                          type="button"
                          onClick={() => handleAcceptReferral(ref.id)}
                          className="px-2 py-0.5 rounded bg-[#E6F4F1] hover:bg-[#CCFBF1] text-[#0F766E] font-semibold text-[10px] cursor-pointer"
                        >
                          Accept
                        </button>
                      )}
                      <Link href={`/cases/${ref.case_id}`} className="font-semibold text-[#0F766E] hover:underline">
                        Review
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
              {referrals.length === 0 && (
                <div className="col-span-full py-6 text-center text-xs text-[#64748B]">
                  No active referrals found.
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* Tab 6: Recovery & SLA */}
      {activeTab === "recovery" && (
        <Card padding="md">
          <CardHeader
            title="Stalled Care Journey Radar & Recovery Playbooks"
            subtitle="Identifies stalled care journeys and proposes coordinator interventions"
            action={<Badge variant="warning">{recoveryCases.length} Stalled Cases</Badge>}
          />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {recoveryCases.map((rc) => (
              <div
                key={rc.case_id}
                className="p-4 rounded-card border border-[#E2E8F0] bg-[#F8FAFC] flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div>
                      <Link
                        href={`/cases/${rc.case_id}`}
                        className="font-semibold text-sm text-[#0F172A] hover:text-[#0F766E] transition block"
                      >
                        {rc.patient_name}
                      </Link>
                      <span className="text-xs font-mono text-[#475569]">{rc.case_number}</span>
                    </div>
                    <Badge variant={rc.priority === "urgent" || rc.priority === "critical" ? "error" : "warning"}>
                      {rc.priority}
                    </Badge>
                  </div>

                  <div className="space-y-1.5 my-3 text-xs">
                    <div className="flex justify-between">
                      <span className="text-[#475569]">Detected Barrier:</span>
                      <span className="font-medium text-[#0F172A]">
                        {rc.barriers_detected.join(", ") || "Missed Visit / Transport"}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#475569]">Active Playbook:</span>
                      <span className="font-medium text-[#0F766E]">{rc.active_playbook}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#475569]">Recovery Attempts:</span>
                      <span className="font-medium text-[#0F172A]">{rc.recovery_attempts}</span>
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-[#E2E8F0] flex items-center justify-between gap-2 mt-2">
                  <Link
                    href={`/cases/${rc.case_id}`}
                    className="text-xs text-[#475569] hover:text-[#0F172A] font-medium"
                  >
                    View Timeline
                  </Link>
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => handleTriggerRecovery(rc.case_id)}
                    disabled={recoveringId === rc.case_id}
                    leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
                  >
                    {recoveringId === rc.case_id ? "Running..." : "Trigger Play"}
                  </Button>
                </div>
              </div>
            ))}
            {recoveryCases.length === 0 && (
              <div className="col-span-full py-8 text-center text-xs text-[#64748B]">
                No stalled cases detected. All care journeys progressing on schedule.
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Tab 7: All Cases */}
      {activeTab === "all_cases" && (
        <Card padding="none" className="overflow-hidden">
          <div className="p-4 sm:p-5 border-b border-[#E2E8F0] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-sm sm:text-base text-[#0F172A]">
                All Active Care Cases ({filteredCases.length})
              </h3>
              <p className="text-xs text-[#64748B]">
                Live operational status, SLA countdowns, and administrative ownership
              </p>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn text-xs">
                <Search className="w-3.5 h-3.5 text-[#64748B]" />
                <input
                  type="text"
                  placeholder="Search patient or code..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent text-xs text-[#0F172A] focus:outline-none w-32 sm:w-44"
                />
              </div>

              <select
                value={filterStatus}
                onChange={(e) => {
                  setFilterStatus(e.target.value);
                  setCurrentPage(1);
                }}
                className="h-8 px-2 bg-white border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] focus:outline-none cursor-pointer"
              >
                <option value="all">All Statuses</option>
                <option value="recovering">Recovering</option>
                <option value="scheduled">Scheduled</option>
                <option value="referred">Referred</option>
                <option value="notified">Notified</option>
                <option value="escalated">Escalated</option>
                <option value="closed">Closed</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8FAFC] text-[#64748B] border-b border-[#E2E8F0]">
                <tr>
                  <th className="py-3 px-5 font-semibold">Case / Patient</th>
                  <th className="py-3 px-4 font-semibold">Screening Code</th>
                  <th className="py-3 px-3 font-semibold">Status</th>
                  <th className="py-3 px-4 font-semibold">SLA Window</th>
                  <th className="py-3 px-4 font-semibold">Coordinator</th>
                  <th className="py-3 px-5 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {paginatedCases.map((c) => {
                  const sla = formatSLARemaining(c.sla_deadline);
                  return (
                    <tr key={c.id} className="hover:bg-[#F8FAFC] transition">
                      <td className="py-3 px-5">
                        <Link
                          href={`/cases/${c.id}`}
                          className="font-medium text-[#0F172A] hover:text-[#0F766E] transition block"
                        >
                          {c.patient_name}
                        </Link>
                        <span className="text-[11px] font-mono text-[#64748B]">{c.case_number}</span>
                      </td>
                      <td className="py-3 px-4">
                        <span className="inline-block px-2 py-0.5 rounded bg-slate-100 text-[#0F172A] font-medium text-[11px]">
                          {c.finding_code}
                        </span>
                      </td>
                      <td className="py-3 px-3">
                        <Badge
                          variant={
                            c.status === "closed"
                              ? "success"
                              : c.status === "escalated"
                              ? "error"
                              : c.status === "recovering"
                              ? "warning"
                              : "neutral"
                          }
                        >
                          {c.status.replace(/_/g, " ")}
                        </Badge>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`text-[11px] font-medium ${
                            sla.isOverdue ? "text-[#DC2626] font-semibold" : "text-[#0F766E]"
                          }`}
                        >
                          {sla.text}
                        </span>
                        <span className="text-[10px] text-[#64748B] block">
                          {c.sla_deadline ? new Date(c.sla_deadline).toLocaleDateString() : "N/A"}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-[#0F172A] font-medium">
                        {c.current_owner || coordinatorName}
                      </td>
                      <td className="py-3 px-5 text-right">
                        <Link href={`/cases/${c.id}`}>
                          <Button size="sm" variant="secondary" leftIcon={<ArrowRight className="w-3.5 h-3.5" />}>
                            Manage
                          </Button>
                        </Link>
                      </td>
                    </tr>
                  );
                })}
                {filteredCases.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-xs text-[#64748B]">
                      No cases match your search or filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <Pagination
            currentPage={currentPage}
            totalItems={filteredCases.length}
            pageSize={pageSize}
            onPageChange={setCurrentPage}
          />
        </Card>
      )}

      {/* Upload Diagnostic Report Modal (Browse files + Drag & Drop + Stepped Processing + Finalization) */}
      <ReportUploadModal
        isOpen={isReportModalOpen}
        onClose={() => {
          setIsReportModalOpen(false);
          setUploadResult(null);
        }}
        caseId={reportCaseId}
        cases={cases.map((c) => ({
          id: c.id,
          patient_name: c.patient_name,
          case_number: c.case_number,
          screening_order_id: c.screening_order_id,
          screening_type: c.screening_type,
        }))}
        onReportFinalized={async () => {
          setIsReportModalOpen(false);
          await loadData();
          toast("Report finalized successfully. Stage 2 completed.", "success");
        }}
      />

      {/* Schedule Screening Modal */}
      <Modal
        isOpen={isScheduleModalOpen}
        onClose={() => setIsScheduleModalOpen(false)}
        title="Schedule Diagnostic Screening Visit"
        subtitle={`Patient: ${schedulePatientName}`}
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setIsScheduleModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" isLoading={isScheduling} onClick={handleScheduleSubmit}>
              Confirm Screening Schedule
            </Button>
          </>
        }
      >
        <form onSubmit={handleScheduleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Screening Date"
              required
              type="date"
              value={screeningDate}
              onChange={(e) => setScreeningDate(e.target.value)}
            />
            <Input
              label="Screening Time"
              required
              type="time"
              value={screeningTime}
              onChange={(e) => setScreeningTime(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-[#0F172A] mb-1.5">
              Screening Instructions & Notes
            </label>
            <textarea
              value={screeningNotes}
              onChange={(e) => setScreeningNotes(e.target.value)}
              className="w-full p-3 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] h-20"
            />
          </div>
        </form>
      </Modal>
    </div>
  );
}
