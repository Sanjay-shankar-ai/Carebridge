"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
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
  ArrowLeft,
  RefreshCw,
} from "lucide-react";
import {
  fetchNotifications,
  markNotificationRead,
  markAllNotificationsRead,
} from "../../services/api";
import { NotificationItem } from "../../types";
import { useAuth } from "../../context/AuthContext";
import { Card, CardHeader } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { LoadingState } from "../../components/ui/EmptyState";

export default function NotificationsPage() {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unread">("all");

  const loadAll = async () => {
    try {
      setLoading(true);
      const res = await fetchNotifications(false, 100);
      setNotifications(res || []);
    } catch (err) {
      console.error("Failed to load notifications:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, [user]);

  const handleMarkAsRead = async (id: string) => {
    try {
      await markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n))
      );
    } catch (err) {
      console.error("Error marking read:", err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, is_read: true, read_at: new Date().toISOString() }))
      );
    } catch (err) {
      console.error("Error marking all read:", err);
    }
  };

  const filtered = notifications.filter((n) => {
    if (filter === "unread") return !n.is_read;
    return true;
  });

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div className="space-y-6 max-w-4xl mx-auto pb-12">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              href="/"
              className="text-xs text-[#0F766E] hover:underline inline-flex items-center gap-1 font-semibold"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Portal</span>
            </Link>
          </div>
          <h1 className="text-xl sm:text-2xl font-semibold text-[#0F172A] tracking-tight">
            Notification Center
          </h1>
          <p className="text-xs sm:text-sm text-[#475569] mt-0.5">
            Full audit of real-time clinical alerts, appointment updates, and care pathway events
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {unreadCount > 0 && (
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<CheckCheck className="w-3.5 h-3.5 text-[#0F766E]" />}
              onClick={handleMarkAllRead}
            >
              Mark All Read
            </Button>
          )}
          <Button
            size="sm"
            variant="secondary"
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />}
            onClick={loadAll}
          >
            Refresh
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2 border-b border-[#E2E8F0] pb-2 text-xs">
        <button
          type="button"
          onClick={() => setFilter("all")}
          className={`px-3 py-1.5 rounded-btn font-semibold cursor-pointer transition ${
            filter === "all" ? "bg-[#0F766E] text-white" : "text-[#64748B] hover:bg-[#F8FAFC]"
          }`}
        >
          All ({notifications.length})
        </button>
        <button
          type="button"
          onClick={() => setFilter("unread")}
          className={`px-3 py-1.5 rounded-btn font-semibold cursor-pointer transition ${
            filter === "unread" ? "bg-[#0F766E] text-white" : "text-[#64748B] hover:bg-[#F8FAFC]"
          }`}
        >
          Unread ({unreadCount})
        </button>
      </div>

      {loading ? (
        <LoadingState message="Loading notifications..." />
      ) : filtered.length === 0 ? (
        <Card padding="lg" className="text-center py-12">
          <Bell className="w-8 h-8 text-[#94A3B8] mx-auto mb-2" />
          <h3 className="font-semibold text-sm text-[#0F172A]">No notifications found</h3>
          <p className="text-xs text-[#64748B] mt-0.5">You are up to date on all care pathway milestones.</p>
        </Card>
      ) : (
        <div className="space-y-2.5">
          {filtered.map((n) => (
            <div
              key={n.id}
              className={`p-4 rounded-card border transition flex items-start justify-between gap-4 ${
                !n.is_read ? "bg-[#F0FDF4]/60 border-[#BBF7D0]" : "bg-white border-[#E2E8F0]"
              }`}
            >
              <div className="space-y-1 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-xs text-[#0F172A]">{n.title}</span>
                  <Badge
                    variant={
                      n.priority === "critical"
                        ? "error"
                        : n.priority === "urgent"
                        ? "warning"
                        : "info"
                    }
                  >
                    {n.priority}
                  </Badge>
                  <span className="text-[11px] text-[#64748B]">
                    {new Date(n.created_at).toLocaleString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
                <p className="text-xs text-[#475569] leading-relaxed">{n.message}</p>
                {n.action_link && (
                  <Link
                    href={n.action_link}
                    className="text-xs font-semibold text-[#0F766E] hover:underline inline-block pt-1"
                  >
                    Open Associated Case →
                  </Link>
                )}
              </div>

              {!n.is_read && (
                <button
                  type="button"
                  onClick={() => handleMarkAsRead(n.id)}
                  className="px-2.5 py-1 rounded bg-[#E6F4F1] text-[#0F766E] hover:bg-[#CCFBF1] text-[11px] font-semibold cursor-pointer shrink-0"
                >
                  Mark Read
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
