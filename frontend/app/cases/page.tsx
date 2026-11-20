"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  FolderGit2,
  Search,
  Filter,
  Clock,
  User,
  Calendar,
  Share2,
  AlertTriangle,
  CheckCircle2,
  ShieldCheck,
  ChevronRight,
  X,
  MessageSquare,
  Activity,
  FileText,
  RotateCcw,
  ArrowRight,
  Stethoscope,
} from "lucide-react";
import { fetchCases, fetchCaseEvents } from "../../services/api";
import { CareCase, CaseTimelineEvent } from "../../types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export default function CasesPage() {
  const [cases, setCases] = useState<CareCase[]>([]);
  const [selectedCase, setSelectedCase] = useState<CareCase | null>(null);
  const [timelineEvents, setTimelineEvents] = useState<CaseTimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    async function loadCases() {
      try {
        setLoading(true);
        const data = await fetchCases();
        setCases(data || []);
        if (data && data.length > 0) {
          selectCase(data[0]);
        }
      } catch (err) {
        console.error("Failed to load cases:", err);
      } finally {
        setLoading(false);
      }
    }
    loadCases();
  }, []);

  const selectCase = async (c: CareCase) => {
    setSelectedCase(c);
    setEventsLoading(true);
    try {
      const events = await fetchCaseEvents(c.id);
      setTimelineEvents(events || []);
    } catch (err) {
      console.error("Error loading events for case:", err);
      setTimelineEvents([]);
    } finally {
      setEventsLoading(false);
    }
  };

  const filteredCases = cases.filter((c) => {
    const matchesSearch =
      c.patient_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.case_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.finding_code.toLowerCase().includes(searchQuery.toLowerCase());

    if (statusFilter === "all") return matchesSearch;
    if (statusFilter === "warning")
      return matchesSearch && (c.sla_status === "warning" || c.sla_status === "breached");
    if (statusFilter === "recovering") return matchesSearch && c.status === "recovering";
    if (statusFilter === "closed")
      return matchesSearch && ["closed", "care_completed"].includes(c.status);
    return matchesSearch && c.status === statusFilter;
  });

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-semibold mb-2">
            <FolderGit2 className="w-3.5 h-3.5" />
            End-to-End Care Pathways
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-[#0F172A] tracking-tight">
            Care Case Management
          </h1>
          <p className="text-sm text-[#475569] mt-1">
            Longitudinal accountability tracking with immutable case timelines and clinical governance.
          </p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-2 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn px-3.5 py-2 flex-1 max-w-md focus-within:ring-2 focus-within:ring-[#0F766E] focus-within:ring-offset-1">
          <Search className="w-4 h-4 text-[#475569]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by patient name, case number, or finding..."
            className="bg-transparent text-sm text-[#0F172A] placeholder-[#475569]/60 focus:outline-none w-full"
            aria-label="Search cases"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto text-xs">
          <span className="text-[#475569] text-xs font-semibold uppercase tracking-wider mr-1">
            Status:
          </span>
          {[
            { id: "all", label: "All Cases" },
            { id: "warning", label: "SLA Warning" },
            { id: "recovering", label: "In Recovery" },
            { id: "scheduled", label: "Scheduled" },
            { id: "closed", label: "Resolved" },
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

      {/* 2-Column Layout: Case List (Left) + Timeline Inspector (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Case List Column */}
        <Card className="lg:col-span-7 overflow-hidden">
          <div className="p-4 border-b border-[#E2E8F0] flex items-center justify-between text-xs text-[#475569]">
            <span className="font-semibold text-[#0F172A] uppercase tracking-wider">
              Cases ({filteredCases.length})
            </span>
            <span>Click row to inspect timeline</span>
          </div>

          <div className="divide-y divide-[#E2E8F0] max-h-[calc(100vh-22rem)] overflow-y-auto">
            {filteredCases.map((c) => {
              const isSelected = selectedCase?.id === c.id;
              return (
                <div
                  key={c.id}
                  onClick={() => selectCase(c)}
                  className={`p-4 transition cursor-pointer flex items-center justify-between gap-4 ${
                    isSelected
                      ? "bg-[#E6F4F1]/60 border-l-4 border-l-[#0F766E]"
                      : "hover:bg-[#F8FAFC]"
                  }`}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-sm text-[#0F172A] truncate">
                        {c.patient_name}
                      </span>
                      <span className="text-xs text-[#475569]">• {c.case_number}</span>
                      <Badge
                        variant={
                          c.priority === "urgent" || c.priority === "critical"
                            ? "error"
                            : "info"
                        }
                      >
                        {c.priority}
                      </Badge>
                    </div>

                    <p className="text-xs text-[#475569] truncate">{c.finding_summary}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-[#475569]">
                      <span>
                        Owner: <strong className="text-[#0F172A] font-medium">{c.current_owner}</strong>
                      </span>
                      <span>•</span>
                      <span className="capitalize text-[#0F766E] font-medium">
                        Status: {c.status.replace("_", " ")}
                      </span>
                    </div>
                  </div>

                  <Link
                    href={`/cases/${c.id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="p-2 rounded-btn bg-white border border-[#E2E8F0] text-[#475569] hover:text-[#0F766E] hover:border-[#0F766E] transition shrink-0 focus:outline-none focus:ring-2 focus:ring-[#0F766E]"
                    title="Open Full Case Detail"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Link>
                </div>
              );
            })}

            {filteredCases.length === 0 && (
              <div className="p-12 text-center text-[#475569] text-sm">
                No care cases match the specified filter.
              </div>
            )}
          </div>
        </Card>

        {/* Timeline Inspector Column */}
        <Card className="lg:col-span-5 p-6">
          {selectedCase ? (
            <div className="space-y-6">
              <div className="flex items-start justify-between pb-4 border-b border-[#E2E8F0]">
                <div>
                  <Badge variant="info">Live Timeline Inspector</Badge>
                  <h3 className="text-lg font-semibold text-[#0F172A] mt-2">
                    {selectedCase.patient_name}
                  </h3>
                  <p className="text-xs text-[#475569]">{selectedCase.case_number}</p>
                </div>

                <Link href={`/cases/${selectedCase.id}`}>
                  <Button size="sm" variant="primary">
                    Full Detail
                  </Button>
                </Link>
              </div>

              {/* Finding Snapshot */}
              <div className="p-3.5 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] text-xs space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-[#475569]">Finding:</span>
                  <span className="font-semibold text-[#0F172A]">{selectedCase.finding_code}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#475569]">SLA Deadline:</span>
                  <span className="font-medium text-[#0F766E]">
                    {selectedCase.sla_deadline
                      ? new Date(selectedCase.sla_deadline).toLocaleDateString()
                      : "Active"}
                  </span>
                </div>
              </div>

              {/* Event Stream */}
              <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
                {timelineEvents.map((e, idx) => (
                  <div
                    key={e.event_id || idx}
                    className="p-3.5 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] text-xs"
                  >
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-semibold text-[#0F172A] capitalize">
                        {e.event_type.replace("_", " ")}
                      </span>
                      <span className="text-[11px] text-[#475569]">
                        {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : "Recent"}
                      </span>
                    </div>
                    <p className="text-[#475569] leading-relaxed text-xs">{e.description}</p>
                  </div>
                ))}

                {timelineEvents.length === 0 && !eventsLoading && (
                  <p className="text-xs text-[#475569] text-center py-6">No events recorded yet.</p>
                )}
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-sm text-[#475569]">
              Select a care case to inspect its longitudinal event timeline.
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
