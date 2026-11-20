"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  Users,
  FolderGit2,
  Calendar,
  Share2,
  RotateCcw,
  Activity,
  BarChart3,
  Settings,
  HeartPulse,
  LogOut,
  ShieldCheck,
  Stethoscope,
  UserCheck,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { Badge } from "./ui/Badge";

export default function Sidebar() {
  const pathname = usePathname();
  const { user, role, logout } = useAuth();
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  useEffect(() => {
    const handleToggle = () => setIsMobileOpen((prev) => !prev);
    if (typeof window !== "undefined") {
      window.addEventListener("carebridge:toggle_sidebar", handleToggle);
    }
    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("carebridge:toggle_sidebar", handleToggle);
      }
    };
  }, []);

  useEffect(() => {
    setIsMobileOpen(false);
  }, [pathname]);

  // Hide sidebar on the login page
  if (pathname === "/login") {
    return null;
  }

  // Navigation configurations per role
  const getNavItems = () => {
    switch (role) {
      case "doctor":
      case "clinician":
        return [
          { name: "Doctor Overview", href: "/doctor", icon: LayoutDashboard },
          { name: "My Patients", href: "/patients", icon: Users },
          { name: "Appointments & Visits", href: "/appointments", icon: Calendar },
          { name: "Referrals Review", href: "/referrals", icon: Share2 },
          { name: "Care Cases", href: "/cases", icon: FolderGit2 },
          { name: "Clinical AI Chat", href: "/chat", icon: MessageSquare },
          { name: "Clinical Analytics", href: "/analytics", icon: BarChart3 },
        ];
      case "patient":
        return [
          { name: "My Health Dashboard", href: "/patient", icon: LayoutDashboard },
          { name: "My Appointments", href: "/appointments", icon: Calendar },
          { name: "CareBridge AI Chat", href: "/chat", icon: MessageSquare },
          { name: "My Referrals", href: "/referrals", icon: Share2 },
          { name: "Care Team & Profile", href: "/patients", icon: Users },
        ];
      case "care_coordinator":
      default:
        return [
          { name: "Coordinator Dashboard", href: "/coordinator", icon: LayoutDashboard },
          { name: "Patients", href: "/patients", icon: Users },
          { name: "Case Management", href: "/cases", icon: FolderGit2 },
          { name: "Recovery Queue", href: "/recovery", icon: RotateCcw },
          { name: "Appointments", href: "/appointments", icon: Calendar },
          { name: "Referrals", href: "/referrals", icon: Share2 },
          { name: "Patient AI Chat", href: "/chat", icon: MessageSquare },
          { name: "AI Activity Monitor", href: "/activity", icon: Activity },
          { name: "Analytics & SLAs", href: "/analytics", icon: BarChart3 },
          { name: "Settings", href: "/settings", icon: Settings },
        ];
    }
  };

  const navItems = getNavItems();

  const getRoleBadge = () => {
    switch (role) {
      case "doctor":
      case "clinician":
        return { label: "Doctor", variant: "info" as const };
      case "patient":
        return { label: "Patient", variant: "success" as const };
      default:
        return { label: "Coordinator", variant: "info" as const };
    }
  };

  const badge = getRoleBadge();

  const sidebarContent = (
    <div className="flex flex-col h-full bg-white select-none">
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-[#E2E8F0]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-btn bg-[#0F766E] text-white flex items-center justify-center shrink-0">
            <HeartPulse className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <span className="font-semibold text-base text-[#0F172A] tracking-tight block">
              CareBridge
            </span>
            <span className="text-[11px] text-[#64748B] block truncate">
              Clinical Care Coordination
            </span>
          </div>
        </div>

        {/* Close Button on Mobile Drawer */}
        <button
          type="button"
          onClick={() => setIsMobileOpen(false)}
          className="md:hidden p-1.5 rounded-btn text-[#64748B] hover:text-[#0F172A]"
          aria-label="Close menu"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Role Pill Indicator */}
      <div className="px-5 pt-4 pb-2">
        <div className="p-2.5 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] flex items-center justify-between">
          <span className="text-xs text-[#475569] font-medium">Active Workspace</span>
          <Badge variant={badge.variant} icon={false}>
            {badge.label}
          </Badge>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));

          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-3.5 py-2.5 rounded-btn text-xs font-medium transition-colors duration-150 ${
                isActive
                  ? "bg-[#E6F4F1] text-[#0F766E] font-semibold border-l-2 border-[#0F766E]"
                  : "text-[#475569] hover:text-[#0F172A] hover:bg-slate-50"
              }`}
            >
              <Icon
                className={`w-4 h-4 shrink-0 ${
                  isActive ? "text-[#0F766E]" : "text-[#64748B]"
                }`}
              />
              <span className="truncate">{item.name}</span>
            </Link>
          );
        })}
      </nav>


      {/* User Footer with Sign Out */}
      <div className="p-4 border-t border-[#E2E8F0] flex items-center justify-between text-xs">
        <div className="min-w-0 pr-2">
          <p className="font-semibold text-[#0F172A] truncate">
            {user?.name || "Active Session"}
          </p>
          <p className="text-[11px] text-[#64748B] truncate">
            {user?.facility || "CareBridge Health"}
          </p>
        </div>
        <button
          onClick={logout}
          title="Sign Out"
          aria-label="Sign out"
          className="p-2 rounded-btn text-[#64748B] hover:text-[#B91C1C] hover:bg-slate-50 transition shrink-0 cursor-pointer"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Fixed Sidebar */}
      <aside className="hidden md:flex w-64 bg-white text-[#0F172A] h-screen sticky top-0 flex-col border-r border-[#E2E8F0] shrink-0 overflow-y-auto overflow-x-hidden">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer Overlay */}
      {isMobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex">
          <div
            className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs transition-opacity"
            onClick={() => setIsMobileOpen(false)}
          />
          <div className="relative w-64 max-w-[80vw] h-full shadow-2xl z-10 flex flex-col">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
}
