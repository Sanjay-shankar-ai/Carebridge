"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  HeartPulse,
  ArrowRight,
  ShieldCheck,
  Stethoscope,
  UserCheck,
  Mail,
  Lock,
  CheckCircle2,
  AlertCircle,
  UserPlus,
  LogIn,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { UserRole } from "../../types";
import { registerPatient, registerDoctor } from "../../services/api";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Input } from "../../components/ui/Input";

export default function LoginPage() {
  const [activeTab, setActiveTab] = useState<"login" | "register">("login");
  const [registerRole, setRegisterRole] = useState<"patient" | "doctor">("patient");

  // Login Form State
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Registration Form State
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regFirstName, setRegFirstName] = useState("");
  const [regLastName, setRegLastName] = useState("");
  const [regFullName, setRegFullName] = useState("");
  const [regFacility, setRegFacility] = useState("Clinic A - Women's Specialty Breast Center");
  const [regSpecialty, setRegSpecialty] = useState("Breast Oncology");
  const [regPhone, setRegPhone] = useState("+91-98765-00000");
  const [regError, setRegError] = useState("");
  const [regSuccess, setRegSuccess] = useState("");

  const { login, switchRoleDemo } = useAuth();
  const router = useRouter();

  const handleLoginFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setLoginError("Please enter your registered email address.");
      return;
    }

    setLoginError("");
    setIsSubmitting(true);
    try {
      await login(email.trim(), password);
    } catch (err: any) {
      setLoginError(err.message || "Authentication failed. Please verify your credentials.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickLogin = async (role: UserRole) => {
    setLoginError("");
    setIsSubmitting(true);
    try {
      await switchRoleDemo(role);
    } catch (err: any) {
      setLoginError(err.message || `Failed to authenticate persona for ${role}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setRegError("");
    setRegSuccess("");
    setIsSubmitting(true);

    try {
      if (registerRole === "patient") {
        if (!regEmail.trim() || !regFirstName.trim() || !regLastName.trim()) {
          setRegError("Please fill in email, first name, and last name.");
          setIsSubmitting(false);
          return;
        }
        const res = await registerPatient({
          email: regEmail.trim(),
          password: regPassword || "PatientPass123!",
          first_name: regFirstName.trim(),
          last_name: regLastName.trim(),
          phone: regPhone,
          preferred_language: "en",
        });
        setRegSuccess(`Patient account created successfully for ${res.name}! Logging you in...`);
        setTimeout(() => {
          login(regEmail.trim(), regPassword || "PatientPass123!");
        }, 1200);
      } else {
        if (!regEmail.trim() || !regFullName.trim()) {
          setRegError("Please fill in email and full doctor name.");
          setIsSubmitting(false);
          return;
        }
        const res = await registerDoctor({
          email: regEmail.trim(),
          password: regPassword || "DoctorPass123!",
          full_name: regFullName.trim(),
          facility: regFacility,
          specialty: regSpecialty,
          phone: regPhone,
        });
        setRegSuccess(`Doctor account created successfully for ${res.name}! Logging you in...`);
        setTimeout(() => {
          login(regEmail.trim(), regPassword || "DoctorPass123!");
        }, 1200);
      }
    } catch (err: any) {
      setRegError(err.message || "Registration failed. Email may already be registered.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen -m-6 md:-m-8 bg-[#F8FAFC] flex items-center justify-center p-4 md:p-8">
      <div className="w-full max-w-4xl bg-white rounded-card border border-[#E2E8F0] shadow-soft overflow-hidden grid grid-cols-1 md:grid-cols-12 min-h-[620px]">
        {/* Left Side: Brand & Governance Overview */}
        <div className="md:col-span-5 bg-[#0F172A] p-8 text-white flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-btn bg-[#0F766E] text-white flex items-center justify-center">
                <HeartPulse className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-white">CareBridge</h1>
                <p className="text-xs text-[#94A3B8]">Autonomous Closed-Loop Health</p>
              </div>
            </div>

            <h2 className="text-xl font-semibold text-white leading-snug mb-3">
              Role-Based Identity & Audit Security
            </h2>
            <p className="text-xs text-[#94A3B8] leading-relaxed">
              Every request is authenticated against database-backed roles (Doctor, Patient, Coordinator) with cryptographic JWT isolation.
            </p>

            {/* Core Trust Signals */}
            <div className="mt-8 space-y-3.5 text-xs">
              <div className="flex items-start gap-2.5">
                <CheckCircle2 className="w-4 h-4 text-[#0F766E] shrink-0 mt-0.5" />
                <span className="text-[#CBD5E1]">
                  <strong>Strict Session Isolation:</strong> Separate LangGraph threads per user & case.
                </span>
              </div>
              <div className="flex items-start gap-2.5">
                <CheckCircle2 className="w-4 h-4 text-[#0F766E] shrink-0 mt-0.5" />
                <span className="text-[#CBD5E1]">
                  <strong>Level 3 Clinical Gatekeeping:</strong> Clinician sign-off required for case closure.
                </span>
              </div>
              <div className="flex items-start gap-2.5">
                <CheckCircle2 className="w-4 h-4 text-[#0F766E] shrink-0 mt-0.5" />
                <span className="text-[#CBD5E1]">
                  <strong>Zero Cross-Bleed:</strong> Patient data strictly isolated from other accounts.
                </span>
              </div>
            </div>
          </div>

          <div className="pt-6 border-t border-[#1E293B] flex items-center gap-2 text-xs text-[#94A3B8]">
            <ShieldCheck className="w-4 h-4 text-[#0F766E]" />
            <span>Cryptographic Bcrypt & JWT Protected</span>
          </div>
        </div>

        {/* Right Side: Unified Authentication */}
        <div className="md:col-span-7 p-8 md:p-10 flex flex-col justify-between bg-white overflow-y-auto max-h-[85vh]">
          <div>
            {/* Header Tabs */}
            <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3 mb-6">
              <div>
                <h2 className="text-2xl font-semibold text-[#0F172A] tracking-tight">
                  {activeTab === "login" ? "Sign In to CareBridge" : "Create New Account"}
                </h2>
                <p className="text-xs text-[#475569] mt-1">
                  {activeTab === "login"
                    ? "Enter your credentials or use 1-click verified role access below."
                    : "Register as a new Patient or Clinician with unique identity."}
                </p>
              </div>

              <div className="flex gap-1 p-1 bg-[#F1F5F9] rounded-btn">
                <button
                  type="button"
                  onClick={() => setActiveTab("login")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-btn transition ${
                    activeTab === "login"
                      ? "bg-white text-[#0F172A] shadow-xs"
                      : "text-[#64748B] hover:text-[#0F172A]"
                  }`}
                >
                  Login
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("register")}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-btn transition ${
                    activeTab === "register"
                      ? "bg-white text-[#0F172A] shadow-xs"
                      : "text-[#64748B] hover:text-[#0F172A]"
                  }`}
                >
                  Register
                </button>
              </div>
            </div>

            {/* TAB 1: LOGIN FORM */}
            {activeTab === "login" && (
              <div>
                <form onSubmit={handleLoginFormSubmit} className="space-y-4">
                  {loginError && (
                    <div className="p-3 rounded-btn bg-[#FEE2E2] border border-[#FCA5A5] text-[#991B1B] text-xs flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0" />
                      <span>{loginError}</span>
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-[#0F172A] mb-1.5">
                      Email Address
                    </label>
                    <div className="relative">
                      <Input
                        type="email"
                        placeholder="e.g. doctor@carebridge.com or your email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                        className="pl-9 text-xs"
                      />
                      <Mail className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-[#0F172A] mb-1.5">
                      Password
                    </label>
                    <div className="relative">
                      <Input
                        type="password"
                        placeholder="Enter your account password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="pl-9 text-xs"
                      />
                      <Lock className="w-4 h-4 text-[#94A3B8] absolute left-3 top-1/2 -translate-y-1/2" />
                    </div>
                  </div>

                  <Button
                    type="submit"
                    variant="primary"
                    size="md"
                    isLoading={isSubmitting}
                    rightIcon={<LogIn className="w-4 h-4" />}
                    className="w-full font-semibold"
                  >
                    Authenticate & Access Dashboard
                  </Button>
                </form>

                {/* 1-Click Verified Role Personas */}
                <div className="mt-6 pt-5 border-t border-[#E2E8F0]">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-[#64748B] block mb-3">
                    Or 1-Click Login as Verified Role:
                  </span>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => handleQuickLogin("care_coordinator")}
                      className="p-3 text-left rounded-btn border border-[#E2E8F0] bg-white hover:bg-[#F8FAFC] hover:border-[#0F766E] transition flex items-start gap-2.5 cursor-pointer group"
                    >
                      <div className="w-8 h-8 rounded-btn bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center shrink-0">
                        <UserCheck className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <span className="font-semibold text-xs text-[#0F172A] block truncate">
                          Priya Nair, RN
                        </span>
                        <span className="text-[11px] text-[#475569] block">
                          Care Coordinator
                        </span>
                      </div>
                    </button>

                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => handleQuickLogin("doctor")}
                      className="p-3 text-left rounded-btn border border-[#E2E8F0] bg-white hover:bg-[#F8FAFC] hover:border-[#0F766E] transition flex items-start gap-2.5 cursor-pointer group"
                    >
                      <div className="w-8 h-8 rounded-btn bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center shrink-0">
                        <Stethoscope className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <span className="font-semibold text-xs text-[#0F172A] block truncate">
                          Dr. Aris Thorne, MD
                        </span>
                        <span className="text-[11px] text-[#475569] block">
                          Doctor / Clinician
                        </span>
                      </div>
                    </button>

                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => handleQuickLogin("patient")}
                      className="p-3 text-left rounded-btn border border-[#E2E8F0] bg-white hover:bg-[#F8FAFC] hover:border-[#0F766E] transition flex items-start gap-2.5 cursor-pointer group"
                    >
                      <div className="w-8 h-8 rounded-btn bg-[#DCFCE7] text-[#15803D] flex items-center justify-center shrink-0">
                        <HeartPulse className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <span className="font-semibold text-xs text-[#0F172A] block truncate">
                          Meenakshi Ramanathan
                        </span>
                        <span className="text-[11px] text-[#475569] block">
                          Patient Portal (P-0147)
                        </span>
                      </div>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: REGISTRATION FORM */}
            {activeTab === "register" && (
              <form onSubmit={handleRegisterSubmit} className="space-y-4">
                {regError && (
                  <div className="p-3 rounded-btn bg-[#FEE2E2] border border-[#FCA5A5] text-[#991B1B] text-xs flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{regError}</span>
                  </div>
                )}
                {regSuccess && (
                  <div className="p-3 rounded-btn bg-[#DCFCE7] border border-[#86EFAC] text-[#166534] text-xs flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                    <span>{regSuccess}</span>
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setRegisterRole("patient")}
                    className={`flex-1 py-2 text-xs font-semibold rounded-btn border transition ${
                      registerRole === "patient"
                        ? "bg-[#E6F4F1] border-[#0F766E] text-[#0F766E]"
                        : "border-[#E2E8F0] text-[#64748B] hover:bg-[#F8FAFC]"
                    }`}
                  >
                    Patient Account
                  </button>
                  <button
                    type="button"
                    onClick={() => setRegisterRole("doctor")}
                    className={`flex-1 py-2 text-xs font-semibold rounded-btn border transition ${
                      registerRole === "doctor"
                        ? "bg-[#E6F4F1] border-[#0F766E] text-[#0F766E]"
                        : "border-[#E2E8F0] text-[#64748B] hover:bg-[#F8FAFC]"
                    }`}
                  >
                    Doctor / Specialist Account
                  </button>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                    Email Address
                  </label>
                  <Input
                    type="email"
                    placeholder="e.g. new.patient@example.com"
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    required
                    className="text-xs"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                    Password
                  </label>
                  <Input
                    type="password"
                    placeholder="Create a secure password (min 6 characters)"
                    value={regPassword}
                    onChange={(e) => setRegPassword(e.target.value)}
                    required
                    className="text-xs"
                  />
                </div>

                {registerRole === "patient" ? (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                        First Name
                      </label>
                      <Input
                        type="text"
                        placeholder="First name"
                        value={regFirstName}
                        onChange={(e) => setRegFirstName(e.target.value)}
                        required
                        className="text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                        Last Name
                      </label>
                      <Input
                        type="text"
                        placeholder="Last name"
                        value={regLastName}
                        onChange={(e) => setRegLastName(e.target.value)}
                        required
                        className="text-xs"
                      />
                    </div>
                  </div>
                ) : (
                  <>
                    <div>
                      <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                        Full Doctor Name
                      </label>
                      <Input
                        type="text"
                        placeholder="e.g. Dr. Maya Patel, MD"
                        value={regFullName}
                        onChange={(e) => setRegFullName(e.target.value)}
                        required
                        className="text-xs"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                          Facility
                        </label>
                        <Input
                          type="text"
                          value={regFacility}
                          onChange={(e) => setRegFacility(e.target.value)}
                          className="text-xs"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                          Specialty
                        </label>
                        <Input
                          type="text"
                          value={regSpecialty}
                          onChange={(e) => setRegSpecialty(e.target.value)}
                          className="text-xs"
                        />
                      </div>
                    </div>
                  </>
                )}

                <Button
                  type="submit"
                  variant="primary"
                  size="md"
                  isLoading={isSubmitting}
                  rightIcon={<UserPlus className="w-4 h-4" />}
                  className="w-full font-semibold"
                >
                  Create Registered {registerRole === "patient" ? "Patient" : "Doctor"} Account
                </Button>
              </form>
            )}
          </div>

          <p className="mt-6 text-center text-xs text-[#64748B]">
            CareBridge AI Healthcare Systems • Secure Multi-Tenant Governance
          </p>
        </div>
      </div>
    </div>
  );
}
