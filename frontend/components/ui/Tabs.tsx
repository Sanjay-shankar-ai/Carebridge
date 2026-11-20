"use client";

import React from "react";

export interface Tab {
  id: string;
  label: string;
  badge?: number | string;
  badgeVariant?: "neutral" | "info" | "success" | "warning" | "error";
  icon?: React.ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onChange, className = "" }: TabsProps) {
  return (
    <div className={`border-b border-[#E2E8F0] ${className}`}>
      <nav className="flex space-x-2 sm:space-x-4 overflow-x-auto no-scrollbar" aria-label="Tabs">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onChange(tab.id)}
              className={`group inline-flex items-center gap-2 py-3 px-3 sm:px-4 border-b-2 font-medium text-xs sm:text-sm whitespace-nowrap transition-colors cursor-pointer ${
                isActive
                  ? "border-[#0F766E] text-[#0F766E] font-semibold"
                  : "border-transparent text-[#64748B] hover:text-[#0F172A] hover:border-[#CBD5E1]"
              }`}
              aria-current={isActive ? "page" : undefined}
            >
              {tab.icon && (
                <span className={isActive ? "text-[#0F766E]" : "text-[#64748B] group-hover:text-[#0F172A]"}>
                  {tab.icon}
                </span>
              )}
              <span>{tab.label}</span>
              {tab.badge !== undefined && tab.badge !== null && (
                <span
                  className={`ml-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    isActive
                      ? "bg-[#E6F4F1] text-[#0F766E]"
                      : "bg-[#F1F5F9] text-[#64748B] group-hover:bg-[#E2E8F0]"
                  }`}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
}
