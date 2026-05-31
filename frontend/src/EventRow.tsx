import { useState } from "react";
import type { SafeEvent } from "./types";
import { EventDetail } from "./EventDetail";

function label(e: SafeEvent): string {
  if (e.event_type === "missing_ppe") {
    const items = e.missing_ppe.length ? e.missing_ppe.join(", ") : "PPE";
    return `Missing ${items}`;
  }
  return `Zone intrusion${e.zone_id ? ` — ${e.zone_id}` : ""}`;
}

function oshaHint(e: SafeEvent): string {
  if (e.event_type === "missing_ppe") {
    const first = e.missing_ppe[0];
    if (first === "hardhat") return "29 CFR 1926.100(a)";
    if (first === "vest")    return "29 CFR 1926.28(a)";
    if (first === "mask")    return "29 CFR 1910.134(a)";
    if (first === "gloves")  return "29 CFR 1910.138(a)";
    return "29 CFR 1926.95(a)";
  }
  return "29 CFR 1926.200(a)";
}

function timeStr(iso: string): string {
  return new Date(iso).toLocaleTimeString();
}

interface Props {
  event: SafeEvent;
}

export function EventRow({ event }: Props) {
  const [showDetail, setShowDetail] = useState(false);
  const isOpen = event.end_frame === null;
  const isPpe  = event.event_type === "missing_ppe";

  return (
    <>
      <div
        onClick={() => setShowDetail(true)}
        title="Click to view OSHA details"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 14px",
          borderRadius: 6,
          background: isOpen ? (isPpe ? "#fff3cd" : "#f8d7da") : "#f0f0f0",
          borderLeft: `4px solid ${isOpen ? (isPpe ? "#f0a500" : "#dc3545") : "#aaa"}`,
          opacity: isOpen ? 1 : 0.7,
          cursor: "pointer",
          transition: "box-shadow .15s",
        }}
        onMouseEnter={e => (e.currentTarget.style.boxShadow = "0 2px 10px rgba(0,0,0,.12)")}
        onMouseLeave={e => (e.currentTarget.style.boxShadow = "none")}
      >
        <span style={{ fontSize: 18 }}>{isPpe ? "🦺" : "⛔"}</span>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{label(event)}</div>
          <div style={{ fontSize: 12, color: "#555" }}>
            Person #{event.track_id}
            {event.zone_id ? ` · ${event.zone_id}` : ""}
            {" · "}frame {event.start_frame}
            {event.end_frame !== null ? `–${event.end_frame}` : "+"}
          </div>
          {/* OSHA citation hint */}
          <div style={{ fontSize: 10, color: "#6b7280", marginTop: 3, fontFamily: "monospace" }}>
            ⚖ {oshaHint(event)} — click for details
          </div>
        </div>

        <div style={{ textAlign: "right", flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
          <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                padding: "1px 6px",
                borderRadius: 4,
                background: event.severity === "CRITICAL" ? "#dc3545" : "#f0a500",
                color: "#fff",
                letterSpacing: 0.5,
                textTransform: "uppercase",
              }}
            >
              {event.severity ?? (isPpe ? "WARNING" : "CRITICAL")}
            </span>
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                padding: "1px 6px",
                borderRadius: 4,
                background: isOpen ? "#1a1a2e" : "#d1d5db",
                color: isOpen ? "#fff" : "#666",
              }}
            >
              {isOpen ? "ACTIVE" : "CLOSED"}
            </span>
          </div>
          <div style={{ fontSize: 11, color: "#888" }}>{timeStr(event.created_at)}</div>
        </div>
      </div>

      {showDetail && (
        <EventDetail event={event} onClose={() => setShowDetail(false)} />
      )}
    </>
  );
}
