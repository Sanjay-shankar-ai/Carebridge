"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Share2,
  Search,
  Clock,
  Building,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ArrowUpRight,
  RefreshCw,
  ChevronRight,
  Plus,
} from "lucide-react";
import { fetchReferrals } from "../../services/api";
import { Referral } from "../../types";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";

export default function ReferralsPage() {
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const loadData = async () => {
    try {
      setLoading(true);
      const data = await fetchReferrals();
      setReferrals(data || []);
    } catch (err) {
      console.error("Failed to load referrals:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filtered = referrals.filter((r) => {
    const matchesSearch =
      r.patient_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.target_facility.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.specialty.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.case_number.toLowerCase().includes(searchQuery.toLowerCase());

    if (statusFilter === "all") return matchesSearch;
    return matchesSearch && r.status === statusFilter;
  });

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-semibold mb-2">
            <Share2 className="w-3.5 h-3.5" />
            Inter-Facility Handoffs & Consultations
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-[#0F172A] tracking-tight">
            Specialist Referral Management
          </h1>
          <p className="text-sm text-[#475569] mt-1">
            Cross-facility coordination, automated status polling, and clinical acceptance tracking.
          </p>
        </div>

        <Button
          variant="secondary"
          onClick={loadData}
          disabled={loading}
          icon={<RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />}
        >
          Refresh Referrals
        </Button>
      </div>

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-2 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn px-3.5 py-2 flex-1 max-w-md focus-within:ring-2 focus-within:ring-[#0F766E]">
          <Search className="w-4 h-4 text-[#475569]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by patient, clinic, doctor, or specialty..."
            className="bg-transparent text-sm text-[#0F172A] placeholder-[#475569]/60 focus:outline-none w-full"
            aria-label="Search referrals"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto text-xs">
          <span className="text-[#475569] text-xs font-semibold uppercase tracking-wider mr-1">
            Status:
          </span>
          {[
            { id: "all", label: "All Referrals" },
            { id: "sent", label: "Pending" },
            { id: "accepted", label: "Accepted" },
            { id: "completed", label: "Completed" },
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

      {/* Referrals Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((r) => (
          <Card key={r.id} className="p-5 flex flex-col justify-between">
            <div>
              <div className="flex items-start justify-between gap-2 mb-3">
                <div>
                  <h3 className="font-semibold text-sm text-[#0F172A]">{r.patient_name}</h3>
                  <span className="text-xs text-[#475569]">{r.case_number}</span>
                </div>
                <Badge
                  variant={
                    r.status === "completed" || r.status === "accepted"
                      ? "success"
                      : r.status === "rejected"
                      ? "error"
                      : "neutral"
                  }
                >
                  {r.status}
                </Badge>
              </div>

              <div className="space-y-2.5 text-xs text-[#475569] my-4">
                <div className="p-3 rounded-card bg-[#F8FAFC] border border-[#E2E8F0]">
                  <span className="text-[#475569] text-[11px] block font-medium">Specialty & Facility:</span>
                  <span className="font-semibold text-[#0F172A] block mt-0.5">{r.specialty}</span>
                  <span className="text-xs text-[#0F766E] block truncate">{r.target_facility}</span>
                </div>

                <div className="text-xs">
                  <span className="text-[#475569] block mb-0.5 font-medium">Clinical Indication:</span>
                  <span className="text-[#0F172A]">{r.reason_for_referral}</span>
                </div>

                <div className="text-xs text-[#475569] pt-1">
                  Referring Provider: <strong className="text-[#0F172A] font-medium">{r.referring_provider}</strong>
                </div>
              </div>
            </div>

            <div className="pt-3 border-t border-[#E2E8F0] flex items-center justify-between text-xs mt-3">
              <Link
                href={`/cases/${r.case_id}`}
                className="text-xs text-[#0F766E] hover:text-[#115E59] font-medium flex items-center gap-1 focus:outline-none focus:underline"
              >
                <span>View Case Pathway</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </Card>
        ))}

        {filtered.length === 0 && !loading && (
          <div className="col-span-full text-center py-12 text-sm text-[#475569]">
            No referrals found.
          </div>
        )}
      </div>
    </div>
  );
}
