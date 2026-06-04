import { useCallback, useEffect, useState } from "react";
import type { SafeEvent, Stats } from "./types";
import { fetchStats } from "./api";
import { useAuth } from "./AuthContext";
import { useWebSocket } from "./useWebSocket";
import { EventRow } from "./EventRow";
import { ZoneEditor } from "./ZoneEditor";
import { LoginPage } from "./LoginPage";
import { SettingsPage } from "./SettingsPage";
import { CopilotPanel } from "./CopilotPanel";
import { CompliancePanel } from "./CompliancePanel";
import { RootCausePanel } from "./RootCausePanel";
import { TimelinePanel } from "./TimelinePanel";
import { RiskPanel } from "./RiskPanel";
import { SetupWizard } from "./SetupWizard";

const MAX_EVENTS = 200;

const ROLE_LABEL: Record<string, string> = {
  safety_officer: "Safety Officer",
  site_manager:   "Site Manager",
  executive:      "Executive",
  auditor:        "Auditor",
};

export default function App() {
  const { user, loading, signOut } = useAuth();

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", background: "#f5f6fa", color: "#9ca3af", fontSize: 14 }}>
        Loading…
      </div>
    );
  }

  if (!user) return <LoginPage />;

  return <Dashboard user={user} signOut={signOut} />;
}

function Dashboard({ user, signOut }: { user: { email: string; role: string }; signOut: () => void }) {
  const [events, setEvents] = useState<SafeEvent[]>([]);
  const [showZoneEditor, setShowZoneEditor] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showSetup, setShowSetup] = useState(
    () => !localStorage.getItem("safesight_setup_done")
  );
  const [stats, setStats] = useState<Stats | null>(null);
  const [filter, setFilter] = useState<"all" | "missing_ppe" | "zone_intrusion" | "near_miss">("all");
  const [severityFilter, setSeverityFilter] = useState<"all" | "WARNING" | "CRITICAL">("all");
  const [connected, setConnected] = useState(false);
  const [view, setView] = useState<"events" | "risk" | "copilot" | "timeline" | "compliance" | "rootcause">("events");

  const refreshStats = useCallback(() => {
    fetchStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    refreshStats();
    const id = setInterval(refreshStats, 10_000);
    return () => clearInterval(id);
  }, [refreshStats]);

  useWebSocket({
    onHistory: (history) => {
      setEvents(history);
      setConnected(true);
    },
    onOpened: (event) => {
      setEvents((prev) => [event, ...prev].slice(0, MAX_EVENTS));
      refreshStats();
    },
    onClosed: (event) => {
      setEvents((prev) =>
        prev.map((e) => (e.event_id === event.event_id ? event : e))
      );
      refreshStats();
    },
  });

  const visible = events.filter(
    (e) =>
      (filter === "all" || e.event_type === filter) &&
      (severityFilter === "all" || e.severity === severityFilter)
  );

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", minHeight: "100vh", background: "#f5f6fa" }}>
      {showSetup     && <SetupWizard onDone={() => setShowSetup(false)} />}
      {showZoneEditor && <ZoneEditor onClose={() => setShowZoneEditor(false)} />}
      {showSettings  && <SettingsPage onClose={() => setShowSettings(false)} />}
      {/* Header */}
      <div
        style={{
          background: "#1a1a2e",
          color: "#fff",
          padding: "14px 24px",
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 18, letterSpacing: 0.5 }}>
          SafeSight AI
        </div>
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: connected ? "#22c55e" : "#ef4444",
            flexShrink: 0,
          }}
          title={connected ? "Live" : "Connecting…"}
        />
        <div style={{ fontSize: 12, color: "#aaa" }}>{connected ? "Live" : "Connecting…"}</div>

        <button
          onClick={() => setShowSetup(true)}
          style={{
            marginLeft: 16, padding: "5px 14px", borderRadius: 20,
            border: "1px solid #3b82f6", background: "rgba(59,130,246,.15)",
            color: "#93c5fd", fontSize: 12, cursor: "pointer", fontWeight: 600,
          }}
          title="Camera &amp; zone setup wizard"
        >
          ⚙ Setup
        </button>

        <button
          onClick={() => setShowZoneEditor(true)}
          style={{
            padding: "5px 14px", borderRadius: 20,
            border: "1px solid #4b5563", background: "transparent",
            color: "#d1d5db", fontSize: 12, cursor: "pointer", fontWeight: 500,
          }}
        >
          Edit Zones
        </button>

        <button
          onClick={() => setShowSettings(true)}
          style={{
            padding: "5px 14px", borderRadius: 20,
            border: "1px solid #4b5563", background: "transparent",
            color: "#d1d5db", fontSize: 12, cursor: "pointer", fontWeight: 500,
          }}
        >
          Alerts
        </button>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 12, color: "#e5e7eb" }}>{user.email}</div>
            <div style={{
              fontSize: 10, color: "#94a3b8",
              textTransform: "uppercase", letterSpacing: 0.5,
            }}>
              {ROLE_LABEL[user.role] ?? user.role}
            </div>
          </div>
          <button
            onClick={signOut}
            style={{
              padding: "5px 12px", borderRadius: 20,
              border: "1px solid #4b5563", background: "transparent",
              color: "#9ca3af", fontSize: 11, cursor: "pointer",
            }}
          >
            Sign out
          </button>
        </div>

        {stats && (
          <div style={{ display: "flex", gap: 20, fontSize: 13 }}>
            <StatChip label="Total" value={stats.total} color="#94a3b8" />
            <StatChip label="Active" value={stats.open} color="#f87171" />
            <StatChip label="Missing PPE" value={stats.by_type["missing_ppe"] ?? 0} color="#fbbf24" />
            <StatChip label="Zone" value={stats.by_type["zone_intrusion"] ?? 0} color="#f87171" />
            <StatChip label="Near Miss" value={stats.by_type["near_miss"] ?? 0} color="#a855f7" />
          </div>
        )}
      </div>

      {/* Toolbar */}
      <div
        style={{
          padding: "12px 24px",
          display: "flex",
          gap: 8,
          alignItems: "center",
          background: "#fff",
          borderBottom: "1px solid #e5e7eb",
        }}
      >
        {/* View toggle */}
        {(["events", "risk", "copilot", "timeline", "compliance", "rootcause"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            style={{
              padding: "4px 14px", borderRadius: 20,
              border: v === "copilot" ? "1px solid #3b82f6" : "1px solid #d1d5db",
              background: view === v ? (v === "copilot" ? "#3b82f6" : "#1a1a2e") : "#fff",
              color: view === v ? "#fff" : (v === "copilot" ? "#3b82f6" : "#374151"),
              cursor: "pointer", fontSize: 12,
              fontWeight: view === v ? 600 : 400,
            }}
          >
            {v === "events"     ? "Events"
             : v === "risk"     ? "Risk"
             : v === "copilot"  ? "🤖 Copilot"
             : v === "timeline"    ? "📋 Timeline"
             : v === "compliance" ? "✅ Compliance"
             :                      "🔍 Root Cause"}
          </button>
        ))}

        {view === "events" && (
          <>
            <span style={{ color: "#d1d5db", margin: "0 4px" }}>|</span>
            <span style={{ fontSize: 13, color: "#555", marginRight: 4 }}>Filter:</span>
            {(["all", "missing_ppe", "zone_intrusion", "near_miss"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: "4px 12px", borderRadius: 20,
                  border: f === "near_miss" ? "1px solid #a855f7" : "1px solid #d1d5db",
                  background: filter === f ? (f === "near_miss" ? "#a855f7" : "#1a1a2e") : "#fff",
                  color: filter === f ? "#fff" : (f === "near_miss" ? "#a855f7" : "#374151"),
                  cursor: "pointer", fontSize: 12,
                  fontWeight: filter === f ? 600 : 400,
                }}
              >
                {f === "all" ? "All" : f === "missing_ppe" ? "Missing PPE" : f === "zone_intrusion" ? "Zone Intrusion" : "⚡ Near Miss"}
              </button>
            ))}
            <span style={{ color: "#d1d5db", margin: "0 4px" }}>|</span>
            <span style={{ fontSize: 13, color: "#555", marginRight: 4 }}>Severity:</span>
            {(["all", "CRITICAL", "WARNING"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSeverityFilter(s)}
                style={{
                  padding: "4px 12px", borderRadius: 20,
                  border: `1px solid ${s === "CRITICAL" ? "#dc3545" : s === "WARNING" ? "#f0a500" : "#d1d5db"}`,
                  background: severityFilter === s
                    ? (s === "CRITICAL" ? "#dc3545" : s === "WARNING" ? "#f0a500" : "#1a1a2e")
                    : "#fff",
                  color: severityFilter === s ? "#fff"
                    : (s === "CRITICAL" ? "#dc3545" : s === "WARNING" ? "#f0a500" : "#374151"),
                  cursor: "pointer", fontSize: 12,
                  fontWeight: severityFilter === s ? 700 : 400,
                }}
              >
                {s === "all" ? "All" : s}
              </button>
            ))}
            <span style={{ marginLeft: "auto", fontSize: 12, color: "#9ca3af" }}>
              {visible.length} event{visible.length !== 1 ? "s" : ""}
            </span>
          </>
        )}
      </div>

      {/* Main content */}
      <div style={{ padding: "16px 24px", maxWidth: view === "copilot" ? 820 : 900, margin: "0 auto" }}>
        {view === "copilot" ? (
          <CopilotPanel userRole={user.role} />
        ) : view === "timeline" ? (
          <TimelinePanel />
        ) : view === "compliance" ? (
          <CompliancePanel />
        ) : view === "rootcause" ? (
          <RootCausePanel />
        ) : view === "risk" ? (
          <RiskPanel />
        ) : visible.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 0", color: "#9ca3af", fontSize: 15 }}>
            {connected ? "No events yet — pipeline is watching." : "Connecting to SafeSight…"}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {visible.map((e) => <EventRow key={e.event_id} event={e} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function StatChip({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontWeight: 700, fontSize: 16, color }}>{value}</div>
      <div style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 0.5 }}>
        {label}
      </div>
    </div>
  );
}
