import React from "react";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padding?: "none" | "sm" | "md" | "lg";
}

export function Card({
  children,
  padding = "md",
  className = "",
  ...props
}: CardProps) {
  const paddings = {
    none: "",
    sm: "p-4", // 16px
    md: "p-6", // 24px
    lg: "p-8", // 32px
  };

  return (
    <div
      className={`bg-white rounded-card border border-[#E2E8F0] shadow-soft ${paddings[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
  className = "",
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 mb-4 border-b border-[#E2E8F0] ${className}`}
    >
      <div>
        <h3 className="text-lg font-semibold text-[#0F172A] tracking-tight">{title}</h3>
        {subtitle && <p className="text-xs text-[#475569] mt-0.5">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
