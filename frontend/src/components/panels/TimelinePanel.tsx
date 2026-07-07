import { useCallback, useEffect, useState } from "react";
import {
  fetchTimeline, addNote, deleteNote, downloadTimelinePdf,
  type TimelineData, type TimelineEvent, type HourGroup,
  type TimelineNote, type IncidentStory,
} from "../../lib/api";

const TYPE_META: Record<string, { icon: string; color: string; label: string }> = {
  missing_ppe:    { icon: "🦺", color: "#d97706", label: "Missing PPE" },
  zone_intrusion: { icon: "⛔", color: "#dc2626", label: "Zone Intrusion" },
  near_miss:      { icon: "⚡", color: "#a855f7", label: "Near Miss" },
};

function fmtTime(iso: string) {
  try { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
  catch { return iso.slice(11, 16); }
}

// ── Incident story card ───────────────────────────────────────────────────────

function IncidentCard({ incident }: { incident: IncidentStory }) {
  const [open, setOpen] = useState(false);
  const isCritical   = incident.severity === "CRITICAL";
  const borderColor  = incident.is_escalating ? "#dc2626" : isCritical ? "#dc2626" : "#d97706";
  const bgColor      = incident.is_escalating ? "#fef2f2" : isCritical ? "#fff5f5" : "#fffbeb";

  return (
    <div style={{
      borderRadius: 8, border: `1px solid ${borderColor}55`,
      background: bgColor, overflow: "hidden", marginBottom: 8,
    }}>
      {/* Header */}
      <div
        onClick={() => setOpen(v => !v)}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "10px 14px", cursor: "pointer",
          borderLeft: `4px solid ${borderColor}`,
        }}
      >
        <span style={{ fontSize: 18 }}>{incident.is_escalating ? "🚨" : "⚠️"}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#1f2937" }}>
            {incident.is_escalating ? "Escalating Incident" : "Multi-Event Incident"} — Worker #{incident.track_id}
          </div>
          <div style={{ fontSize: 11, color: "#6b7280" }}>
            {incident.event_count} events · {incident.duration_minutes.toFixed(0)} min ·
            {" "}{fmtTime(incident.start_time)} → {fmtTime(incident.end_time)}
            {incident.zones.length > 0 && ` · ${incident.zones.join(", ")}`}
          </div>
        </div>
        <div style={{ display: "flex", gap: 5, alignItems: "center", flexShrink: 0 }}>
          {incident.event_types.map((t) => {
            const m = TYPE_META[t] ?? { icon: "❓", color: "#6b7280" };
            return (
              <span key={t} style={{
                fontSize: 10, padding: "2px 7px", borderRadius: 10,
                background: m.color + "22", color: m.color, fontWeight: 700,
              }}>{m.icon}</span>
            );
          })}
          <span style={{
            fontSize: 9, padding: "2px 7px", borderRadius: 4,
            background: borderColor, color: "#fff", fontWeight: 700, letterSpacing: 0.5,
          }}>
            {incident.severity}
          </span>
          <span style={{ fontSize: 11, color: "#9ca3af" }}>{open ? "▲" : "▼"}</span>
        </div>
      </div>

      {/* Narrative */}
      <div style={{ padding: "8px 14px 6px 18px", fontSize: 12, color: "#374151", lineHeight: 1.6 }}>
        {incident.narrative}
      </div>

      {/* Expanded event sequence */}
      {open && (
        <div style={{ padding: "0 14px 10px 18px" }}>
          <div style={{ fontSize: 10, color: "#9ca3af", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
            Event sequence
          </div>
          {incident.events.map((ev, i) => {
            const m = TYPE_META[ev.event_type] ?? { icon: "❓", color: "#6b7280", label: ev.event_type };
            const ppe = ev.missing_ppe?.join(", ");
            return (
              <div key={ev.event_id} style={{
                display: "flex", gap: 8, alignItems: "flex-start",
                padding: "4px 0", borderBottom: i < incident.events.length - 1 ? "1px solid #f1f5f9" : "none",
              }}>
                <span style={{ fontSize: 12, color: "#9ca3af", minWidth: 20 }}>{i + 1}.</span>
                <span style={{ fontSize: 13 }}>{m.icon}</span>
                <div style={{ flex: 1, fontSize: 12, color: "#374151" }}>
                  {m.label}{ppe ? ` — ${ppe}` : ""}
                </div>
                <span style={{
                  fontSize: 9, padding: "1px 6px", borderRadius: 3,
                  background: ev.severity === "CRITICAL" ? "#dc2626" : "#d97706",
                  color: "#fff", fontWeight: 700, flexShrink: 0,
                }}>{ev.severity}</span>
                <span style={{ fontSize: 11, color: "#9ca3af", flexShrink: 0 }}>{fmtTime(ev.created_at)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Supervisor note input ─────────────────────────────────────────────────────

function NoteInput({ eventId, onAdded }: { eventId: string; onAdded: (n: TimelineNote) => void }) {
  const [text, setText]   = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    const trimmed = text.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    try {
      const note = await addNote(eventId, trimmed);
      onAdded(note);
      setText("");
    } catch { /* swallow */ }
    finally { setSaving(false); }
  }

  return (
    <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="Add intervention note… (Enter to save)"
        style={{
          flex: 1, fontSize: 12, padding: "5px 10px",
          border: "1px solid #d1d5db", borderRadius: 6, outline: "none",
        }}
      />
      <button
        onClick={submit}
        disabled={!text.trim() || saving}
        style={{
          fontSize: 11, padding: "5px 12px", borderRadius: 6,
          border: "none", background: "#1a1a2e", color: "#fff",
          cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1,
        }}
      >
        {saving ? "…" : "Save"}
      </button>
    </div>
  );
}

// ── Single event row ──────────────────────────────────────────────────────────

function EventEntry({ event: ev, onNoteAdded, onNoteDeleted }: {
  event: TimelineEvent;
  onNoteAdded:   (eventId: string, note: TimelineNote) => void;
  onNoteDeleted: (eventId: string, noteId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const meta     = TYPE_META[ev.event_type] ?? { icon: "❓", color: "#6b7280", label: ev.event_type };
  const ppe      = ev.missing_ppe?.join(", ");
  const isOpen   = ev.end_frame === null;

  return (
    <div
      style={{
        borderRadius: 6, border: `1px solid ${meta.color}33`,
        background: "#fff", marginBottom: 4,
      }}
    >
      {/* Row header */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "8px 12px", cursor: "pointer",
          borderLeft: `3px solid ${meta.color}`,
        }}
      >
        <span style={{ fontSize: 14 }}>{meta.icon}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#1f2937" }}>
            {meta.label}{ppe ? ` — ${ppe}` : ""}
          </div>
          <div style={{ fontSize: 11, color: "#6b7280" }}>
            Worker #{ev.track_id}
            {ev.zone_id ? ` · ${ev.zone_id}` : ""}
            {" · "}{fmtTime(ev.created_at)}
          </div>
        </div>
        <div style={{ display: "flex", gap: 5, alignItems: "center", flexShrink: 0 }}>
          {ev.notes.length > 0 && (
            <span style={{ fontSize: 10, color: "#3b82f6", fontWeight: 600 }}>
              📝 {ev.notes.length}
            </span>
          )}
          <span style={{
            fontSize: 9, padding: "2px 6px", borderRadius: 4, fontWeight: 700,
            background: ev.severity === "CRITICAL" ? "#dc2626" : ev.event_type === "near_miss" ? "#a855f7" : "#d97706",
            color: "#fff",
          }}>
            {ev.severity}
          </span>
          <span style={{
            fontSize: 9, padding: "2px 6px", borderRadius: 4, fontWeight: 600,
            background: isOpen ? "#1a1a2e" : "#e5e7eb",
            color: isOpen ? "#fff" : "#6b7280",
          }}>
            {isOpen ? "ACTIVE" : "CLOSED"}
          </span>
          <span style={{ fontSize: 11, color: "#9ca3af" }}>{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {/* Expanded — notes + note input */}
      {expanded && (
        <div style={{ padding: "6px 12px 10px", borderTop: "1px solid #f1f5f9" }}>
          {ev.osha_codes?.length > 0 && (
            <div style={{ fontSize: 10, color: "#6b7280", marginBottom: 6, fontFamily: "monospace" }}>
              OSHA: {ev.osha_codes.join(", ")}
            </div>
          )}
          {ev.notes.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 4 }}>
              {ev.notes.map((note) => (
                <div key={note.note_id} style={{
                  fontSize: 12, color: "#374151", background: "#f8fafc",
                  borderRadius: 5, padding: "5px 8px",
                  display: "flex", justifyContent: "space-between", gap: 8,
                }}>
                  <span>
                    <span style={{ color: "#9ca3af", fontSize: 10 }}>{fmtTime(note.created_at)} · </span>
                    {note.note}
                  </span>
                  <button
                    onClick={() => deleteNote(note.note_id).then(() => onNoteDeleted(ev.event_id, note.note_id))}
                    style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: 12, padding: 0 }}
                    title="Delete note"
                  >×</button>
                </div>
              ))}
            </div>
          )}
          <NoteInput
            eventId={ev.event_id}
            onAdded={(n) => onNoteAdded(ev.event_id, n)}
          />
        </div>
      )}
    </div>
  );
}

// ── Hour bucket ───────────────────────────────────────────────────────────────

function HourBucket({ group, onNoteAdded, onNoteDeleted }: {
  group: HourGroup;
  onNoteAdded:   (eventId: string, note: TimelineNote) => void;
  onNoteDeleted: (eventId: string, noteId: string) => void;
}) {
  const [open, setOpen] = useState(true);
  const counts = group.events.reduce<Record<string, number>>((acc, e) => {
    acc[e.event_type] = (acc[e.event_type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div style={{ marginBottom: 8 }}>
      <div
        onClick={() => setOpen(v => !v)}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "7px 12px", cursor: "pointer",
          background: "#f1f5f9", borderRadius: 7,
          borderLeft: "4px solid #3b82f6",
        }}
      >
        <span style={{ fontSize: 13, fontWeight: 700, color: "#1e3a5f" }}>
          {group.label}
        </span>
        <div style={{ display: "flex", gap: 5 }}>
          {Object.entries(counts).map(([type, n]) => {
            const m = TYPE_META[type] ?? { color: "#6b7280", icon: "?" };
            return (
              <span key={type} style={{
                fontSize: 10, padding: "1px 7px", borderRadius: 10,
                background: m.color + "22", color: m.color, fontWeight: 700,
              }}>
                {m.icon} {n}
              </span>
            );
          })}
        </div>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "#6b7280" }}>
          {group.event_count} event{group.event_count !== 1 ? "s" : ""} {open ? "▲" : "▼"}
        </span>
      </div>

      {open && (
        <div style={{ marginTop: 4, paddingLeft: 8 }}>
          {group.events.map((ev) => (
            <EventEntry
              key={ev.event_id}
              event={ev}
              onNoteAdded={onNoteAdded}
              onNoteDeleted={onNoteDeleted}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function TimelinePanel() {
  const [data, setData]       = useState<TimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [date, setDate]       = useState(() => new Date().toISOString().slice(0, 10));
  const [pdfLoading, setPdfLoading] = useState(false);

  const load = useCallback((d: string) => {
    setLoading(true);
    setError(null);
    fetchTimeline(d)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(date); }, [date, load]);

  // Mutate notes in local state without a full reload
  function handleNoteAdded(eventId: string, note: TimelineNote) {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        hours: prev.hours.map((h) => ({
          ...h,
          events: h.events.map((ev) =>
            ev.event_id === eventId
              ? { ...ev, notes: [...ev.notes, note] }
              : ev
          ),
        })),
      };
    });
  }

  function handleNoteDeleted(eventId: string, noteId: string) {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        hours: prev.hours.map((h) => ({
          ...h,
          events: h.events.map((ev) =>
            ev.event_id === eventId
              ? { ...ev, notes: ev.notes.filter((n) => n.note_id !== noteId) }
              : ev
          ),
        })),
      };
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        background: "#fff", borderRadius: 10,
        border: "1px solid #e5e7eb", padding: "10px 16px",
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>Date</span>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          style={{
            fontSize: 13, padding: "4px 8px", borderRadius: 6,
            border: "1px solid #d1d5db", outline: "none",
          }}
        />
        {data && (
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            {data.total_events} event{data.total_events !== 1 ? "s" : ""}
          </span>
        )}
        <button
          onClick={() => { setPdfLoading(true); downloadTimelinePdf(date); setTimeout(() => setPdfLoading(false), 3000); }}
          disabled={pdfLoading}
          style={{
            marginLeft: "auto", fontSize: 12, padding: "5px 14px", borderRadius: 6,
            border: "1px solid #3b82f6", background: pdfLoading ? "#e5e7eb" : "#3b82f6",
            color: pdfLoading ? "#9ca3af" : "#fff", cursor: pdfLoading ? "default" : "pointer",
            fontWeight: 600,
          }}
        >
          {pdfLoading ? "Generating…" : "⬇ Export PDF"}
        </button>
      </div>

      {/* Content */}
      {loading && (
        <div style={{ textAlign: "center", padding: 50, color: "#9ca3af" }}>
          Loading timeline…
        </div>
      )}
      {error && (
        <div style={{ padding: 20, color: "#dc2626", background: "#fef2f2", borderRadius: 8, fontSize: 13 }}>
          {error}
        </div>
      )}
      {!loading && !error && data && data.total_events === 0 && (
        <div style={{ textAlign: "center", padding: 50, color: "#9ca3af", fontSize: 14 }}>
          No events recorded for {date}.
        </div>
      )}
      {/* Incident stories — shown above the hour feed */}
      {!loading && data && data.incidents && data.incidents.length > 0 && (
        <div>
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginBottom: 8,
          }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#dc2626" }}>
              🚨 Incident Stories
            </span>
            <span style={{
              fontSize: 11, padding: "2px 8px", borderRadius: 10,
              background: "#dc2626", color: "#fff", fontWeight: 700,
            }}>
              {data.incidents.length}
            </span>
            <span style={{ fontSize: 11, color: "#6b7280" }}>
              — multi-event sequences from the same worker
            </span>
          </div>
          {data.incidents.map((inc) => (
            <IncidentCard key={inc.incident_id} incident={inc} />
          ))}
        </div>
      )}

      {/* Hour-by-hour event feed */}
      {!loading && data && data.hours.map((group) => (
        <HourBucket
          key={group.hour}
          group={group}
          onNoteAdded={handleNoteAdded}
          onNoteDeleted={handleNoteDeleted}
        />
      ))}
    </div>
  );
}
