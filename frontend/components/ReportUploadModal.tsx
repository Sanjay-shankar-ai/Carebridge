"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Upload,
  FileText,
  CheckCircle2,
  AlertTriangle,
  X,
  RefreshCw,
  Eye,
  FileCheck,
  ShieldCheck,
  ArrowRight,
} from "lucide-react";
import { Modal } from "./ui/Modal";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";

export interface CaseOption {
  id: string;
  patient_name: string;
  case_number: string;
  screening_order_id?: string;
  screening_type?: string;
}

interface ReportUploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  caseId?: string;
  patientName?: string;
  screeningOrderId?: string;
  screeningType?: string;
  cases?: CaseOption[];
  onReportFinalized?: (result: any) => void;
}

export type ProcessingState =
  | "IDLE"
  | "UPLOADED"
  | "EXTRACTING"
  | "VALIDATING"
  | "READY_TO_FINALIZE"
  | "FINALIZED"
  | "REQUIRES_REVIEW"
  | "FAILED";

export const ReportUploadModal: React.FC<ReportUploadModalProps> = ({
  isOpen,
  onClose,
  caseId,
  patientName,
  screeningOrderId = "ORD-SCR-001",
  screeningType = "Mammogram",
  cases = [],
  onReportFinalized,
}) => {
  const [selectedCaseId, setSelectedCaseId] = useState(caseId || "");
  const [selectedOrderId, setSelectedOrderId] = useState(screeningOrderId || "ORD-SCR-001");
  const [selectedModality, setSelectedModality] = useState(screeningType || "Mammogram");

  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [progress, setProgress] = useState(0);
  const [processingState, setProcessingState] = useState<ProcessingState>("IDLE");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [extractedData, setExtractedData] = useState<any>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [requiresDoctorReview, setRequiresDoctorReview] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (caseId) {
      setSelectedCaseId(caseId);
    } else if (cases.length > 0 && !selectedCaseId) {
      setSelectedCaseId(cases[0].id);
      setSelectedOrderId(cases[0].screening_order_id || `ORD-${cases[0].case_number}`);
      if (cases[0].screening_type) setSelectedModality(cases[0].screening_type);
    }
  }, [caseId, cases]);

  const resetState = () => {
    setFile(null);
    setProgress(0);
    setProcessingState("IDLE");
    setErrorMessage(null);
    setExtractedData(null);
    setPreviewUrl(null);
    setIsFinalizing(false);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelection(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelection(e.target.files[0]);
    }
  };

  const handleFileSelection = (selectedFile: File) => {
    setErrorMessage(null);
    const allowed = ["application/pdf", "image/png", "image/jpeg", "image/jpg"];
    const ext = selectedFile.name.split(".").pop()?.toLowerCase();
    if (!allowed.includes(selectedFile.type) && !["pdf", "png", "jpg", "jpeg"].includes(ext || "")) {
      setErrorMessage("Only PDF, JPG, and PNG documents are accepted.");
      return;
    }
    if (selectedFile.size > 10 * 1024 * 1024) {
      setErrorMessage("File exceeds the maximum 10 MB limit.");
      return;
    }

    setFile(selectedFile);
    uploadFile(selectedFile);
  };

  const uploadFile = async (uploadingFile: File) => {
    const targetCaseId = selectedCaseId || caseId;
    if (!targetCaseId) {
      setErrorMessage("Please select a patient case before uploading.");
      return;
    }

    setProcessingState("UPLOADED");
    setProgress(25);

    const formData = new FormData();
    formData.append("file", uploadingFile);
    formData.append("screening_order_id", selectedOrderId);
    formData.append("screening_type", selectedModality);

    try {
      setTimeout(() => {
        setProcessingState("EXTRACTING");
        setProgress(50);
      }, 400);

      setTimeout(() => {
        setProcessingState("VALIDATING");
        setProgress(75);
      }, 800);

      const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
      const res = await fetch(`/api/v1/cases/${targetCaseId}/upload-report-file`, {
        method: "POST",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      });

      const json = await res.json();
      setProgress(100);

      if (!res.ok || json.success === false) {
        setProcessingState("FAILED");
        setErrorMessage(json.message || json.detail || "Upload or text extraction failed.");
        if (json.data?.preview) {
          setPreviewUrl(json.data.preview);
        }
        return;
      }

      setProcessingState("READY_TO_FINALIZE");
      setExtractedData(json.data);
      if (json.data?.preview) {
        setPreviewUrl(json.data.preview);
      }
    } catch (err: any) {
      setProcessingState("FAILED");
      setErrorMessage(err.message || "Network communication error during report upload.");
    }
  };

  const handleFinalize = async () => {
    const targetCaseId = selectedCaseId || caseId;
    if (!targetCaseId) return;
    setIsFinalizing(true);
    setErrorMessage(null);

    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
      const res = await fetch(`/api/v1/cases/${targetCaseId}/finalize-report`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          finding_code: extractedData?.finding_code || "BI-RADS 4",
          finding_summary: extractedData?.finding_summary,
          clinical_recommendation: extractedData?.recommendation,
          requires_doctor_review: requiresDoctorReview,
        }),
      });

      const json = await res.json();
      if (!res.ok || json.success === false) {
        throw new Error(json.message || json.detail || "Finalization failed");
      }

      const finalStatus = json.data?.status || "FINALIZED";
      setProcessingState(finalStatus === "REQUIRES_REVIEW" ? "REQUIRES_REVIEW" : "FINALIZED");
      if (onReportFinalized) {
        onReportFinalized(json.data);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to finalize report.");
    } finally {
      setIsFinalizing(false);
    }
  };

  const currentPatientName =
    patientName ||
    cases.find((c) => c.id === selectedCaseId)?.patient_name ||
    "Selected Patient";

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        resetState();
        onClose();
      }}
      title="Upload Diagnostic Screening Report"
      size="lg"
    >
      <div className="space-y-4 text-xs text-[#0F172A]">
        {/* Patient and Screening Order Selection */}
        <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn space-y-2.5">
          {cases.length > 0 && !caseId ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="text-[11px] font-semibold text-[#64748B] block mb-1">
                  Choose Patient *
                </label>
                <select
                  value={selectedCaseId}
                  onChange={(e) => {
                    const cid = e.target.value;
                    setSelectedCaseId(cid);
                    const matched = cases.find((c) => c.id === cid);
                    if (matched) {
                      setSelectedOrderId(matched.screening_order_id || `ORD-${matched.case_number}`);
                      if (matched.screening_type) setSelectedModality(matched.screening_type);
                    }
                  }}
                  className="w-full h-8 px-2 bg-white border border-[#CBD5E1] rounded text-xs text-[#0F172A]"
                >
                  {cases.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.patient_name} ({c.case_number})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[11px] font-semibold text-[#64748B] block mb-1">
                  Screening Order (Preselected)
                </label>
                <input
                  type="text"
                  value={selectedOrderId}
                  onChange={(e) => setSelectedOrderId(e.target.value)}
                  className="w-full h-8 px-2 bg-white border border-[#CBD5E1] rounded text-xs text-[#0F172A]"
                />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-[#64748B] block mb-1">
                  Modality
                </label>
                <input
                  type="text"
                  value={selectedModality}
                  onChange={(e) => setSelectedModality(e.target.value)}
                  className="w-full h-8 px-2 bg-white border border-[#CBD5E1] rounded text-xs text-[#0F172A]"
                />
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="text-[#64748B] block text-[11px]">Patient Case</span>
                <span className="font-semibold text-xs text-[#0F172A]">{currentPatientName}</span>
              </div>
              <div>
                <span className="text-[#64748B] block text-[11px]">Screening Order</span>
                <span className="font-semibold text-xs text-[#0F766E]">{selectedOrderId}</span>
              </div>
              <div>
                <span className="text-[#64748B] block text-[11px]">Modality</span>
                <Badge variant="info">{selectedModality}</Badge>
              </div>
            </div>
          )}
        </div>

        {/* Processing State Banner */}
        {processingState !== "IDLE" && (
          <div className="p-3 rounded-btn border flex items-center justify-between text-xs bg-[#F0FDF4] border-[#BBF7D0]">
            <div className="flex items-center gap-2">
              {processingState === "FAILED" ? (
                <AlertTriangle className="w-4 h-4 text-[#DC2626]" />
              ) : processingState === "FINALIZED" ? (
                <CheckCircle2 className="w-4 h-4 text-[#15803D]" />
              ) : (
                <RefreshCw className="w-4 h-4 text-[#0F766E] animate-spin" />
              )}
              <span className="font-semibold capitalize">
                Status: {processingState.replace(/_/g, " ")}
              </span>
            </div>
            <Badge
              variant={
                processingState === "FAILED"
                  ? "error"
                  : processingState === "FINALIZED"
                  ? "success"
                  : "warning"
              }
            >
              Stage 2: {processingState === "FINALIZED" ? "Completed" : "Pending"}
            </Badge>
          </div>
        )}

        {/* Error Notice */}
        {errorMessage && (
          <div className="p-3 bg-[#FEF2F2] border border-[#FCA5A5] rounded-btn text-xs text-[#991B1B] flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Drag and Drop Zone */}
        {!file && (
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-card p-6 text-center transition-colors cursor-pointer ${
              dragActive ? "border-[#0F766E] bg-[#E6F4F1]" : "border-[#CBD5E1] bg-[#FAFAFA] hover:bg-[#F1F5F9]"
            }`}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              onChange={handleFileChange}
              className="hidden"
            />
            <div className="w-12 h-12 mx-auto mb-2 rounded-full bg-[#E6F4F1] flex items-center justify-center text-[#0F766E]">
              <Upload className="w-6 h-6" />
            </div>
            <p className="font-semibold text-xs text-[#0F172A] mb-1">
              Drag & Drop Medical Report Here or Click to Browse
            </p>
            <p className="text-[11px] text-[#64748B] mb-3">
              Accepted Formats: PDF, JPG, PNG (Max file size: 10 MB)
            </p>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                fileInputRef.current?.click();
              }}
            >
              Browse files
            </Button>
          </div>
        )}

        {/* File Card & Progress */}
        {file && (
          <div className="p-4 border border-[#E2E8F0] rounded-card bg-white space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-btn bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center font-bold">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <span className="font-semibold text-xs text-[#0F172A] block">{file.name}</span>
                  <span className="text-[11px] text-[#64748B]">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={processingState === "FINALIZED" || isFinalizing}
                >
                  Replace
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={resetState}
                  disabled={processingState === "FINALIZED" || isFinalizing}
                >
                  <X className="w-4 h-4 text-[#64748B]" />
                </Button>
              </div>
            </div>

            {/* Progress Bar */}
            {progress > 0 && progress < 100 && (
              <div className="w-full bg-[#E2E8F0] h-2 rounded-full overflow-hidden">
                <div
                  className="bg-[#0F766E] h-2 transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            )}

            {/* Preview Section */}
            {previewUrl && (
              <div className="mt-3 p-2 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn">
                <span className="text-[11px] font-semibold text-[#64748B] uppercase tracking-wider block mb-1">
                  Document Preview (Page 1)
                </span>
                <img
                  src={previewUrl}
                  alt="Report Preview"
                  className="max-h-48 mx-auto rounded border border-[#E2E8F0] shadow-sm"
                />
              </div>
            )}

            {/* Extracted Findings Review Card */}
            {extractedData && processingState === "READY_TO_FINALIZE" && (
              <div className="p-3 bg-[#F0FDF4] border border-[#BBF7D0] rounded-btn space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-[#15803D]">
                    Extracted Report Summary
                  </span>
                  <Badge variant="error">{extractedData.finding_code || "BI-RADS 4"}</Badge>
                </div>
                <p className="text-[11px] text-[#334155] leading-relaxed">
                  <strong>Findings:</strong> {extractedData.finding_summary}
                </p>
                <p className="text-[11px] text-[#334155] leading-relaxed">
                  <strong>Recommendation:</strong> {extractedData.recommendation}
                </p>

                <div className="pt-2 border-t border-[#BBF7D0] flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="requireDocReview"
                    checked={requiresDoctorReview}
                    onChange={(e) => setRequiresDoctorReview(e.target.checked)}
                    className="w-4 h-4 text-[#0F766E] rounded"
                  />
                  <label htmlFor="requireDocReview" className="text-[11px] text-[#0F172A] cursor-pointer">
                    Hospital requires attending physician verification (Status will show REQUIRES_REVIEW)
                  </label>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Modal Actions */}
        <div className="flex justify-end gap-2 pt-2 border-t border-[#E2E8F0]">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              resetState();
              onClose();
            }}
          >
            Close
          </Button>
          {processingState === "READY_TO_FINALIZE" && (
            <Button
              type="button"
              variant="primary"
              disabled={isFinalizing}
              onClick={handleFinalize}
              leftIcon={<ShieldCheck className="w-4 h-4" />}
            >
              {isFinalizing ? "Finalizing Report..." : "Finalize Report (Complete Stage 2)"}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
};
