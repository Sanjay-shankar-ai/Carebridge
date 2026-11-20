"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AuthUser, UserRole } from "../types";
export type { AuthUser, UserRole };
import { loginUser } from "../services/api";

export const ROLE_HOME_PATHS: Record<UserRole, string> = {
  doctor: "/doctor",
  clinician: "/doctor",
  patient: "/patient",
  care_coordinator: "/coordinator",
};

export const DEMO_CREDENTIALS: Record<UserRole, { email: string; pass: string }> = {
  care_coordinator: { email: "coordinator@carebridge.com", pass: "CoordinatorPass123!" },
  doctor: { email: "doctor@carebridge.com", pass: "DoctorPass123!" },
  clinician: { email: "doctor@carebridge.com", pass: "DoctorPass123!" },
  patient: { email: "patient@carebridge.com", pass: "PatientPass123!" },
};

function clearClientChatState() {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.clear();
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && (key.startsWith("carebridge_chat_") || key.includes("session") || key.includes("draft") || key === "carebridge_active_session_id")) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach((k) => localStorage.removeItem(k));
  } catch (e) {
    console.warn("Notice clearing client chat state:", e);
  }
}

interface AuthContextType {
  user: AuthUser | null;
  role: UserRole | null;
  isLoading: boolean;
  login: (email: string, password?: string) => Promise<AuthUser>;
  logout: () => void;
  switchRoleDemo: (role: UserRole) => Promise<AuthUser>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();

  useEffect(() => {
    try {
      const stored = localStorage.getItem("carebridge_auth_user");
      if (stored) {
        const parsed = JSON.parse(stored) as AuthUser;
        if (parsed && parsed.token && parsed.role) {
          setUser(parsed);
          setIsLoading(false);
          return;
        }
      }
    } catch (e) {
      console.warn("Storage read error, clearing invalid auth state:", e);
      localStorage.removeItem("carebridge_auth_user");
    }
    setUser(null);
    setIsLoading(false);
  }, []);

  const login = async (email: string, password?: string): Promise<AuthUser> => {
    setIsLoading(true);
    try {
      // Clear previous user's chat state & drafts
      clearClientChatState();

      const res = await loginUser(email, password);
      const authUser: AuthUser = {
        id: res.id,
        name: res.name,
        email: res.email,
        role: res.role as UserRole,
        facility: res.facility,
        patient_id: res.patient_id,
        case_id: res.case_id,
        phone: res.phone,
        token: res.token,
      };

      setUser(authUser);
      try {
        localStorage.setItem("carebridge_auth_user", JSON.stringify(authUser));
      } catch (e) {
        console.warn("Failed to persist user session in localStorage:", e);
      }

      const targetPath = ROLE_HOME_PATHS[authUser.role] || "/coordinator";
      router.push(targetPath);
      return authUser;
    } catch (err: any) {
      console.error("Login failure:", err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    clearClientChatState();
    setUser(null);
    try {
      localStorage.removeItem("carebridge_auth_user");
    } catch {}
    router.push("/login");
  };

  const switchRoleDemo = async (targetRole: UserRole): Promise<AuthUser> => {
    const cred = DEMO_CREDENTIALS[targetRole];
    if (!cred) {
      throw new Error(`No demo credentials registered for role '${targetRole}'`);
    }
    return await login(cred.email, cred.pass);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        role: (user?.role as UserRole) || null,
        isLoading,
        login,
        logout,
        switchRoleDemo,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
