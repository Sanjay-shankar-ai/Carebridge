"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  Bell,
  Check,
  CheckCheck,
  Clock,
  Calendar,
  AlertTriangle,
  Share2,
  CheckCircle2,
  MessageSquare,
  ExternalLink,
  X,
} from "lucide-react";
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from "../services/api";
import { NotificationItem } from "../types";
import { useAuth } from "../context/AuthContext";

export default function NotificationCenter() {
  const { user } = useAuth();
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [activeFilter, setActiveFilter] = useState<"all" | "unread">("all");
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load notifications from PostgreSQL
  const loadNotifications = async () => {
    if (!user) return;
    try {
      const [notifsRes, countRes] = await Promise.all([
        fetchNotifications(false, 30),
        fetchUnreadCount(),
      ]);
      if (notifsRes) {
        setNotifications(notifsRes);
      }
      if (countRes && typeof countRes.unread_count === "number") {
        setUnreadCount(countRes.unread_count);
      }
    } catch (err) {
      console.warn("Failed to fetch notifications:", err);
    }
  };

  useEffect(() => {
    loadNotifications();
  }, [user]);

  // Real-Time EventSource (SSE) Connection with auto-reconnect & fallback polling
  useEffect(() => {
    if (!user?.token) return;

    let eventSource: EventSource | null = null;
    let reconnectTimeout: NodeJS.Timeout;

    const connectSSE = () => {
      try {
        const url = `http://localhost:8000/api/v1/notifications/stream?token=${encodeURIComponent(user.token)}`;
        eventSource = new EventSource(url);

        eventSource.addEventListener("notification", (e: MessageEvent) => {
          try {
            const data: NotificationItem = JSON.parse(e.data);
            setNotifications((prev) => {
              // Avoid duplicates
              if (prev.some((n) => n.id === data.id)) return prev;
              return [data, ...prev];
            });
            setUnreadCount((c) => c + 1);

            // Phase 5: SSE notification triggers real-time refetch of authoritative backend domain data
            if (typeof window !== "undefined") {
              window.dispatchEvent(new CustomEvent("carebridge:data_updated", { detail: data }));
            }
          } catch (err) {
            console.error("Error parsing notification event:", err);
          }
        });

        eventSource.onerror = () => {
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
          // Exponential backoff reconnect
          reconnectTimeout = setTimeout(connectSSE, 5000);
        };
      } catch (err) {
        console.warn("SSE connection error:", err);
      }
    };

    connectSSE();

    // Fallback polling interval (every 10s)
    const interval = setInterval(loadNotifications, 10000);

    return () => {
      if (eventSource) {
        eventSource.close();
      }
      clearTimeout(reconnectTimeout);
      clearInterval(interval);
    };
  }, [user?.token]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleMarkAsRead = async (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    try {
      await markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch (err) {
      console.error("Failed to mark notification as read:", err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
      setUnreadCount(0);
    } catch (err) {
      console.error("Failed to mark all notifications as read:", err);
    }
  };

  const handleNotificationClick = async (notif: NotificationItem) => {
    if (!notif.is_read) {
      await handleMarkAsRead(notif.id);
    }
    setIsOpen(false);
    if (notif.action_link) {
      router.push(notif.action_link);
    }
  };

  const formatRelativeTime = (isoString: string) => {
    if (!isoString) return "";
    const date = new Date(isoString);
    const now = new Date();
    const diffSeconds = Math.round((now.getTime() - date.getTime()) / 1000);

    if (diffSeconds < 60) return "Just now";
    const diffMins = Math.round(diffSeconds / 60);
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.round(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.round(diffHours / 24);
    return `${diffDays}d ago`;
  };

  const getEventIcon = (eventType: string, priority: string) => {
    if (priority === "critical" || eventType === "clinical_escalation") {
      return <AlertTriangle className="w-4 h-4 text-[#DC2626]" />;
    }
    if (eventType.includes("appointment")) {
      return <Calendar className="w-4 h-4 text-[#0F766E]" />;
    }
    if (eventType.includes("referral")) {
      return <Share2 className="w-4 h-4 text-[#0F766E]" />;
    }
    if (eventType.includes("closure")) {
      return <CheckCircle2 className="w-4 h-4 text-[#15803D]" />;
    }
    if (eventType.includes("message")) {
      return <MessageSquare className="w-4 h-4 text-[#0F766E]" />;
    }
    if (eventType.includes("sla")) {
      return <Clock className="w-4 h-4 text-[#D97706]" />;
    }
    return <Bell className="w-4 h-4 text-[#0F766E]" />;
  };

  const filteredNotifications = notifications.filter((n) => {
    if (activeFilter === "unread") return !n.is_read;
    return true;
  });

  return (
    <div className="relative" ref={containerRef}>
      {/* Notification Bell Button */}
      <button
        type="button"
        onClick={() => {
          setIsOpen(!isOpen);
          if (!isOpen) loadNotifications();
        }}
        aria-label="View notifications"
        className="relative p-2 rounded-btn text-[#475569] hover:text-[#0F172A] hover:bg-slate-50 border border-[#E2E8F0] transition cursor-pointer"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-[#DC2626] text-white text-[10px] font-bold flex items-center justify-center shadow-xs animate-pulse">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown Popover */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-white rounded-card border border-[#E2E8F0] shadow-xl z-50 overflow-hidden animate-in fade-in duration-150">
          {/* Header */}
          <div className="p-3.5 border-b border-[#E2E8F0] flex items-center justify-between bg-[#F8FAFC]">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-xs text-[#0F172A]">Notifications</span>
              {unreadCount > 0 && (
                <span className="px-1.5 py-0.5 rounded-full bg-[#FEE2E2] text-[#991B1B] text-[10px] font-semibold">
                  {unreadCount} unread
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={handleMarkAllRead}
                  className="text-[11px] font-semibold text-[#0F766E] hover:text-[#115E59] flex items-center gap-1 cursor-pointer"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  <span>Mark all read</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="text-[#64748B] hover:text-[#0F172A] p-1 cursor-pointer"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Filter Tabs */}
          <div className="px-3 py-1.5 border-b border-[#E2E8F0] flex items-center gap-2 text-[11px]">
            <button
              onClick={() => setActiveFilter("all")}
              className={`px-2 py-1 rounded font-semibold cursor-pointer transition ${
                activeFilter === "all"
                  ? "bg-[#E6F4F1] text-[#0F766E]"
                  : "text-[#64748B] hover:text-[#0F172A]"
              }`}
            >
              All ({notifications.length})
            </button>
            <button
              onClick={() => setActiveFilter("unread")}
              className={`px-2 py-1 rounded font-semibold cursor-pointer transition ${
                activeFilter === "unread"
                  ? "bg-[#E6F4F1] text-[#0F766E]"
                  : "text-[#64748B] hover:text-[#0F172A]"
              }`}
            >
              Unread ({unreadCount})
            </button>
          </div>

          {/* Notification List */}
          <div className="max-h-[360px] overflow-y-auto divide-y divide-[#E2E8F0]">
            {filteredNotifications.length === 0 ? (
              <div className="py-10 text-center text-xs text-[#64748B]">
                <Bell className="w-6 h-6 mx-auto mb-2 text-[#CBD5E1]" />
                <p>No {activeFilter === "unread" ? "unread " : ""}notifications.</p>
                <p className="text-[10px] text-[#94A3B8] mt-0.5">You are up to date on your care pathway.</p>
              </div>
            ) : (
              filteredNotifications.slice(0, 10).map((n) => (
                <div
                  key={n.id}
                  onClick={() => handleNotificationClick(n)}
                  className={`p-3.5 transition flex items-start gap-3 cursor-pointer ${
                    !n.is_read
                      ? "bg-[#F0FDF4]/50 hover:bg-[#F0FDF4]"
                      : "hover:bg-[#F8FAFC]"
                  }`}
                >
                  <div className="mt-0.5 shrink-0">
                    <div className="w-7 h-7 rounded-full bg-[#F1F5F9] border border-[#E2E8F0] flex items-center justify-center">
                      {getEventIcon(n.event_type, n.priority)}
                    </div>
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1 mb-0.5">
                      <span className="font-semibold text-xs text-[#0F172A] truncate">
                        {n.title}
                      </span>
                      <span className="text-[10px] text-[#64748B] shrink-0">
                        {formatRelativeTime(n.created_at)}
                      </span>
                    </div>

                    <p className="text-[11px] text-[#475569] leading-snug line-clamp-2">
                      {n.message}
                    </p>

                    <div className="mt-1.5 flex items-center justify-between text-[10px]">
                      {n.priority === "critical" ? (
                        <span className="text-[#DC2626] font-semibold uppercase">Critical Alert</span>
                      ) : n.priority === "urgent" ? (
                        <span className="text-[#D97706] font-semibold uppercase">Urgent Notice</span>
                      ) : (
                        <span className="text-[#0F766E] font-medium">Care Update</span>
                      )}

                      {!n.is_read && (
                        <button
                          type="button"
                          onClick={(e) => handleMarkAsRead(n.id, e)}
                          title="Mark as read"
                          className="text-[#64748B] hover:text-[#0F766E] flex items-center gap-0.5 cursor-pointer font-medium"
                        >
                          <Check className="w-3 h-3" />
                          <span>Mark read</span>
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Dropdown Footer: View All Notifications */}
          <div className="p-2.5 bg-[#F8FAFC] border-t border-[#E2E8F0] text-center">
            <button
              type="button"
              onClick={() => {
                setIsOpen(false);
                router.push("/notifications");
              }}
              className="text-xs font-semibold text-[#0F766E] hover:text-[#115E59] inline-flex items-center gap-1 cursor-pointer"
            >
              <span>View all notifications ({notifications.length})</span>
              <ExternalLink className="w-3 h-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
