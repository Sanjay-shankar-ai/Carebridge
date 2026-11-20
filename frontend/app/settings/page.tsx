"use client";

import { useState } from "react";
import {
  Settings,
  Shield,
  Sliders,
  Cpu,
  Clock,
  Languages,
  CheckCircle2,
  Save,
  RotateCcw,
  AlertTriangle,
  Radio,
  Lock,
  MessageSquare,
  KeyRound,
} from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export default function SettingsPage() {
  const [provider, setProvider] = useState("groq");
  const [groqModel, setGroqModel] = useState("openai/gpt-oss-120b");
  const [temperature, setTemperature] = useState(0.1);

  // SLA Timers (Hours/Days)
  const [notificationSLA, setNotificationSLA] = useState(24);
  const [referralSLA, setReferralSLA] = useState(48);
  const [appointmentSLA, setAppointmentSLA] = useState(14);
  const [closureSLA, setClosureSLA] = useState(60);
  const [inactivityDays, setInactivityDays] = useState(5);

  // Autonomy Toggles
  const [l1AutoDispatch, setL1AutoDispatch] = useState(true);
  const [l2SmartReschedule, setL2SmartReschedule] = useState(true);
  const [l3StrictPhysicianGate, setL3StrictPhysicianGate] = useState(true);

  // Channels
  const [channelWhatsApp, setChannelWhatsApp] = useState(true);
  const [channelSMS, setChannelSMS] = useState(true);
  const [channelPortal, setChannelPortal] = useState(true);

  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSave = () => {
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3500);
  };

  const handleReset = () => {
    setProvider("groq");
    setGroqModel("openai/gpt-oss-120b");
    setTemperature(0.1);
    setNotificationSLA(24);
    setReferralSLA(48);
    setAppointmentSLA(14);
    setClosureSLA(60);
    setInactivityDays(5);
    setL1AutoDispatch(true);
    setL2SmartReschedule(true);
    setL3StrictPhysicianGate(true);
  };

  return (
    <div className="space-y-6 max-w-[1200px] mx-auto pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4F1] text-[#0F766E] text-xs font-semibold mb-2">
            <Sliders className="w-3.5 h-3.5" />
            System Governance & Parameters
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-[#0F172A] tracking-tight">
            Platform Configuration
          </h1>
          <p className="text-sm text-[#475569] mt-1">
            Configure LLM reasoning models, clinical turnaround SLAs, and AI autonomy safety gates.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="secondary"
            onClick={handleReset}
            icon={<RotateCcw className="w-3.5 h-3.5" />}
          >
            Reset Defaults
          </Button>
          <Button
            variant="primary"
            onClick={handleSave}
            icon={<Save className="w-3.5 h-3.5" />}
          >
            Save Changes
          </Button>
        </div>
      </div>

      {/* Save Success Banner */}
      {savedSuccess && (
        <div className="bg-[#E6F4F1] border border-[#0F766E]/20 rounded-card p-4 flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-[#0F766E] shrink-0" />
          <div>
            <h4 className="text-xs font-semibold text-[#0F766E] uppercase tracking-wider">
              Governance Configuration Persisted
            </h4>
            <p className="text-xs text-[#0F172A] mt-0.5">
              Reasoning parameters, SLA thresholds, and clinical gates successfully synchronized.
            </p>
          </div>
        </div>
      )}

      {/* Grid of Settings Sections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Section 1: AI Reasoning & LLM Configuration */}
        <Card className="p-6 space-y-4">
          <div className="flex items-center gap-2.5 pb-3 border-b border-[#E2E8F0]">
            <div className="w-9 h-9 rounded-btn bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center font-bold">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-[#0F172A] text-sm">LLM Engine & Groq Inference</h3>
              <p className="text-xs text-[#475569]">Primary cognitive loop and fallback provider</p>
            </div>
          </div>

          <div className="space-y-4 text-xs">
            <div>
              <label htmlFor="providerSelect" className="block text-[#0F172A] font-semibold mb-1.5">
                Inference Provider
              </label>
              <select
                id="providerSelect"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full h-11 bg-white border border-[#E2E8F0] rounded-btn px-3.5 py-2 text-sm text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2"
              >
                <option value="groq">GroqCloud (Ultra-low latency LPU inference)</option>
                <option value="openai">OpenAI Direct (Fallback provider)</option>
              </select>
            </div>

            <Input
              label="Model Architecture"
              type="text"
              value={groqModel}
              onChange={(e) => setGroqModel(e.target.value)}
            />

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label htmlFor="tempSlider" className="text-[#0F172A] font-semibold text-xs">
                  Sampling Temperature
                </label>
                <span className="font-mono text-[#0F766E] font-bold">{temperature}</span>
              </div>
              <input
                id="tempSlider"
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
                className="w-full accent-[#0F766E]"
              />
              <span className="text-xs text-[#475569] mt-1 block">
                Deterministic low temperature (0.1) enforced for clinical protocol safety.
              </span>
            </div>
          </div>
        </Card>

        {/* Section 2: Clinical SLA Targets */}
        <Card className="p-6 space-y-4">
          <div className="flex items-center gap-2.5 pb-3 border-b border-[#E2E8F0]">
            <div className="w-9 h-9 rounded-btn bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center font-bold">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-[#0F172A] text-sm">Clinical SLA Targets</h3>
              <p className="text-xs text-[#475569]">Maximum allowable turnaround before escalation</p>
            </div>
          </div>

          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Result to Outreach"
                type="number"
                value={notificationSLA}
                onChange={(e) => setNotificationSLA(parseInt(e.target.value))}
                helperText="Target: 24 Hours"
              />

              <Input
                label="Referral Acceptance"
                type="number"
                value={referralSLA}
                onChange={(e) => setReferralSLA(parseInt(e.target.value))}
                helperText="Target: 48 Hours"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Diagnostic Visit"
                type="number"
                value={appointmentSLA}
                onChange={(e) => setAppointmentSLA(parseInt(e.target.value))}
                helperText="Target: 14 Days"
              />

              <Input
                label="Verified Case Closure"
                type="number"
                value={closureSLA}
                onChange={(e) => setClosureSLA(parseInt(e.target.value))}
                helperText="Target: 60 Days"
              />
            </div>
          </div>
        </Card>

        {/* Section 3: Safety Guardrails & Autonomy Levels */}
        <Card className="p-6 space-y-4 lg:col-span-2">
          <div className="flex items-center gap-2.5 pb-3 border-b border-[#E2E8F0]">
            <div className="w-9 h-9 rounded-btn bg-amber-50 text-amber-700 flex items-center justify-center font-bold">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-[#0F172A] text-sm">Autonomy Guardrails & Clinician Gates</h3>
              <p className="text-xs text-[#475569]">Deterministic human-in-the-loop verification rules</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
            <label className="flex items-start gap-3 p-4 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] cursor-pointer hover:border-[#0F766E]/40 transition">
              <input
                type="checkbox"
                checked={l1AutoDispatch}
                onChange={(e) => setL1AutoDispatch(e.target.checked)}
                className="mt-1 accent-[#0F766E] rounded"
              />
              <div>
                <span className="font-semibold text-[#0F172A] block">Level 1: Auto Patient Outreach</span>
                <span className="text-xs text-[#475569] mt-0.5 block leading-relaxed">
                  Translate and dispatch screening notifications within 24h of abnormal lab result.
                </span>
              </div>
            </label>

            <label className="flex items-start gap-3 p-4 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] cursor-pointer hover:border-[#0F766E]/40 transition">
              <input
                type="checkbox"
                checked={l2SmartReschedule}
                onChange={(e) => setL2SmartReschedule(e.target.checked)}
                className="mt-1 accent-[#0F766E] rounded"
              />
              <div>
                <span className="font-semibold text-[#0F172A] block">Level 2: Adaptive Rescheduling</span>
                <span className="text-xs text-[#475569] mt-0.5 block leading-relaxed">
                  Allow recovery agent to align slots based on patient caregiver availability.
                </span>
              </div>
            </label>

            <label className="flex items-start gap-3 p-4 rounded-card bg-[#F8FAFC] border border-[#E2E8F0] cursor-pointer hover:border-[#0F766E]/40 transition">
              <input
                type="checkbox"
                checked={l3StrictPhysicianGate}
                onChange={(e) => setL3StrictPhysicianGate(e.target.checked)}
                className="mt-1 accent-[#0F766E] rounded"
              />
              <div>
                <span className="font-semibold text-[#0F172A] block">Level 3: Strict Clinician Gate</span>
                <span className="text-xs text-[#475569] mt-0.5 block leading-relaxed">
                  Zero AI closures: Case completion strictly requires licensed physician pathology sign-off.
                </span>
              </div>
            </label>
          </div>
        </Card>
      </div>
    </div>
  );
}
