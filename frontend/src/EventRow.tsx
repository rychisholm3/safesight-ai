import type { SafeEvent } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function label(e: SafeEvent): string {
  if (e.event_type === "missing_ppe") {
    const items = e.missing_ppe.length ? e.missing_ppe.join(", ") : "PPE";
    return `Missing ${items}`;
  }
  return `Zone intrusion${e.zone_id ? ` — ${e.zone_id}` : ""}`;
}

function timeStr(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

interface Props {
  event: SafeEvent;
}

export function EventRow({ event }: Props) {
  const isOpen = event.end_frame === null;
  const isPpe = event.event_type === "missing_ppe";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 14px",
        borderRadius: 6,
        background: isOpen ? (isPpe ? "#fff3cd" : "#f8d7da") : "#f0f0f0",
        borderLeft: `4px solid ${isOpen ? (isPpe ? "#f0a500" : "#dc3545") : "#aaa"}`,
        opacity: isOpen ? 1 : 0.7,
      }}
    >
      <span style={{ fontSize: 18 }}>{isPpe ? "🦺" : "⛔"}</span>

      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{label(event)}</div>
        <div style={{ fontSize: 12, color: "#555" }}>
          Person #{event.track_id}
          {event.zone_id ? ` · ${event.zone_id}` : ""}
          {" · "}frame {event.start_frame}
          {event.end_frame !== null ? `–${event.end_frame}` : "+"}
        </div>
      </div>

      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: isOpen ? (isPpe ? "#856404" : "#842029") : "#666",
          }}
        >
          {isOpen ? "ACTIVE" : "CLOSED"}
        </div>
        <div style={{ fontSize: 11, color: "#888" }}>{timeStr(event.created_at)}</div>
      </div>

      {event.snapshot_path && (
        <a
          href={`${BASE}/snapshots/${event.snapshot_path.split(/[\\/]/).pop()}`}
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: 11, color: "#0d6efd", flexShrink: 0 }}
        >
          snapshot
        </a>
      )}
    </div>
  );
}
