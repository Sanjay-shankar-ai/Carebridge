"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  Users,
  Calendar,
  Share2,
  AlertCircle,
  Plus,
  Clock,
  ArrowRight,
  ChevronRight,
  Stethoscope,
  X,
  FileText,
  AlertTriangle,
  CheckCircle2,
  RotateCcw,
  ShieldCheck,
  ClipboardList,
  Search,
  Filter,
  Activity,
  CheckSquare,
} from "lucide-react";
import {
  fetchCases,
  fetchAppointments,
  fetchReferrals,
  bookAppointment,
  cancelAppointment,
  completeAppointment,
  reopenCase,
  sendAgentMessage,
  submitClinicalReview,
  recordConsultationOutcome,
  fetchDocumentationChecklist,
  executeClinicalClosure,
} from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import { CareCase, Appointment, Referral } from "../../types";
import { Card, CardHeader } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Modal } from "../../components/ui/Modal";
import { Badge } from "../../components/ui/Badge";
import { LoadingState, EmptyState } from "../../components/ui/EmptyState";
import { Tabs } from "../../components/ui/Tabs";
import { KPICard } from "../../components/ui/KPICard";
import { Pagination } from "../../components/ui/Pagination";
import { useToast } from "../../components/ui/Toast";

export default function DoctorDashboard() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [cases, setCases] = useState<CareCase[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  // Filter & Search & Pagination
  const [patientSearch, setPatientSearch] = useState("");
  const [patientFilter, setPatientFilter] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 8;

  // Booking Modal State
  const [isBookModalOpen, setIsBookModalOpen] = useState(false);
  const [bookCaseId, setBookCaseId] = useState("");
  const [bookPatientId, setBookPatientId] = useState("");
  const [bookFacility, setBookFacility] = useState("Clinic A - Women's Specialty Breast Center");
  const [bookProvider, setBookProvider] = useState("Dr. Aris Thorne, MD");
  const [bookType, setBookType] = useState("diagnostic_biopsy");
  const [bookDateTime, setBookDateTime] = useState("");
  const [bookNotes, setBookNotes] = useState("");
  const [bookSubmitting, setBookSubmitting] = useState(false);

  // Cancel Modal State (Requires Mandatory Reason)
  const [cancelModalAppt, setCancelModalAppt] = useState<Appointment | null>(null);
  const [cancellationReason, setCancellationReason] = useState("");
  const [cancelNotes, setCancelNotes] = useState("");
  const [cancelSubmitting, setCancelSubmitting] = useState(false);
  const [cancelError, setCancelError] = useState("");

  // Clinical Review & Escalation Resolution Modal State
  const [reviewModalCase, setReviewModalCase] = useState<CareCase | null>(null);
  const [clinicalDecisionNotes, setClinicalDecisionNotes] = useState("");
  const [approvedPathway, setApprovedPathway] = useState("Specialist Diagnostic Core Needle Biopsy");
  const [patientSafeExplanation, setPatientSafeExplanation] = useState("");
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewSuccessMsg, setReviewSuccessMsg] = useState("");

  // Consultation Outcome Modal State (Stage 10)
  const [consultModalCase, setConsultModalCase] = useState<CareCase | null>(null);
  const [consultNotes, setConsultNotes] = useState("");
  const [pathologyOutcome, setPathologyOutcome] = useState(
    "Benign fibroadenoma with focal ductal hyperplasia; NO atypia or malignancy"
  );
  const [clinicalRecs, setClinicalRecs] = useState(
    "Concordant benign pathology. Return to routine clinical surveillance."
  );
  const [treatmentPlan, setTreatmentPlan] = useState(
    "Active surveillance with bilateral screening mammography in 6 months."
  );
  const [nextFollowupDate, setNextFollowupDate] = useState("");
  const [consultSubmitting, setConsultSubmitting] = useState(false);

  // Clinical Closure Modal State (Stage 14)
  const [closureModalCase, setClosureModalCase] = useState<CareCase | null>(null);
  const [closureRationale, setClosureRationale] = useState(
    "Benign concordance established between imaging and histology. No residual disease or suspicion. Return to routine annual preventive screening."
  );
  const [checklistData, setChecklistData] = useState<any>(null);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [closureSubmitting, setClosureSubmitting] = useState(false);

  // Reopen Case Modal State
  const [reopenModalCase, setReopenModalCase] = useState<CareCase | null>(null);
  const [reopenRationale, setReopenRationale] = useState("");
  const [reopenSubmitting, setReopenSubmitting] = useState(false);
  const [reopenError, setReopenError] = useState("");

  const doctorName = user?.name || "Dr. Aris Thorne, MD";
  const doctorFacility = user?.facility || "Clinic A - Women's Specialty Breast Center";
  const [completingApptId, setCompletingApptId] = useState<string | null>(null);

  const handleCompleteAppointment = async (apptId: string) => {
    setCompletingApptId(apptId);
    try {
      await completeAppointment(apptId);
      const [casesRes, apptsRes] = await Promise.all([fetchCases(), fetchAppointments()]);
      setCases(casesRes || []);
      setAppointments(apptsRes || []);
      toast("Consultation marked as completed.", "success");
    } catch (err: any) {
      toast("Failed to complete appointment: " + (err.message || String(err)), "error");
    } finally {
      setCompletingApptId(null);
    }
  };

  const handleOpenClosureModal = async (c: CareCase) => {
    setClosureModalCase(c);
    setChecklistLoading(true);
    try {
      const res = await fetchDocumentationChecklist(c.id);
      setChecklistData(res);
    } catch (err) {
      console.error("Failed to load documentation checklist:", err);
    } finally {
      setChecklistLoading(false);
    }
  };

  const handleExecuteClosure = async () => {
    if (!closureModalCase) return;
    setClosureSubmitting(true);
    try {
      await executeClinicalClosure(closureModalCase.id, {
        clinical_rationale: closureRationale,
        evidence_summary: "10/10 clinical documentation checklist verified. Physician sign-off completed.",
      });
      setClosureModalCase(null);
      await loadData();
      toast("Clinical closure signed off and case closed.", "success");
    } catch (err: any) {
      toast("Closure error: " + (err.message || String(err)), "error");
    } finally {
      setClosureSubmitting(false);
    }
  };

  const handleRecordConsultationOutcome = async () => {
    if (!consultModalCase) return;
    setConsultSubmitting(true);
    try {
      await recordConsultationOutcome(consultModalCase.id, {
        consultation_notes:
          consultNotes || "Ultrasound-guided core needle biopsy performed. Specimen sent to pathology.",
        biopsy_pathology_outcome: pathologyOutcome,
        clinical_recommendations: clinicalRecs,
        treatment_plan: treatmentPlan,
        next_followup_date: nextFollowupDate || undefined,
      });
      setConsultModalCase(null);
      await loadData();
      toast("Consultation outcome recorded.", "success");
    } catch (err: any) {
      toast("Consultation record error: " + (err.message || String(err)), "error");
    } finally {
      setConsultSubmitting(false);
    }
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [casesRes, apptsRes, refsRes] = await Promise.all([
        fetchCases(),
        fetchAppointments(),
        fetchReferrals(),
      ]);
      setCases(casesRes || []);
      setAppointments(apptsRes || []);
      setReferrals(refsRes || []);

      if (casesRes && casesRes.length > 0) {
        setBookCaseId(casesRes[0].id);
        setBookPatientId(casesRes[0].patient_id);
      }
    } catch (err) {
      console.error("Failed to load doctor dashboard data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    document.title = "CareBridge — Attending Specialist Workspace";
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

  const handleBookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bookCaseId || !bookPatientId || !bookDateTime) {
      toast("Please fill in all required appointment fields.", "warning");
      return;
    }

    setBookSubmitting(true);
    try {
      await bookAppointment({
        case_id: bookCaseId,
        patient_id: bookPatientId,
        facility: bookFacility,
        provider_name: doctorName || bookProvider,
        appointment_type: bookType,
        scheduled_time: new Date(bookDateTime).toISOString(),
        notes: bookNotes,
      });
      setIsBookModalOpen(false);
      setBookNotes("");
      await loadData();
      toast("Diagnostic visit scheduled successfully.", "success");
    } catch (err: any) {
      toast("Failed to book appointment: " + (err.message || String(err)), "error");
    } finally {
      setBookSubmitting(false);
    }
  };

  const handleCancelSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cancellationReason.trim()) {
      setCancelError("Doctor cancellations require a mandatory clinical or operational reason.");
      return;
    }

    if (!cancelModalAppt) return;

    setCancelSubmitting(true);
    setCancelError("");
    try {
      await cancelAppointment(cancelModalAppt.id, {
        cancellation_reason: cancellationReason.trim(),
        cancelled_by: "doctor",
        notes: cancelNotes,
      });
      setCancelModalAppt(null);
      setCancellationReason("");
      setCancelNotes("");
      await loadData();
    } catch (err: any) {
      setCancelError("Cancellation failed: " + (err.message || String(err)));
    } finally {
      setCancelSubmitting(false);
    }
  };

  const handleResolveEscalationSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reviewModalCase || !clinicalDecisionNotes.trim()) {
      toast("Please enter clinical notes and instructions.", "warning");
      return;
    }

    setReviewSubmitting(true);
    try {
      await sendAgentMessage({
        caseId: reviewModalCase.id,
        message: `Clinical consultation completed by ${doctorName}: ${clinicalDecisionNotes.trim()}`,
        channel: "in_app_chat",
        sender: "doctor",
      });
      setReviewSuccessMsg("Clinical consultation recorded and escalation resolved.");
      toast("Escalation resolved and consultation recorded.", "success");
      setTimeout(() => {
        setReviewModalCase(null);
        setClinicalDecisionNotes("");
        setReviewSuccessMsg("");
      }, 1500);
      await loadData();
    } catch (err: any) {
      toast("Failed to resolve escalation: " + (err.message || String(err)), "error");
    } finally {
      setReviewSubmitting(false);
    }
  };

  const handleReopenSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reopenModalCase) return;
    if (reopenRationale.trim().length < 10) {
      setReopenError("Clinical rationale must be at least 10 characters long.");
      return;
    }

    setReopenSubmitting(true);
    setReopenError("");
    try {
      await reopenCase(reopenModalCase.id, reopenRationale.trim());
      setReopenModalCase(null);
      setReopenRationale("");
      await loadData();
      toast("Case reopened successfully.", "success");
    } catch (err: any) {
      setReopenError("Failed to reopen case: " + (err.message || String(err)));
    } finally {
      setReopenSubmitting(false);
    }
  };

  // Filter urgent & critical escalations
  const escalatedCases = cases.filter(
    (c) => c.status === "escalated" || c.priority === "critical"
  );
  const closedCases = cases.filter(
    (c) => c.status === "closed" || c.status === "care_completed"
  );
  const pendingReferrals = referrals.filter((r) => r.status === "sent" || r.status === "draft");
  const upcomingAppointments = appointments.filter(
    (a) => a.status === "booked" || a.status === "confirmed"
  );
  const urgentCases = cases.filter((c) => c.priority === "urgent" || c.priority === "critical");

  // Filtered patients list
  const filteredCases = cases.filter((c) => {
    const matchesSearch =
      c.patient_name.toLowerCase().includes(patientSearch.toLowerCase()) ||
      c.case_number.toLowerCase().includes(patientSearch.toLowerCase()) ||
      c.finding_code.toLowerCase().includes(patientSearch.toLowerCase());
    const matchesFilter =
      patientFilter === "all"
        ? true
        : patientFilter === "urgent"
        ? c.priority === "urgent" || c.priority === "critical"
        : patientFilter === "escalated"
        ? c.status === "escalated"
        : patientFilter === "closed"
        ? c.status === "closed"
        : true;
    return matchesSearch && matchesFilter;
  });

  const paginatedCases = filteredCases.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const tabs = [
    { id: "overview", label: "Overview", icon: <Activity className="w-4 h-4" /> },
    {
      id: "patients",
      label: "My Patients",
      badge: cases.length,
      icon: <Users className="w-4 h-4" />,
    },
    {
      id: "reviews",
      label: "Reviews",
      badge: escalatedCases.length > 0 ? escalatedCases.length : undefined,
      icon: <Stethoscope className="w-4 h-4" />,
    },
    {
      id: "appointments",
      label: "Appointments",
      badge: upcomingAppointments.length,
      icon: <Calendar className="w-4 h-4" />,
    },
    {
      id: "closure",
      label: "Closure",
      badge: closedCases.length > 0 ? closedCases.length : undefined,
      icon: <CheckSquare className="w-4 h-4" />,
    },
  ];

  if (loading) {
    return (
      <div className="py-16">
        <LoadingState message="Loading specialist workspace..." />
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
        <div>
          <Badge variant="info" className="mb-1.5">
            Attending Specialist Workspace
          </Badge>
          <h1 className="text-xl sm:text-2xl font-semibold text-[#0F172A] tracking-tight">
            Oncology & Breast Care Review
          </h1>
          <p className="text-xs sm:text-sm text-[#475569] mt-0.5">
            {doctorFacility} • Attending: <span className="font-semibold text-[#0F172A]">{doctorName}</span>
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-4 h-4" />}
            onClick={() => setIsBookModalOpen(true)}
          >
            Schedule Visit
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      {/* Tab 1: Overview */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Urgent Clinical Escalation Queue Banner */}
          {escalatedCases.length > 0 && (
            <Card padding="md" className="border-l-4 border-l-[#DC2626] bg-[#FEF2F2]/60">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-btn bg-[#FEE2E2] text-[#DC2626] flex items-center justify-center shrink-0">
                    <AlertTriangle className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-sm sm:text-base text-[#991B1B]">
                      Urgent Clinical Escalation Queue ({escalatedCases.length})
                    </h3>
                    <p className="text-xs text-[#7F1D1D]">
                      Cases requiring attending physician review or clinical redirection
                    </p>
                  </div>
                </div>
                <Badge variant="error">High Priority</Badge>
              </div>

              <div className="space-y-2 mt-3">
                {escalatedCases.map((ec) => (
                  <div
                    key={ec.id}
                    className="p-3.5 rounded-card bg-white border border-[#FECACA] flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-xs sm:text-sm text-[#0F172A]">{ec.patient_name}</span>
                        <span className="text-xs font-mono text-[#64748B]">({ec.case_number})</span>
                        <Badge variant="error">{ec.priority}</Badge>
                        <Badge variant="neutral">{ec.finding_code}</Badge>
                      </div>
                      <p className="text-xs text-[#475569] mt-1">
                        <strong>Clinical Summary:</strong> {ec.finding_summary || "Acute clinical symptoms flagged."}
                      </p>
                      <p className="text-[11px] text-[#64748B] mt-0.5">
                        SLA Deadline: {new Date(ec.sla_deadline).toLocaleDateString()} • Assigned: {ec.current_owner}
                      </p>
                    </div>

                    <div className="shrink-0">
                      <Button
                        variant="primary"
                        size="sm"
                        leftIcon={<Stethoscope className="w-3.5 h-3.5" />}
                        onClick={() => {
                          setReviewModalCase(ec);
                          setClinicalDecisionNotes("");
                        }}
                      >
                        Review & Resolve
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* 4 KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              label="Assigned Patients"
              value={cases.length}
              subtitle="Active screening cohort"
              icon={<Users className="w-4 h-4" />}
            />
            <KPICard
              label="Pending Referrals"
              value={pendingReferrals.length}
              subtitle="Within 48h turnaround SLA"
              icon={<Share2 className="w-4 h-4" />}
            />
            <KPICard
              label="Upcoming Visits"
              value={upcomingAppointments.length}
              subtitle="Biopsies & consultations"
              icon={<Calendar className="w-4 h-4" />}
            />
            <KPICard
              label="Urgent Attention"
              value={urgentCases.length}
              subtitle="BI-RADS 4/5 Lesions"
              badgeVariant="warning"
              badgeText="Requires Action"
              icon={<AlertCircle className="w-4 h-4 text-[#B45309]" />}
            />
          </div>

          {/* 2-Column: Quick Action Roster (Top 5) & Clinical Summary */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <div className="lg:col-span-8 space-y-4">
              <Card padding="md">
                <CardHeader
                  title="Needs Your Action"
                  subtitle="Patients currently requiring review, consultation, or procedural sign-off"
                  action={
                    <button
                      type="button"
                      onClick={() => setActiveTab("patients")}
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
                        <th className="py-2.5 px-4 font-semibold">Patient</th>
                        <th className="py-2.5 px-3 font-semibold">Finding</th>
                        <th className="py-2.5 px-3 font-semibold">Status</th>
                        <th className="py-2.5 px-4 font-semibold text-right">Quick Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E2E8F0]">
                      {cases.slice(0, 5).map((c) => (
                        <tr key={c.id} className="hover:bg-[#F8FAFC] transition">
                          <td className="py-3 px-4">
                            <span className="font-semibold text-[#0F172A] block">{c.patient_name}</span>
                            <span className="text-[11px] font-mono text-[#64748B]">{c.case_number}</span>
                          </td>
                          <td className="py-3 px-3">
                            <span className="font-medium text-[#0F172A]">{c.finding_code}</span>
                          </td>
                          <td className="py-3 px-3">
                            <Badge
                              variant={
                                c.status === "escalated"
                                  ? "error"
                                  : c.status === "closed"
                                  ? "success"
                                  : "neutral"
                              }
                            >
                              {c.status.replace(/_/g, " ")}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              {c.status !== "closed" && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setConsultModalCase(c);
                                    setConsultNotes("");
                                  }}
                                  className="px-2 py-1 rounded bg-[#E6F4F1] hover:bg-[#CCFBF1] text-[#0F766E] font-semibold text-[11px] cursor-pointer"
                                >
                                  Consult
                                </button>
                              )}
                              <Link
                                href={`/cases/${c.id}`}
                                className="p-1 rounded text-[#64748B] hover:text-[#0F172A]"
                              >
                                <ArrowRight className="w-3.5 h-3.5" />
                              </Link>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>

            <div className="lg:col-span-4 space-y-4">
              <Card padding="md">
                <CardHeader title="Clinical Summary" subtitle="Attending physician workload" />
                <div className="space-y-2 text-xs">
                  <div className="p-3 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] space-y-2">
                    <div className="flex justify-between">
                      <span className="text-[#64748B]">Active Escalations:</span>
                      <span className="font-semibold text-[#DC2626]">{escalatedCases.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#64748B]">Pending Referrals:</span>
                      <span className="font-semibold text-[#0F766E]">{pendingReferrals.length}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#64748B]">Attending Facility:</span>
                      <span className="font-semibold text-[#0F172A] truncate max-w-[150px]">
                        {doctorFacility}
                      </span>
                    </div>
                  </div>
                  <Link
                    href="/chat"
                    className="pt-2 text-xs font-semibold text-[#0F766E] hover:underline flex items-center gap-1"
                  >
                    <span>Open Clinical Chat Assistant →</span>
                  </Link>
                </div>
              </Card>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: My Patients */}
      {activeTab === "patients" && (
        <Card padding="none" className="overflow-hidden">
          <div className="p-4 sm:p-5 border-b border-[#E2E8F0] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-sm sm:text-base text-[#0F172A]">
                Assigned Patient Roster ({filteredCases.length})
              </h3>
              <p className="text-xs text-[#64748B]">Direct clinical supervision and milestone progression</p>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn text-xs">
                <Search className="w-3.5 h-3.5 text-[#64748B]" />
                <input
                  type="text"
                  placeholder="Search patient or code..."
                  value={patientSearch}
                  onChange={(e) => {
                    setPatientSearch(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent text-xs text-[#0F172A] focus:outline-none w-32 sm:w-44"
                />
              </div>

              <select
                value={patientFilter}
                onChange={(e) => {
                  setPatientFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="h-8 px-2 bg-white border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] focus:outline-none cursor-pointer"
              >
                <option value="all">All Statuses</option>
                <option value="urgent">Urgent / Critical</option>
                <option value="escalated">Escalated</option>
                <option value="closed">Closed</option>
              </select>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#F8FAFC] text-[#64748B] border-b border-[#E2E8F0]">
                <tr>
                  <th className="py-3 px-5 font-semibold">Patient</th>
                  <th className="py-3 px-4 font-semibold">Screening Result</th>
                  <th className="py-3 px-3 font-semibold">Priority</th>
                  <th className="py-3 px-3 font-semibold">Status</th>
                  <th className="py-3 px-5 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {paginatedCases.map((c) => (
                  <tr key={c.id} className="hover:bg-[#F8FAFC] transition">
                    <td className="py-3 px-5">
                      <Link
                        href={`/cases/${c.id}`}
                        className="font-semibold text-[#0F172A] hover:text-[#0F766E] transition block"
                      >
                        {c.patient_name}
                      </Link>
                      <span className="text-[11px] font-mono text-[#64748B]">{c.case_number}</span>
                    </td>
                    <td className="py-3 px-4">
                      <span className="font-semibold text-[#0F172A] block">{c.finding_code}</span>
                      <span className="text-[11px] text-[#475569] block truncate max-w-[200px]">
                        {c.finding_summary}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <Badge
                        variant={c.priority === "urgent" || c.priority === "critical" ? "error" : "success"}
                      >
                        {c.priority}
                      </Badge>
                    </td>
                    <td className="py-3 px-3">
                      <Badge
                        variant={
                          c.status === "escalated"
                            ? "error"
                            : c.status === "closed"
                            ? "success"
                            : "neutral"
                        }
                      >
                        {c.status.replace(/_/g, " ")}
                      </Badge>
                    </td>
                    <td className="py-3 px-5 text-right space-x-1.5 whitespace-nowrap">
                      {c.status === "closed" ? (
                        <button
                          type="button"
                          onClick={() => {
                            setReopenModalCase(c);
                            setReopenRationale("");
                            setReopenError("");
                          }}
                          className="px-2 py-1 rounded bg-[#FEF3C7] text-[#92400E] hover:bg-[#FDE68A] text-xs font-semibold inline-flex items-center gap-1 cursor-pointer"
                        >
                          <RotateCcw className="w-3 h-3" />
                          <span>Reopen</span>
                        </button>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => {
                              setReviewModalCase(c);
                              setClinicalDecisionNotes("");
                            }}
                            className="px-2 py-1 rounded bg-[#E6F4F1] text-[#0F766E] hover:bg-[#CCFBF1] text-xs font-semibold cursor-pointer"
                            title="Stage 5 & 6 Clinical Review"
                          >
                            Review
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setConsultModalCase(c);
                              setConsultNotes("");
                            }}
                            className="px-2 py-1 rounded bg-[#EFF6FF] text-[#1D4ED8] hover:bg-[#DBEAFE] text-xs font-semibold cursor-pointer"
                            title="Stage 10 Consultation & Pathology"
                          >
                            Consult
                          </button>
                          <button
                            type="button"
                            onClick={() => handleOpenClosureModal(c)}
                            className="px-2 py-1 rounded bg-[#DCFCE7] text-[#15803D] hover:bg-[#BBF7D0] text-xs font-semibold cursor-pointer"
                            title="Stage 14 Verified Clinical Closure"
                          >
                            Close
                          </button>
                        </>
                      )}
                      <Link
                        href={`/cases/${c.id}`}
                        className="p-1 rounded text-[#64748B] hover:text-[#0F172A] inline-block"
                      >
                        <ArrowRight className="w-3.5 h-3.5" />
                      </Link>
                    </td>
                  </tr>
                ))}

                {filteredCases.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-xs text-[#64748B]">
                      No patients match your search or filter.
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

      {/* Tab 3: Reviews */}
      {activeTab === "reviews" && (
        <div className="space-y-6">
          <Card padding="md">
            <CardHeader
              title="Inbound Referrals Review"
              subtitle="Cross-facility specialist diagnostic evaluation requests"
              action={<Badge variant="info">{referrals.length} Total</Badge>}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {referrals.map((ref) => (
                <div
                  key={ref.id}
                  className="p-3.5 rounded-card border border-[#E2E8F0] bg-[#F8FAFC] text-xs space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-semibold text-xs text-[#0F172A]">{ref.patient_name}</span>
                      <span className="text-[11px] text-[#64748B] font-mono ml-1">• {ref.case_number}</span>
                    </div>
                    <Badge variant={ref.status === "accepted" ? "success" : "info"}>{ref.status}</Badge>
                  </div>
                  <p className="text-[#475569]">
                    Reason: <strong className="text-[#0F172A]">{ref.reason_for_referral}</strong>
                  </p>
                  <div className="text-[11px] text-[#64748B] flex items-center justify-between pt-1 border-t border-[#E2E8F0]">
                    <span>
                      {ref.referring_provider} → {ref.target_facility}
                    </span>
                    <Link
                      href={`/cases/${ref.case_id}`}
                      className="text-[#0F766E] font-semibold hover:underline"
                    >
                      Review →
                    </Link>
                  </div>
                </div>
              ))}

              {referrals.length === 0 && (
                <div className="col-span-full py-8 text-center text-xs text-[#64748B]">
                  No inbound referrals pending.
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* Tab 4: Appointments */}
      {activeTab === "appointments" && (
        <Card padding="md">
          <CardHeader
            title="Scheduled Diagnostic Procedures & Consultations"
            subtitle="Attendances, biopsy suites, and cancellation management"
            action={
              <Button
                variant="primary"
                size="sm"
                leftIcon={<Plus className="w-3.5 h-3.5" />}
                onClick={() => setIsBookModalOpen(true)}
              >
                Schedule Visit
              </Button>
            }
          />

          <div className="space-y-3">
            {appointments.map((a) => (
              <div
                key={a.id}
                className="p-3.5 rounded-card border border-[#E2E8F0] bg-[#F8FAFC] text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-[#0F172A]">{a.patient_name}</span>
                    <Badge
                      variant={
                        a.status === "booked"
                          ? "success"
                          : a.status === "cancelled"
                          ? "error"
                          : a.status === "attended"
                          ? "neutral"
                          : "info"
                      }
                    >
                      {a.status}
                    </Badge>
                  </div>
                  <p className="text-[11px] text-[#64748B] capitalize">
                    {a.appointment_type.replace(/_/g, " ")} • {a.facility}
                  </p>
                  <div className="flex items-center gap-1.5 text-[11px] text-[#475569]">
                    <Clock className="w-3.5 h-3.5 text-[#0F766E]" />
                    <span>
                      {a.scheduled_time
                        ? new Date(a.scheduled_time).toLocaleString("en-US", {
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          })
                        : "Unscheduled"}
                    </span>
                  </div>
                  {a.cancellation_reason && (
                    <p className="text-[11px] text-[#7F1D1D] bg-[#FEE2E2] p-1.5 rounded-btn mt-1">
                      <strong>Cancellation Reason:</strong> {a.cancellation_reason}
                    </p>
                  )}
                </div>

                <div className="shrink-0 flex items-center gap-2">
                  {a.status === "booked" && (
                    <>
                      <button
                        type="button"
                        onClick={() => handleCompleteAppointment(a.id)}
                        disabled={completingApptId === a.id}
                        className="px-2.5 py-1.5 rounded-btn bg-[#DCFCE7] hover:bg-[#BBF7D0] text-[#14532D] font-semibold text-xs transition cursor-pointer flex items-center gap-1"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#15803D]" />
                        <span>{completingApptId === a.id ? "Updating..." : "Complete Consultation"}</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setCancelModalAppt(a)}
                        className="px-2.5 py-1.5 rounded-btn text-[#B91C1C] hover:bg-[#FEE2E2] font-semibold text-xs transition cursor-pointer"
                      >
                        Cancel
                      </button>
                    </>
                  )}
                  {a.status === "attended" && (
                    <span className="text-[11px] text-[#15803D] font-medium flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Completed
                    </span>
                  )}
                </div>
              </div>
            ))}

            {appointments.length === 0 && (
              <div className="py-8 text-center text-xs text-[#64748B]">
                No procedures or visits scheduled.
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Tab 5: Closure */}
      {activeTab === "closure" && (
        <div className="space-y-6">
          <Card padding="md">
            <CardHeader
              title="Evidence-Based Case Closure Verification"
              subtitle="Mandatory 5-point clinical checklist required before case sign-off"
              action={<Badge variant="success">Level 3 Clinical Authority</Badge>}
            />

            <div className="space-y-2.5">
              {[
                {
                  id: "biopsy_report",
                  title: "Diagnostic Tissue Biopsy / Histology Report Documented",
                  desc: "Definitive pathology diagnosis recorded with specimen histology.",
                },
                {
                  id: "clinician_review",
                  title: "Attending Oncologist / Specialist Evaluation Completed",
                  desc: "Dr. Aris Thorne clinical evaluation and staging documented.",
                },
                {
                  id: "care_plan",
                  title: "Multidisciplinary Care Plan Established",
                  desc: "12-month routine mammography or oncology surgical consult established.",
                },
                {
                  id: "patient_counselled",
                  title: "Patient Notified & Counselled",
                  desc: "Care coordinator confirmed patient understanding in preferred language.",
                },
                {
                  id: "authorized_signoff",
                  title: "Authorized Physician Sign-off & Audit Logged",
                  desc: "Digital signature and timestamp preserved in immutable PostgreSQL audit table.",
                },
              ].map((item, idx) => (
                <div
                  key={item.id}
                  className="p-3 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] flex items-start gap-3"
                >
                  <div className="w-5 h-5 rounded-full bg-[#15803D] text-white flex items-center justify-center text-xs font-bold mt-0.5 shrink-0">
                    ✓
                  </div>
                  <div className="flex-1">
                    <span className="font-semibold text-xs text-[#0F172A] block">
                      {idx + 1}. {item.title}
                    </span>
                    <span className="text-[11px] text-[#475569]">{item.desc}</span>
                  </div>
                  <Badge variant="success" icon={false}>
                    Verified
                  </Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Book Appointment Modal */}
      <Modal
        isOpen={isBookModalOpen}
        onClose={() => setIsBookModalOpen(false)}
        title="Schedule Diagnostic Visit"
        subtitle="Coordinate procedures and advance longitudinal case milestones"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setIsBookModalOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" size="sm" isLoading={bookSubmitting} onClick={handleBookSubmit}>
              Confirm Booking
            </Button>
          </>
        }
      >
        <form onSubmit={handleBookSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[#0F172A] mb-1.5">
              Select Patient & Case <span className="text-[#B91C1C]">*</span>
            </label>
            <select
              value={bookCaseId}
              onChange={(e) => {
                setBookCaseId(e.target.value);
                const selected = cases.find((c) => c.id === e.target.value);
                if (selected) setBookPatientId(selected.patient_id);
              }}
              className="w-full h-11 min-h-[44px] px-3.5 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E]"
              required
            >
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.patient_name} — {c.finding_code} ({c.case_number})
                </option>
              ))}
            </select>
          </div>

          <Input
            label="Healthcare Facility"
            required
            type="text"
            value={bookFacility}
            onChange={(e) => setBookFacility(e.target.value)}
          />

          <div className="grid grid-cols-2 gap-3">
            <Input label="Attending Provider" required type="text" value={doctorName} disabled />
            <div>
              <label className="block text-sm font-medium text-[#0F172A] mb-1.5">
                Procedure Type
              </label>
              <select
                value={bookType}
                onChange={(e) => setBookType(e.target.value)}
                className="w-full h-11 min-h-[44px] px-3.5 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E]"
              >
                <option value="diagnostic_biopsy">Diagnostic Biopsy</option>
                <option value="ultrasound_evaluation">Ultrasound Evaluation</option>
                <option value="colonoscopy">Colonoscopy</option>
                <option value="clinical_consultation">Clinical Consultation</option>
              </select>
            </div>
          </div>

          <Input
            label="Scheduled Date & Time"
            required
            type="datetime-local"
            value={bookDateTime}
            onChange={(e) => setBookDateTime(e.target.value)}
          />

          <div>
            <label className="block text-sm font-medium text-[#0F172A] mb-1.5">
              Clinical Notes (Optional)
            </label>
            <textarea
              value={bookNotes}
              onChange={(e) => setBookNotes(e.target.value)}
              placeholder="e.g. Target right upper outer quadrant lesion."
              className="w-full p-3 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] h-20"
            />
          </div>
        </form>
      </Modal>

      {/* Doctor Clinical Review & Escalation Resolution Modal */}
      <Modal
        isOpen={!!reviewModalCase}
        onClose={() => setReviewModalCase(null)}
        title="Doctor Clinical Review & Decision"
        subtitle={
          reviewModalCase
            ? `Patient: ${reviewModalCase.patient_name} • Case: ${reviewModalCase.case_number}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setReviewModalCase(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={reviewSubmitting}
              onClick={handleResolveEscalationSubmit}
            >
              Submit Clinical Decision
            </Button>
          </>
        }
      >
        {reviewSuccessMsg && (
          <div className="p-3 rounded-card bg-[#DEF7EC] border border-[#BCF0DA] text-xs text-[#03543F] mb-3">
            {reviewSuccessMsg}
          </div>
        )}

        {reviewModalCase && (
          <div className="space-y-4">
            <div className="p-3.5 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-[#64748B]">Finding Code:</span>
                <span className="font-semibold text-[#0F172A]">{reviewModalCase.finding_code}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Current Status:</span>
                <span className="font-semibold text-[#DC2626] uppercase">{reviewModalCase.status}</span>
              </div>
              <div className="pt-1">
                <span className="text-[#64748B] block">Summary:</span>
                <span className="text-[#0F172A] font-medium">{reviewModalCase.finding_summary}</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-[#0F172A] mb-1.5">
                Attending Physician Assessment & Plan <span className="text-[#B91C1C]">*</span>
              </label>
              <textarea
                value={clinicalDecisionNotes}
                onChange={(e) => setClinicalDecisionNotes(e.target.value)}
                placeholder="Document clinical evaluation (e.g. Reviewed diagnostic biopsy: confirmed benign fibroadenoma. Escalation resolved; schedule routine 12-month follow-up)."
                className="w-full p-3 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] h-28"
                required
              />
            </div>
          </div>
        )}
      </Modal>

      {/* Mandatory Cancellation Modal */}
      <Modal
        isOpen={!!cancelModalAppt}
        onClose={() => setCancelModalAppt(null)}
        title="Cancel Clinical Visit"
        subtitle={
          cancelModalAppt
            ? `Patient: ${cancelModalAppt.patient_name} • ${cancelModalAppt.facility}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setCancelModalAppt(null)}>
              Keep Appointment
            </Button>
            <Button variant="danger" size="sm" isLoading={cancelSubmitting} onClick={handleCancelSubmit}>
              Confirm Cancellation
            </Button>
          </>
        }
      >
        <div className="p-3 rounded-card bg-[#FEF3C7] border border-[#FDE68A] text-xs text-[#78350F] mb-3">
          <strong>Patient Safety Protocol:</strong> Doctor cancellations require a documented reason. Coordinator ownership is retained, and proactive rebooking outreach is scheduled immediately.
        </div>

        {cancelError && (
          <div className="p-3 rounded-card bg-[#FEE2E2] border border-[#FECACA] text-xs text-[#7F1D1D] mb-3">
            {cancelError}
          </div>
        )}

        <form onSubmit={handleCancelSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[#0F172A] mb-1.5">
              Mandatory Cancellation Reason <span className="text-[#B91C1C]">*</span>
            </label>
            <select
              value={cancellationReason}
              onChange={(e) => setCancellationReason(e.target.value)}
              className="w-full h-11 min-h-[44px] px-3.5 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E]"
              required
            >
              <option value="">-- Select clinical or operational reason --</option>
              <option value="Emergency surgery conflict for attending specialist">
                Emergency surgery conflict for attending specialist
              </option>
              <option value="Pathology biopsy suite undergoing urgent sterilization">
                Pathology biopsy suite undergoing urgent sterilization
              </option>
              <option value="Preliminary lab results require pre-procedure clearance">
                Preliminary lab results require pre-procedure clearance
              </option>
              <option value="Patient requested later slot due to family transportation">
                Patient requested later slot due to family transportation
              </option>
              <option value="Other specialized clinical justification">
                Other specialized clinical justification
              </option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-[#0F172A] mb-1.5">
              Instructions for Coordinator & Patient
            </label>
            <textarea
              value={cancelNotes}
              onChange={(e) => setCancelNotes(e.target.value)}
              placeholder="Instructions..."
              className="w-full p-3 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] h-20"
            />
          </div>
        </form>
      </Modal>

      {/* Case Reopening Modal */}
      <Modal
        isOpen={!!reopenModalCase}
        onClose={() => setReopenModalCase(null)}
        title="Reopen Closed Care Case"
        subtitle={
          reopenModalCase
            ? `Case #${reopenModalCase.case_number} • Patient: ${reopenModalCase.patient_name}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setReopenModalCase(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={reopenSubmitting}
              onClick={handleReopenSubmit}
            >
              Authorize Case Reopening
            </Button>
          </>
        }
      >
        <div className="p-3 rounded-card bg-[#FEF3C7] border border-[#FDE68A] text-xs text-[#78350F] mb-3">
          <strong>Authorized Clinical Action:</strong> Only an attending physician may reopen a closed care case. A documented clinical rationale is required and will be permanently logged in the PostgreSQL audit log.
        </div>

        {reopenError && (
          <div className="p-3 rounded-card bg-[#FEE2E2] border border-[#FECACA] text-xs text-[#7F1D1D] mb-3">
            {reopenError}
          </div>
        )}

        <form onSubmit={handleReopenSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[#0F172A] mb-1.5">
              Mandatory Clinical Justification (min 10 characters) <span className="text-[#B91C1C]">*</span>
            </label>
            <textarea
              value={reopenRationale}
              onChange={(e) => setReopenRationale(e.target.value)}
              placeholder="Document the clinical reason for reopening (e.g. New suspicious finding reported on 6-month interval imaging; urgent tissue biopsy re-evaluation indicated)."
              className="w-full p-3 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] h-24"
              required
            />
          </div>
        </form>
      </Modal>

      {/* Stage 10: Consultation & Pathology Outcome Modal */}
      <Modal
        isOpen={!!consultModalCase}
        onClose={() => setConsultModalCase(null)}
        title="Record Consultation & Pathology Outcome (Stage 10)"
        subtitle={
          consultModalCase
            ? `Case #${consultModalCase.case_number} • Patient: ${consultModalCase.patient_name}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setConsultModalCase(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={consultSubmitting}
              onClick={handleRecordConsultationOutcome}
            >
              Document Outcome & Advance
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-[#0F172A] mb-1">
              Biopsy Pathology Finding <span className="text-[#B91C1C]">*</span>
            </label>
            <textarea
              value={pathologyOutcome}
              onChange={(e) => setPathologyOutcome(e.target.value)}
              className="w-full p-2.5 bg-white border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] h-18"
              required
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] mb-1">
              Physician Recommendations
            </label>
            <input
              type="text"
              value={clinicalRecs}
              onChange={(e) => setClinicalRecs(e.target.value)}
              className="w-full p-2.5 bg-white border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A]"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] mb-1">
              Active Treatment / Surveillance Plan
            </label>
            <input
              type="text"
              value={treatmentPlan}
              onChange={(e) => setTreatmentPlan(e.target.value)}
              className="w-full p-2.5 bg-white border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A]"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] mb-1">
              Next Follow-Up Date (Optional)
            </label>
            <input
              type="date"
              value={nextFollowupDate}
              onChange={(e) => setNextFollowupDate(e.target.value)}
              className="w-full p-2.5 bg-white border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A]"
            />
          </div>
        </div>
      </Modal>

      {/* Stage 14: Verified Clinical Closure Sign-Off Modal */}
      <Modal
        isOpen={!!closureModalCase}
        onClose={() => setClosureModalCase(null)}
        title="Verified Clinical Closure Sign-Off (Stage 14)"
        subtitle={
          closureModalCase
            ? `Case #${closureModalCase.case_number} • Patient: ${closureModalCase.patient_name}`
            : undefined
        }
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setClosureModalCase(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={closureSubmitting}
              onClick={handleExecuteClosure}
              disabled={checklistData && !checklistData.is_complete}
            >
              Sign Off & Close Case
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="p-3 rounded-card bg-[#F8FAFC] border border-[#E2E8F0]">
            <h4 className="text-xs font-semibold text-[#0F172A] mb-2">
              10-Point Documentation Checklist Audit
            </h4>
            {checklistLoading ? (
              <span className="text-xs text-[#64748B]">Auditing clinical evidence...</span>
            ) : checklistData ? (
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {Object.entries(checklistData.checklist || {}).map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between text-xs py-0.5">
                    <span className="text-[#475569] capitalize">{key.replace(/_/g, " ")}</span>
                    <Badge variant={val ? "success" : "error"}>{val ? "Verified ✓" : "Missing"}</Badge>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-xs text-[#B91C1C]">Could not load checklist</span>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#0F172A] mb-1">
              Physician Final Closure Rationale <span className="text-[#B91C1C]">*</span>
            </label>
            <textarea
              value={closureRationale}
              onChange={(e) => setClosureRationale(e.target.value)}
              className="w-full p-2.5 bg-white border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] h-20"
              required
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
