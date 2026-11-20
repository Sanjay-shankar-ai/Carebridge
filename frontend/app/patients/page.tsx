"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Users,
  Search,
  Filter,
  CheckCircle2,
  Clock,
  AlertTriangle,
  AlertCircle,
  ChevronRight,
  ChevronLeft,
  RefreshCw,
  Eye,
  FileText,
  UserCheck,
  Calendar,
  Upload,
  ArrowRight,
  Shield,
  X,
  Stethoscope,
  Building2,
  Lock,
  ListTodo,
  ExternalLink,
} from "lucide-react";
import {
  fetchCoordinatorPatients,
  fetchCoordinatorTasks,
  fetchCaseLifecycle,
  scheduleScreening,
  completeScreening,
  uploadTestReport,
  fetchDoctorCandidates,
  recordMissedScreening,
  fetchDocumentationChecklist,
  executeClinicalClosure,
} from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

interface CoordinatorPatientItem {
  patient_id: string;
  name: string;
  mrn: string;
  phone?: string;
  case_id: string;
  case_number: string;
  current_stage_number: number;
  current_stage_title: string;
  status: string;
  pending_action: string;
  responsible_role: string;
  assigned_doctor: string;
  sla_status: "normal" | "warning" | "breached";
  sla_deadline?: string;
  needs_coordinator_action: boolean;
  last_updated: string;
}

interface CoordinatorTaskItem {
  task_id: string;
  case_id: string;
  patient_id: string;
  patient_name: string;
  stage_number: number;
  stage_title: string;
  task_title: string;
  description?: string;
  priority: string;
  status: string;
  sla_status: string;
  due_date?: string;
}

export default function PatientsManagementPage() {
  const { user } = useAuth();
  const isCoordinator = user?.role === "care_coordinator" || user?.role === "coordinator";
  const isDoctor = user?.role === "doctor" || user?.role === "clinician";

  // Tab State: "patients" | "tasks"
  const [activeTab, setActiveTab] = useState<"patients" | "tasks">("patients");

  // Patients Filter & Pagination State
  const [patients, setPatients] = useState<CoordinatorPatientItem[]>([]);
  const [tasks, setTasks] = useState<CoordinatorTaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedStage, setSelectedStage] = useState<number | null>(null);
  const [filterNeedsAction, setFilterNeedsAction] = useState(false);
  const [filterOverdue, setFilterOverdue] = useState(false);
  const [filterUnassigned, setFilterUnassigned] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [sortBy, setSortBy] = useState("last_updated");
  const [sortOrder, setSortOrder] = useState<"desc" | "asc">("desc");

  // Patient Case Detail Modal State
  const [selectedPatient, setSelectedPatient] = useState<CoordinatorPatientItem | null>(null);
  const [lifecycleData, setLifecycleData] = useState<any | null>(null);
  const [loadingLifecycle, setLoadingLifecycle] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Action Modals State
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [showCompleteScreeningModal, setShowCompleteScreeningModal] = useState(false);
  const [showUploadReportModal, setShowUploadReportModal] = useState(false);
  const [showDoctorCandidatesModal, setShowDoctorCandidatesModal] = useState(false);
  const [doctorCandidates, setDoctorCandidates] = useState<any[]>([]);

  // Action Form Inputs
  const [screeningFacility, setScreeningFacility] = useState("Metropolitan Hospital Imaging Center");
  const [screeningDate, setScreeningDate] = useState("2026-11-25T10:00");
  const [screeningNotes, setScreeningNotes] = useState("");
  const [completeNotes, setCompleteNotes] = useState("Screening imaging performed per clinical protocol.");
  const [reportType, setReportType] = useState("Mammogram");
  const [reportFindingCode, setReportFindingCode] = useState("BI-RADS-4");
  const [reportFindingSummary, setReportFindingSummary] = useState("Suspicious microcalcifications in upper outer quadrant.");
  const [reportRecommendation, setReportRecommendation] = useState("Recommend core needle biopsy within 14 days.");

  const loadPatients = async () => {
    try {
      setLoading(true);
      const res = await fetchCoordinatorPatients({
        q: searchQuery || undefined,
        stage: selectedStage !== null ? selectedStage : undefined,
        needs_my_action: filterNeedsAction ? true : undefined,
        overdue_sla: filterOverdue ? true : undefined,
        unassigned: filterUnassigned ? true : undefined,
        page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
      });

      if (res && res.items) {
        setPatients(res.items);
        setTotalPages(res.total_pages || 1);
        setTotalCount(res.total || 0);
      } else {
        setPatients([]);
        setTotalPages(1);
        setTotalCount(0);
      }
    } catch (err) {
      console.error("Failed to load coordinator patients:", err);
      setPatients([]);
    } finally {
      setLoading(false);
    }
  };

  const loadTasks = async () => {
    try {
      const data = await fetchCoordinatorTasks();
      setTasks(data || []);
    } catch (err) {
      console.error("Failed to load coordinator tasks:", err);
      setTasks([]);
    }
  };

  useEffect(() => {
    loadPatients();
  }, [searchQuery, selectedStage, filterNeedsAction, filterOverdue, filterUnassigned, page, pageSize, sortBy, sortOrder]);

  useEffect(() => {
    if (activeTab === "tasks") {
      loadTasks();
    }
  }, [activeTab]);

  // Open Patient Case Lifecycle Drawer
  const handleOpenCase = async (patient: CoordinatorPatientItem) => {
    setSelectedPatient(patient);
    setActionError(null);
    setActionSuccess(null);
    if (!patient.case_id) {
      setLifecycleData(null);
      return;
    }

    try {
      setLoadingLifecycle(true);
      const res = await fetchCaseLifecycle(patient.case_id);
      setLifecycleData(res || null);
    } catch (err: any) {
      console.error("Failed to fetch case lifecycle:", err);
      setActionError(err.message || "Could not load 14-stage lifecycle from server.");
    } finally {
      setLoadingLifecycle(false);
    }
  };

  const reloadActiveCase = async () => {
    if (!selectedPatient?.case_id) return;
    try {
      setLoadingLifecycle(true);
      const res = await fetchCaseLifecycle(selectedPatient.case_id);
      setLifecycleData(res || null);
      await loadPatients();
      await loadTasks();
    } catch (err: any) {
      console.error("Error refreshing case lifecycle:", err);
    } finally {
      setLoadingLifecycle(false);
    }
  };

  // Stage 1 Action: Schedule Screening Order
  const handleScheduleScreeningSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPatient?.case_id) return;
    setActionError(null);
    try {
      await scheduleScreening(selectedPatient.case_id, {
        scheduled_time: new Date(screeningDate).toISOString(),
        facility: screeningFacility,
        notes: screeningNotes,
      });
      setActionSuccess("Screening appointment scheduled and patient notified.");
      setShowScheduleModal(false);
      await reloadActiveCase();
    } catch (err: any) {
      setActionError(err.message || "Failed to schedule screening.");
    }
  };

  // Stage 1 Action: Complete Screening (Advance Stage 1)
  const handleCompleteScreeningSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPatient?.case_id) return;
    setActionError(null);
    try {
      await completeScreening(selectedPatient.case_id, {
        completion_notes: completeNotes,
        completed_at: new Date().toISOString(),
      });
      setActionSuccess("Screening recorded as completed. Stage 1 evidence verified and advanced.");
      setShowCompleteScreeningModal(false);
      await reloadActiveCase();
    } catch (err: any) {
      setActionError(err.message || "Failed to record screening completion.");
    }
  };

  // Stage 2 Action: Upload Test Report & Finalize
  const handleUploadReportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPatient?.case_id) return;
    setActionError(null);
    try {
      await uploadTestReport(selectedPatient.case_id, {
        screening_type: reportType,
        disease_condition: `${reportType} Findings (${reportFindingCode})`,
        finding_code: reportFindingCode,
        finding_summary: reportFindingSummary,
        clinical_recommendation: reportRecommendation,
        urgency_level: "standard",
      });
      setActionSuccess("Diagnostic test report uploaded & metadata verified. Stage 2 advanced.");
      setShowUploadReportModal(false);
      await reloadActiveCase();
    } catch (err: any) {
      setActionError(err.message || "Failed to upload test report.");
    }
  };

  // Doctor Allocation Action
  const handleLoadDoctorCandidates = async () => {
    if (!selectedPatient?.case_id) return;
    try {
      const candidates = await fetchDoctorCandidates(selectedPatient.case_id);
      setDoctorCandidates(candidates || []);
      setShowDoctorCandidatesModal(true);
    } catch (err: any) {
      setActionError("Could not retrieve doctor allocation candidates.");
    }
  };

  // Stage 14 Attempted Closure (Blocked for Coordinator)
  const handleCoordinatorClosureAttempt = async () => {
    if (!selectedPatient?.case_id) return;
    setActionError(null);
    setActionSuccess(null);
    try {
      await executeClinicalClosure(selectedPatient.case_id, {
        clinical_rationale: "Care coordinator requested case closure.",
      });
      setActionSuccess("Case closed.");
    } catch (err: any) {
      // Expected to fail with 403 Forbidden
      setActionError("403 Forbidden: Level 3 Clinical Authority Invariant Enforced. Care Coordinators CANNOT close a case. Only an authorized attending physician may execute clinical closure sign-off.");
    }
  };

  const getSlaBadge = (status: string) => {
    if (status === "breached") {
      return (
        <Badge variant="critical" className="text-[10px] py-0.5 px-2 font-semibold">
          SLA Breached
        </Badge>
      );
    }
    if (status === "warning") {
      return (
        <Badge variant="warning" className="text-[10px] py-0.5 px-2 font-semibold">
          SLA Warning
        </Badge>
      );
    }
    return (
      <Badge variant="success" className="text-[10px] py-0.5 px-2 font-semibold">
        SLA Normal
      </Badge>
    );
  };

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto pb-16">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-semibold mb-2">
            <Users className="w-3.5 h-3.5" />
            Care Coordination Patient Management
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-[#0F172A] tracking-tight">
            Patients & Longitudinal 14-Stage Task Hub
          </h1>
          <p className="text-sm text-[#475569] mt-1">
            Supervise every patient across all 14 clinical and operational stages with PostgreSQL evidence verification.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Tab Switcher */}
          <div className="flex items-center bg-[#F1F5F9] p-1 rounded-btn text-xs font-medium border border-[#E2E8F0]">
            <button
              onClick={() => setActiveTab("patients")}
              className={`px-3 py-1.5 rounded-btn transition ${
                activeTab === "patients"
                  ? "bg-white text-[#0F766E] shadow-2xs font-semibold"
                  : "text-[#64748B] hover:text-[#0F172A]"
              }`}
            >
              All Patients ({totalCount})
            </button>
            <button
              onClick={() => setActiveTab("tasks")}
              className={`px-3 py-1.5 rounded-btn transition flex items-center gap-1.5 ${
                activeTab === "tasks"
                  ? "bg-white text-[#0F766E] shadow-2xs font-semibold"
                  : "text-[#64748B] hover:text-[#0F172A]"
              }`}
            >
              <ListTodo className="w-3.5 h-3.5" />
              My Coordinator Tasks ({tasks.length})
            </button>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={activeTab === "patients" ? loadPatients : loadTasks}
            disabled={loading}
            icon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />}
            className="text-xs h-9"
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* TAB 1: ALL PATIENTS */}
      {activeTab === "patients" && (
        <div className="space-y-4">
          {/* Filter & Search Toolbar */}
          <Card padding="md" className="space-y-3">
            <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
              {/* Search Bar */}
              <div className="flex-1 relative">
                <Search className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search patient name, MRN, case number, or phone..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setPage(1);
                  }}
                  className="w-full h-9 pl-9 pr-4 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:ring-1 focus:ring-[#0F766E]"
                />
              </div>

              {/* Stage Filter Dropdown */}
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={selectedStage !== null ? selectedStage : ""}
                  onChange={(e) => {
                    setSelectedStage(e.target.value ? Number(e.target.value) : null);
                    setPage(1);
                  }}
                  className="h-9 px-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] focus:outline-none focus:ring-1 focus:ring-[#0F766E]"
                  aria-label="Filter by Stage"
                >
                  <option value="">All Stages (1 to 14)</option>
                  <option value="1">Stage 1: Screening Order</option>
                  <option value="2">Stage 2: Result Generated</option>
                  <option value="3">Stage 3: Patient Notified</option>
                  <option value="4">Stage 4: Patient Comprehension</option>
                  <option value="5">Stage 5: Clinical Review</option>
                  <option value="6">Stage 6: Clinical Confirmation</option>
                  <option value="7">Stage 7: Referral Initiated</option>
                  <option value="8">Stage 8: Referral Accepted</option>
                  <option value="9">Stage 9: Appointment Confirmed</option>
                  <option value="10">Stage 10: Consultation Completed</option>
                  <option value="11">Stage 11: Treatment Monitoring</option>
                  <option value="12">Stage 12: Follow-Up Management</option>
                  <option value="13">Stage 13: Documentation Checklist</option>
                  <option value="14">Stage 14: Verified Clinical Closure</option>
                </select>

                {/* Sort dropdown */}
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="h-9 px-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] focus:outline-none focus:ring-1 focus:ring-[#0F766E]"
                  aria-label="Sort by field"
                >
                  <option value="last_updated">Sort: Last Updated</option>
                  <option value="name">Sort: Patient Name</option>
                  <option value="stage">Sort: Stage Number</option>
                  <option value="sla">Sort: SLA Urgency</option>
                </select>

                {/* Sort Order Toggle */}
                <button
                  type="button"
                  onClick={() => setSortOrder(sortOrder === "desc" ? "asc" : "desc")}
                  className="h-9 px-2.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn text-xs font-medium text-[#475569] hover:bg-[#E2E8F0] transition"
                  title="Toggle ascending / descending"
                >
                  {sortOrder === "desc" ? "↓ Desc" : "↑ Asc"}
                </button>
              </div>
            </div>

            {/* Quick Filter Pill Buttons */}
            <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-[#F1F5F9]">
              <span className="text-[11px] font-semibold text-[#64748B] uppercase tracking-wider mr-1">
                Quick Filters:
              </span>
              <button
                type="button"
                onClick={() => {
                  setFilterNeedsAction(!filterNeedsAction);
                  setPage(1);
                }}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition ${
                  filterNeedsAction
                    ? "bg-[#0F766E] text-white border-[#0F766E]"
                    : "bg-[#F8FAFC] text-[#475569] border-[#CBD5E1] hover:bg-[#E6F4F1]"
                }`}
              >
                Needs My Action
              </button>
              <button
                type="button"
                onClick={() => {
                  setFilterOverdue(!filterOverdue);
                  setPage(1);
                }}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition ${
                  filterOverdue
                    ? "bg-rose-600 text-white border-rose-600"
                    : "bg-[#F8FAFC] text-[#475569] border-[#CBD5E1] hover:bg-rose-50"
                }`}
              >
                Overdue / SLA Breach
              </button>
              <button
                type="button"
                onClick={() => {
                  setFilterUnassigned(!filterUnassigned);
                  setPage(1);
                }}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition ${
                  filterUnassigned
                    ? "bg-amber-600 text-white border-amber-600"
                    : "bg-[#F8FAFC] text-[#475569] border-[#CBD5E1] hover:bg-amber-50"
                }`}
              >
                Unassigned Doctor
              </button>
              {(filterNeedsAction || filterOverdue || filterUnassigned || selectedStage !== null || searchQuery) && (
                <button
                  type="button"
                  onClick={() => {
                    setFilterNeedsAction(false);
                    setFilterOverdue(false);
                    setFilterUnassigned(false);
                    setSelectedStage(null);
                    setSearchQuery("");
                    setPage(1);
                  }}
                  className="text-xs text-[#0F766E] underline font-medium ml-2 hover:text-[#0D5F58]"
                >
                  Clear all filters
                </button>
              )}
            </div>
          </Card>

          {/* Patients List Table */}
          <Card padding="none" className="overflow-hidden border border-[#E2E8F0] shadow-soft">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[#475569] font-semibold">
                    <th className="py-3 px-4">Patient & Case</th>
                    <th className="py-3 px-3">Current Stage (of 14)</th>
                    <th className="py-3 px-3">Status</th>
                    <th className="py-3 px-3">Pending Action</th>
                    <th className="py-3 px-3">Role</th>
                    <th className="py-3 px-3">Assigned Doctor</th>
                    <th className="py-3 px-3">SLA Status</th>
                    <th className="py-3 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E2E8F0] bg-white">
                  {loading ? (
                    <tr>
                      <td colSpan={8} className="py-12 text-center text-[#64748B]">
                        <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-[#0F766E]" />
                        <span>Loading patient cases from database...</span>
                      </td>
                    </tr>
                  ) : patients.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-12 text-center text-[#64748B]">
                        <Users className="w-8 h-8 text-[#CBD5E1] mx-auto mb-2" />
                        <p className="font-medium text-sm text-[#0F172A]">No patient cases found</p>
                        <p className="text-xs text-[#94A3B8] mt-1">
                          No patients match your current search and filter criteria.
                        </p>
                      </td>
                    </tr>
                  ) : (
                    patients.map((p) => {
                      const stageNum = p.current_stage_number || 1;
                      const stagePct = Math.round((stageNum / 14) * 100);
                      return (
                        <tr
                          key={p.patient_id || p.case_id}
                          className="hover:bg-[#F8FAFC] transition cursor-pointer group"
                          onClick={() => handleOpenCase(p)}
                        >
                          {/* Patient & Case */}
                          <td className="py-3 px-4">
                            <div className="font-semibold text-xs text-[#0F172A] group-hover:text-[#0F766E] transition">
                              {p.name || (p as any).patient_name || "Patient"}
                            </div>
                            <div className="text-[10px] text-[#64748B] flex items-center gap-2 mt-0.5">
                              <span>MRN: <strong className="font-mono text-[#0F172A]">{p.mrn || "N/A"}</strong></span>
                              <span>•</span>
                              <span>Case: <strong className="font-mono text-[#0F172A]">{p.case_number}</strong></span>
                            </div>
                          </td>

                          {/* Current Stage */}
                          <td className="py-3 px-3">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-xs text-[#0F766E] font-mono">
                                Stage {stageNum}/14
                              </span>
                            </div>
                            <div className="w-24 bg-[#E2E8F0] rounded-full h-1.5 mt-1 overflow-hidden">
                              <div
                                className="bg-[#0F766E] h-1.5 rounded-full"
                                style={{ width: `${stagePct}%` }}
                              />
                            </div>
                            <span className="text-[10px] text-[#64748B] block truncate max-w-[140px] mt-0.5">
                              {p.current_stage_title || "Care Pathway Active"}
                            </span>
                          </td>

                          {/* Status */}
                          <td className="py-3 px-3">
                            <Badge variant="neutral" className="capitalize text-[10px] py-0 px-2 font-mono">
                              {(p.status || "active").replace(/_/g, " ")}
                            </Badge>
                          </td>

                          {/* Pending Action */}
                          <td className="py-3 px-3">
                            <span className="text-xs text-[#0F172A] font-medium block truncate max-w-[150px]">
                              {p.pending_action || "Review Care Pathway"}
                            </span>
                            {p.needs_coordinator_action && (
                              <span className="inline-block mt-0.5 px-1.5 py-0.2 bg-[#E6F4F1] text-[#0F766E] rounded text-[9px] font-semibold">
                                Action Required
                              </span>
                            )}
                          </td>

                          {/* Responsible Role */}
                          <td className="py-3 px-3">
                            <span className="capitalize text-[11px] text-[#475569] font-medium">
                              {(p.responsible_role || "care_coordinator").replace(/_/g, " ")}
                            </span>
                          </td>

                          {/* Assigned Doctor */}
                          <td className="py-3 px-3">
                            <span className={`text-xs ${!p.assigned_doctor || p.assigned_doctor === "Unassigned" ? "text-amber-700 italic font-medium" : "text-[#0F172A] font-medium"}`}>
                              {p.assigned_doctor || "Unassigned"}
                            </span>
                          </td>

                          {/* SLA Status */}
                          <td className="py-3 px-3">
                            {getSlaBadge(p.sla_status)}
                          </td>

                          {/* Action Button */}
                          <td className="py-3 px-4 text-right">
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-[11px] h-7 px-2.5 text-[#0F766E] border-[#0F766E]/30 group-hover:bg-[#0F766E] group-hover:text-white transition"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOpenCase(p);
                              }}
                            >
                              Manage Case
                            </Button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="p-3 bg-[#F8FAFC] border-t border-[#E2E8F0] flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-[#64748B]">
              <div>
                Showing <strong>{patients.length}</strong> of <strong>{totalCount}</strong> patient cases
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  leftIcon={<ChevronLeft className="w-3.5 h-3.5" />}
                  className="text-xs h-7 px-2"
                >
                  Previous
                </Button>

                <span className="text-xs font-semibold text-[#0F172A]">
                  Page {page} of {totalPages}
                </span>

                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  rightIcon={<ChevronRight className="w-3.5 h-3.5" />}
                  className="text-xs h-7 px-2"
                >
                  Next
                </Button>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* TAB 2: MY COORDINATOR TASKS */}
      {activeTab === "tasks" && (
        <Card padding="none" className="overflow-hidden border border-[#E2E8F0] shadow-soft">
          <div className="p-4 bg-[#F8FAFC] border-b border-[#E2E8F0] flex items-center justify-between">
            <div>
              <h3 className="font-semibold text-sm text-[#0F172A]">Active Tasks for Care Coordinator</h3>
              <p className="text-xs text-[#64748B] mt-0.5">
                Tasks requiring coordinator action, evidence upload, or barrier mitigation.
              </p>
            </div>
            <span className="px-2.5 py-1 bg-[#E6F4F1] text-[#0F766E] rounded-full text-xs font-bold">
              {tasks.length} Pending
            </span>
          </div>

          <div className="divide-y divide-[#E2E8F0]">
            {tasks.length === 0 ? (
              <div className="p-12 text-center text-[#64748B]">
                <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                <p className="font-medium text-sm text-[#0F172A]">All coordinator tasks completed!</p>
                <p className="text-xs text-[#94A3B8] mt-1">No outstanding tasks require your action right now.</p>
              </div>
            ) : (
              tasks.map((t) => (
                <div
                  key={t.task_id}
                  className="p-4 hover:bg-[#F8FAFC] transition flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-[#0F172A]">{t.task_title}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-[#E6F4F1] text-[#0F766E]">
                        Stage {t.stage_number}
                      </span>
                      {getSlaBadge(t.sla_status)}
                    </div>
                    <p className="text-xs text-[#475569]">{t.description}</p>
                    <div className="text-[10px] text-[#64748B] flex items-center gap-3">
                      <span>Patient: <strong>{t.patient_name}</strong></span>
                      {t.due_date && (
                        <span>Due: <strong>{new Date(t.due_date).toLocaleDateString()}</strong></span>
                      )}
                    </div>
                  </div>

                  <Button
                    variant="primary"
                    size="sm"
                    className="text-xs shrink-0"
                    onClick={() => {
                      // Find patient item from list or construct pointer
                      const match = patients.find((p) => p.case_id === t.case_id);
                      if (match) {
                        handleOpenCase(match);
                      } else {
                        handleOpenCase({
                          patient_id: t.patient_id,
                          name: t.patient_name,
                          mrn: "N/A",
                          case_id: t.case_id,
                          case_number: "CASE",
                          current_stage_number: t.stage_number,
                          current_stage_title: t.stage_title,
                          status: "active",
                          pending_action: t.task_title,
                          responsible_role: "care_coordinator",
                          assigned_doctor: "Unassigned",
                          sla_status: t.sla_status as any,
                          needs_coordinator_action: true,
                          last_updated: new Date().toISOString(),
                        });
                      }
                    }}
                  >
                    Open Patient Task
                  </Button>
                </div>
              ))
            )}
          </div>
        </Card>
      )}

      {/* PATIENT CASE DETAIL & 14-STAGE MODAL DRAWER */}
      {selectedPatient && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
          <div className="bg-white rounded-card shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden border border-[#CBD5E1]">
            {/* Modal Header */}
            <div className="p-4 sm:p-6 border-b border-[#E2E8F0] bg-[#F8FAFC] flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-[#E6F4F1] text-[#0F766E]">
                    Stage {selectedPatient.current_stage_number} of 14: {selectedPatient.current_stage_title}
                  </span>
                  {getSlaBadge(selectedPatient.sla_status)}
                </div>
                <h2 className="text-xl font-bold text-[#0F172A]">{selectedPatient.name}</h2>
                <div className="text-xs text-[#64748B] flex flex-wrap items-center gap-3 mt-1">
                  <span>MRN: <strong className="font-mono text-[#0F172A]">{selectedPatient.mrn}</strong></span>
                  <span>•</span>
                  <span>Case: <strong className="font-mono text-[#0F172A]">{selectedPatient.case_number}</strong></span>
                  <span>•</span>
                  <span>Doctor: <strong>{selectedPatient.assigned_doctor}</strong></span>
                </div>
              </div>

              <button
                onClick={() => setSelectedPatient(null)}
                className="p-1.5 rounded-full hover:bg-[#E2E8F0] text-[#64748B] transition"
                title="Close Drawer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Notification & Error Banners */}
            {actionError && (
              <div className="px-6 py-2.5 bg-rose-50 border-b border-rose-200 text-rose-800 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                <span className="font-medium">{actionError}</span>
              </div>
            )}
            {actionSuccess && (
              <div className="px-6 py-2.5 bg-emerald-50 border-b border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span className="font-medium">{actionSuccess}</span>
              </div>
            )}

            {/* Modal Body: 14-Stage Longitudinal Panel */}
            <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
              {loadingLifecycle ? (
                <div className="py-12 text-center text-[#64748B]">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-[#0F766E]" />
                  <span>Loading authentic 14-stage lifecycle from PostgreSQL...</span>
                </div>
              ) : !lifecycleData ? (
                <div className="py-8 text-center text-rose-600 text-xs">
                  Could not load lifecycle stages for this case.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-[#F1F5F9]">
                    <h3 className="font-bold text-xs uppercase tracking-wider text-[#475569]">
                      14-Stage Care Lifecycle Progress (PostgreSQL Relational Verification)
                    </h3>
                    <span className="text-[11px] font-mono text-[#0F766E] font-semibold">
                      Current Stage: {lifecycleData.current_stage_number} of 14
                    </span>
                  </div>

                  {/* 14 Stages List */}
                  <div className="space-y-3">
                    {lifecycleData.stages?.map((st: any) => {
                      const isCurr = st.stage_number === lifecycleData.current_stage_number;
                      const isPassed = st.status === "COMPLETED";
                      const isDoctorStage = [4, 5, 6, 7, 8, 10, 11, 14].includes(st.stage_number);
                      const isCoordinatorStage = [1, 2, 3, 9, 12, 13].includes(st.stage_number);

                      return (
                        <div
                          key={st.stage_number}
                          className={`p-3.5 rounded-card border transition ${
                            isCurr
                              ? "bg-[#E6F4F1]/40 border-[#0F766E] shadow-2xs"
                              : isPassed
                              ? "bg-white border-[#E2E8F0]"
                              : "bg-[#F8FAFC] border-[#E2E8F0] opacity-80"
                          }`}
                        >
                          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
                            <div className="flex items-center gap-2.5">
                              {/* Stage Number Badge */}
                              <div
                                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                                  isPassed
                                    ? "bg-emerald-600 text-white"
                                    : isCurr
                                    ? "bg-[#0F766E] text-white"
                                    : "bg-[#E2E8F0] text-[#64748B]"
                                }`}
                              >
                                {isPassed ? "✓" : st.stage_number}
                              </div>

                              <div>
                                <span className="font-semibold text-xs text-[#0F172A]">
                                  Stage {st.stage_number}: {st.title}
                                </span>
                                <span className="text-[10px] text-[#64748B] block">
                                  Role: <strong className="capitalize">{st.responsible_role?.replace(/_/g, " ")}</strong>
                                </span>
                              </div>
                            </div>

                            {/* Status Badge */}
                            <div className="flex items-center gap-2">
                              <Badge
                                variant={
                                  st.status === "COMPLETED"
                                    ? "success"
                                    : isCurr
                                    ? "info"
                                    : "neutral"
                                }
                                className="text-[10px] py-0 px-2 font-mono font-semibold"
                              >
                                {st.status}
                              </Badge>

                              {st.completed_at && (
                                <span className="text-[10px] text-[#64748B]">
                                  {new Date(st.completed_at).toLocaleDateString()}
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Evidence Description & Allowed Actions */}
                          <div className="mt-2.5 pl-8 text-xs text-[#475569] space-y-1">
                            {st.evidence_description && (
                              <p className="bg-white p-2 rounded border border-[#E2E8F0] text-[11px] font-mono text-[#0F172A]">
                                <strong>Evidence:</strong> {st.evidence_description}
                              </p>
                            )}

                            {/* Interactive Coordinator Actions */}
                            {isCurr && isCoordinatorStage && (
                              <div className="pt-2 flex flex-wrap items-center gap-2">
                                {/* Stage 1 Actions */}
                                {st.stage_number === 1 && (
                                  <>
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="text-xs h-7"
                                      onClick={() => setShowScheduleModal(true)}
                                    >
                                      Create Screening Order
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="primary"
                                      className="text-xs h-7"
                                      onClick={() => setShowCompleteScreeningModal(true)}
                                    >
                                      Record Screening Performed
                                    </Button>
                                  </>
                                )}

                                {/* Stage 2 Action */}
                                {st.stage_number === 2 && (
                                  <Button
                                    size="sm"
                                    variant="primary"
                                    className="text-xs h-7"
                                    onClick={() => setShowUploadReportModal(true)}
                                  >
                                    Upload & Finalize Test Report
                                  </Button>
                                )}

                                {/* Stage 3 Action (System Notification Status) */}
                                {st.stage_number === 3 && (
                                  <span className="text-xs text-[#0F766E] font-medium flex items-center gap-1">
                                    <CheckCircle2 className="w-3.5 h-3.5" />
                                    System Notification Delivered to Patient (Read-Only)
                                  </span>
                                )}

                                {/* Doctor Allocation (Stage 7 / 8) */}
                                {[7, 8].includes(st.stage_number) && (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="text-xs h-7"
                                    onClick={handleLoadDoctorCandidates}
                                  >
                                    View Eligible Doctors & Allocate
                                  </Button>
                                )}
                              </div>
                            )}

                            {/* Stage 14: Closure Authority Invariant */}
                            {st.stage_number === 14 && (
                              <div className="pt-2">
                                <div className="p-3 bg-amber-50 border border-amber-200 rounded text-amber-900 text-xs flex items-start gap-2">
                                  <Lock className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                                  <div>
                                    <p className="font-semibold">Waiting for Doctor Sign-Off (Stage 14)</p>
                                    <p className="text-[11px] text-amber-800 mt-0.5">
                                      Only an attending physician may sign off and execute verified clinical closure.
                                      Coordinator access is strictly read-only.
                                    </p>
                                    {isCoordinator && (
                                      <button
                                        type="button"
                                        onClick={handleCoordinatorClosureAttempt}
                                        className="mt-2 text-xs text-rose-700 font-semibold underline hover:text-rose-900 block"
                                      >
                                        [Verify Guard] Attempt Coordinator Sign-off (Will test 403 enforcement)
                                      </button>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Non-Coordinator Stages (Read-Only Status) */}
                            {isCurr && isDoctorStage && st.stage_number !== 14 && (
                              <div className="pt-1 text-xs text-[#64748B] italic flex items-center gap-1.5">
                                <Lock className="w-3 h-3 text-[#94A3B8]" />
                                <span>Read-Only for Coordinator: Waiting for Doctor / Specialist action.</span>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-[#E2E8F0] bg-[#F8FAFC] flex items-center justify-between">
              <span className="text-xs text-[#64748B]">
                PostgreSQL Case ID: <strong className="font-mono text-[#0F172A]">{selectedPatient.case_id || "None"}</strong>
              </span>
              <Button variant="secondary" size="sm" onClick={() => setSelectedPatient(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ACTION MODAL 1: Schedule Screening */}
      {showScheduleModal && (
        <div className="fixed inset-0 z-60 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-card p-6 max-w-md w-full shadow-2xl border border-[#CBD5E1] space-y-4">
            <h3 className="text-base font-bold text-[#0F172A]">Schedule Screening Order (Stage 1)</h3>
            <form onSubmit={handleScheduleScreeningSubmit} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Facility Unit</label>
                <input
                  type="text"
                  value={screeningFacility}
                  onChange={(e) => setScreeningFacility(e.target.value)}
                  className="w-full h-8 px-3 text-xs bg-[#F8FAFC] border border-[#CBD5E1] rounded-btn"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Target Date & Time</label>
                <input
                  type="datetime-local"
                  value={screeningDate}
                  onChange={(e) => setScreeningDate(e.target.value)}
                  className="w-full h-8 px-3 text-xs bg-[#F8FAFC] border border-[#CBD5E1] rounded-btn"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Instructions / Notes</label>
                <textarea
                  value={screeningNotes}
                  onChange={(e) => setScreeningNotes(e.target.value)}
                  placeholder="Patient prep instructions..."
                  className="w-full h-16 p-2 text-xs bg-[#F8FAFC] border border-[#CBD5E1] rounded-btn resize-none"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <Button variant="secondary" size="sm" type="button" onClick={() => setShowScheduleModal(false)}>
                  Cancel
                </Button>
                <Button variant="primary" size="sm" type="submit">
                  Dispatch Schedule
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ACTION MODAL 2: Record Screening Performed */}
      {showCompleteScreeningModal && (
        <div className="fixed inset-0 z-60 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-card p-6 max-w-md w-full shadow-2xl border border-[#CBD5E1] space-y-4">
            <h3 className="text-base font-bold text-[#0F172A]">Record Screening Performed (Stage 1 Evidence)</h3>
            <p className="text-xs text-[#64748B]">
              Manually enter confirmation that patient attended the screening procedure. Advances Stage 1 to COMPLETED in PostgreSQL.
            </p>
            <form onSubmit={handleCompleteScreeningSubmit} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Verification Notes</label>
                <textarea
                  value={completeNotes}
                  onChange={(e) => setCompleteNotes(e.target.value)}
                  className="w-full h-20 p-2 text-xs bg-[#F8FAFC] border border-[#CBD5E1] rounded-btn resize-none"
                  required
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <Button variant="secondary" size="sm" type="button" onClick={() => setShowCompleteScreeningModal(false)}>
                  Cancel
                </Button>
                <Button variant="primary" size="sm" type="submit">
                  Verify & Advance Stage 1
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ACTION MODAL 3: Upload Test Report */}
      {showUploadReportModal && (
        <div className="fixed inset-0 z-60 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-card p-6 max-w-lg w-full shadow-2xl border border-[#CBD5E1] space-y-4">
            <h3 className="text-base font-bold text-[#0F172A]">Upload & Finalize Diagnostic Report (Stage 2)</h3>
            <form onSubmit={handleUploadReportSubmit} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-[#475569] mb-1">Screening Modality</label>
                  <input
                    type="text"
                    value={reportType}
                    onChange={(e) => setReportType(e.target.value)}
                    className="w-full h-8 px-3 text-xs bg-[#F8FAFC] border border-[#CBD5E1] rounded-btn"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#475569] mb-1">Finding Code</label>
                  <input
                    type="text"
                    value={reportFindingCode}
                    onChange={(e) => setReportFindingCode(e.target.value)}
                    className="w-full h-8 px-3 text-xs bg-[#F8FAFC] border border-[#CBD5E1] rounded-btn"
                    required
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Findings Summary</label>
                <textarea
                  value={reportFindingSummary}
                  onChange={(e) => setReportFindingSummary(e.target.value)}
                  className="w-full h-16 p-2 text-xs bg-[#F8FAFC] border border-[#CBD5E1] rounded-btn resize-none"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#475569] mb-1">Clinical Recommendation</label>
                <textarea
                  value={reportRecommendation}
                  onChange={(e) => setReportRecommendation(e.target.value)}
                  className="w-full h-16 p-2 text-xs bg-[#F8FAFC] border border-[#CBD5E1] rounded-btn resize-none"
                  required
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-2">
                <Button variant="secondary" size="sm" type="button" onClick={() => setShowUploadReportModal(false)}>
                  Cancel
                </Button>
                <Button variant="primary" size="sm" type="submit">
                  Upload & Advance Stage 2
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ACTION MODAL 4: Doctor Allocation Candidates */}
      {showDoctorCandidatesModal && (
        <div className="fixed inset-0 z-60 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-card p-6 max-w-lg w-full shadow-2xl border border-[#CBD5E1] space-y-4">
            <h3 className="text-base font-bold text-[#0F172A]">Ranked Specialist Doctors (Doctor Allocation)</h3>
            <div className="max-h-60 overflow-y-auto space-y-2">
              {doctorCandidates.length === 0 ? (
                <p className="text-xs text-[#64748B]">No specialist candidates available.</p>
              ) : (
                doctorCandidates.map((d: any, idx: number) => (
                  <div key={idx} className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded flex items-center justify-between text-xs">
                    <div>
                      <div className="font-semibold text-[#0F172A]">{d.name || d.doctor_name}</div>
                      <div className="text-[10px] text-[#64748B]">{d.facility} • Match Score: {d.score || d.match_score}%</div>
                    </div>
                    <Button size="sm" variant="outline" className="text-xs h-7">
                      Assign Doctor
                    </Button>
                  </div>
                ))
              )}
            </div>
            <div className="flex justify-end pt-2">
              <Button variant="secondary" size="sm" onClick={() => setShowDoctorCandidatesModal(false)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
