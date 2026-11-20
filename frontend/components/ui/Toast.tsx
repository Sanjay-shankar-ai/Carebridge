"use client";

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from "lucide-react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastItem {
  id: string;
  message: string;
  type?: ToastType;
}

interface ToastContextType {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextType>({
  toast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, type: ToastType = "success") => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);

    // Auto-dismiss after 4.5 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const icons: Record<ToastType, React.ReactNode> = {
    success: <CheckCircle2 className="w-4 h-4 text-[#15803D]" />,
    error: <AlertCircle className="w-4 h-4 text-[#B91C1C]" />,
    warning: <AlertTriangle className="w-4 h-4 text-[#B45309]" />,
    info: <Info className="w-4 h-4 text-[#0F766E]" />,
  };

  const borders: Record<ToastType, string> = {
    success: "border-l-4 border-l-[#15803D] bg-white border-[#E2E8F0]",
    error: "border-l-4 border-l-[#B91C1C] bg-white border-[#E2E8F0]",
    warning: "border-l-4 border-l-[#B45309] bg-white border-[#E2E8F0]",
    info: "border-l-4 border-l-[#0F766E] bg-white border-[#E2E8F0]",
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* Toast Corner Container */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto p-3.5 rounded-card border shadow-lg flex items-start gap-3 transition-all animate-in slide-in-from-bottom-5 duration-200 ${
              borders[t.type || "success"]
            }`}
          >
            <div className="mt-0.5 shrink-0">{icons[t.type || "success"]}</div>
            <p className="text-xs text-[#0F172A] leading-snug flex-1 font-medium">{t.message}</p>
            <button
              type="button"
              onClick={() => removeToast(t.id)}
              className="p-1 text-[#94A3B8] hover:text-[#0F172A] rounded-btn cursor-pointer shrink-0"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
