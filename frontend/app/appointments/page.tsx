"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Calendar,
  Search,
  Filter,
  Clock,
  MapPin,
  User,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RotateCcw,
  MessageSquare,
  Plus,
  X,
  Stethoscope,
  ChevronRight,
  RefreshCw,
} from "lucide-react";
import {
  fetchAppointments,
  fetchCases,
  bookAppointment,
  cancelAppointment,
} from "../../services/api";
import { Appointment, CareCase } from "../../types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [cases, setCases] = useState<CareCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Booking Modal
  const [isBookModalOpen, setIsBookModalOpen] = useState(false);
  const [bookCaseId, setBookCaseId] = useState("");
  const [bookPatientId, setBookPatientId] = useState("");
  const [bookFacility, setBookFacility] = useState("Clinic A - Women's Specialty Breast Center");
  const [bookProvider, setBookProvider] = useState("Dr. Aris Thorne, MD");
  const [bookType, setBookType] = useState("diagnostic_biopsy");
  const [bookDateTime, setBookDateTime] = useState("");
  const [bookNotes, setBookNotes] = useState("");
  const [bookSubmitting, setBookSubmitting] = useState(false);

  // Cancellation Modal
  const [cancelModalAppt, setCancelModalAppt] = useState<Appointment | null>(null);
  const [cancellationReason, setCancellationReason] = useState("");
  const [cancelNotes, setCancelNotes] = useState("");
  const [cancelSubmitting, setCancelSubmitting] = useState(false);
  const [cancelError, setCancelError] = useState("");

  const loadData = async () => {
    try {
      setLoading(true);
      const [apptsRes, casesRes] = await Promise.all([
        fetchAppointments(),
        fetchCases(),
      ]);
      setAppointments(apptsRes || []);
      setCases(casesRes || []);

      if (casesRes && casesRes.length > 0) {
        setBookCaseId(casesRes[0].id);
        setBookPatientId(casesRes[0].patient_id);
      }
    } catch (err) {
      console.error("Failed to load appointments data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleBookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bookCaseId || !bookPatientId || !bookDateTime) {
      alert("Please fill in all required fields.");
      return;
    }

    setBookSubmitting(true);
    try {
      await bookAppointment({
        case_id: bookCaseId,
        patient_id: bookPatientId,
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
      alert("Failed to book appointment: " + (err.message || String(err)));
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

  const filtered = appointments.filter((a) => {
    const matchesSearch =
      a.patient_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.facility.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.provider_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.case_number.toLowerCase().includes(searchQuery.toLowerCase());

    if (statusFilter === "all") return matchesSearch;
    return matchesSearch && a.status === statusFilter;
  });

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-semibold mb-2">
            <Calendar className="w-3.5 h-3.5" />
            Scheduling & Attendance Coordination
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-[#0F172A] tracking-tight">
            Appointment Management
          </h1>
          <p className="text-sm text-[#475569] mt-1">
            Tracking diagnostic visits, verified attendance, reasons for cancellation, and proactive recovery.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            onClick={() => setIsBookModalOpen(true)}
            icon={<Plus className="w-4 h-4" />}
          >
            Book New Appointment
          </Button>
          <Button
            variant="secondary"
            onClick={loadData}
            disabled={loading}
            icon={<RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />}
            aria-label="Refresh appointments"
          />
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-2 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn px-3.5 py-2 flex-1 max-w-md focus-within:ring-2 focus-within:ring-[#0F766E]">
          <Search className="w-4 h-4 text-[#475569]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by patient, clinic, doctor, or case..."
            className="bg-transparent text-sm text-[#0F172A] placeholder-[#475569]/60 focus:outline-none w-full"
            aria-label="Search appointments"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto text-xs">
          <span className="text-[#475569] text-xs font-semibold uppercase tracking-wider mr-1">
            Status:
          </span>
          {[
            { id: "all", label: "All Visits" },
            { id: "booked", label: "Booked" },
            { id: "attended", label: "Attended" },
            { id: "no_show", label: "No-Shows" },
            { id: "cancelled", label: "Cancelled" },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setStatusFilter(f.id)}
              className={`h-9 px-3.5 rounded-btn font-medium text-xs transition cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2 ${
                statusFilter === f.id
                  ? "bg-[#0F766E] text-white"
                  : "bg-white text-[#475569] hover:text-[#0F172A] border border-[#E2E8F0]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </Card>

      {/* Appointments List */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((a) => (
          <Card key={a.id} className="p-5 flex flex-col justify-between">
            <div>
              <div className="flex items-start justify-between gap-2 mb-3">
                <div>
                  <h3 className="font-semibold text-sm text-[#0F172A]">{a.patient_name}</h3>
                  <span className="text-xs text-[#475569]">{a.case_number}</span>
                </div>
                <Badge
                  variant={
                    a.status === "attended" || a.status === "booked"
                      ? "success"
                      : a.status === "cancelled" || a.status === "no_show"
                      ? "error"
                      : "neutral"
                  }
                >
                  {a.status.replace("_", " ")}
                </Badge>
              </div>

              <div className="space-y-2 text-xs text-[#475569] my-3">
                <div className="flex items-center gap-2">
                  <Calendar className="w-3.5 h-3.5 text-[#0F766E] shrink-0" />
                  <span className="font-medium text-[#0F172A]">
                    {a.scheduled_time
                      ? new Date(a.scheduled_time).toLocaleString("en-US", {
                          weekday: "short",
                          month: "short",
                          day: "numeric",
                          hour: "numeric",
                          minute: "2-digit",
                        })
                      : "Unscheduled"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <MapPin className="w-3.5 h-3.5 text-[#475569] shrink-0" />
                  <span className="truncate">{a.facility}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Stethoscope className="w-3.5 h-3.5 text-[#475569] shrink-0" />
                  <span className="truncate">{a.provider_name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Clock className="w-3.5 h-3.5 text-[#475569] shrink-0" />
                  <span className="capitalize">{a.appointment_type.replace("_", " ")}</span>
                </div>
              </div>

              {a.cancellation_reason && (
                <div className="mt-2 p-2.5 rounded-card bg-rose-50 border border-rose-200 text-xs text-[#B91C1C]">
                  <strong>Reason:</strong> {a.cancellation_reason}
                </div>
              )}
            </div>

            <div className="pt-3 border-t border-[#E2E8F0] flex items-center justify-between gap-2 mt-3">
              <Link
                href={`/cases/${a.case_id}`}
                className="text-xs text-[#475569] hover:text-[#0F172A] font-medium focus:outline-none focus:underline"
              >
                Case Detail
              </Link>
              {a.status === "booked" && (
                <button
                  onClick={() => setCancelModalAppt(a)}
                  className="text-xs text-[#B91C1C] hover:underline font-medium"
                >
                  Cancel Visit
                </button>
              )}
            </div>
          </Card>
        ))}

        {filtered.length === 0 && !loading && (
          <div className="col-span-full py-12 text-center text-sm text-[#475569]">
            No appointments match the specified criteria.
          </div>
        )}
      </div>

      {/* Book Appointment Modal */}
      <Modal
        isOpen={isBookModalOpen}
        onClose={() => setIsBookModalOpen(false)}
        title="Schedule Diagnostic Visit"
        description="Book a new procedure or specialist evaluation"
        size="md"
      >
        <form onSubmit={handleBookSubmit} className="space-y-4">
          <div>
            <label htmlFor="bookCaseSelect" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
              Select Care Case <span className="text-[#B91C1C]">*</span>
            </label>
            <select
              id="bookCaseSelect"
              value={bookCaseId}
              onChange={(e) => {
                const targetId = e.target.value;
                setBookCaseId(targetId);
                const found = cases.find((c) => c.id === targetId);
                if (found) setBookPatientId(found.patient_id);
              }}
              className="w-full h-11 px-3 py-2 bg-white border border-[#E2E8F0] rounded-btn text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2"
              required
            >
              {cases.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.patient_name} — {c.case_number} ({c.finding_code})
                </option>
              ))}
            </select>
          </div>

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
              <label htmlFor="modalBookTypeSelect" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
                Appointment Type
              </label>
              <select
                id="modalBookTypeSelect"
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
            <label htmlFor="modalBookNotes" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
              Clinical Notes (Optional)
            </label>
            <textarea
              id="modalBookNotes"
              value={bookNotes}
              onChange={(e) => setBookNotes(e.target.value)}
              placeholder="Clinical instructions or notes..."
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
        onClose={() => {
          setCancelModalAppt(null);
          setCancelError("");
        }}
        title="Cancel Appointment"
        description={`Patient: ${cancelModalAppt?.patient_name}`}
        size="md"
      >
        <form onSubmit={handleCancelSubmit} className="space-y-4">
          {cancelError && (
            <div className="p-3 rounded-card bg-rose-50 border border-rose-200 text-xs text-[#B91C1C]">
              {cancelError}
            </div>
          )}

          <div>
            <label htmlFor="cancelApptReason" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
              Mandatory Cancellation Reason <span className="text-[#B91C1C]">*</span>
            </label>
            <select
              id="cancelApptReason"
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
            <label htmlFor="cancelApptNotes" className="block text-xs font-semibold text-[#0F172A] mb-1.5">
              Notes
            </label>
            <textarea
              id="cancelApptNotes"
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
              onClick={() => {
                setCancelModalAppt(null);
                setCancelError("");
              }}
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
    </div>
  );
}
