"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  FolderGit2,
  Calendar,
  Share2,
  Clock,
  CheckCircle2,
  AlertCircle,
  ArrowLeft,
  UserCheck,
  Stethoscope,
  Plus,
  MessageSquare,
  FileText,
  Activity,
  X,
} from "lucide-react";
import {
  fetchCaseDetail,
  fetchCaseEvents,
  fetchAppointments,
  fetchReferrals,
  bookAppointment,
  cancelAppointment,
} from "../../../services/api";
import { CareCase, Appointment, Referral, CaseTimelineEvent } from "../../../types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { ReportUploadModal } from "@/components/ReportUploadModal";

export default function CaseDetailPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params?.caseId as string;

  const [careCase, setCareCase] = useState<CareCase | null>(null);
  const [events, setEvents] = useState<CaseTimelineEvent[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);

  // Booking Modal
  const [isBookModalOpen, setIsBookModalOpen] = useState(false);
  const [bookDateTime, setBookDateTime] = useState("");
  const [bookType, setBookType] = useState("diagnostic_biopsy");
  const [bookFacility, setBookFacility] = useState("Clinic A - Women's Specialty Breast Center");
  const [bookProvider, setBookProvider] = useState("Dr. Arjun Menon, MD");
  const [bookNotes, setBookNotes] = useState("");
  const [bookSubmitting, setBookSubmitting] = useState(false);

  // Cancellation Modal
  const [cancelModalAppt, setCancelModalAppt] = useState<Appointment | null>(null);
  const [cancellationReason, setCancellationReason] = useState("");
  const [cancelNotes, setCancelNotes] = useState("");
  const [cancelSubmitting, setCancelSubmitting] = useState(false);

  // Upload Report Modal
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);

  const loadData = async () => {
    if (!caseId) return;
    try {
      if (!careCase) {
        setLoading(true);
      }
      const [caseRes, eventsRes, apptsRes, refsRes] = await Promise.all([
        fetchCaseDetail(caseId).catch(() => null),
        fetchCaseEvents(caseId).catch(() => []),
        fetchAppointments(undefined, caseId).catch(() => []),
        fetchReferrals(undefined, caseId).catch(() => []),
      ]);

      if (caseRes) {
        setCareCase(caseRes);
      }
      setEvents(eventsRes || []);
      setAppointments(apptsRes || []);
      setReferrals(refsRes || []);
    } catch (err) {
      console.error("Failed to load case detail:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [caseId]);

  const handleBookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!careCase || !bookDateTime) return;

    setBookSubmitting(true);
    try {
      await bookAppointment({
        case_id: careCase.id,
        patient_id: careCase.patient_id,
        facility: bookFacility,
        provider_name: bookProvider,
        appointment_type: bookType,
        scheduled_time: new Date(bookDateTime).toISOString(),
        notes: bookNotes,
      });
      setIsBookModalOpen(false);
      setBookNotes("");
      await loadData();
    } catch (err: any) {
      alert("Booking failed: " + (err.message || String(err)));
    } finally {
      setBookSubmitting(false);
    }
  };

  const handleCancelSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cancellationReason.trim()) {
      alert("A mandatory cancellation reason is required.");
      return;
    }
    if (!cancelModalAppt) return;

    setCancelSubmitting(true);
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
      alert("Cancellation failed: " + (err.message || String(err)));
    } finally {
      setCancelSubmitting(false);
    }
  };

  if (loading && !careCase) {
    return (
      <div className="min-h-[50vh] flex flex-col items-center justify-center gap-3">
        <div className="w-8 h-8 border-2 border-[#0F766E]/30 border-t-[#0F766E] rounded-full animate-spin" />
        <p className="text-sm text-[#475569] font-medium">Loading Case Detail...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-12">
      {/* Top Header & Navigation */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <button
            onClick={() => router.back()}
            className="inline-flex items-center gap-1.5 text-xs text-[#475569] hover:text-[#0F172A] font-medium mb-2 transition focus:outline-none focus:underline"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Cases</span>
          </button>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-semibold text-[#0F172A] tracking-tight">
              {careCase?.patient_name || "Patient Care Case"}
            </h1>
            <Badge
              variant={
                careCase?.status === "closed" && events.length > 0 && referrals.length > 0
                  ? "success"
                  : careCase?.status === "closed" || careCase?.status === "recovering"
                  ? "warning"
                  : "info"
              }
            >
              {careCase?.status === "closed" && (events.length === 0 || referrals.length === 0)
                ? "closure pending evidence"
                : careCase?.status?.replace(/_/g, " ") || "Active"}
            </Badge>
          </div>
          <p className="text-xs text-[#475569] mt-1">
            Case Number: <span className="font-medium text-[#0F172A]">{careCase?.case_number}</span> • Target SLA:{" "}
            {careCase?.sla_deadline ? new Date(careCase.sla_deadline).toLocaleDateString() : "Active"}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link href={`/chat?caseId=${careCase?.id}`}>
            <Button variant="primary" icon={<MessageSquare className="w-4 h-4" />}>
              Open AI Chat for Case
            </Button>
          </Link>
          <Button
            variant="secondary"
            onClick={() => setIsBookModalOpen(true)}
            icon={<Plus className="w-4 h-4 text-[#0F766E]" />}
          >
            Book Visit
          </Button>
          <Button
            variant="secondary"
            onClick={() => setIsUploadModalOpen(true)}
            icon={<FileText className="w-4 h-4 text-[#0F766E]" />}
          >
            Upload Report
          </Button>
        </div>
      </div>

      {/* Case Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-5">
          <span className="text-xs font-medium text-[#475569] uppercase tracking-wider block mb-1">
            Screening Finding
          </span>
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold text-[#0F172A]">
              {careCase?.finding_code || "BI-RADS 4"}
            </span>
            <Badge variant="error">{careCase?.priority || "Urgent"}</Badge>
          </div>
          <p className="text-xs text-[#475569] mt-2 leading-relaxed">
            {careCase?.finding_summary || "Tissue biopsy indicated within 14 days."}
          </p>
        </Card>

        <Card className="p-5">
          <span className="text-xs font-medium text-[#475569] uppercase tracking-wider block mb-1">
            Clinical Ownership
          </span>
          <div className="flex items-center gap-3 mt-1">
            <div className="w-10 h-10 rounded-btn bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center font-bold text-xs shrink-0">
              <Stethoscope className="w-5 h-5" />
            </div>
            <div>
              <span className="font-semibold text-xs text-[#0F172A] block">Dr. Arjun Menon, MD</span>
              <span className="text-xs text-[#475569] block">Attending Breast Specialist</span>
            </div>
          </div>
          <div className="mt-3 pt-2.5 border-t border-[#E2E8F0] flex justify-between text-xs">
            <span className="text-[#475569]">Coordinator:</span>
            <span className="font-medium text-[#0F766E]">Priya Nair, RN</span>
          </div>
        </Card>

        <Card className="p-5">
          <span className="text-xs font-medium text-[#475569] uppercase tracking-wider block mb-1">
            Inferred Barriers & Recovery
          </span>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs font-semibold text-[#0F172A]">
              {careCase?.inferred_barriers?.join(", ") || "Transportation (Resolved)"}
            </span>
          </div>
          <p className="text-xs text-[#475569] mt-2">
            Recovery attempts: <span className="font-medium text-[#0F172A]">{careCase?.recovery_attempts || 1}</span> • Strategy: Daughter availability alignment.
          </p>
        </Card>
      </div>

      {/* Main Grid: Longitudinal Timeline & Clinical Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (8 cols): Case Event Timeline */}
        <Card className="lg:col-span-8 p-6">
          <div className="flex items-center justify-between pb-4 border-b border-[#E2E8F0] mb-6">
            <div>
              <h2 className="font-semibold text-base text-[#0F172A]">
                Longitudinal Timeline & Case Events
              </h2>
              <p className="text-xs text-[#475569]">
                Complete verifiable audit trail of AI outreach, clinical milestones, and recovery actions
              </p>
            </div>
            <Badge variant="info">{events.length} Events Logged</Badge>
          </div>

          <div className="space-y-6 relative before:absolute before:inset-0 before:left-4 before:w-0.5 before:bg-[#E2E8F0]">
            {events.map((evt, idx) => (
              <div key={evt.event_id || idx} className="relative flex items-start gap-4 pl-8">
                <span className="absolute left-2.5 top-1.5 w-3 h-3 rounded-full bg-[#0F766E] ring-4 ring-white" />
                <div className="flex-1 p-4 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-[#0F172A] capitalize">
                      {evt.event_type.replace("_", " ")}
                    </span>
                    <span className="text-[11px] text-[#475569]">
                      {evt.timestamp ? new Date(evt.timestamp).toLocaleString() : "Recent"}
                    </span>
                  </div>
                  <p className="text-[#475569] leading-relaxed text-xs">{evt.description}</p>
                </div>
              </div>
            ))}

            {events.length === 0 && (
              <div className="text-center py-8 text-xs text-[#475569]">
                No timeline events recorded yet.
              </div>
            )}
          </div>
        </Card>

        {/* Right Column (4 cols): Associated Appointments & Referrals */}
        <div className="lg:col-span-4 space-y-6">
          {/* Appointments */}
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-sm text-[#0F172A]">Case Appointments</h3>
              <button
                onClick={() => setIsBookModalOpen(true)}
                className="text-xs text-[#0F766E] hover:text-[#115E59] font-medium flex items-center gap-1 focus:outline-none focus:underline"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Book</span>
              </button>
            </div>

            <div className="space-y-3">
              {appointments.map((a) => (
                <div
                  key={a.id}
                  className="p-3.5 rounded-card border border-[#E2E8F0] bg-[#F8FAFC] text-xs"
                >
                  <div className="flex justify-between items-start">
                    <span className="font-medium text-[#0F172A] capitalize">
                      {a.appointment_type.replace("_", " ")}
                    </span>
                    <Badge
                      variant={
                        ["booked", "confirmed", "CONFIRMED", "COMPLETED", "completed", "attended"].includes(a.status)
                          ? "success"
                          : ["cancelled", "CANCELLED"].includes(a.status)
                          ? "error"
                          : "neutral"
                      }
                    >
                      {a.status}
                    </Badge>
                  </div>
                  <p className="text-xs text-[#475569] mt-1">
                    {a.scheduled_time
                      ? new Date(a.scheduled_time).toLocaleString("en-US", {
                          month: "short",
                          day: "numeric",
                          hour: "numeric",
                          minute: "2-digit",
                        })
                      : "Unscheduled"}
                  </p>
                  <p className="text-[11px] text-[#475569]">{a.facility}</p>

                  {a.status === "booked" && (
                    <div className="mt-2.5 pt-2 border-t border-[#E2E8F0] flex justify-end">
                      <button
                        onClick={() => setCancelModalAppt(a)}
                        className="text-xs text-[#B91C1C] hover:underline font-medium"
                      >
                        Cancel Visit
                      </button>
                    </div>
                  )}
                </div>
              ))}

              {appointments.length === 0 && (
                <p className="text-xs text-[#475569] text-center py-4">No appointments found.</p>
              )}
            </div>
          </Card>

          {/* Referrals */}
          <Card className="p-6">
            <h3 className="font-semibold text-sm text-[#0F172A] mb-3">Referrals</h3>
            <div className="space-y-3">
              {referrals.map((r) => (
                <div
                  key={r.id}
                  className="p-3 rounded-card border border-[#E2E8F0] bg-[#F8FAFC] text-xs"
                >
                  <div className="flex justify-between items-start">
                    <span className="font-medium text-[#0F172A]">{r.specialty}</span>
                    <Badge variant="success">{r.status}</Badge>
                  </div>
                  <p className="text-xs text-[#475569] mt-1">{r.target_facility}</p>
                </div>
              ))}

              {referrals.length === 0 && (
                <p className="text-xs text-[#475569] text-center py-4">No referrals found.</p>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* Book Appointment Modal */}
      <Modal
        isOpen={isBookModalOpen && !!careCase}
        onClose={() => setIsBookModalOpen(false)}
        title="Schedule Diagnostic Visit"
        description={`Patient: ${careCase?.patient_name}`}
        size="md"
      >
        <form onSubmit={handleBookSubmit} className="space-y-4">
          <Input
            label="Healthcare Facility"
            type="text"
            value={bookFacility}
            onChange={(e) => setBookFacility(e.target.value)}
            required
          />

          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Attending Provider"
              type="text"
              value={bookProvider}
              onChange={(e) => setBookProvider(e.target.value)}
              required
            />
            <div>
              <label htmlFor="bookTypeSelect" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
                Appointment Type
              </label>
              <select
                id="bookTypeSelect"
                value={bookType}
                onChange={(e) => setBookType(e.target.value)}
                className="w-full h-11 px-3 py-2 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2"
              >
                <option value="diagnostic_biopsy">Diagnostic Biopsy</option>
                <option value="ultrasound_evaluation">Ultrasound Evaluation</option>
                <option value="colonoscopy">Diagnostic Colonoscopy</option>
                <option value="clinical_consultation">Clinical Consultation</option>
              </select>
            </div>
          </div>

          <Input
            label="Scheduled Date & Time"
            type="datetime-local"
            value={bookDateTime}
            onChange={(e) => setBookDateTime(e.target.value)}
            required
          />

          <div>
            <label htmlFor="bookNotesTextarea" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
              Clinical Notes (Optional)
            </label>
            <textarea
              id="bookNotesTextarea"
              value={bookNotes}
              onChange={(e) => setBookNotes(e.target.value)}
              placeholder="Clinical notes..."
              className="w-full p-3 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] h-20 focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#E2E8F0]">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsBookModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={bookSubmitting}
            >
              {bookSubmitting ? "Booking..." : "Confirm Booking"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Cancellation Modal */}
      <Modal
        isOpen={!!cancelModalAppt}
        onClose={() => setCancelModalAppt(null)}
        title="Cancel Appointment"
        description={`Patient: ${cancelModalAppt?.patient_name}`}
        size="md"
      >
        <form onSubmit={handleCancelSubmit} className="space-y-4">
          <div>
            <label htmlFor="cancelReasonSelect" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
              Mandatory Cancellation Reason <span className="text-[#B91C1C]">*</span>
            </label>
            <select
              id="cancelReasonSelect"
              value={cancellationReason}
              onChange={(e) => setCancellationReason(e.target.value)}
              className="w-full h-11 px-3 py-2 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2"
              required
            >
              <option value="">-- Select reason --</option>
              <option value="Emergency clinical conflict">Emergency clinical conflict</option>
              <option value="Procedure suite maintenance">Procedure suite maintenance</option>
              <option value="Patient requested alternative date">Patient requested alternative date</option>
              <option value="Clinical pre-clearance pending">Clinical pre-clearance pending</option>
            </select>
          </div>

          <div>
            <label htmlFor="cancelNotesTextarea" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
              Notes
            </label>
            <textarea
              id="cancelNotesTextarea"
              value={cancelNotes}
              onChange={(e) => setCancelNotes(e.target.value)}
              placeholder="Notes..."
              className="w-full p-3 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] h-20 focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-3 border-t border-[#E2E8F0]">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setCancelModalAppt(null)}
            >
              Keep Visit
            </Button>
            <Button
              type="submit"
              variant="danger"
              disabled={cancelSubmitting}
            >
              {cancelSubmitting ? "Processing..." : "Confirm Cancellation"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Coordinator Report Upload & Finalization Modal */}
      <ReportUploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        caseId={careCase?.id || caseId}
        patientName={careCase?.patient_name || "Patient"}
        screeningOrderId={careCase?.screening_order_id || "ORD-SCR-001"}
        screeningType={careCase?.screening_type || "Mammogram"}
        onReportFinalized={async () => {
          setIsUploadModalOpen(false);
          await loadData();
        }}
      />
    </div>
  );
}
