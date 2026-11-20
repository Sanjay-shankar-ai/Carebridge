import React from "react";
import { Card } from "./Card";
import { Badge } from "./Badge";

interface KPICardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  badgeText?: string;
  badgeVariant?: "neutral" | "info" | "success" | "warning" | "error";
  className?: string;
}

export function KPICard({
  label,
  value,
  subtitle,
  icon,
  badgeText,
  badgeVariant = "info",
  className = "",
}: KPICardProps) {
  return (
    <Card padding="md" className={`flex flex-col justify-between ${className}`}>
      <div className="flex items-center justify-between text-xs font-semibold text-[#64748B] uppercase tracking-wider mb-2">
        <span>{label}</span>
        {icon && <span className="text-[#0F766E]">{icon}</span>}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-semibold text-[#0F172A] tracking-tight">{value}</span>
        {badgeText && (
          <Badge variant={badgeVariant} icon={false}>
            {badgeText}
          </Badge>
        )}
      </div>
      {subtitle && <p className="text-xs text-[#475569] mt-2 leading-snug">{subtitle}</p>}
    </Card>
  );
}
