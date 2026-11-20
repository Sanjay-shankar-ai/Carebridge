import Link from "next/link";
import { ShieldAlert, Home } from "lucide-react";
import { Button } from "../../components/ui/Button";

export default function ForbiddenPage() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6 max-w-md mx-auto">
      <div className="w-16 h-16 rounded-full bg-[#FEE2E2] border border-[#FECACA] text-[#DC2626] flex items-center justify-center mb-4">
        <ShieldAlert className="w-8 h-8" />
      </div>
      <span className="text-xs font-mono font-bold text-[#DC2626] uppercase tracking-wider mb-1">
        403 — Access Restricted
      </span>
      <h1 className="text-2xl font-semibold text-[#0F172A] tracking-tight mb-2">
        Clinical Role Restriction
      </h1>
      <p className="text-xs text-[#475569] leading-relaxed mb-6">
        You do not have authorization to view this resource under your current active role. CareBridge enforces strict role-based access control (PATIENT, DOCTOR, CARE_COORDINATOR) to protect patient clinical data and PHI.
      </p>

      <div className="flex items-center gap-3">
        <Link href="/">
          <Button variant="primary" leftIcon={<Home className="w-4 h-4" />}>
            Return to Dashboard
          </Button>
        </Link>
      </div>
    </div>
  );
}
