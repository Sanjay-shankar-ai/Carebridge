import React from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  subtitle,
  badge,
  breadcrumbs,
  actions,
  className = "",
}: PageHeaderProps) {
  return (
    <div className={`pb-4 border-b border-[#E2E8F0] ${className}`}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-[#64748B] mb-2">
          {breadcrumbs.map((item, idx) => {
            const isLast = idx === breadcrumbs.length - 1;
            return (
              <React.Fragment key={idx}>
                {idx > 0 && <ChevronRight className="w-3.5 h-3.5 text-[#94A3B8]" />}
                {item.href && !isLast ? (
                  <Link href={item.href} className="hover:text-[#0F172A] transition">
                    {item.label}
                  </Link>
                ) : (
                  <span className={isLast ? "font-semibold text-[#0F172A]" : ""}>{item.label}</span>
                )}
              </React.Fragment>
            );
          })}
        </nav>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          {badge && <div className="mb-1.5">{badge}</div>}
          <h1 className="text-xl sm:text-2xl font-semibold text-[#0F172A] tracking-tight">{title}</h1>
          {subtitle && <p className="text-xs sm:text-sm text-[#475569] mt-0.5">{subtitle}</p>}
        </div>

        {actions && <div className="flex items-center gap-2.5 shrink-0">{actions}</div>}
      </div>
    </div>
  );
}
