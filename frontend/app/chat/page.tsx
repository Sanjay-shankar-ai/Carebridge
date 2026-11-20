"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Send,
  Globe,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  RefreshCw,
  Calendar,
  User,
  HeartPulse,
  Stethoscope,
  History,
  MessageSquare,
  Plus,
  PanelLeftClose,
  PanelLeft,
  Search,
  Clock,
  ChevronRight,
  Edit2,
  Trash2,
  UserCheck,
  Square,
  Copy,
  Check,
  RotateCcw,
  ArrowDown,
  Sparkles,
} from "lucide-react";
import {
  fetchCases,
  sendAgentMessage,
  streamAgentMessage,
  fetchChatHistory,
  fetchConversationSessions,
  createConversationSession,
  renameConversationSession,
  deleteConversationSession,
} from "../../services/api";
import { useAuth } from "../../context/AuthContext";
import { CareCase, ChatMessage, ToolResultChip } from "../../types";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { MarkdownRenderer } from "@/components/MarkdownRenderer";

interface SessionItem {
  id: string;
  title?: string;
  summary?: string;
  case_id?: string;
  patient_id?: string;
  last_interaction_at?: string;
  created_at?: string;
  is_active?: boolean;
}

function ChatContent() {
  const searchParams = useSearchParams();
  const queryCaseId = searchParams.get("caseId");
  const { user } = useAuth();

  const [cases, setCases] = useState<CareCase[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState<string>("");
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [sessionSearch, setSessionSearch] = useState<string>("");
  const [showHistorySidebar, setShowHistorySidebar] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [selectedLanguage, setSelectedLanguage] = useState("en");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [suggestedActions, setSuggestedActions] = useState<string[]>([]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef<boolean>(false);

  const isDoctor = user?.role === "doctor" || user?.role === "clinician";
  const isPatient = user?.role === "patient";

  const getRoleEmptySuggestedActions = () => {
    if (isDoctor) {
      return [
        "Which reports need my review?",
        "Show patients waiting for biopsy verification",
        "Summarize pending pathology findings",
        "Check upcoming appointments",
      ];
    } else if (isPatient) {
      return [
        "Explain my report",
        "Where am I in my care journey?",
        "When is my next appointment?",
        "I need help with transportation",
      ];
    } else {
      return [
        "Any new patients?",
        "Show overdue tasks",
        "Show cases needing recovery",
        "Check SLA countdowns",
      ];
    }
  };

  const initializeWelcome = (careCase: CareCase | null) => {
    if (isDoctor) {
      const docName = user?.name || "Doctor";
      setMessages([
        {
          id: `msg-welcome-doctor-${Date.now()}`,
          sender: "ai",
          text: careCase
            ? `👨‍⚕️ Clinical Co-Pilot Active — Reviewing Case **${careCase.case_number}** (${careCase.patient_name || "Patient"}).\n\nScreening Finding: \`${careCase.finding_code || "Screening Abnormality"}\`\n\nHow would you like to proceed with this patient?`
            : `Hello ${docName}. I am your CareBridge Clinical Decision Co-Pilot.\n\nYou are in general operational mode with zero patient context loaded. Select a patient from the roster if you wish to review specific diagnostic files, or ask an operational question below.`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      setSuggestedActions(getRoleEmptySuggestedActions());
    } else if (isPatient) {
      const patientFirst = user?.name
        ? user.name.split(" ")[0]
        : careCase?.patient_name
        ? careCase.patient_name.split(" ")[0]
        : "Patient";
      setMessages([
        {
          id: `msg-welcome-patient-${Date.now()}`,
          sender: "ai",
          text: `Hello ${patientFirst}! Welcome to CareBridge. I am your dedicated AI Care Companion working alongside your care team. How can I assist you with your health check, screening report, or care appointments today?`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          language: selectedLanguage,
        },
      ]);
      setSuggestedActions(getRoleEmptySuggestedActions());
    } else {
      setMessages([
        {
          id: `msg-welcome-coord-${Date.now()}`,
          sender: "ai",
          text: `Hello ${user?.name || "Care Coordinator"}, CareBridge Cognitive Supervisor Agent active.\n\nMonitoring patient SLA countdowns, stalled cases, and care recovery queues. How can I assist with care coordination today?`,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      setSuggestedActions(getRoleEmptySuggestedActions());
    }
  };

  const loadUserSessions = async (search?: string) => {
    try {
      const res = await fetchConversationSessions(undefined, search);
      setSessions(res || []);
    } catch (err) {
      console.warn("Could not load user sessions:", err);
      setSessions([]);
    }
  };

  const handleStartNewChat = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsStreaming(false);
    setIsLoading(false);
    setSelectedSessionId("");
    if (!isPatient) {
      setSelectedCaseId("");
    }
    const targetCase = cases.find((c) => c.id === selectedCaseId) || null;
    initializeWelcome(isPatient ? targetCase : null);
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  };

  const handleSelectSession = async (sessId: string) => {
    if (sessId === selectedSessionId) return;
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsStreaming(false);
    setIsLoading(true);
    setSelectedSessionId(sessId);

    try {
      const hist = await fetchChatHistory(undefined, sessId);
      if (hist && hist.length > 0) {
        const rawMsgs: ChatMessage[] = hist.map((m: any) => ({
          id: m.id,
          sender:
            m.sender === "patient"
              ? "patient"
              : m.sender === "clinician" || m.sender === "doctor"
              ? "clinician"
              : "ai",
          text: m.content || "",
          timestamp: m.sent_at
            ? new Date(m.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
            : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          language: m.language,
        }));
        const loadedMsgs: ChatMessage[] = [];
        for (const msg of rawMsgs) {
          const prev = loadedMsgs[loadedMsgs.length - 1];
          if (prev && prev.sender === msg.sender && prev.text.trim() === msg.text.trim()) {
            continue;
          }
          loadedMsgs.push(msg);
        }
        setMessages(loadedMsgs);
        setSuggestedActions([]);
      } else {
        const targetCase = cases.find((c) => c.id === selectedCaseId) || null;
        initializeWelcome(targetCase);
      }
    } catch (err) {
      console.error("Failed to load session messages:", err);
      const targetCase = cases.find((c) => c.id === selectedCaseId) || null;
      initializeWelcome(targetCase);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRenameSession = async (sessId: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const newTitle = window.prompt("Rename conversation:", currentTitle);
    if (!newTitle || newTitle.trim() === "" || newTitle === currentTitle) return;
    try {
      await renameConversationSession(sessId, newTitle.trim());
      await loadUserSessions(sessionSearch);
    } catch (err) {
      console.error("Failed to rename conversation:", err);
    }
  };

  const handleDeleteSession = async (sessId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this conversation?")) return;
    try {
      await deleteConversationSession(sessId);
      if (selectedSessionId === sessId) {
        handleStartNewChat();
      }
      await loadUserSessions(sessionSearch);
    } catch (err) {
      console.error("Failed to delete conversation:", err);
    }
  };

  useEffect(() => {
    async function loadInitialData() {
      try {
        const caseList = await fetchCases().catch(() => []);
        setCases(caseList || []);

        let targetCase: CareCase | undefined;
        if (queryCaseId && caseList) {
          targetCase = caseList.find((c) => c.id === queryCaseId);
        } else if (isPatient) {
          if (user?.case_id && caseList) {
            targetCase = caseList.find((c) => c.id === user.case_id);
          } else if (user?.patient_id && caseList) {
            targetCase = caseList.find((c) => c.patient_id === user.patient_id);
          }
        }

        if (targetCase && isPatient) {
          setSelectedCaseId(targetCase.id);
          setSelectedLanguage(targetCase.patient_language || "en");
        } else if (queryCaseId && targetCase) {
          setSelectedCaseId(targetCase.id);
        } else {
          setSelectedCaseId("");
        }

        // Always land on a fresh, empty conversation
        setSelectedSessionId("");
        initializeWelcome(targetCase || null);

        // Load user's own session history list
        await loadUserSessions();
      } catch (err) {
        console.error("Failed to load initial chat data:", err);
        handleStartNewChat();
      }
    }
    loadInitialData();
  }, [queryCaseId, user]);

  // Handle scroll detection for auto-scroll pause
  const handleScroll = () => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const isBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    setIsAtBottom(isBottom);
  };

  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    messagesEndRef.current?.scrollIntoView({ behavior });
    setIsAtBottom(true);
  };

  useEffect(() => {
    if (isAtBottom) {
      scrollToBottom();
    }
  }, [messages, isStreaming, isLoading]);

  // Handle Stop Generating button
  const handleStopGenerating = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setIsLoading(false);
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.sender === "ai" && last.isStreaming) {
        return [
          ...prev.slice(0, -1),
          { ...last, isStreaming: false, text: last.text || "(Generation stopped)" },
        ];
      }
      return prev;
    });
  };

  // Handle Copy Message button
  const handleCopyMessage = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => {
      setCopiedId((curr) => (curr === id ? null : curr));
    }, 2000);
  };

  // Handle Send Message with SSE streaming
  const handleSendMessage = async (textToSend?: string) => {
    const messageContent = (textToSend || inputText).trim();
    if (!messageContent || isStreaming || isLoading || inFlightRef.current) return;
    inFlightRef.current = true;

    setErrorMessage(null);
    setInputText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    const senderRole = isDoctor ? "clinician" : isPatient ? "patient" : "care_coordinator";

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      sender: isDoctor ? "clinician" : "patient",
      text: messageContent,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    const aiMsgId = `ai-${Date.now()}`;
    const aiPlaceholder: ChatMessage = {
      id: aiMsgId,
      sender: "ai",
      text: "",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      isStreaming: true,
      toolResults: [],
    };

    setMessages((prev) => [...prev, userMsg, aiPlaceholder]);
    setIsLoading(true);
    setIsStreaming(true);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const accumulatedTools: ToolResultChip[] = [];

    try {
      await streamAgentMessage({
        caseId: selectedCaseId || undefined,
        sessionId: selectedSessionId || undefined,
        message: messageContent,
        channel: "in_app_chat",
        sender: senderRole,
        signal: abortController.signal,
        onToken: (token: string) => {
          setIsLoading(false);
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.id === aiMsgId) {
              return [
                ...prev.slice(0, -1),
                { ...last, text: last.text + token, isStreaming: true },
              ];
            }
            return prev;
          });
        },
        onToolStarted: (tool: string, description?: string) => {
          // Tool started
        },
        onToolResult: (res: { tool: string; status: "success" | "failed" | "warning"; summary: string }) => {
          accumulatedTools.push({
            tool: res.tool,
            status: res.status,
            summary: res.summary || `${res.tool.replace(/_/g, " ")} executed`,
          });
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.id === aiMsgId) {
              return [
                ...prev.slice(0, -1),
                { ...last, toolResults: [...accumulatedTools] },
              ];
            }
            return prev;
          });
        },
        onFinal: (finalData: any) => {
          if (finalData.session_id && !selectedSessionId) {
            setSelectedSessionId(finalData.session_id);
            loadUserSessions(sessionSearch);
          }
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.id === aiMsgId) {
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  text: finalData.content || last.text,
                  isStreaming: false,
                  detectedIntent: finalData.primary_intent,
                  toolResults: [...accumulatedTools],
                },
              ];
            }
            return prev;
          });
        },
        onError: (err: any) => {
          console.error("Stream error received:", err);
          setErrorMessage("Something went wrong while generating the response. Please try again.");
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.id === aiMsgId) {
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  isStreaming: false,
                  error: true,
                  text:
                    last.text ||
                    "I am having a brief connection delay with the care team service. Please try sending your message again.",
                },
              ];
            }
            return prev;
          });
        },
      });
    } catch (err: any) {
      if (abortController.signal.aborted) {
        // Handled cleanly by user stop
        return;
      }
      console.warn("Backend streaming execution error:", err);
      setErrorMessage("Something went wrong while communicating with the AI service.");
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.id === aiMsgId) {
          return [
            ...prev.slice(0, -1),
            {
              ...last,
              isStreaming: false,
              error: true,
              text:
                last.text ||
                (isDoctor
                  ? "Clinical co-pilot is experiencing a temporary connection delay. Please verify the case number or check your patient roster."
                  : "I am having a brief connection delay with your care companion service. Please try sending your message again, or ask a question about your screening results."),
            },
          ];
        }
        return prev;
      });
    } finally {
      inFlightRef.current = false;
      setIsLoading(false);
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const handleRegenerate = () => {
    // Find last user message
    const lastUserMsg = [...messages].reverse().find((m) => m.sender === "patient" || m.sender === "clinician");
    if (lastUserMsg) {
      handleSendMessage(lastUserMsg.text);
    }
  };

  const handleLanguageChange = (lang: string) => {
    setSelectedLanguage(lang);
    const targetCase = cases.find((c) => c.id === selectedCaseId) || null;
    initializeWelcome(targetCase);
  };

  const filteredSessions = sessions.filter((s) => {
    if (!sessionSearch.trim()) return true;
    const term = sessionSearch.toLowerCase();
    const title = (s.title || s.summary || "").toLowerCase();
    return title.includes(term);
  });

  const currentCase = cases.find((c) => c.id === selectedCaseId) || null;

  return (
    <div className="space-y-6">
      {/* Top Banner & Control Header */}
      <Card padding="md" className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1 text-xs font-semibold uppercase tracking-wider text-[#0F766E]">
            <MessageSquare className="w-4 h-4" />
            {isDoctor
              ? "Clinical Assistant"
              : isPatient
              ? "Patient Care Companion"
              : "Care Coordination Assistant"}
          </div>
          <h1 className="text-xl sm:text-2xl font-semibold text-[#0F172A] tracking-tight">
            {isDoctor
              ? "CareBridge Doctor Assistant"
              : isPatient
              ? "CareBridge Patient Assistant"
              : "CareBridge Supervisor AI Brain"}
          </h1>
          <p className="text-xs text-[#475569] mt-1">
            {isDoctor ? (
              <span>
                Attending Specialist: <strong>{user?.name || "Dr. Arjun Menon, MD"}</strong> • Patient Focus:{" "}
                <strong className="text-[#0F172A]">
                  {currentCase ? `${currentCase.patient_name} (${currentCase.case_number})` : "None (General Clinical Mode)"}
                </strong>
              </span>
            ) : isPatient ? (
              <span>
                Patient Portal: <strong className="text-[#0F172A]">{user?.name || "Patient"}</strong>
              </span>
            ) : (
              <span>
                Coordinator: <strong>{user?.name || "Care Coordinator"}</strong> • Patient Focus:{" "}
                <strong className="text-[#0F172A]">
                  {currentCase ? `${currentCase.patient_name} (${currentCase.case_number})` : "None (Operational Overview Mode)"}
                </strong>
              </span>
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {/* New Chat Primary Button */}
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Plus className="w-3.5 h-3.5" />}
            onClick={handleStartNewChat}
            className="text-xs h-8 px-3 font-semibold"
          >
            New Chat
          </Button>

          {/* History Sidebar Toggle */}
          <button
            onClick={() => setShowHistorySidebar(!showHistorySidebar)}
            className={`px-3 py-1.5 h-8 rounded-btn text-xs font-medium border flex items-center gap-1.5 transition ${
              showHistorySidebar
                ? "bg-[#E6F4F1] border-[#0F766E] text-[#0F766E]"
                : "bg-white border-[#E2E8F0] text-[#475569] hover:bg-[#F8FAFC]"
            }`}
            title="Toggle Chat History Drawer"
          >
            {showHistorySidebar ? <PanelLeftClose className="w-3.5 h-3.5" /> : <PanelLeft className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">History</span>
          </button>

          {/* Language Selector for Patient view */}
          {isPatient && (
            <div className="flex items-center gap-1 bg-[#F8FAFC] p-1 rounded-btn border border-[#E2E8F0] text-xs h-8">
              <Globe className="w-3.5 h-3.5 text-[#475569] ml-1 shrink-0" />
              <button
                onClick={() => handleLanguageChange("en")}
                className={`px-2 py-0.5 rounded-btn font-medium transition ${
                  selectedLanguage === "en" ? "bg-[#0F766E] text-white" : "text-[#475569] hover:text-[#0F172A]"
                }`}
              >
                EN
              </button>
              <button
                onClick={() => handleLanguageChange("ar")}
                className={`px-2 py-0.5 rounded-btn font-medium transition ${
                  selectedLanguage === "ar" ? "bg-[#0F766E] text-white" : "text-[#475569] hover:text-[#0F172A]"
                }`}
              >
                AR
              </button>
              <button
                onClick={() => handleLanguageChange("es")}
                className={`px-2 py-0.5 rounded-btn font-medium transition ${
                  selectedLanguage === "es" ? "bg-[#0F766E] text-white" : "text-[#475569] hover:text-[#0F172A]"
                }`}
              >
                ES
              </button>
            </div>
          )}

          {/* Patient context selector for Doctor/Coordinator */}
          {!isPatient && cases.length > 0 && (
            <div className="flex items-center gap-1.5">
              <select
                value={selectedCaseId}
                onChange={(e) => {
                  const newId = e.target.value;
                  setSelectedCaseId(newId);
                  const c = cases.find((item) => item.id === newId) || null;
                  initializeWelcome(c);
                }}
                className="h-8 px-2.5 bg-white border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] focus:outline-none focus:ring-1 focus:ring-[#0F766E]"
                aria-label="Focus on specific patient"
              >
                <option value="">No Patient Context (General Mode)</option>
                {cases.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.patient_name} ({c.finding_code || c.case_number})
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </Card>

      {/* Main Chat Interface with Left History Sidebar */}
      <Card className="flex h-[640px] overflow-hidden border border-[#E2E8F0] p-0 shadow-soft">
        {/* Left Side: Session History Drawer */}
        {showHistorySidebar && (
          <aside className="w-72 sm:w-80 border-r border-[#E2E8F0] bg-white flex flex-col shrink-0">
            {/* Sidebar Header */}
            <div className="p-3 border-b border-[#E2E8F0] flex items-center justify-between bg-[#F8FAFC]">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-[#0F766E]" />
                <h3 className="font-semibold text-xs text-[#0F172A]">Conversations</h3>
              </div>
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<Plus className="w-3 h-3" />}
                onClick={handleStartNewChat}
                className="text-[11px] h-6 px-2 text-[#0F766E]"
              >
                New
              </Button>
            </div>

            {/* Conversation Search Bar */}
            <div className="p-2 border-b border-[#E2E8F0] bg-white">
              <div className="relative">
                <input
                  type="text"
                  placeholder="Search conversations..."
                  value={sessionSearch}
                  onChange={(e) => setSessionSearch(e.target.value)}
                  className="w-full h-7 pl-7 pr-3 text-[11px] bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:ring-1 focus:ring-[#0F766E]"
                />
                <Search className="w-3.5 h-3.5 text-[#94A3B8] absolute left-2 top-1/2 -translate-y-1/2" />
              </div>
            </div>

            {/* Sessions List */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1 divide-y divide-[#F8FAFC]">
              {filteredSessions.length === 0 ? (
                <div className="p-4 text-center text-xs text-[#94A3B8]">
                  <MessageSquare className="w-5 h-5 mx-auto mb-2 text-[#CBD5E1]" />
                  <span>No saved conversations. Start a new chat to begin.</span>
                </div>
              ) : (
                filteredSessions.map((s, idx) => {
                  const isSelected = selectedSessionId === s.id;
                  const title = s.title || s.summary || `Conversation #${idx + 1}`;
                  const dateLabel = s.last_interaction_at
                    ? new Date(s.last_interaction_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })
                    : s.created_at
                    ? new Date(s.created_at).toLocaleDateString()
                    : "Recent";

                  return (
                    <div
                      key={s.id}
                      onClick={() => handleSelectSession(s.id)}
                      className={`group w-full text-left p-2 rounded-btn transition text-xs flex items-center justify-between gap-2 cursor-pointer ${
                        isSelected
                          ? "bg-[#E6F4F1] text-[#0F766E] border border-[#0F766E]/30 font-medium"
                          : "text-[#475569] hover:bg-[#F8FAFC] border border-transparent"
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <span className="font-medium text-xs text-[#0F172A] block truncate">
                          {title}
                        </span>
                        <span className="text-[10px] text-[#64748B] flex items-center gap-1 mt-0.5">
                          <Clock className="w-2.5 h-2.5" />
                          {dateLabel}
                        </span>
                      </div>

                      {/* Action buttons on hover / selected */}
                      <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition">
                        <button
                          type="button"
                          onClick={(e) => handleRenameSession(s.id, title, e)}
                          className="p-1 hover:text-[#0F766E] text-[#94A3B8]"
                          title="Rename conversation"
                        >
                          <Edit2 className="w-3 h-3" />
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteSession(s.id, e)}
                          className="p-1 hover:text-[#DC2626] text-[#94A3B8]"
                          title="Delete conversation"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Persistence Footer */}
            <div className="p-2.5 border-t border-[#E2E8F0] bg-[#F8FAFC] text-[10px] text-[#64748B] flex items-center justify-between">
              <span className="flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-[#15803D]" />
                Role-Isolated Session Storage
              </span>
              <span className="font-mono text-[9px] text-[#94A3B8]">PostgreSQL 17</span>
            </div>
          </aside>
        )}

        {/* Right Side: Active Chat Window */}
        <div className="flex-1 flex flex-col bg-[#F8FAFC] min-w-0 relative">
          {/* Error Banner */}
          {errorMessage && (
            <div className="px-4 py-2 bg-rose-50 border-b border-rose-200 text-rose-800 text-xs flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                <span>{errorMessage}</span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRegenerate}
                className="h-6 text-[10px] border-rose-300 text-rose-700 hover:bg-rose-100"
              >
                Retry
              </Button>
            </div>
          )}

          {/* Messages Scroll Area */}
          <div
            ref={messagesContainerRef}
            onScroll={handleScroll}
            className="flex-1 p-6 overflow-y-auto space-y-4"
          >
            {messages.map((m) => {
              const isUserMsg = m.sender === "patient" || m.sender === "clinician";
              const isArabic = m.language === "ar" || /[\u0600-\u06FF]/.test(m.text);

              return (
                <div
                  key={m.id}
                  className={`flex ${isUserMsg ? "justify-end" : "justify-start"}`}
                  dir={isArabic ? "rtl" : "ltr"}
                >
                  <div className={`max-w-[85%] sm:max-w-[78%] flex items-start gap-3 ${isUserMsg ? "flex-row-reverse" : ""}`}>
                    {/* User / AI Avatar */}
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-semibold ${
                        isUserMsg
                          ? "bg-[#0F766E] text-white"
                          : "bg-[#E6F4F1] text-[#0F766E] border border-[#0F766E]/20"
                      }`}
                    >
                      {isUserMsg ? (
                        isDoctor ? <Stethoscope className="w-4 h-4" /> : <User className="w-4 h-4" />
                      ) : (
                        <HeartPulse className="w-4 h-4" />
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      {/* Message Bubble */}
                      <div
                        className={`p-4 rounded-card text-xs leading-relaxed relative group ${
                          isUserMsg
                            ? "bg-[#0F766E] text-white rounded-tr-none shadow-soft"
                            : m.error
                            ? "bg-rose-50 border border-rose-200 text-rose-900 rounded-tl-none shadow-2xs"
                            : "bg-white border border-[#E2E8F0] text-[#0F172A] rounded-tl-none shadow-2xs"
                        }`}
                        aria-live={m.isStreaming ? "polite" : undefined}
                      >
                        {isUserMsg ? (
                          <div className="whitespace-pre-wrap">{m.text}</div>
                        ) : (
                          <div>
                            <MarkdownRenderer content={m.text || (m.isStreaming ? " " : "")} />
                            {m.isStreaming && (
                              <span className="inline-block w-1.5 h-3.5 ml-1 bg-[#0F766E] animate-pulse align-middle" />
                            )}
                          </div>
                        )}

                        {/* Hover Quick Actions */}
                        {!m.isStreaming && (
                          <div
                            className={`absolute top-2 ${
                              isUserMsg ? "left-2" : "right-2"
                            } opacity-0 group-hover:opacity-100 transition flex items-center gap-1 bg-white/80 dark:bg-slate-800/80 backdrop-blur rounded px-1.5 py-0.5 border border-slate-200 shadow-2xs`}
                          >
                            <button
                              type="button"
                              onClick={() => handleCopyMessage(m.id, m.text)}
                              className="text-slate-500 hover:text-slate-800 p-0.5"
                              title="Copy message text"
                            >
                              {copiedId === m.id ? (
                                <Check className="w-3 h-3 text-emerald-600" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                            </button>
                            {!isUserMsg && (
                              <button
                                type="button"
                                onClick={handleRegenerate}
                                className="text-slate-500 hover:text-slate-800 p-0.5"
                                title="Regenerate response"
                              >
                                <RotateCcw className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Action Status Chip Row (strictly rendered from tool_result events) */}
                      {m.toolResults && m.toolResults.length > 0 && (
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {m.toolResults.map((tr, trIdx) => (
                            <span
                              key={trIdx}
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                                tr.status === "success"
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                  : tr.status === "failed"
                                  ? "bg-rose-50 text-rose-700 border-rose-200"
                                  : "bg-amber-50 text-amber-700 border-amber-200"
                              }`}
                            >
                              {tr.status === "success" ? (
                                <CheckCircle2 className="w-3 h-3 text-emerald-600 shrink-0" />
                              ) : (
                                <AlertCircle className="w-3 h-3 text-rose-600 shrink-0" />
                              )}
                              <span>{tr.summary}</span>
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Message Footer: Timestamp & Intent Badge */}
                      <div
                        className={`text-[10px] text-[#64748B] mt-1 flex items-center gap-2 ${
                          isUserMsg ? "justify-end" : "justify-start"
                        }`}
                      >
                        <span>{m.timestamp}</span>
                        {m.detectedIntent && (
                          <Badge variant="neutral" className="text-[9px] py-0 px-1.5 h-4">
                            Intent: {m.detectedIntent.replace(/_/g, " ")}
                          </Badge>
                        )}
                        {copiedId === m.id && (
                          <span className="text-[9px] text-emerald-600 font-medium">Copied!</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Pulsing Typing Indicator while waiting for initial tokens */}
            {isLoading && (
              <div className="flex justify-start">
                <div className="max-w-[80%] flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-[#E6F4F1] text-[#0F766E] flex items-center justify-center shrink-0">
                    <Sparkles className="w-4 h-4 animate-pulse text-[#0F766E]" />
                  </div>
                  <div className="bg-white border border-[#E2E8F0] p-3 rounded-card text-xs text-[#475569] flex items-center gap-2 shadow-2xs">
                    <span className="w-2 h-2 rounded-full bg-[#0F766E] animate-bounce"></span>
                    <span className="w-2 h-2 rounded-full bg-[#0F766E] animate-bounce delay-100"></span>
                    <span className="w-2 h-2 rounded-full bg-[#0F766E] animate-bounce delay-200"></span>
                    <span className="text-slate-500 font-medium ml-1">Analyzing care pathways...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Floating "Scroll to bottom" button */}
          {!isAtBottom && (
            <button
              onClick={() => scrollToBottom("smooth")}
              className="absolute bottom-28 right-6 z-10 px-3 py-1.5 bg-white border border-slate-300 shadow-md rounded-full text-xs font-medium text-slate-700 hover:bg-slate-50 flex items-center gap-1.5 transition"
            >
              <ArrowDown className="w-3.5 h-3.5 text-teal-600" />
              <span>Scroll to bottom</span>
            </button>
          )}

          {/* Quick Action Suggestion Chips */}
          <div className="p-3 bg-white border-t border-[#E2E8F0]">
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
              <span className="text-[10px] font-semibold text-[#64748B] uppercase tracking-wider shrink-0 mr-1">
                Suggested:
              </span>
              {suggestedActions.map((action, i) => (
                <button
                  key={i}
                  disabled={isStreaming || isLoading}
                  onClick={() => handleSendMessage(action)}
                  className="px-2.5 py-1 rounded-btn bg-[#F8FAFC] hover:bg-[#E6F4F1] border border-[#CBD5E1] hover:border-[#0F766E] text-xs font-medium text-[#0F172A] whitespace-nowrap transition cursor-pointer shadow-2xs disabled:opacity-50"
                >
                  {action}
                </button>
              ))}
            </div>
          </div>

          {/* Chat Input Bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="p-3.5 bg-white border-t border-[#E2E8F0] flex items-end gap-2"
          >
            {/* Auto-growing Multi-line Textarea */}
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                rows={1}
                value={inputText}
                disabled={isStreaming}
                onChange={(e) => {
                  setInputText(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder={
                  isDoctor
                    ? "Ask Clinical Co-Pilot: Which reports need review? Verify biopsy, check appointments..."
                    : isPatient
                    ? "Ask about your screening report, care pathway, or upcoming visits... (Shift+Enter for newline)"
                    : "Ask Supervisor: Any new patients? Show overdue tasks, check recovery queues..."
                }
                className="w-full resize-none min-h-[44px] max-h-[140px] px-3.5 py-2.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-btn text-xs text-[#0F172A] placeholder-[#94A3B8] focus:outline-none focus:ring-2 focus:ring-[#0F766E] focus:ring-offset-2 leading-relaxed"
              />
            </div>

            {/* Stream Control: Stop Generating or Send */}
            {isStreaming ? (
              <Button
                type="button"
                variant="outline"
                size="md"
                onClick={handleStopGenerating}
                leftIcon={<Square className="w-3.5 h-3.5 fill-current text-rose-600" />}
                className="border-rose-300 text-rose-700 hover:bg-rose-50 h-11 shrink-0 px-3.5 text-xs font-semibold"
              >
                Stop
              </Button>
            ) : (
              <Button
                type="submit"
                variant="primary"
                size="md"
                disabled={isLoading || !inputText.trim()}
                leftIcon={<Send className="w-4 h-4" />}
                className="h-11 shrink-0"
              >
                Send
              </Button>
            )}
          </form>
        </div>
      </Card>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="flex items-center gap-2 text-xs text-[#64748B]">
            <RefreshCw className="w-4 h-4 animate-spin text-[#0F766E]" />
            <span>Loading CareBridge Chat...</span>
          </div>
        </div>
      }
    >
      <ChatContent />
    </Suspense>
  );
}
