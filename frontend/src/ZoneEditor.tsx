import { useCallback, useEffect, useRef, useState } from "react";
import type { Zone, ZonesConfig } from "./types";
import { fetchZones, saveZones } from "./api";

const ZONE_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4"];
const DRAWING_COLOR = "#f97316";
const POINT_RADIUS = 5;

interface Props {
  onClose: () => void;
}

interface DraftZone {
  id: string;
  name: string;
  rule: "no_entry" | "require_ppe";
  required_ppe: string;
  points: [number, number][];
}

function emptyDraft(): DraftZone {
  return { id: "", name: "", rule: "no_entry", required_ppe: "", points: [] };
}

export function ZoneEditor({ onClose }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [config, setConfig] = useState<ZonesConfig>({ required_ppe: [], zones: [] });
  const [draft, setDraft] = useState<DraftZone>(emptyDraft());
  const [drawing, setDrawing] = useState(false);
  const [status, setStatus] = useState<string>("");
  const [saving, setSaving] = useState(false);

  // Load existing zones on mount
  useEffect(() => {
    fetchZones()
      .then(setConfig)
      .catch(() => {});
  }, []);

  // Redraw canvas whenever image, saved zones, or draft changes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (image) {
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    } else {
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#64748b";
      ctx.font = "16px system-ui";
      ctx.textAlign = "center";
      ctx.fillText("Upload a frame to start drawing zones", canvas.width / 2, canvas.height / 2);
    }

    // Draw saved zones
    config.zones.forEach((zone, i) => {
      if (zone.polygon.length < 2) return;
      const color = ZONE_COLORS[i % ZONE_COLORS.length];
      ctx.beginPath();
      const scaleX = canvas.width / (image?.naturalWidth ?? canvas.width);
      const scaleY = canvas.height / (image?.naturalHeight ?? canvas.height);
      zone.polygon.forEach(([x, y], j) => {
        const sx = x * scaleX;
        const sy = y * scaleY;
        j === 0 ? ctx.moveTo(sx, sy) : ctx.lineTo(sx, sy);
      });
      ctx.closePath();
      ctx.fillStyle = color + "33";
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
      // Label
      const cx = zone.polygon.reduce((s, [x]) => s + x, 0) / zone.polygon.length * scaleX;
      const cy = zone.polygon.reduce((s, [, y]) => s + y, 0) / zone.polygon.length * scaleY;
      ctx.fillStyle = color;
      ctx.font = "bold 13px system-ui";
      ctx.textAlign = "center";
      ctx.fillText(zone.name || zone.id, cx, cy);
    });

    // Draw draft polygon
    if (draft.points.length > 0) {
      ctx.beginPath();
      draft.points.forEach(([x, y], j) => {
        j === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.strokeStyle = DRAWING_COLOR;
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      draft.points.forEach(([x, y]) => {
        ctx.beginPath();
        ctx.arc(x, y, POINT_RADIUS, 0, Math.PI * 2);
        ctx.fillStyle = DRAWING_COLOR;
        ctx.fill();
      });
    }
  }, [image, config, draft]);

  const handleImageUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => setImage(img);
    img.src = url;
  }, []);

  const canvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!drawing) return;
      const rect = canvasRef.current!.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      setDraft((d) => ({ ...d, points: [...d.points, [x, y]] }));
    },
    [drawing]
  );

  const canvasDblClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!drawing || draft.points.length < 3) return;
      e.preventDefault();
      setDrawing(false);
      setStatus("Polygon closed. Fill in the zone details and click Add Zone.");
    },
    [drawing, draft.points.length]
  );

  function startDrawing() {
    setDraft((d) => ({ ...d, points: [] }));
    setDrawing(true);
    setStatus("Click to place points. Double-click to close the polygon.");
  }

  function cancelDrawing() {
    setDraft(emptyDraft());
    setDrawing(false);
    setStatus("");
  }

  function addZone() {
    if (!draft.id.trim()) { setStatus("Zone ID is required."); return; }
    if (!draft.name.trim()) { setStatus("Zone name is required."); return; }
    if (draft.points.length < 3) { setStatus("Draw a polygon first (need at least 3 points)."); return; }

    const canvas = canvasRef.current!;
    const scaleX = (image?.naturalWidth ?? canvas.width) / canvas.width;
    const scaleY = (image?.naturalHeight ?? canvas.height) / canvas.height;

    const polygon: [number, number][] = draft.points.map(([x, y]) => [
      Math.round(x * scaleX),
      Math.round(y * scaleY),
    ]);

    const newZone: Zone = {
      id: draft.id.trim(),
      name: draft.name.trim(),
      rule: draft.rule,
      polygon,
      ...(draft.rule === "require_ppe" && draft.required_ppe.trim()
        ? { required_ppe: draft.required_ppe.split(",").map((s) => s.trim()).filter(Boolean) }
        : {}),
    };

    setConfig((c) => ({ ...c, zones: [...c.zones, newZone] }));
    setDraft(emptyDraft());
    setDrawing(false);
    setStatus(`Zone "${newZone.name}" added. Click Save to write to zones.json.`);
  }

  function removeZone(id: string) {
    setConfig((c) => ({ ...c, zones: c.zones.filter((z) => z.id !== id) }));
  }

  async function handleSave() {
    setSaving(true);
    setStatus("");
    try {
      await saveZones(config);
      setStatus("Saved successfully!");
    } catch {
      setStatus("Save failed — is the API running?");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#fff", borderRadius: 10, width: "90vw", maxWidth: 1100,
          maxHeight: "90vh", display: "flex", flexDirection: "column", overflow: "hidden",
        }}
      >
        {/* Modal header */}
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #e5e7eb", display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontWeight: 700, fontSize: 16 }}>Zone Editor</span>
          <span style={{ fontSize: 13, color: "#6b7280" }}>Draw polygons to define keep-out zones</span>
          <button onClick={onClose} style={{ marginLeft: "auto", border: "none", background: "none", fontSize: 20, cursor: "pointer", color: "#6b7280" }}>✕</button>
        </div>

        {/* Body */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
          {/* Canvas side */}
          <div style={{ flex: 1, padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Reference frame:</label>
              <input type="file" accept="image/*" onChange={handleImageUpload} style={{ fontSize: 13 }} />
            </div>
            <canvas
              ref={canvasRef}
              width={720}
              height={405}
              onClick={canvasClick}
              onDoubleClick={canvasDblClick}
              style={{
                border: "1px solid #d1d5db", borderRadius: 6,
                cursor: drawing ? "crosshair" : "default",
                maxWidth: "100%",
                background: "#1e293b",
              }}
            />
            {status && (
              <div style={{ fontSize: 13, color: status.includes("fail") ? "#dc2626" : "#059669", fontWeight: 500 }}>
                {status}
              </div>
            )}
          </div>

          {/* Controls side */}
          <div style={{ width: 300, borderLeft: "1px solid #e5e7eb", padding: 16, display: "flex", flexDirection: "column", gap: 14, overflowY: "auto" }}>

            {/* Drawing controls */}
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>1. Draw polygon</div>
              {!drawing ? (
                <button onClick={startDrawing} style={btnStyle("#1a1a2e", "#fff")}>
                  Start Drawing
                </button>
              ) : (
                <div style={{ display: "flex", gap: 8 }}>
                  <button onClick={cancelDrawing} style={btnStyle("#6b7280", "#fff")}>Cancel</button>
                  <div style={{ fontSize: 12, color: "#6b7280", alignSelf: "center" }}>
                    {draft.points.length} point{draft.points.length !== 1 ? "s" : ""}
                  </div>
                </div>
              )}
            </div>

            {/* Zone form */}
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>2. Zone details</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <Field label="Zone ID" value={draft.id} onChange={(v) => setDraft((d) => ({ ...d, id: v }))} placeholder="e.g. forklift_lane" />
                <Field label="Name" value={draft.name} onChange={(v) => setDraft((d) => ({ ...d, name: v }))} placeholder="e.g. Forklift Lane" />
                <div>
                  <label style={labelStyle}>Rule</label>
                  <select
                    value={draft.rule}
                    onChange={(e) => setDraft((d) => ({ ...d, rule: e.target.value as DraftZone["rule"] }))}
                    style={inputStyle}
                  >
                    <option value="no_entry">No entry</option>
                    <option value="require_ppe">Require PPE</option>
                  </select>
                </div>
                {draft.rule === "require_ppe" && (
                  <Field
                    label="Required PPE (comma-separated)"
                    value={draft.required_ppe}
                    onChange={(v) => setDraft((d) => ({ ...d, required_ppe: v }))}
                    placeholder="hardhat, vest, face_shield"
                  />
                )}
              </div>
            </div>

            <button onClick={addZone} style={btnStyle("#059669", "#fff")}>
              Add Zone
            </button>

            <hr style={{ border: "none", borderTop: "1px solid #e5e7eb" }} />

            {/* Zone list */}
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
                Zones ({config.zones.length})
              </div>
              {config.zones.length === 0 ? (
                <div style={{ fontSize: 12, color: "#9ca3af" }}>No zones yet.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {config.zones.map((z, i) => (
                    <div
                      key={z.id}
                      style={{
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "6px 10px", borderRadius: 6, background: "#f9fafb",
                        borderLeft: `3px solid ${ZONE_COLORS[i % ZONE_COLORS.length]}`,
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 600, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{z.name}</div>
                        <div style={{ fontSize: 11, color: "#6b7280" }}>{z.rule} · {z.polygon.length} pts</div>
                      </div>
                      <button
                        onClick={() => removeZone(z.id)}
                        style={{ border: "none", background: "none", color: "#dc2626", cursor: "pointer", fontSize: 16 }}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button onClick={handleSave} disabled={saving} style={{ ...btnStyle("#1a1a2e", "#fff"), marginTop: "auto", opacity: saving ? 0.6 : 1 }}>
              {saving ? "Saving…" : "Save to zones.json"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={inputStyle}
      />
    </div>
  );
}

const labelStyle: React.CSSProperties = { display: "block", fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 3 };
const inputStyle: React.CSSProperties = { width: "100%", padding: "6px 8px", borderRadius: 5, border: "1px solid #d1d5db", fontSize: 13, boxSizing: "border-box" };
function btnStyle(bg: string, color: string): React.CSSProperties {
  return { width: "100%", padding: "8px 12px", borderRadius: 6, border: "none", background: bg, color, fontWeight: 600, fontSize: 13, cursor: "pointer" };
}
