import React from "react";
import { FolderOpen, AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "./Button";

export function EmptyState({
  icon = <FolderOpen className="w-8 h-8 text-[#64748B]" />,
  title = "No records found",
  description = "There are currently no items to display in this view.",
  action,
}: {
  icon?: React.ReactNode;
  title?: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center max-w-sm mx-auto my-6">
      <div className="w-14 h-14 rounded-full bg-[#F1F5F9] border border-[#E2E8F0] flex items-center justify-center mb-3">
        {icon}
      </div>
      <h4 className="text-base font-semibold text-[#0F172A] mb-1">{title}</h4>
      <p className="text-xs text-[#475569] leading-relaxed mb-4">{description}</p>
      {action}
    </div>
  );
}

export function LoadingState({
  message = "Loading records...",
}: {
  message?: string;
}) {
  return (
    <div className="space-y-4 max-w-4xl mx-auto p-4">
      <div className="flex items-center gap-2 text-xs text-[#64748B] mb-2 animate-pulse">
        <div className="w-4 h-4 border-2 border-[#0F766E] border-t-transparent rounded-full animate-spin" />
        <span>{message}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="p-4 rounded-card border border-[#E2E8F0] bg-white animate-pulse space-y-3">
            <div className="h-3 bg-slate-200 rounded w-1/2" />
            <div className="h-7 bg-slate-200 rounded w-1/3" />
            <div className="h-2.5 bg-slate-100 rounded w-3/4" />
          </div>
        ))}
      </div>
      <div className="p-6 rounded-card border border-[#E2E8F0] bg-white animate-pulse space-y-4">
        <div className="h-4 bg-slate-200 rounded w-1/4" />
        <div className="space-y-2">
          <div className="h-10 bg-slate-100 rounded" />
          <div className="h-10 bg-slate-100 rounded" />
          <div className="h-10 bg-slate-100 rounded" />
        </div>
      </div>
    </div>
  );
}

export function ErrorState({
  title = "Unable to load data",
  description = "A connection error occurred while loading this section.",
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center max-w-sm mx-auto my-6 border border-[#FECACA] bg-[#FEF2F2]/60 rounded-card">
      <div className="w-12 h-12 rounded-full bg-[#FEE2E2] flex items-center justify-center mb-3 text-[#DC2626]">
        <AlertCircle className="w-6 h-6" />
      </div>
      <h4 className="text-sm font-semibold text-[#991B1B] mb-1">{title}</h4>
      <p className="text-xs text-[#7F1D1D] leading-relaxed mb-4">{description}</p>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry} leftIcon={<RefreshCw className="w-3.5 h-3.5" />}>
          Try Again
        </Button>
      )}
    </div>
  );
}
