"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth, ROLE_HOME_PATHS } from "../../context/AuthContext";

export default function DashboardRedirect() {
  const { role } = useAuth();
  const router = useRouter();

  useEffect(() => {
    const dest = (role && ROLE_HOME_PATHS[role]) ? ROLE_HOME_PATHS[role] : "/coordinator";
    router.replace(dest);
  }, [role, router]);

  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center gap-3">
      <div className="w-8 h-8 border-2 border-[#0F766E]/30 border-t-[#0F766E] rounded-full animate-spin" />
      <p className="text-xs text-[#475569] font-medium">Navigating to your role workspace...</p>
    </div>
  );
}
