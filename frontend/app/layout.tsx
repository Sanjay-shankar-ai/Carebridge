import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "../context/AuthContext";
import { ToastProvider } from "../components/ui/Toast";
import Sidebar from "../components/Sidebar";
import Header from "../components/Header";

export const metadata: Metadata = {
  title: "CareBridge — Closed-Loop Care Coordination",
  description:
    "Intelligent screening-to-care tracking, proactive recovery, and role-based clinical collaboration.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full bg-[#F8FAFC] text-[#0F172A] antialiased selection:bg-[#E6F4F1] selection:text-[#0F766E] overflow-hidden">
        <AuthProvider>
          <ToastProvider>
            {/* Fixed full-viewport shell — nothing outside this scrolls */}
            <div className="flex h-full w-full overflow-hidden">
              <Sidebar />
              <div className="flex flex-col flex-1 min-w-0 h-full overflow-hidden">
                <Header />
                {/* Only this inner area scrolls */}
                <main className="flex-1 overflow-y-auto p-4 sm:p-6 md:p-8">
                  <div className="max-w-[1280px] w-full mx-auto">{children}</div>
                </main>
              </div>
            </div>
          </ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
