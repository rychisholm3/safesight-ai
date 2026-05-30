import { useCallback, useEffect, useState } from "react";
import type { SafeEvent, Stats } from "./types";
import { fetchStats } from "./api";
import { useWebSocket } from "./useWebSocket";
import { EventRow } from "./EventRow";

const MAX_EVENTS = 200;

export default function App() {
  const [events, setEvents] = useState<SafeEvent[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [filter, setFilter] = useState<"all" | "missing_ppe" | "zone_intrusion">("all");
  const [connected, setConnected] = useState(false);

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
    (e) => filter === "all" || e.event_type === filter
  );

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", minHeight: "100vh", background: "#f5f6fa" }}>
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

        {stats && (
          <div style={{ marginLeft: "auto", display: "flex", gap: 20, fontSize: 13 }}>
            <StatChip label="Total" value={stats.total} color="#94a3b8" />
            <StatChip label="Active" value={stats.open} color="#f87171" />
            <StatChip label="Missing PPE" value={stats.by_type["missing_ppe"] ?? 0} color="#fbbf24" />
            <StatChip label="Zone" value={stats.by_type["zone_intrusion"] ?? 0} color="#f87171" />
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
        <span style={{ fontSize: 13, color: "#555", marginRight: 4 }}>Filter:</span>
        {(["all", "missing_ppe", "zone_intrusion"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: "4px 12px",
              borderRadius: 20,
              border: "1px solid #d1d5db",
              background: filter === f ? "#1a1a2e" : "#fff",
              color: filter === f ? "#fff" : "#374151",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: filter === f ? 600 : 400,
            }}
          >
            {f === "all" ? "All" : f === "missing_ppe" ? "Missing PPE" : "Zone Intrusion"}
          </button>
        ))}
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#9ca3af" }}>
          {visible.length} event{visible.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Event list */}
      <div style={{ padding: "16px 24px", maxWidth: 860, margin: "0 auto" }}>
        {visible.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              padding: "60px 0",
              color: "#9ca3af",
              fontSize: 15,
            }}
          >
            {connected ? "No events yet — pipeline is watching." : "Connecting to SafeSight…"}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {visible.map((e) => (
              <EventRow key={e.event_id} event={e} />
            ))}
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
