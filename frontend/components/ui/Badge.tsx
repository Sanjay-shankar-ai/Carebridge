import React from "react";
import { CheckCircle2, AlertTriangle, AlertCircle, Info, Clock, AlertOctagon, HelpCircle } from "lucide-react";

export type BadgeVariant =
  | "success"
  | "warning"
  | "error"
  | "info"
  | "neutral"
  | "purple"
  | "blue"
  | "grey";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  icon?: boolean;
}

export function Badge({
  children,
  variant = "neutral",
  icon = true,
  className = "",
  ...props
}: BadgeProps) {
  const styles: Record<BadgeVariant, string> = {
    success: "bg-[#DCFCE7] text-[#14532D] border-[#BBF7D0]", // COMPLETED / closed / verified -> green
    warning: "bg-[#FEF3C7] text-[#78350F] border-[#FDE68A]", // PENDING / scheduled -> amber
    error: "bg-[#FEE2E2] text-[#7F1D1D] border-[#FECACA]", // BLOCKED / breached / critical -> red
    info: "bg-[#E6F4F1] text-[#0F766E] border-[#CCFBF1]", // clinical teal
    blue: "bg-[#EFF6FF] text-[#1E40AF] border-[#BFDBFE]", // IN_PROGRESS / active -> blue
    purple: "bg-[#F3E8FF] text-[#581C87] border-[#E9D5FF]", // REQUIRES_REVIEW / escalated -> purple
    grey: "bg-[#F1F5F9] text-[#334155] border-[#E2E8F0]", // NOT_STARTED / default -> grey
    neutral: "bg-[#F1F5F9] text-[#334155] border-[#E2E8F0]",
  };

  const icons: Record<BadgeVariant, React.ReactNode> = {
    success: <CheckCircle2 className="w-3 h-3 text-[#15803D]" />,
    warning: <AlertTriangle className="w-3 h-3 text-[#B45309]" />,
    error: <AlertCircle className="w-3 h-3 text-[#B91C1C]" />,
    info: <Info className="w-3 h-3 text-[#0F766E]" />,
    blue: <Clock className="w-3 h-3 text-[#2563EB]" />,
    purple: <AlertOctagon className="w-3 h-3 text-[#7E22CE]" />,
    grey: <Clock className="w-3 h-3 text-[#64748B]" />,
    neutral: <Clock className="w-3 h-3 text-[#64748B]" />,
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles[variant]} ${className}`}
      {...props}
    >
      {icon && icons[variant]}
      <span>{children}</span>
    </span>
  );
}

/**
 * StatusBadge maps raw lifecycle/care case status strings directly to design system tokens
 */
export function StatusBadge({ status, className = "" }: { status: string; className?: string }) {
  const normalized = (status || "").toLowerCase().trim();

  let variant: BadgeVariant = "grey";
  if (
    normalized === "completed" ||
    normalized === "closed" ||
    normalized === "verified" ||
    normalized === "attended" ||
    normalized === "care_completed"
  ) {
    variant = "success";
  } else if (
    normalized === "pending" ||
    normalized === "scheduled" ||
    normalized === "booked" ||
    normalized === "screening_scheduled" ||
    normalized === "warning"
  ) {
    variant = "warning";
  } else if (
    normalized === "active" ||
    normalized === "in_progress" ||
    normalized === "recovering" ||
    normalized === "screening_completed" ||
    normalized === "result_generated" ||
    normalized === "referred"
  ) {
    variant = "blue";
  } else if (
    normalized === "blocked" ||
    normalized === "breached" ||
    normalized === "critical" ||
    normalized === "cancelled"
  ) {
    variant = "error";
  } else if (
    normalized === "requires_review" ||
    normalized === "escalated" ||
    normalized === "doctor_review"
  ) {
    variant = "purple";
  }

  const label = status ? status.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()) : "Not Started";

  return (
    <Badge variant={variant} className={className}>
      {label}
    </Badge>
  );
}
