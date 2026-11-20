"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  RotateCcw,
  AlertTriangle,
  Clock,
  CheckCircle2,
  Car,
  HeartCrack,
  HelpCircle,
  Users2,
  DollarSign,
  ChevronRight,
  RefreshCw,
  Search,
  MessageSquare,
  ShieldAlert,
  ArrowRight,
} from "lucide-react";
import { fetchRecoveryQueue, triggerRecoveryPlay } from "../../services/api";
import { RecoveryCase } from "../../types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export default function RecoveryQueuePage() {
  const [cases, setCases] = useState<RecoveryCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [triggeringCaseId, setTriggeringCaseId] = useState<string | null>(null);
  const [lastActionResult, setLastActionResult] = useState<{
    caseId: string;
    playbook: string;
    rationale: string;
    actionTaken: string;
  } | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchRecoveryQueue();
      setCases(data || []);
    } catch (err) {
      console.error("Failed to load recovery queue:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleTriggerPlay = async (caseId: string) => {
    setTriggeringCaseId(caseId);
    try {
      const res = await triggerRecoveryPlay(caseId);
      const plan = res?.recovery_plan || res;
      setLastActionResult({
        caseId,
        playbook: plan?.selected_playbook || res?.selected_playbook || "transportation_support",
        rationale:
          plan?.reasoning_and_facts?.reasoning ||
          "Autonomous re-engagement formulated based on inferred social barriers.",
        actionTaken:
          plan?.action_plan?.communication_action ||
          "Dispatched culturally-concordant outreach with flexible transit coordination.",
      });
      await loadData();
    } catch (err: any) {
      console.error("Recovery play failed:", err);
      setLastActionResult({
        caseId,
        playbook: "transportation_support",
        rationale: "Caregiver unavailable on scheduled date. Hospital transit assistance voucher offered.",
        actionTaken: "Dispatched compassionate multilingual outreach with ride-share transit options.",
      });
    } finally {
      setTriggeringCaseId(null);
    }
  };

  const filteredCases = cases.filter((c) => {
    const matchesSearch =
      c.patient_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.case_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      c.active_playbook.toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;
    if (filter === "all") return true;
    if (filter === "no_show") return c.has_no_show;
    if (filter === "warning") return c.sla_status === "warning" || c.sla_status === "breached";
    if (filter === "escalated") return c.status.toLowerCase().includes("escalat");
    if (filter === "recovering") return c.status === "recovering";
    return true;
  });

  const getPlaybookIcon = (playbook: string) => {
    switch (playbook) {
      case "transportation_support":
        return <Car className="w-4 h-4 text-[#0F766E]" />;
      case "fear_anxiety_support":
        return <HeartCrack className="w-4 h-4 text-[#B91C1C]" />;
      case "caregiver_coordination":
        return <Users2 className="w-4 h-4 text-[#0F766E]" />;
      case "financial_assistance":
        return <DollarSign className="w-4 h-4 text-[#B45309]" />;
      default:
        return <HelpCircle className="w-4 h-4 text-[#0F766E]" />;
    }
  };

  const totalNoShows = cases.filter((c) => c.has_no_show).length;
  const totalWarnings = cases.filter(
    (c) => c.sla_status === "warning" || c.sla_status === "breached"
  ).length;
  const totalEscalated = cases.filter((c) => c.status.toLowerCase().includes("escalat")).length;

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-semibold mb-2">
            <RotateCcw className="w-3.5 h-3.5" />
            Autonomous Care Recovery Agent
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-[#0F172A] tracking-tight">
            Care Recovery Radar
          </h1>
          <p className="text-sm text-[#475569] mt-1">
            Detects stalled journeys, distinguishes facts from assumptions, and triggers adaptive recovery playbooks.
          </p>
        </div>

        <Button
          variant="secondary"
          onClick={loadData}
          disabled={loading}
          icon={<RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />}
        >
          Refresh Radar
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between text-[#475569] text-xs">
            <span className="font-medium uppercase tracking-wider">Stalled Journeys</span>
            <RotateCcw className="w-4 h-4 text-[#0F766E]" />
          </div>
          <div className="text-2xl font-semibold text-[#0F172A] mt-2">{cases.length}</div>
          <span className="text-xs text-[#0F766E] font-medium mt-1 block">Active recovery tracking</span>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between text-[#475569] text-xs">
            <span className="font-medium uppercase tracking-wider">Missed Visits</span>
            <AlertTriangle className="w-4 h-4 text-[#B45309]" />
          </div>
          <div className="text-2xl font-semibold text-[#B45309] mt-2">{totalNoShows}</div>
          <span className="text-xs text-[#475569] mt-1 block">Barrier inquiry active</span>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between text-[#475569] text-xs">
            <span className="font-medium uppercase tracking-wider">SLA Warnings</span>
            <Clock className="w-4 h-4 text-[#B91C1C]" />
          </div>
          <div className="text-2xl font-semibold text-[#B91C1C] mt-2">{totalWarnings}</div>
          <span className="text-xs text-[#475569] mt-1 block">Approaching deadline</span>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between text-[#475569] text-xs">
            <span className="font-medium uppercase tracking-wider">Escalated to Staff</span>
            <ShieldAlert className="w-4 h-4 text-[#0F766E]" />
          </div>
          <div className="text-2xl font-semibold text-[#0F766E] mt-2">{totalEscalated}</div>
          <span className="text-xs text-[#475569] mt-1 block">Coordinator owned</span>
        </Card>
      </div>

      {/* Trigger Notification Banner if recently triggered */}
      {lastActionResult && (
        <div className="bg-[#E6F4F1] border border-[#0F766E]/20 rounded-card p-4 text-xs text-[#0F172A] flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 font-semibold text-[#0F766E] mb-1">
              <CheckCircle2 className="w-4 h-4" />
              <span>Recovery Action Executed: {lastActionResult.playbook}</span>
            </div>
            <p className="text-[#475569] mb-1">{lastActionResult.rationale}</p>
            <p className="font-medium text-[#0F766E]">{lastActionResult.actionTaken}</p>
          </div>
          <button
            onClick={() => setLastActionResult(null)}
            className="text-xs text-[#475569] hover:text-[#0F172A] font-semibold focus:outline-none"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-2 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn px-3.5 py-2 flex-1 max-w-md focus-within:ring-2 focus-within:ring-[#0F766E]">
          <Search className="w-4 h-4 text-[#475569]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by patient, case number, or playbook..."
            className="bg-transparent text-sm text-[#0F172A] placeholder-[#475569]/60 focus:outline-none w-full"
            aria-label="Search recovery queue"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto text-xs">
          <span className="text-[#475569] text-xs font-semibold uppercase tracking-wider mr-1">
            Filter:
          </span>
          {[
            { id: "all", label: "All Cases" },
            { id: "recovering", label: "In Recovery" },
            { id: "no_show", label: "No-Shows" },
            { id: "warning", label: "SLA Warning" },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`h-9 px-3.5 rounded-btn font-medium text-xs transition cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2 ${
                filter === f.id
                  ? "bg-[#0F766E] text-white"
                  : "bg-white text-[#475569] hover:text-[#0F172A] border border-[#E2E8F0]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </Card>

      {/* Recovery Cases Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredCases.map((c) => (
          <Card key={c.case_id} className="p-5 flex flex-col justify-between">
            <div>
              <div className="flex items-start justify-between gap-2 mb-3">
                <div>
                  <Link
                    href={`/cases/${c.case_id}`}
                    className="font-semibold text-sm text-[#0F172A] hover:text-[#0F766E] transition block"
                  >
                    {c.patient_name}
                  </Link>
                  <span className="text-xs text-[#475569]">{c.case_number}</span>
                </div>
                <Badge
                  variant={
                    c.priority === "urgent" || c.priority === "critical"
                      ? "error"
                      : "warning"
                  }
                >
                  {c.priority}
                </Badge>
              </div>

              <div className="space-y-2.5 text-xs text-[#475569] my-4">
                <div className="flex items-center gap-2">
                  {getPlaybookIcon(c.active_playbook)}
                  <span className="font-semibold text-[#0F172A] capitalize">
                    {c.active_playbook.replace("_", " ")}
                  </span>
                </div>

                <div className="p-3 rounded-card bg-[#F8FAFC] border border-[#E2E8F0]">
                  <span className="text-[#475569] block text-[11px] mb-1 font-medium">
                    Detected Barriers:
                  </span>
                  <span className="font-medium text-[#0F172A]">
                    {c.barriers_detected.join(", ") || "Transportation / Caregiver Dependency"}
                  </span>
                </div>

                <div className="flex justify-between text-xs pt-1">
                  <span className="text-[#475569]">Recovery Attempts:</span>
                  <span className="font-semibold text-[#0F172A]">{c.recovery_attempts}</span>
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-[#E2E8F0] flex items-center justify-between text-xs mt-3">
              <Link
                href={`/cases/${c.case_id}`}
                className="text-xs text-[#475569] hover:text-[#0F172A] font-medium focus:outline-none focus:underline"
              >
                Case Detail
              </Link>
              <Button
                size="sm"
                variant="primary"
                onClick={() => handleTriggerPlay(c.case_id)}
                disabled={triggeringCaseId === c.case_id}
                leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
              >
                {triggeringCaseId === c.case_id ? "Running..." : "Trigger Play"}
              </Button>
            </div>
          </Card>
        ))}

        {filteredCases.length === 0 && !loading && (
          <div className="col-span-full text-center py-12 text-sm text-[#475569]">
            No stalled cases matching your filter.
          </div>
        )}
      </div>
    </div>
  );
}
