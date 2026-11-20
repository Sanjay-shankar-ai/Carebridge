"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Share2,
  FileText,
  User,
  Activity,
  Calendar,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  ShieldCheck,
  Copy,
  Check,
  Code,
  ExternalLink,
  Search,
  Filter,
  RefreshCw,
  Lock,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import {
  searchFHIRResources,
  fetchFHIRCapabilityStatement,
  validateFHIRPayload,
} from "../../services/api";

type FHIRResourceType =
  | "Patient"
  | "DiagnosticReport"
  | "ServiceRequest"
  | "Task"
  | "Appointment"
  | "Communication"
  | "Consent"
  | "AuditEvent";

const RESOURCE_META: Record<
  FHIRResourceType,
  { label: string; icon: any; description: string; profile: string }
> = {
  Patient: {
    label: "Patient",
    icon: User,
    description: "Demographics, identifiers, contact channels & language preferences",
    profile: "http://hl7.org/fhir/StructureDefinition/Patient",
  },
  DiagnosticReport: {
    label: "DiagnosticReport",
    icon: Activity,
    description: "Mammogram screening findings, BI-RADS codes & diagnostic interpretations",
    profile: "http://hl7.org/fhir/StructureDefinition/DiagnosticReport",
  },
  ServiceRequest: {
    label: "ServiceRequest",
    icon: FileText,
    description: "Inter-facility referrals, specialist radiology & oncology orders",
    profile: "http://hl7.org/fhir/StructureDefinition/ServiceRequest",
  },
  Task: {
    label: "Task",
    icon: CheckCircle2,
    description: "Care coordination workflows, navigation items & recovery plays",
    profile: "http://hl7.org/fhir/StructureDefinition/Task",
  },
  Appointment: {
    label: "Appointment",
    icon: Calendar,
    description: "Scheduled diagnostic procedures, consultations & attendance states",
    profile: "http://hl7.org/fhir/StructureDefinition/Appointment",
  },
  Communication: {
    label: "Communication",
    icon: Share2,
    description: "Patient exchanges, SMS/chat touchpoints & translated notifications",
    profile: "http://hl7.org/fhir/StructureDefinition/Communication",
  },
  Consent: {
    label: "Consent",
    icon: ShieldCheck,
    description: "Patient data sharing scopes, automated outreach & navigation permits",
    profile: "http://hl7.org/fhir/StructureDefinition/Consent",
  },
  AuditEvent: {
    label: "AuditEvent",
    icon: Lock,
    description: "Immutable security provenance, AI actions & clinical access records",
    profile: "http://hl7.org/fhir/StructureDefinition/AuditEvent",
  },
};

export default function FHIRInteroperabilityPage() {
  const { user, role, isLoading } = useAuth();
  const router = useRouter();

  const [activeResource, setActiveResource] = useState<FHIRResourceType>("Patient");
  const [bundleData, setBundleData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Inspector Modal State
  const [inspectModalOpen, setInspectModalOpen] = useState(false);
  const [selectedResource, setSelectedResource] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  // Validation Tool State
  const [validatorOpen, setValidatorOpen] = useState(false);
  const [validationInput, setValidationInput] = useState("");
  const [validationResult, setValidationResult] = useState<any>(null);
  const [validating, setValidating] = useState(false);

  // Capability Statement
  const [capabilityOpen, setCapabilityOpen] = useState(false);
  const [capabilityData, setCapabilityData] = useState<any>(null);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
      return;
    }
    if (user) {
      loadResourceBundle(activeResource);
    }
  }, [activeResource, user, isLoading]);

  const loadResourceBundle = async (type: FHIRResourceType) => {
    setLoading(true);
    setError(null);
    try {
      const res = await searchFHIRResources(type);
      setBundleData(res);
    } catch (err: any) {
      setError(err?.message || `Failed to fetch FHIR ${type} bundle.`);
      setBundleData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenInspector = (resource: any) => {
    setSelectedResource(resource);
    setInspectModalOpen(true);
    setCopied(false);
  };

  const handleCopyJSON = (data: any) => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenCapability = async () => {
    setCapabilityOpen(true);
    if (!capabilityData) {
      try {
        const cs = await fetchFHIRCapabilityStatement();
        setCapabilityData(cs);
      } catch (err) {
        console.error("Capability fetch error:", err);
      }
    }
  };

  const handleRunValidation = async () => {
    setValidating(true);
    setValidationResult(null);
    try {
      const parsed = JSON.parse(validationInput);
      const res = await validateFHIRPayload(activeResource, parsed);
      setValidationResult(res);
    } catch (err: any) {
      setValidationResult({
        resourceType: "OperationOutcome",
        issue: [
          {
            severity: "error",
            code: "invalid",
            diagnostics: err?.message || "Invalid JSON syntax",
          },
        ],
      });
    } finally {
      setValidating(false);
    }
  };

  const ActiveIcon = RESOURCE_META[activeResource].icon;

  return (
    <div className="min-h-screen bg-[#F8FAFC] pb-16">
      {/* Top Banner */}
      <div className="bg-white border-b border-[#E2E8F0] px-6 lg:px-8 py-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="px-2.5 py-0.5 rounded-full bg-[#E6F4F1] text-[#0F766E] border border-[#CCFBF1] text-xs font-semibold uppercase tracking-wider">
                  HL7 FHIR Interoperability
                </span>
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-xs font-mono font-medium">
                  Release 4 (v4.0.1)
                </span>
              </div>
              <h1 className="text-2xl font-bold text-[#0F172A] tracking-tight">
                FHIR R4 Healthcare Exchange Gateway
              </h1>
              <p className="text-sm text-[#64748B] mt-1 max-w-2xl">
                Interoperable clinical records synchronized with PostgreSQL 17. Exposes standard FHIR resources with role-isolated security boundaries.
              </p>
            </div>

            {/* Quick Actions */}
            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={handleOpenCapability}
                className="px-3.5 py-2 rounded-btn text-xs font-semibold text-[#0F766E] bg-[#E6F4F1] hover:bg-[#CCFBF1] border border-[#0F766E]/20 transition flex items-center gap-1.5 cursor-pointer"
              >
                <Code className="w-4 h-4" />
                <span>CapabilityStatement</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setValidatorOpen(true);
                  if (bundleData?.entry?.[0]?.resource) {
                    setValidationInput(JSON.stringify(bundleData.entry[0].resource, null, 2));
                  }
                }}
                className="px-3.5 py-2 rounded-btn text-xs font-semibold text-white bg-[#0F766E] hover:bg-[#0D655E] transition shadow-xs flex items-center gap-1.5 cursor-pointer"
              >
                <ShieldCheck className="w-4 h-4" />
                <span>Validate Resource</span>
              </button>
            </div>
          </div>

          {/* Resource Selector Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto mt-6 pt-2 border-t border-[#F1F5F9] no-scrollbar">
            {(Object.keys(RESOURCE_META) as FHIRResourceType[]).map((rType) => {
              const meta = RESOURCE_META[rType];
              const Icon = meta.icon;
              const isActive = activeResource === rType;
              return (
                <button
                  key={rType}
                  type="button"
                  onClick={() => setActiveResource(rType)}
                  className={`px-3 py-2 rounded-btn text-xs font-medium flex items-center gap-2 transition whitespace-nowrap cursor-pointer ${
                    isActive
                      ? "bg-[#0F766E] text-white shadow-xs"
                      : "text-[#475569] hover:text-[#0F172A] hover:bg-slate-100"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{meta.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="max-w-7xl mx-auto px-6 lg:px-8 mt-6">
        {/* Active Resource Card Header */}
        <div className="bg-white rounded-card border border-[#E2E8F0] p-5 mb-5 shadow-soft">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <div className="w-10 h-10 rounded-lg bg-[#E6F4F1] border border-[#CCFBF1] text-[#0F766E] flex items-center justify-center shrink-0">
                <ActiveIcon className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-[#0F172A]">
                    FHIR {RESOURCE_META[activeResource].label} Resources
                  </h2>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-mono">
                    Total: {bundleData?.total ?? (loading ? "..." : 0)}
                  </span>
                </div>
                <p className="text-xs text-[#64748B] mt-0.5">
                  {RESOURCE_META[activeResource].description}
                </p>
                <div className="flex items-center gap-1.5 mt-2 text-[11px] text-[#0F766E] font-mono">
                  <span>Profile:</span>
                  <a
                    href={RESOURCE_META[activeResource].profile}
                    target="_blank"
                    rel="noreferrer"
                    className="hover:underline flex items-center gap-0.5 text-xs text-[#0F766E]"
                  >
                    <span>{RESOURCE_META[activeResource].profile}</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => loadResourceBundle(activeResource)}
                disabled={loading}
                className="p-2 rounded-btn border border-[#E2E8F0] hover:bg-slate-50 text-[#475569] transition cursor-pointer"
                title="Refresh resources"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-[#0F766E]" : ""}`} />
              </button>
            </div>
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="p-4 rounded-card bg-[#FEF2F2] border border-[#FEE2E2] text-xs text-[#991B1B] mb-5 flex items-center gap-2.5">
            <AlertTriangle className="w-4 h-4 shrink-0 text-[#DC2626]" />
            <span>{error}</span>
          </div>
        )}

        {/* Resources Grid / Table */}
        {loading ? (
          <div className="bg-white rounded-card border border-[#E2E8F0] p-12 text-center shadow-soft">
            <RefreshCw className="w-8 h-8 text-[#0F766E] animate-spin mx-auto mb-3" />
            <p className="text-sm font-medium text-[#0F172A]">Querying PostgreSQL & Serializing FHIR R4 Bundle...</p>
            <p className="text-xs text-[#64748B] mt-1">Applying patient isolation and role-based access checks</p>
          </div>
        ) : !bundleData?.entry || bundleData.entry.length === 0 ? (
          <div className="bg-white rounded-card border border-[#E2E8F0] p-12 text-center shadow-soft">
            <FileText className="w-10 h-10 text-[#94A3B8] mx-auto mb-3" />
            <p className="text-sm font-semibold text-[#0F172A]">No FHIR {activeResource} resources found</p>
            <p className="text-xs text-[#64748B] mt-1">
              {role === "patient"
                ? "No records are currently linked to your patient profile."
                : "No matching entries found in the current care database."}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {bundleData.entry.map((entryItem: any, idx: number) => {
              const res = entryItem.resource;
              const resId = res.id;
              const resStatus = res.status || "active";

              // Extract preview labels based on resource type
              let titleText = `${res.resourceType} #${resId.slice(0, 8)}...`;
              let subtitleText = "HL7 FHIR Resource";

              if (res.resourceType === "Patient") {
                const nameObj = res.name?.[0];
                titleText = nameObj?.text || `${nameObj?.given?.join(" ")} ${nameObj?.family}`;
                subtitleText = `MRN: ${res.identifier?.[0]?.value || "N/A"} • Gender: ${res.gender} • DOB: ${res.birthDate}`;
              } else if (res.resourceType === "DiagnosticReport") {
                titleText = res.code?.text || "Diagnostic Screening";
                subtitleText = `${res.conclusion || "Final report"} • Performed: ${res.effectiveDateTime?.slice(0, 10)}`;
              } else if (res.resourceType === "ServiceRequest") {
                titleText = `Referral: ${res.code?.text || "Specialist Care"}`;
                subtitleText = `Requester: ${res.requester?.display || "CareBridge"} • Target: ${res.performer?.[0]?.display || "Specialty Facility"}`;
              } else if (res.resourceType === "Task") {
                titleText = res.code?.text || res.description || "Care Coordination Task";
                subtitleText = `Assigned: ${res.owner?.display || "Coordinator"} • Priority: ${res.priority}`;
              } else if (res.resourceType === "Appointment") {
                titleText = res.description || `Visit: ${res.serviceType?.[0]?.text || "Procedure"}`;
                subtitleText = `Scheduled: ${new Date(res.start).toLocaleString()} • Status: ${res.status}`;
              } else if (res.resourceType === "Communication") {
                titleText = `Communication (${res.medium?.[0]?.text || "in_app_chat"})`;
                subtitleText = `Payload: ${res.payload?.[0]?.contentString?.slice(0, 60)}...`;
              } else if (res.resourceType === "Consent") {
                titleText = `Consent: ${res.category?.[0]?.text || "Privacy Scope"}`;
                subtitleText = `Provision: ${res.provision?.type} • Granted: ${res.dateTime?.slice(0, 10)}`;
              } else if (res.resourceType === "AuditEvent") {
                titleText = `Audit: ${res.subtype?.[0]?.code || res.action}`;
                subtitleText = `${res.outcomeDesc || "REST operation"} • Recorded: ${new Date(res.recorded).toLocaleString()}`;
              }

              return (
                <div
                  key={resId || idx}
                  className="bg-white rounded-card border border-[#E2E8F0] p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:border-[#0F766E]/40 transition shadow-soft"
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="w-8 h-8 rounded bg-slate-50 border border-slate-200 text-[#0F766E] flex items-center justify-center shrink-0 mt-0.5">
                      <ActiveIcon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-[#0F172A] truncate">
                          {titleText}
                        </span>
                        <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-mono font-medium">
                          {res.resourceType}/{resId.slice(0, 8)}...
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                            resStatus === "active" || resStatus === "final" || resStatus === "booked" || resStatus === "completed"
                              ? "bg-[#E6F4F1] text-[#0F766E] border border-[#CCFBF1]"
                              : resStatus === "urgent" || resStatus === "critical"
                              ? "bg-[#FEE2E2] text-[#991B1B]"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {resStatus}
                        </span>
                      </div>
                      <p className="text-xs text-[#64748B] mt-1 truncate">{subtitleText}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                    <button
                      type="button"
                      onClick={() => handleOpenInspector(res)}
                      className="px-3 py-1.5 rounded-btn text-xs font-semibold text-[#0F766E] bg-[#E6F4F1] hover:bg-[#CCFBF1] transition flex items-center gap-1.5 cursor-pointer"
                    >
                      <Code className="w-3.5 h-3.5" />
                      <span>Inspect JSON</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* JSON Inspector Modal */}
      {inspectModalOpen && selectedResource && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-card max-w-3xl w-full max-h-[85vh] flex flex-col border border-[#E2E8F0] shadow-xl animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-4 border-b border-[#E2E8F0] flex items-center justify-between bg-[#F8FAFC]">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-[#E6F4F1] border border-[#CCFBF1] text-[#0F766E] flex items-center justify-center">
                  <Code className="w-3.5 h-3.5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[#0F172A]">
                    {selectedResource.resourceType}/{selectedResource.id}
                  </h3>
                  <p className="text-[11px] text-[#64748B]">HL7 FHIR Release 4 JSON Representation</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleCopyJSON(selectedResource)}
                  className="px-2.5 py-1 rounded-btn text-xs font-medium text-[#475569] hover:text-[#0F172A] bg-white border border-[#E2E8F0] transition flex items-center gap-1.5 cursor-pointer"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-[#0F766E]" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copied ? "Copied!" : "Copy JSON"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setInspectModalOpen(false)}
                  className="w-7 h-7 rounded-full text-slate-400 hover:text-slate-600 flex items-center justify-center cursor-pointer"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Modal Code Viewer */}
            <div className="p-4 overflow-y-auto font-mono text-xs bg-[#0F172A] text-[#F8FAFC] flex-1">
              <pre className="whitespace-pre-wrap leading-relaxed">
                {JSON.stringify(selectedResource, null, 2)}
              </pre>
            </div>

            {/* Modal Footer */}
            <div className="p-3 border-t border-[#E2E8F0] bg-[#F8FAFC] flex items-center justify-between text-xs text-[#64748B]">
              <span>Standard: FHIR R4 (application/fhir+json)</span>
              <button
                type="button"
                onClick={() => setInspectModalOpen(false)}
                className="px-3 py-1.5 rounded-btn bg-white border border-[#E2E8F0] text-xs font-medium text-[#0F172A] hover:bg-slate-50 cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Capability Statement Modal */}
      {capabilityOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-card max-w-3xl w-full max-h-[85vh] flex flex-col border border-[#E2E8F0] shadow-xl animate-in fade-in zoom-in-95 duration-150">
            <div className="p-4 border-b border-[#E2E8F0] flex items-center justify-between bg-[#F8FAFC]">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-[#E6F4F1] border border-[#CCFBF1] text-[#0F766E] flex items-center justify-center">
                  <ShieldCheck className="w-3.5 h-3.5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[#0F172A]">CareBridge CapabilityStatement</h3>
                  <p className="text-[11px] text-[#64748B]">GET /api/v1/fhir/metadata</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setCapabilityOpen(false)}
                className="w-7 h-7 rounded-full text-slate-400 hover:text-slate-600 flex items-center justify-center cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="p-4 overflow-y-auto font-mono text-xs bg-[#0F172A] text-[#F8FAFC] flex-1">
              <pre className="whitespace-pre-wrap leading-relaxed">
                {capabilityData
                  ? JSON.stringify(capabilityData, null, 2)
                  : "Loading CapabilityStatement from server..."}
              </pre>
            </div>

            <div className="p-3 border-t border-[#E2E8F0] bg-[#F8FAFC] flex items-center justify-between text-xs text-[#64748B]">
              <span>Endpoint: /api/v1/fhir/metadata</span>
              <button
                type="button"
                onClick={() => setCapabilityOpen(false)}
                className="px-3 py-1.5 rounded-btn bg-white border border-[#E2E8F0] text-xs font-medium text-[#0F172A] hover:bg-slate-50 cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Inbound Validator Modal */}
      {validatorOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-card max-w-3xl w-full max-h-[85vh] flex flex-col border border-[#E2E8F0] shadow-xl animate-in fade-in zoom-in-95 duration-150">
            <div className="p-4 border-b border-[#E2E8F0] flex items-center justify-between bg-[#F8FAFC]">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded bg-[#E6F4F1] border border-[#CCFBF1] text-[#0F766E] flex items-center justify-center">
                  <ShieldCheck className="w-3.5 h-3.5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[#0F172A]">
                    FHIR R4 Schema Validator ($validate)
                  </h3>
                  <p className="text-[11px] text-[#64748B]">
                    Validates against official HL7 FHIR {activeResource} specifications
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setValidatorOpen(false)}
                className="w-7 h-7 rounded-full text-slate-400 hover:text-slate-600 flex items-center justify-center cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="p-4 overflow-y-auto space-y-4 flex-1">
              <div>
                <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                  FHIR {activeResource} Payload (JSON):
                </label>
                <textarea
                  value={validationInput}
                  onChange={(e) => setValidationInput(e.target.value)}
                  rows={10}
                  className="w-full font-mono text-xs p-3 rounded-btn border border-[#E2E8F0] bg-slate-50 focus:bg-white focus:outline-hidden focus:border-[#0F766E] transition"
                  placeholder='{ "resourceType": "...", ... }'
                />
              </div>

              {validationResult && (
                <div
                  className={`p-3.5 rounded-card border text-xs ${
                    validationResult.issue?.[0]?.severity === "information"
                      ? "bg-[#E6F4F1] border-[#CCFBF1] text-[#0F766E]"
                      : "bg-[#FEF2F2] border-[#FEE2E2] text-[#991B1B]"
                  }`}
                >
                  <div className="flex items-center gap-2 font-semibold">
                    {validationResult.issue?.[0]?.severity === "information" ? (
                      <CheckCircle2 className="w-4 h-4 text-[#0F766E]" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-[#DC2626]" />
                    )}
                    <span>OperationOutcome: {validationResult.issue?.[0]?.severity.toUpperCase()}</span>
                  </div>
                  <p className="mt-1 font-mono text-[11px] leading-relaxed">
                    {validationResult.issue?.[0]?.diagnostics}
                  </p>
                </div>
              )}
            </div>

            <div className="p-3 border-t border-[#E2E8F0] bg-[#F8FAFC] flex items-center justify-between">
              <span className="text-xs text-[#64748B]">POST /api/v1/fhir/{activeResource}/validate</span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setValidatorOpen(false)}
                  className="px-3 py-1.5 rounded-btn bg-white border border-[#E2E8F0] text-xs font-medium text-[#0F172A] hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleRunValidation}
                  disabled={validating || !validationInput.trim()}
                  className="px-4 py-1.5 rounded-btn bg-[#0F766E] hover:bg-[#0D655E] text-xs font-semibold text-white transition shadow-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {validating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                  <span>Validate against FHIR R4</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
