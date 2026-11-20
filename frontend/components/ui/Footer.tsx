import React from "react";
import Link from "next/link";
import { HeartPulse, ShieldCheck, PhoneCall } from "lucide-react";

export function Footer() {
  return (
    <footer className="mt-16 border-t border-[#E2E8F0] bg-white text-xs text-[#475569]">
      <div className="max-w-[1200px] mx-auto px-6 py-10 grid grid-cols-1 md:grid-cols-4 gap-8">
        {/* Brand Col */}
        <div className="space-y-3 md:col-span-1">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-btn bg-[#0F766E] text-white flex items-center justify-center">
              <HeartPulse className="w-5 h-5" />
            </div>
            <span className="font-semibold text-sm text-[#0F172A] tracking-tight">CareBridge</span>
          </div>
          <p className="text-xs text-[#475569] leading-relaxed">
            Closed-loop healthcare coordination bridging screening to verified definitive treatment.
          </p>
          <div className="flex items-center gap-1.5 text-[11px] text-[#0F766E] font-medium">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>HIPAA Compliant & WCAG AA Accessible</span>
          </div>
        </div>

        {/* Clinical Services */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-[#0F172A]">Clinical Pathways</h4>
          <ul className="space-y-1.5 text-xs">
            <li><span className="hover:text-[#0F766E] transition">Diagnostic Breast Oncology</span></li>
            <li><span className="hover:text-[#0F766E] transition">Colorectal FIT Diagnostic Follow-up</span></li>
            <li><span className="hover:text-[#0F766E] transition">Pathology & Biopsy Tracking</span></li>
            <li><span className="hover:text-[#0F766E] transition">Empathetic Care Recovery</span></li>
          </ul>
        </div>

        {/* Roles & Portals */}
        <div className="space-y-2">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-[#0F172A]">Portals</h4>
          <ul className="space-y-1.5 text-xs">
            <li><Link href="/doctor" className="hover:text-[#0F766E] transition">Clinician Workspace</Link></li>
            <li><Link href="/patient" className="hover:text-[#0F766E] transition">Patient Care Journey</Link></li>
            <li><Link href="/coordinator" className="hover:text-[#0F766E] transition">Care Coordinator Radar</Link></li>
            <li><Link href="/admin" className="hover:text-[#0F766E] transition">Platform Administration</Link></li>
          </ul>
        </div>

        {/* Emergency Assistance Notice */}
        <div className="space-y-2.5 p-4 rounded-card bg-[#F8FAFC] border border-[#E2E8F0]">
          <div className="flex items-center gap-1.5 font-semibold text-xs text-[#0F172A]">
            <PhoneCall className="w-3.5 h-3.5 text-[#0F766E]" />
            <span>Clinical Emergency Notice</span>
          </div>
          <p className="text-[11px] text-[#475569] leading-relaxed">
            CareBridge is a care coordination platform. If you are experiencing a medical emergency, please call emergency services immediately or visit the nearest emergency department.
          </p>
        </div>
      </div>

      <div className="border-t border-[#E2E8F0] py-4 px-6 text-center text-[11px] text-[#64748B]">
        © {new Date().getFullYear()} CareBridge Healthcare Systems. All rights reserved. Built with privacy-first clinical architecture.
      </div>
    </footer>
  );
}
