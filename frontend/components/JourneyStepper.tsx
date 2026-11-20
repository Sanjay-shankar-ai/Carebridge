"use client";

import React, { useState } from "react";
import { Check, Clock, AlertCircle, ChevronRight, X, User, Calendar, ShieldCheck } from "lucide-react";
import { Badge } from "./ui/Badge";
import { Card } from "./ui/Card";

export interface LifecycleStageItem {
  stage_number?: number;
  title: string;
  status: "completed" | "active" | "pending" | "blocked";
  description?: string;
  patient_info?: string;
  default_patient_info?: string;
  responsible_role?: string;
  completed_at?: string;
  pending_actions?: string[];
}

interface JourneyStepperProps {
  stages: LifecycleStageItem[];
  currentStageNumber?: number;
  className?: string;
}

export function JourneyStepper({
  stages,
  currentStageNumber = 4,
  className = "",
}: JourneyStepperProps) {
  const [selectedStage, setSelectedStage] = useState<LifecycleStageItem | null>(null);

  // If selected stage not set, default to active stage or stage 1
  const activeOrSelected =
    selectedStage ||
    stages.find((s, idx) => (s.stage_number || idx + 1) === currentStageNumber) ||
    stages[0] ||
    null;

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Desktop Horizontal Stepper Pipeline */}
      <div className="hidden lg:block bg-white p-5 rounded-card border border-[#E2E8F0] shadow-2xs">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-semibold text-sm text-[#0F172A]">14-Stage Longitudinal Care Pathway</h3>
            <p className="text-xs text-[#64748B]">Click any stage to view clinical actions, ownership, and milestones</p>
          </div>
          <Badge variant="info">
            Current: Stage {currentStageNumber} of 14
          </Badge>
        </div>

        {/* Pipeline Bar */}
        <div className="overflow-x-auto pb-2">
          <div className="flex items-center gap-1 min-w-[900px]">
            {stages.map((stage, idx) => {
              const num = stage.stage_number || idx + 1;
              const isCompleted = stage.status === "completed";
              const isActive = stage.status === "active";
              const isSelected = activeOrSelected && (activeOrSelected.stage_number || stages.indexOf(activeOrSelected) + 1) === num;

              return (
                <button
                  key={num}
                  type="button"
                  onClick={() => setSelectedStage(stage)}
                  className={`flex-1 min-w-[62px] p-2 rounded-btn border text-left transition cursor-pointer flex flex-col justify-between ${
                    isSelected
                      ? "ring-2 ring-[#0F766E] border-[#0F766E] bg-[#E6F4F1]"
                      : isActive
                      ? "border-[#0F766E] bg-[#F0FDFA]"
                      : isCompleted
                      ? "border-[#BBF7D0] bg-[#F0FDF4]"
                      : "border-[#E2E8F0] bg-[#F8FAFC] opacity-75 hover:opacity-100"
                  }`}
                  title={`Stage ${num}: ${stage.title}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold ${
                        isCompleted
                          ? "bg-[#15803D] text-white"
                          : isActive
                          ? "bg-[#0F766E] text-white"
                          : "bg-[#E2E8F0] text-[#64748B]"
                      }`}
                    >
                      {isCompleted ? <Check className="w-2.5 h-2.5" /> : num}
                    </span>
                    <span
                      className={`text-[8px] font-bold uppercase tracking-wider ${
                        isCompleted
                          ? "text-[#15803D]"
                          : isActive
                          ? "text-[#0F766E]"
                          : "text-[#94A3B8]"
                      }`}
                    >
                      {isCompleted ? "Done" : isActive ? "Active" : "Wait"}
                    </span>
                  </div>
                  <span className="text-[10px] font-semibold text-[#0F172A] truncate block">
                    {stage.title}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Mobile Vertical Stepper View */}
      <div className="lg:hidden bg-white p-4 rounded-card border border-[#E2E8F0]">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm text-[#0F172A]">Care Journey Stepper</h3>
          <Badge variant="info">Stage {currentStageNumber} of 14</Badge>
        </div>

        <div className="space-y-1.5 max-h-[320px] overflow-y-auto pr-1">
          {stages.map((stage, idx) => {
            const num = stage.stage_number || idx + 1;
            const isCompleted = stage.status === "completed";
            const isActive = stage.status === "active";
            const isSelected = activeOrSelected && (activeOrSelected.stage_number || stages.indexOf(activeOrSelected) + 1) === num;

            return (
              <button
                key={num}
                type="button"
                onClick={() => setSelectedStage(stage)}
                className={`w-full p-2.5 rounded-card border text-left flex items-center justify-between gap-3 transition cursor-pointer ${
                  isSelected
                    ? "ring-2 ring-[#0F766E] border-[#0F766E] bg-[#E6F4F1]"
                    : isActive
                    ? "border-[#0F766E] bg-[#F0FDFA]"
                    : isCompleted
                    ? "border-[#E2E8F0] bg-white"
                    : "border-[#E2E8F0] bg-[#F8FAFC] opacity-75"
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span
                    className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                      isCompleted
                        ? "bg-[#15803D] text-white"
                        : isActive
                        ? "bg-[#0F766E] text-white"
                        : "bg-[#E2E8F0] text-[#64748B]"
                    }`}
                  >
                    {isCompleted ? <Check className="w-3 h-3" /> : num}
                  </span>
                  <div className="min-w-0">
                    <span className="font-semibold text-xs text-[#0F172A] truncate block">
                      {num}. {stage.title}
                    </span>
                    <span className="text-[10px] text-[#64748B] block truncate">
                      {stage.responsible_role?.replace("_", " ") || "Care Team"}
                    </span>
                  </div>
                </div>
                <Badge
                  variant={isCompleted ? "success" : isActive ? "info" : "neutral"}
                  className="text-[9px] py-0 px-1.5 h-4 shrink-0"
                >
                  {stage.status}
                </Badge>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Stage Detail Panel (Interactive, not 14 open cards!) */}
      {activeOrSelected && (
        <Card padding="md" className="border-l-4 border-l-[#0F766E]">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="space-y-2 flex-1">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-bold font-mono">
                  Stage {activeOrSelected.stage_number || stages.indexOf(activeOrSelected) + 1} of 14
                </span>
                <Badge
                  variant={
                    activeOrSelected.status === "completed"
                      ? "success"
                      : activeOrSelected.status === "active"
                      ? "info"
                      : "neutral"
                  }
                >
                  {activeOrSelected.status}
                </Badge>
                {activeOrSelected.completed_at && (
                  <span className="text-xs text-[#64748B]">
                    Completed on {new Date(activeOrSelected.completed_at).toLocaleDateString()}
                  </span>
                )}
              </div>

              <h3 className="text-base font-semibold text-[#0F172A]">
                {activeOrSelected.title}
              </h3>

              <p className="text-xs text-[#475569] leading-relaxed">
                {activeOrSelected.patient_info ||
                  activeOrSelected.default_patient_info ||
                  activeOrSelected.description ||
                  "Longitudinal verification stage within the closed-loop CareBridge protocol."}
              </p>

              {activeOrSelected.pending_actions && activeOrSelected.pending_actions.length > 0 && (
                <div className="mt-2 p-2.5 rounded-btn bg-[#FEF3C7] border border-[#F59E0B]/30 text-xs text-[#92400E]">
                  <strong>Action in progress: </strong>
                  {activeOrSelected.pending_actions[0]}
                </div>
              )}
            </div>

            <div className="p-3 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] text-xs space-y-1.5 shrink-0 sm:w-64">
              <div className="flex items-center justify-between">
                <span className="text-[#64748B]">Accountable Role:</span>
                <span className="font-semibold text-[#0F172A] capitalize">
                  {activeOrSelected.responsible_role?.replace("_", " ") || "Care Team"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#64748B]">Protocol Level:</span>
                <span className="font-semibold text-[#0F766E]">Evidence Required</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#64748B]">Audit Logged:</span>
                <span className="font-semibold text-[#15803D]">PostgreSQL 17</span>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
