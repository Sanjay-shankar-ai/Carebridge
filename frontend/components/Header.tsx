"use client";

import { useState, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { Bell, ShieldCheck, Activity, Calendar, Plus, Share2, Globe, Menu } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { Button } from "./ui/Button";
import NotificationCenter from "./NotificationCenter";

export default function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, role } = useAuth();
  const [currentLang, setCurrentLang] = useState("en");

  useEffect(() => {
    const saved = typeof window !== "undefined" ? localStorage.getItem("carebridge_lang") : null;
    const initial = saved || (user as any)?.preferred_language || "en";
    handleLanguageChange(initial, false);
  }, [user]);

  const handleLanguageChange = (lang: string, persist = true) => {
    // Scope 8: Arabic RTL and language selector (English, Arabic, Spanish; strictly no Tamil)
    if (!["en", "ar", "es"].includes(lang)) {
      lang = "en";
    }
    setCurrentLang(lang);
    if (persist && typeof window !== "undefined") {
      localStorage.setItem("carebridge_lang", lang);
    }
    if (typeof document !== "undefined") {
      document.documentElement.lang = lang;
      document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    }
  };

  // Hide header on login page
  if (pathname === "/login") {
    return null;
  }

  const currentDate = new Date().toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  const getRoleTitle = () => {
    switch (role) {
      case "doctor":
      case "clinician":
        return "Doctor / Specialist";
      case "patient":
        return "Patient Portal";
      default:
        return "Care Coordinator";
    }
  };

  return (
    <header className="h-16 bg-white border-b border-[#E2E8F0] px-6 lg:px-8 flex items-center justify-between sticky top-0 z-30 shadow-soft">
      {/* Left: Hamburger (mobile) + Title & Subtitle */}
      <div className="flex items-center gap-3 sm:gap-4">
        <button
          type="button"
          onClick={() => {
            if (typeof window !== "undefined") {
              window.dispatchEvent(new CustomEvent("carebridge:toggle_sidebar"));
            }
          }}
          className="md:hidden p-1.5 rounded-btn border border-[#E2E8F0] text-[#475569] hover:bg-[#F8FAFC] cursor-pointer"
          aria-label="Toggle navigation menu"
        >
          <Menu className="w-4 h-4" />
        </button>

        <div>
          <span className="text-xs text-[#64748B] font-medium block leading-tight">
            {currentDate} • <span className="text-[#0F766E] font-semibold">{getRoleTitle()}</span>
          </span>
          <h2 className="text-base font-semibold text-[#0F172A] leading-tight">
            {user?.name || "CareBridge Clinical Portal"}
          </h2>
        </div>

        <div className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#E6F4F1] border border-[#CCFBF1] text-xs font-medium text-[#0F766E]">
          <Activity className="w-3.5 h-3.5" />
          <span>Screening-to-Care Protocol</span>
        </div>
      </div>

      {/* Right Controls: Notification + User */}
      <div className="flex items-center gap-3">
        {/* Primary CTA: Book Appointment for staff roles */}
        {role !== "patient" && (
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="w-3.5 h-3.5" />}
            onClick={() => router.push("/appointments")}
          >
            Book Appointment
          </Button>
        )}

        {/* FHIR Interoperability Gateway link (Phase 8) */}
        <Link
          href="/fhir"
          className="hidden sm:flex items-center gap-1.5 px-2.5 py-1.5 rounded-btn text-xs font-semibold text-[#0F766E] bg-[#E6F4F1] hover:bg-[#CCFBF1] border border-[#0F766E]/20 transition"
          title="HL7 FHIR R4 Interoperability Gateway"
        >
          <Share2 className="w-3.5 h-3.5" />
          <span>FHIR R4</span>
        </Link>

        {/* Language Selector (Phase 5: English, Arabic, Spanish; strictly no Tamil) */}
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-btn bg-[#F8FAFC] border border-[#CBD5E1] text-xs font-medium text-[#334155]">
          <Globe className="w-3.5 h-3.5 text-[#0F766E]" />
          <select
            value={currentLang}
            onChange={(e) => handleLanguageChange(e.target.value)}
            className="bg-transparent text-xs font-semibold text-[#0F172A] focus:outline-none cursor-pointer"
            aria-label="Select Portal Language"
          >
            <option value="en">English (EN)</option>
            <option value="ar">العربية (Arabic - RTL)</option>
            <option value="es">Español (ES)</option>
          </select>
        </div>

        {/* Real-Time Notification Center (Phase 7) */}
        <NotificationCenter />

        {/* User Capsule */}
        <div className="flex items-center gap-2.5 pl-2 border-l border-[#E2E8F0]">
          <div className="w-8 h-8 rounded-full bg-[#E6F4F1] border border-[#CCFBF1] text-[#0F766E] flex items-center justify-center text-xs font-semibold">
            {user?.name
              ? user.name
                  .split(" ")
                  .map((n) => n[0])
                  .join("")
                  .slice(0, 2)
                  .toUpperCase()
              : "CB"}
          </div>
          <div className="hidden md:block text-left">
            <span className="block text-xs font-semibold text-[#0F172A] leading-tight">
              {user?.name || "CareBridge User"}
            </span>
            <span className="block text-[11px] text-[#64748B] capitalize leading-tight">
              {user?.facility || "General Health"}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
