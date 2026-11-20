"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth, ROLE_HOME_PATHS } from "../context/AuthContext";

export default function Home() {
  const { user, role, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!user || !role) {
      router.replace("/login");
      return;
    }
    const dest = ROLE_HOME_PATHS[role] || "/coordinator";
    router.replace(dest);
  }, [user, role, isLoading, router]);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3">
      <div className="w-8 h-8 border-2 border-[#0F766E]/30 border-t-[#0F766E] rounded-full animate-spin" />
      <p className="text-xs text-[#475569] font-medium">Entering CareBridge Workspace...</p>
    </div>
  );
}
