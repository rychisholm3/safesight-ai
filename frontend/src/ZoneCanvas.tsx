/**
 * ZoneCanvas — SVG-based polygon drawing component.
 *
 * Interactions:
 *  • Click canvas (drawing mode)  → add vertex
 *  • Hover near first vertex (≥3 pts) → snap indicator; click to close polygon
 *  • After closing → inline form to name the zone and pick its type
 *  • Drag any vertex of a completed zone → reposition it
 *  • Undo / Cancel buttons during drawing
 */
import { useEffect, useRef, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DrawnZone {
  id: string;
  name: string;
  rule: "no_entry" | "require_ppe";
  required_ppe: string[];
  points: [number, number][];  // natural-image pixel coordinates
}

interface Props {
  imageUrl: string;
  zones: DrawnZone[];
  onZonesChange: (zones: DrawnZone[]) => void;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SNAP_PX   = 16;   // SVG-space pixels to snap to first vertex

const ZONE_FILL: Record<string, string> = {
  no_entry:    "#ef444433",
  require_ppe: "#f59e0b33",
};
const ZONE_STROKE: Record<string, string> = {
  no_entry:    "#ef4444",
  require_ppe: "#f59e0b",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function svgPt(e: MouseEvent, svg: SVGSVGElement): [number, number] {
  const p = svg.createSVGPoint();
  p.x = e.clientX;
  p.y = e.clientY;
  const t = p.matrixTransform(svg.getScreenCTM()!.inverse());
  return [t.x, t.y];
}

function dist(a: [number, number], b: [number, number]) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

function centroid(pts: [number, number][]): [number, number] {
  return [
    pts.reduce((s, [x]) => s + x, 0) / pts.length,
    pts.reduce((s, [, y]) => s + y, 0) / pts.length,
  ];
}

function ptsAttr(pts: [number, number][]) {
  return pts.map(([x, y]) => `${x},${y}`).join(" ");
}

// ── Component ─────────────────────────────────────────────────────────────────

type Mode = "idle" | "drawing" | "pending";

interface PendingForm {
  name: string;
  rule: "no_entry" | "require_ppe";
  ppe: string;
}

export function ZoneCanvas({ imageUrl, zones, onZonesChange }: Props) {
  const svgRef  = useRef<SVGSVGElement>(null);
  const imgRef  = useRef<HTMLImageElement>(null);

  const [naturalW, setNaturalW] = useState(1920);
  const [naturalH, setNaturalH] = useState(1080);
  const [mode,       setMode]       = useState<Mode>("idle");
  const [currentPts, setCurrentPts] = useState<[number, number][]>([]);
  const [mousePos,   setMousePos]   = useState<[number, number]>([0, 0]);
  const [pendingPts, setPendingPts] = useState<[number, number][]>([]);
  const [form, setForm] = useState<PendingForm>({ name: "", rule: "no_entry", ppe: "" });

  // For window-level drag tracking
  const [dragTarget, setDragTarget] = useState<{ zi: number; pi: number } | null>(null);
  const dragRef   = useRef(dragTarget);   dragRef.current   = dragTarget;
  const zonesRef  = useRef(zones);        zonesRef.current  = zones;
  const svgRefCb  = useRef(svgRef);       svgRefCb.current  = svgRef;

  // ── Natural dimensions ──────────────────────────────────────────────────────
  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    const onLoad = () => {
      if (img.naturalWidth > 0) {
        setNaturalW(img.naturalWidth);
        setNaturalH(img.naturalHeight);
      }
    };
    if (img.complete && img.naturalWidth > 0) onLoad();
    img.addEventListener("load", onLoad);
    return () => img.removeEventListener("load", onLoad);
  }, [imageUrl]);

  // ── Window-level drag ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!dragTarget) return;

    const onMove = (e: MouseEvent) => {
      const svg = svgRefCb.current.current;
      const dt  = dragRef.current;
      if (!svg || !dt) return;
      const [x, y] = svgPt(e, svg);
      onZonesChange(
        zonesRef.current.map((z, i) =>
          i === dt.zi
            ? { ...z, points: z.points.map((p, j) => j === dt.pi ? [Math.round(x), Math.round(y)] as [number, number] : p) }
            : z
        )
      );
    };
    const onUp = () => setDragTarget(null);

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup",   onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup",   onUp);
    };
  }, [dragTarget, onZonesChange]);

  // ── SVG mouse handlers ──────────────────────────────────────────────────────
  function onSvgMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!svgRef.current) return;
    setMousePos(svgPt(e.nativeEvent, svgRef.current));
  }

  function onSvgClick(e: React.MouseEvent<SVGSVGElement>) {
    if (mode !== "drawing" || !svgRef.current) return;
    const [x, y] = svgPt(e.nativeEvent, svgRef.current);

    // Close polygon?
    if (currentPts.length >= 3 && dist([x, y], currentPts[0]) < SNAP_PX) {
      setPendingPts(currentPts);
      setCurrentPts([]);
      setMode("pending");
      return;
    }
    setCurrentPts((p) => [...p, [x, y]]);
  }

  // ── Drawing controls ────────────────────────────────────────────────────────
  function startDrawing() {
    setCurrentPts([]);
    setMode("drawing");
  }
  function cancelDrawing() {
    setCurrentPts([]);
    setMode("idle");
  }
  function undoPoint() {
    setCurrentPts((p) => p.slice(0, -1));
  }

  // ── Confirm / discard pending polygon ───────────────────────────────────────
  function confirmZone() {
    if (!form.name.trim()) return;
    const zone: DrawnZone = {
      id:            `zone_${Date.now()}`,
      name:          form.name.trim(),
      rule:          form.rule,
      required_ppe:  form.rule === "require_ppe"
                       ? form.ppe.split(",").map((s) => s.trim()).filter(Boolean)
                       : [],
      points:        pendingPts,
    };
    onZonesChange([...zones, zone]);
    setPendingPts([]);
    setForm({ name: "", rule: "no_entry", ppe: "" });
    setMode("idle");
  }
  function discardPending() {
    setPendingPts([]);
    setMode("idle");
  }

  function removeZone(i: number) {
    onZonesChange(zones.filter((_, j) => j !== i));
  }

  // ── Derived ─────────────────────────────────────────────────────────────────
  const nearFirst =
    mode === "drawing" &&
    currentPts.length >= 3 &&
    dist(mousePos, currentPts[0]) < SNAP_PX;

  const labelFontSize = Math.max(naturalW * 0.018, 14);
  const vertexR       = Math.max(naturalW * 0.004, 6);
  const strokeW       = Math.max(naturalW * 0.002, 2.5);

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div>
      {/* ── Canvas ── */}
      <div style={{
        position: "relative",
        width: "100%",
        aspectRatio: `${naturalW} / ${naturalH}`,
        background: "#0f172a",
        borderRadius: 8,
        overflow: "hidden",
        cursor: mode === "drawing" ? "crosshair" : dragTarget ? "grabbing" : "default",
        userSelect: "none",
      }}>
        <img
          ref={imgRef}
          src={imageUrl}
          draggable={false}
          style={{ width: "100%", height: "100%", display: "block", objectFit: "fill" }}
          alt="Camera view"
        />

        <svg
          ref={svgRef}
          viewBox={`0 0 ${naturalW} ${naturalH}`}
          preserveAspectRatio="none"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
          onClick={onSvgClick}
          onMouseMove={onSvgMouseMove}
        >
          {/* ── Completed zones ── */}
          {zones.map((zone, zi) => {
            const fill   = ZONE_FILL[zone.rule]   ?? "#3b82f633";
            const stroke = ZONE_STROKE[zone.rule] ?? "#3b82f6";
            const [cx, cy] = centroid(zone.points);
            return (
              <g key={zone.id}>
                <polygon
                  points={ptsAttr(zone.points)}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={strokeW}
                />
                {/* Draggable vertex handles */}
                {zone.points.map(([x, y], pi) => (
                  <circle
                    key={pi}
                    cx={x} cy={y} r={vertexR * 1.4}
                    fill={stroke}
                    stroke="#fff"
                    strokeWidth={strokeW * 0.7}
                    style={{ cursor: "grab", pointerEvents: "all" }}
                    onMouseDown={(e) => {
                      e.stopPropagation();
                      setDragTarget({ zi, pi });
                    }}
                  />
                ))}
                {/* Zone label */}
                <text
                  x={cx} y={cy}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#fff"
                  fontSize={labelFontSize}
                  fontWeight="bold"
                  style={{ pointerEvents: "none", filter: "drop-shadow(0 1px 3px rgba(0,0,0,.9))" }}
                >
                  {zone.name}
                </text>
                <text
                  x={cx} y={cy + labelFontSize * 1.3}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill={stroke}
                  fontSize={labelFontSize * 0.72}
                  fontWeight="600"
                  style={{ pointerEvents: "none", filter: "drop-shadow(0 1px 2px rgba(0,0,0,.9))" }}
                >
                  {zone.rule === "no_entry" ? "⛔ NO ENTRY" : "⚠ REQUIRE PPE"}
                </text>
              </g>
            );
          })}

          {/* ── Pending (closed, awaiting naming) ── */}
          {pendingPts.length >= 3 && (
            <polygon
              points={ptsAttr(pendingPts)}
              fill={ZONE_FILL[form.rule] ?? "#3b82f633"}
              stroke={ZONE_STROKE[form.rule] ?? "#3b82f6"}
              strokeWidth={strokeW}
              strokeDasharray={`${strokeW * 4} ${strokeW * 2}`}
            />
          )}

          {/* ── Active drawing polyline + rubber-band ── */}
          {mode === "drawing" && currentPts.length > 0 && (
            <g style={{ pointerEvents: "none" }}>
              <polyline
                points={ptsAttr([...currentPts, mousePos])}
                fill="none"
                stroke="#f97316"
                strokeWidth={strokeW}
                strokeDasharray={`${strokeW * 4} ${strokeW * 2}`}
              />
              {currentPts.map(([x, y], i) => {
                const isFirst = i === 0;
                const snap    = isFirst && nearFirst;
                return (
                  <circle
                    key={i}
                    cx={x} cy={y}
                    r={snap ? vertexR * 2.2 : vertexR}
                    fill={snap ? "#22c55e" : "#f97316"}
                    stroke="#fff"
                    strokeWidth={strokeW * 0.7}
                    style={{ transition: "r .1s, fill .1s" }}
                  />
                );
              })}
              {/* "Close zone" tooltip near first point */}
              {nearFirst && (
                <text
                  x={currentPts[0][0] + vertexR * 3}
                  y={currentPts[0][1] - vertexR * 2}
                  fill="#22c55e"
                  fontSize={labelFontSize * 0.85}
                  fontWeight="bold"
                  style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,.9))" }}
                >
                  ✓ Close zone
                </text>
              )}
            </g>
          )}
        </svg>
      </div>

      {/* ── Controls bar ── */}
      <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {mode === "idle" && (
          <button onClick={startDrawing} style={btn("#1a1a2e", "#fff")}>
            + Draw Zone
          </button>
        )}

        {mode === "drawing" && (
          <>
            <button onClick={cancelDrawing} style={btn("#6b7280", "#fff")}>Cancel</button>
            <button
              onClick={undoPoint}
              disabled={currentPts.length === 0}
              style={{ ...btn("#374151", "#fff"), opacity: currentPts.length === 0 ? 0.4 : 1 }}
            >
              ↩ Undo
            </button>
            <span style={{ fontSize: 12, color: "#6b7280" }}>
              {currentPts.length === 0
                ? "Click the image to place your first corner"
                : currentPts.length < 3
                  ? `${3 - currentPts.length} more corner${3 - currentPts.length > 1 ? "s" : ""} needed to close`
                  : "Click another corner — or click the first corner (green) to close the zone"}
            </span>
          </>
        )}
      </div>

      {/* ── Naming form (after polygon closed) ── */}
      {mode === "pending" && (
        <div style={{
          marginTop: 12, padding: "14px 16px",
          background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac",
        }}>
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 10, color: "#15803d" }}>
            ✓ Zone shape drawn — give it a name
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <label style={lbl}>Zone name</label>
              <input
                autoFocus
                placeholder="e.g. Forklift Lane"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && confirmZone()}
                style={inp}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <label style={lbl}>Zone type</label>
              <select
                value={form.rule}
                onChange={(e) => setForm((f) => ({ ...f, rule: e.target.value as PendingForm["rule"] }))}
                style={{ ...inp, width: "auto" }}
              >
                <option value="no_entry">🚫 No Entry — alert anyone inside</option>
                <option value="require_ppe">⚠️ Require PPE — alert if gear is missing</option>
              </select>
            </div>
            {form.rule === "require_ppe" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <label style={lbl}>Required PPE (comma-separated)</label>
                <input
                  placeholder="hardhat, vest"
                  value={form.ppe}
                  onChange={(e) => setForm((f) => ({ ...f, ppe: e.target.value }))}
                  style={inp}
                />
              </div>
            )}
            <button
              onClick={confirmZone}
              disabled={!form.name.trim()}
              style={{ ...btn("#059669", "#fff"), opacity: form.name.trim() ? 1 : 0.4 }}
            >
              Add Zone
            </button>
            <button onClick={discardPending} style={btn("#dc2626", "#fff")}>
              Discard
            </button>
          </div>
        </div>
      )}

      {/* ── Zone list ── */}
      {zones.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 6 }}>
            {zones.length} zone{zones.length !== 1 ? "s" : ""} configured
            <span style={{ fontWeight: 400, color: "#9ca3af", marginLeft: 8 }}>
              — drag corners on the image to fine-tune
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {zones.map((z, i) => {
              const col = ZONE_STROKE[z.rule] ?? "#3b82f6";
              return (
                <div key={z.id} style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 12px", background: "#f9fafb",
                  borderRadius: 6, borderLeft: `3px solid ${col}`,
                }}>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{z.name}</span>
                    <span style={{ fontSize: 11, color: "#6b7280", marginLeft: 8 }}>
                      {z.rule === "no_entry"
                        ? "🚫 No entry — anyone inside triggers alert"
                        : `⚠️ Requires: ${z.required_ppe.length ? z.required_ppe.join(", ") : "hardhat, vest"}`}
                      {" · "}{z.points.length} corners
                    </span>
                  </div>
                  <button
                    onClick={() => removeZone(i)}
                    title="Remove zone"
                    style={{ background: "none", border: "none", color: "#dc2626", cursor: "pointer", fontSize: 18, lineHeight: 1, padding: "0 2px" }}
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Tiny style helpers ────────────────────────────────────────────────────────
// (intentionally minimal to avoid pulling in a CSS-in-JS library)

function btn(bg: string, color: string): React.CSSProperties {
  return {
    padding: "7px 16px", borderRadius: 6, border: "none",
    background: bg, color, fontWeight: 600, fontSize: 13,
    cursor: "pointer", whiteSpace: "nowrap" as const,
  };
}

const lbl: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, color: "#374151",
};
const inp: React.CSSProperties = {
  padding: "6px 10px", borderRadius: 6,
  border: "1px solid #d1d5db", fontSize: 13, minWidth: 180,
};
