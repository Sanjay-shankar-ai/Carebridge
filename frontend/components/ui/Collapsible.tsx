"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

interface CollapsibleProps {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

export function Collapsible({
  title,
  subtitle,
  defaultOpen = false,
  children,
  icon,
  className = "",
}: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={`border border-[#E2E8F0] rounded-card bg-white overflow-hidden transition-all ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full p-4 flex items-center justify-between text-left hover:bg-[#F8FAFC] transition cursor-pointer"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-3 min-w-0">
          {icon && <span className="text-[#0F766E] shrink-0">{icon}</span>}
          <div>
            <h4 className="font-semibold text-xs sm:text-sm text-[#0F172A]">{title}</h4>
            {subtitle && <p className="text-[11px] text-[#64748B] mt-0.5">{subtitle}</p>}
          </div>
        </div>
        <span className="p-1 rounded-btn hover:bg-[#E2E8F0] text-[#64748B]">
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
      </button>
      {isOpen && <div className="p-4 pt-2 border-t border-[#E2E8F0] bg-[#FAFAFA]">{children}</div>}
    </div>
  );
}
