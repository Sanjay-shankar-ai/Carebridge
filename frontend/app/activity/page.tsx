"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  Shield,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Wrench,
  RefreshCw,
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  ExternalLink,
  Code2,
} from "lucide-react";
import { fetchAIActivity } from "../../services/api";
import { AIActivityItem } from "../../types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export default function AIActivityPage() {
  const [activities, setActivities] = useState<AIActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [autonomyFilter, setAutonomyFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchAIActivity();
      setActivities(data || []);
    } catch (err) {
      console.error("Failed to load AI activity telemetry:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredActivities = activities.filter((act) => {
    const matchesSearch =
      act.triggering_event.toLowerCase().includes(searchQuery.toLowerCase()) ||
      act.action_explanation.toLowerCase().includes(searchQuery.toLowerCase()) ||
      act.tool_selected.toLowerCase().includes(searchQuery.toLowerCase()) ||
      act.case_number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      act.patient_name.toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;

    if (autonomyFilter !== "all") {
      if (act.autonomy_level.toString() !== autonomyFilter) return false;
    }

    if (statusFilter !== "all") {
      if (act.status !== statusFilter) return false;
    }

    return true;
  });

  const level1Count = activities.filter((a) => a.autonomy_level === 1).length;
  const level2Count = activities.filter((a) => a.autonomy_level === 2).length;
  const level3Count = activities.filter((a) => a.autonomy_level === 3).length;

  const getAutonomyBadge = (level: number) => {
    switch (level) {
      case 1:
        return (
          <Badge variant="success">
            Level 1: Fully Autonomous
          </Badge>
        );
      case 2:
        return (
          <Badge variant="info">
            Level 2: Policy-Constrained
          </Badge>
        );
      case 3:
        return (
          <Badge variant="warning">
            Level 3: Human Authorized Gate
          </Badge>
        );
      default:
        return null;
    }
  };

  const getApprovalBadge = (status: string) => {
    switch (status) {
      case "approved":
        return <Badge variant="success">Clinician Approved</Badge>;
      case "pending_approval":
        return <Badge variant="warning">Pending Authorization</Badge>;
      case "policy_checked":
        return <Badge variant="info">Policy Bounds Verified</Badge>;
      default:
        return <Badge variant="neutral">Autonomous Dispatch</Badge>;
    }
  };

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-semibold mb-2">
            <Activity className="w-3.5 h-3.5" />
            Supervisor Agent Observability
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-[#0F172A] tracking-tight">
            AI Activity Monitor
          </h1>
          <p className="text-sm text-[#475569] mt-1">
            Real-time audit log of agent trigger events, reasoning rationale, selected tools, results, and autonomy safety gates.
          </p>
        </div>

        <Button
          variant="secondary"
          onClick={loadData}
          disabled={loading}
          icon={<RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />}
        >
          Refresh Traces
        </Button>
      </div>

      {/* Metric Tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between text-[#475569] text-xs">
            <span className="font-medium uppercase tracking-wider">Total AI Actions</span>
            <Activity className="w-4 h-4 text-[#0F766E]" />
          </div>
          <div className="text-2xl font-semibold text-[#0F172A] mt-2">{activities.length}</div>
          <span className="text-xs text-[#0F766E] font-medium mt-1 block">Logged telemetry steps</span>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between text-[#475569] text-xs">
            <span className="font-medium uppercase tracking-wider">Level 1: Autonomous</span>
            <ShieldCheck className="w-4 h-4 text-[#15803D]" />
          </div>
          <div className="text-2xl font-semibold text-[#15803D] mt-2">{level1Count}</div>
          <span className="text-xs text-[#475569] mt-1 block">Zero human latency</span>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between text-[#475569] text-xs">
            <span className="font-medium uppercase tracking-wider">Level 2: Policy Bound</span>
            <Shield className="w-4 h-4 text-[#0F766E]" />
          </div>
          <div className="text-2xl font-semibold text-[#0F766E] mt-2">{level2Count}</div>
          <span className="text-xs text-[#475569] mt-1 block">Rule-verified actions</span>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between text-[#475569] text-xs">
            <span className="font-medium uppercase tracking-wider">Level 3: Clinician Gate</span>
            <ShieldAlert className="w-4 h-4 text-[#B45309]" />
          </div>
          <div className="text-2xl font-semibold text-[#B45309] mt-2">{level3Count}</div>
          <span className="text-xs text-[#475569] mt-1 block">Physician signed sign-offs</span>
        </Card>
      </div>

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-2 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn px-3.5 py-2 flex-1 max-w-md focus-within:ring-2 focus-within:ring-[#0F766E]">
          <Search className="w-4 h-4 text-[#475569]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by trigger, tool, patient, or case..."
            className="bg-transparent text-sm text-[#0F172A] placeholder-[#475569]/60 focus:outline-none w-full"
            aria-label="Search activities"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto text-xs">
          <span className="text-[#475569] text-xs font-semibold uppercase tracking-wider mr-1">
            Autonomy:
          </span>
          {[
            { id: "all", label: "All Levels" },
            { id: "1", label: "L1 Autonomous" },
            { id: "2", label: "L2 Policy" },
            { id: "3", label: "L3 Human Auth" },
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setAutonomyFilter(f.id)}
              className={`h-9 px-3.5 rounded-btn font-medium text-xs transition cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2 ${
                autonomyFilter === f.id
                  ? "bg-[#0F766E] text-white"
                  : "bg-white text-[#475569] hover:text-[#0F172A] border border-[#E2E8F0]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </Card>

      {/* Activity Stream List */}
      <Card className="divide-y divide-[#E2E8F0] overflow-hidden">
        {filteredActivities.map((act) => {
          const isExpanded = expandedId === act.id;
          return (
            <div key={act.id} className="p-5 hover:bg-[#F8FAFC] transition">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-8 h-8 rounded-btn bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center shrink-0 mt-0.5 font-bold text-xs">
                    <Wrench className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-semibold text-sm text-[#0F172A]">{act.patient_name}</span>
                      <span className="text-xs text-[#475569]">• {act.case_number}</span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-[#0F172A] border border-[#E2E8F0] font-mono text-xs">
                        {act.tool_selected}
                      </span>
                      {getAutonomyBadge(act.autonomy_level)}
                      {getApprovalBadge(act.approval_status)}
                    </div>
                    <p className="text-xs text-[#475569] leading-relaxed">{act.action_explanation}</p>
                  </div>
                </div>

                <div className="flex items-center gap-4 shrink-0 text-right">
                  <div className="text-xs text-[#475569]">
                    <span className="block font-medium text-[#0F172A]">
                      {act.timestamp ? new Date(act.timestamp).toLocaleTimeString() : "Just now"}
                    </span>
                    <span className="text-[11px] text-[#475569]">{act.duration_ms}ms</span>
                  </div>

                  <button
                    onClick={() => setExpandedId(isExpanded ? null : act.id)}
                    className="p-2 rounded-btn text-[#475569] hover:text-[#0F172A] hover:bg-slate-100 transition focus:outline-none focus:ring-2 focus:ring-[#0F766E]"
                    aria-label={isExpanded ? "Collapse trace" : "Expand trace"}
                  >
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Collapsible Tool Payload Details */}
              {isExpanded && (
                <div className="mt-4 pt-3 border-t border-[#E2E8F0] bg-[#F8FAFC] p-4 rounded-card text-xs space-y-2">
                  <div>
                    <span className="text-[#475569] font-medium block mb-1">Triggering Event:</span>
                    <span className="text-[#0F172A]">{act.triggering_event}</span>
                  </div>
                  <div>
                    <span className="text-[#475569] font-medium block mb-1">Execution Result:</span>
                    <pre className="p-3 rounded-btn bg-white border border-[#E2E8F0] text-[#0F172A] text-xs font-mono overflow-x-auto whitespace-pre-wrap">
                      {act.tool_result}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {filteredActivities.length === 0 && !loading && (
          <div className="p-12 text-center text-[#475569] text-sm">
            No AI activities found.
          </div>
        )}
      </Card>
    </div>
  );
}
