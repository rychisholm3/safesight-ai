/**
 * EventDetail — full violation detail modal with OSHA regulation cards.
 *
 * Opened when a user clicks an EventRow. Fetches the matched OSHA codes
 * from /osha/lookup and renders:
 *   • Violation summary (type, severity, worker, zone, time)
 *   • Snapshot image (if one was captured)
 *   • One OSHA card per matched regulation:
 *       - CFR citation, title, fine range
 *       - Plain-English explanation
 *       - Corrective action checklist
 *       - Link to official OSHA page
 */
import { useEffect, useState } from "react";
import type { SafeEvent } from "./types";
import { fetchOshaLookup } from "./api";
import type { OshaCode } from "./api";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtCurrency(n: number): string {
  return "$" + n.toLocaleString("en-US");
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

function severityColor(s: string): string {
  return s === "CRITICAL" ? "#dc2626" : "#d97706";
}

function eventLabel(e: SafeEvent): string {
  if (e.event_type === "missing_ppe") {
    const items = e.missing_ppe.length ? e.missing_ppe.map(p => p.toUpperCase()).join(" + ") : "PPE";
    return `Missing ${items}`;
  }
  return `Zone Intrusion${e.zone_id ? ` — ${e.zone_id}` : ""}`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function OshaCard({ code }: { code: OshaCode }) {
  return (
    <div style={{
      borderRadius: 8,
      border: "1px solid #e5e7eb",
      overflow: "hidden",
      background: "#fff",
    }}>
      {/* Card header */}
      <div style={{
        background: "#1a1a2e",
        padding: "10px 16px",
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        flexWrap: "wrap",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: "#94a3b8", fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", marginBottom: 2 }}>
            OSHA Regulation
          </div>
          <div style={{ fontSize: 15, fontWeight: 800, color: "#fff", letterSpacing: 0.3 }}>
            {code.code}
          </div>
          <div style={{ fontSize: 13, color: "#cbd5e1", marginTop: 2 }}>
            {code.title}
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase" }}>
            Fine per violation
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "#fbbf24", marginTop: 2 }}>
            {fmtCurrency(code.fine_min_usd)} – {fmtCurrency(code.fine_max_usd)}
          </div>
          <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>
            Willful: up to {fmtCurrency(code.willful_max_usd)}
          </div>
        </div>
      </div>

      {/* Plain-English explanation */}
      <div style={{ padding: "12px 16px", background: "#f8fafc", borderBottom: "1px solid #e5e7eb" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
          What this means
        </div>
        <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.6 }}>
          {code.plain_english}
        </div>
      </div>

      {/* Regulatory description */}
      <div style={{ padding: "10px 16px", borderBottom: "1px solid #e5e7eb" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
          Regulation text
        </div>
        <div style={{ fontSize: 12, color: "#6b7280", lineHeight: 1.6, fontStyle: "italic" }}>
          "{code.description}"
        </div>
      </div>

      {/* Corrective actions */}
      <div style={{ padding: "12px 16px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
          Corrective actions
        </div>
        <ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}>
          {code.corrective_actions.map((action, i) => (
            <li key={i} style={{ fontSize: 13, color: "#374151", lineHeight: 1.5 }}>
              {action}
            </li>
          ))}
        </ol>
      </div>

      {/* Footer */}
      {code.reference_url && (
        <div style={{ padding: "8px 16px", background: "#f8fafc", borderTop: "1px solid #e5e7eb" }}>
          <a
            href={code.reference_url}
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: 12, color: "#3b82f6", textDecoration: "none", fontWeight: 500 }}
          >
            View full regulation on OSHA.gov →
          </a>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  event: SafeEvent;
  onClose: () => void;
}

export function EventDetail({ event, onClose }: Props) {
  const [codes, setCodes]     = useState<OshaCode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchOshaLookup(event)
      .then(setCodes)
      .catch(() => setCodes([]))
      .finally(() => setLoading(false));
  }, [event.event_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const isOpen = event.end_frame === null;
  const isPpe  = event.event_type === "missing_ppe";
  const sColor = severityColor(event.severity);
  const snapshotFile = event.snapshot_path?.split(/[\\/]/).pop();

  return (
    <div
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 200, padding: 16,
      }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{
        background: "#f8fafc",
        borderRadius: 12,
        width: "96vw", maxWidth: 720,
        maxHeight: "92vh",
        display: "flex", flexDirection: "column",
        overflow: "hidden",
        boxShadow: "0 32px 80px rgba(0,0,0,.5)",
      }}>

        {/* ── Header ── */}
        <div style={{
          background: "#1a1a2e",
          padding: "16px 20px",
          display: "flex", alignItems: "flex-start", gap: 14,
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 28, lineHeight: 1 }}>{isPpe ? "🦺" : "⛔"}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 17, color: "#fff" }}>
              {eventLabel(event)}
            </div>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 3 }}>
              Worker #{event.track_id}
              {event.zone_id ? ` · Zone: ${event.zone_id}` : ""}
              {" · "}
              {fmtTime(event.created_at)}
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
            <span style={{
              fontSize: 11, fontWeight: 800, padding: "3px 10px", borderRadius: 5,
              background: sColor, color: "#fff", letterSpacing: 0.8, textTransform: "uppercase",
            }}>
              {event.severity}
            </span>
            <span style={{
              fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 5,
              background: isOpen ? "#22c55e" : "#64748b", color: "#fff", letterSpacing: 0.5,
            }}>
              {isOpen ? "ACTIVE" : "CLOSED"}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", color: "#9ca3af", fontSize: 24, cursor: "pointer", lineHeight: 1, marginLeft: 4 }}
          >
            ×
          </button>
        </div>

        {/* ── Body ── */}
        <div style={{ flex: 1, overflowY: "auto", padding: "18px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Snapshot */}
          {snapshotFile && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
                Captured snapshot
              </div>
              <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #e5e7eb" }}>
                <img
                  src={`${BASE}/snapshots/${snapshotFile}`}
                  alt="Violation snapshot"
                  style={{ width: "100%", display: "block", maxHeight: 260, objectFit: "cover" }}
                  onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
              </div>
            </div>
          )}

          {/* Violation details row */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: 10,
          }}>
            {[
              { label: "Event type",   value: isPpe ? "Missing PPE" : "Zone Intrusion" },
              { label: "Worker ID",    value: `#${event.track_id}` },
              { label: "Zone",         value: event.zone_id ?? "—" },
              { label: "Start frame",  value: String(event.start_frame) },
              { label: "End frame",    value: event.end_frame !== null ? String(event.end_frame) : "Ongoing" },
              ...(isPpe && event.missing_ppe.length ? [{ label: "Missing PPE", value: event.missing_ppe.join(", ") }] : []),
            ].map(({ label, value }) => (
              <div key={label} style={{
                background: "#fff", borderRadius: 7, padding: "10px 14px",
                border: "1px solid #e5e7eb",
              }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>
                  {label}
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "#1f2937", marginTop: 3 }}>
                  {value}
                </div>
              </div>
            ))}
          </div>

          {/* OSHA cards */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>
              {loading ? "Loading OSHA regulations…" : `${codes.length} OSHA regulation${codes.length !== 1 ? "s" : ""} triggered`}
            </div>

            {loading && (
              <div style={{ textAlign: "center", padding: "24px 0", color: "#9ca3af" }}>
                <div style={{ width: 28, height: 28, border: "3px solid #e2e8f0", borderTopColor: "#3b82f6", borderRadius: "50%", animation: "spin .7s linear infinite", margin: "0 auto 10px" }} />
                Fetching OSHA regulations…
              </div>
            )}

            {!loading && codes.length === 0 && (
              <div style={{ padding: "20px", textAlign: "center", color: "#9ca3af", fontSize: 13, background: "#fff", borderRadius: 8, border: "1px solid #e5e7eb" }}>
                No OSHA codes matched for this violation type.
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {codes.map(code => (
                <OshaCard key={code.code} code={code} />
              ))}
            </div>
          </div>

          {/* Disclaimer */}
          {!loading && codes.length > 0 && (
            <div style={{ padding: "10px 14px", background: "#fffbeb", borderRadius: 7, border: "1px solid #fde68a", fontSize: 11, color: "#92400e" }}>
              <strong>Disclaimer:</strong> Fine amounts reflect the 2024 OSHA adjusted penalty schedule for serious violations.
              Actual fines depend on severity, employer history, and abatement good faith. Consult a qualified safety professional
              or OSHA area office for compliance guidance.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
