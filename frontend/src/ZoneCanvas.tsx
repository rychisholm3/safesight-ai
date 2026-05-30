/**
 * ZoneCanvas — SVG-based interactive polygon zone editor.
 *
 * Fully guided interactions:
 *  • Instructional overlay when no zones exist (disappears when drawing starts)
 *  • Live step banner during drawing ("Place 2 more corners…")
 *  • Click to place vertices; first vertex glows green when you can close the shape
 *  • Click the green first vertex to close and open the naming form
 *  • Drag any corner handle on a finished zone to fine-tune its shape
 *  • Undo last point or cancel drawing at any time
 */
import { useEffect, useRef, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DrawnZone {
  id: string;
  name: string;
  rule: "no_entry" | "require_ppe";
  required_ppe: string[];
  points: [number, number][];  // natural image pixel coordinates
}

interface Props {
  imageUrl: string;
  zones: DrawnZone[];
  onZonesChange: (zones: DrawnZone[]) => void;
}

// ── Visual constants ──────────────────────────────────────────────────────────

const SNAP_PX = 18;

const COLORS: Record<string, { fill: string; stroke: string; label: string }> = {
  no_entry:    { fill: "#ef444428", stroke: "#ef4444", label: "🚫 NO ENTRY"     },
  require_ppe: { fill: "#f59e0b28", stroke: "#f59e0b", label: "⚠ REQUIRE PPE"  },
};
const FALLBACK = { fill: "#3b82f628", stroke: "#3b82f6", label: "ZONE" };

// ── SVG coordinate helper ─────────────────────────────────────────────────────

function svgPt(e: MouseEvent, svg: SVGSVGElement): [number, number] {
  const p = svg.createSVGPoint();
  p.x = e.clientX; p.y = e.clientY;
  const t = p.matrixTransform(svg.getScreenCTM()!.inverse());
  return [t.x, t.y];
}

function dist2(a: [number, number], b: [number, number]) {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

function centroid(pts: [number, number][]): [number, number] {
  return [
    pts.reduce((s, [x]) => s + x, 0) / pts.length,
    pts.reduce((s, [, y]) => s + y, 0) / pts.length,
  ];
}

function polyAttr(pts: [number, number][]) {
  return pts.map(([x, y]) => `${x},${y}`).join(" ");
}

// ── Component ─────────────────────────────────────────────────────────────────

type Mode = "idle" | "drawing" | "pending";

interface NamingForm { name: string; rule: "no_entry" | "require_ppe"; ppe: string }

export function ZoneCanvas({ imageUrl, zones, onZonesChange }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  const [nw, setNw] = useState(1920);
  const [nh, setNh] = useState(1080);
  const [mode,       setMode]       = useState<Mode>("idle");
  const [currentPts, setCurrentPts] = useState<[number, number][]>([]);
  const [mousePos,   setMousePos]   = useState<[number, number]>([0, 0]);
  const [pendingPts, setPendingPts] = useState<[number, number][]>([]);
  const [form, setForm] = useState<NamingForm>({ name: "", rule: "no_entry", ppe: "" });
  const [dragTarget, setDragTarget] = useState<{ zi: number; pi: number } | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const dragRef  = useRef(dragTarget); dragRef.current  = dragTarget;
  const zonesRef = useRef(zones);      zonesRef.current = zones;
  const svgCbRef = useRef(svgRef);     svgCbRef.current = svgRef;

  // ── Natural image size ──────────────────────────────────────────────────────
  useEffect(() => {
    const img = imgRef.current;
    if (!img) return;
    const apply = () => { if (img.naturalWidth > 0) { setNw(img.naturalWidth); setNh(img.naturalHeight); } };
    if (img.complete) apply();
    img.addEventListener("load", apply);
    return () => img.removeEventListener("load", apply);
  }, [imageUrl]);

  // ── Window-level drag (so dragging outside SVG still works) ────────────────
  useEffect(() => {
    if (!dragTarget) return;
    const onMove = (e: MouseEvent) => {
      const svg = svgCbRef.current.current;
      const dt  = dragRef.current;
      if (!svg || !dt) return;
      const [x, y] = svgPt(e, svg);
      onZonesChange(zonesRef.current.map((z, i) =>
        i !== dt.zi ? z : {
          ...z,
          points: z.points.map((p, j) =>
            j === dt.pi ? [Math.round(x), Math.round(y)] as [number, number] : p
          ),
        }
      ));
    };
    const onUp = () => setDragTarget(null);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup",   onUp);
    return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
  }, [dragTarget, onZonesChange]);

  // ── SVG interaction ─────────────────────────────────────────────────────────
  function onSvgClick(e: React.MouseEvent<SVGSVGElement>) {
    if (mode !== "drawing" || !svgRef.current) return;
    const [x, y] = svgPt(e.nativeEvent, svgRef.current);
    if (currentPts.length >= 3 && dist2([x, y], currentPts[0]) < SNAP_PX) {
      setPendingPts(currentPts);
      setCurrentPts([]);
      setMode("pending");
      return;
    }
    setCurrentPts(p => [...p, [x, y]]);
  }

  function onSvgMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!svgRef.current) return;
    setMousePos(svgPt(e.nativeEvent, svgRef.current));
  }

  // ── Actions ─────────────────────────────────────────────────────────────────
  function startDrawing() { setCurrentPts([]); setMode("drawing"); }
  function cancelDrawing() { setCurrentPts([]); setMode("idle"); }
  function undoPoint()    { setCurrentPts(p => p.slice(0, -1)); }

  function confirmZone() {
    if (!form.name.trim()) return;
    const zone: DrawnZone = {
      id:           `zone_${Date.now()}`,
      name:         form.name.trim(),
      rule:         form.rule,
      required_ppe: form.rule === "require_ppe"
                      ? form.ppe.split(",").map(s => s.trim()).filter(Boolean)
                      : [],
      points:       pendingPts,
    };
    onZonesChange([...zones, zone]);
    setPendingPts([]);
    setForm({ name: "", rule: "no_entry", ppe: "" });
    setMode("idle");
    setSuccessMsg(`"${zone.name}" saved! You can draw another zone or continue.`);
    setTimeout(() => setSuccessMsg(null), 4000);
  }

  function discardPending() { setPendingPts([]); setMode("idle"); }
  function removeZone(i: number) { onZonesChange(zones.filter((_, j) => j !== i)); }

  // ── Derived ─────────────────────────────────────────────────────────────────
  const nearFirst = mode === "drawing" && currentPts.length >= 3
    && dist2(mousePos, currentPts[0]) < SNAP_PX;

  const vr  = Math.max(nw * 0.004, 7);   // vertex radius
  const sw  = Math.max(nw * 0.002, 2.5); // stroke width
  const fs  = Math.max(nw * 0.018, 14);  // font size

  const drawingBanner = (() => {
    if (currentPts.length === 0) return "Click anywhere on the image to place your first corner";
    if (currentPts.length === 1) return "Click to place more corners — you need at least 3";
    if (currentPts.length === 2) return "One more corner needed before you can close the zone";
    return nearFirst
      ? "Click the green circle to close and finish the zone ✓"
      : "Keep adding corners — or click the green first corner to close the zone";
  })();

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div>
      {/* ── Canvas wrapper ── */}
      <div style={{
        position: "relative",
        width: "100%",
        aspectRatio: `${nw} / ${nh}`,
        background: "#0f172a",
        borderRadius: 8,
        overflow: "hidden",
        cursor: mode === "drawing" ? "crosshair" : dragTarget ? "grabbing" : "default",
        userSelect: "none",
        border: mode === "drawing" ? "2px solid #f97316" : "2px solid transparent",
        transition: "border-color .2s",
      }}>
        <img
          ref={imgRef}
          src={imageUrl}
          draggable={false}
          style={{ width: "100%", height: "100%", display: "block", objectFit: "fill" }}
          alt="Camera / video view"
        />

        {/* ── SVG overlay ── */}
        <svg
          ref={svgRef}
          viewBox={`0 0 ${nw} ${nh}`}
          preserveAspectRatio="none"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
          onClick={onSvgClick}
          onMouseMove={onSvgMouseMove}
        >
          {/* Completed zones */}
          {zones.map((zone, zi) => {
            const c = COLORS[zone.rule] ?? FALLBACK;
            const [cx, cy] = centroid(zone.points);
            return (
              <g key={zone.id}>
                <polygon points={polyAttr(zone.points)} fill={c.fill} stroke={c.stroke} strokeWidth={sw} />
                {zone.points.map(([x, y], pi) => (
                  <circle
                    key={pi} cx={x} cy={y} r={vr * 1.5}
                    fill={c.stroke} stroke="#fff" strokeWidth={sw * 0.7}
                    style={{ cursor: "grab", pointerEvents: "all" }}
                    onMouseDown={e => { e.stopPropagation(); setDragTarget({ zi, pi }); }}
                  />
                ))}
                <text x={cx} y={cy - fs * 0.6} textAnchor="middle" dominantBaseline="middle"
                  fill="#fff" fontSize={fs} fontWeight="bold"
                  style={{ pointerEvents: "none", filter: "drop-shadow(0 1px 3px rgba(0,0,0,.95))" }}>
                  {zone.name}
                </text>
                <text x={cx} y={cy + fs * 0.85} textAnchor="middle" dominantBaseline="middle"
                  fill={c.stroke} fontSize={fs * 0.68} fontWeight="600"
                  style={{ pointerEvents: "none", filter: "drop-shadow(0 1px 2px rgba(0,0,0,.95))" }}>
                  {c.label}
                </text>
              </g>
            );
          })}

          {/* Closed polygon awaiting naming */}
          {pendingPts.length >= 3 && (() => {
            const c = COLORS[form.rule] ?? FALLBACK;
            return <polygon points={polyAttr(pendingPts)} fill={c.fill} stroke={c.stroke}
              strokeWidth={sw} strokeDasharray={`${sw * 4} ${sw * 2}`} />;
          })()}

          {/* Active drawing */}
          {mode === "drawing" && currentPts.length > 0 && (
            <g style={{ pointerEvents: "none" }}>
              <polyline
                points={polyAttr([...currentPts, mousePos])}
                fill="none" stroke="#f97316" strokeWidth={sw}
                strokeDasharray={`${sw * 4} ${sw * 2}`}
              />
              {currentPts.map(([x, y], i) => {
                const snap = i === 0 && nearFirst;
                return (
                  <circle key={i} cx={x} cy={y}
                    r={snap ? vr * 2.4 : vr}
                    fill={snap ? "#22c55e" : "#f97316"}
                    stroke="#fff" strokeWidth={sw * 0.7}
                    style={{ transition: "r .12s, fill .12s" }}
                  />
                );
              })}
              {nearFirst && (
                <text x={currentPts[0][0] + vr * 3.5} y={currentPts[0][1] - vr * 2}
                  fill="#22c55e" fontSize={fs * 0.85} fontWeight="bold"
                  style={{ filter: "drop-shadow(0 1px 2px rgba(0,0,0,.95))" }}>
                  ✓ Click to close
                </text>
              )}
            </g>
          )}
        </svg>

        {/* ── Idle instruction overlay (only when no zones yet) ── */}
        {mode === "idle" && zones.length === 0 && (
          <div style={{
            position: "absolute", top: "50%", left: "50%",
            transform: "translate(-50%, -50%)",
            background: "rgba(0,0,0,0.78)",
            borderRadius: 12, padding: "18px 22px",
            color: "#fff", maxWidth: "60%", minWidth: 260,
            pointerEvents: "none",
            backdropFilter: "blur(3px)",
          }}>
            <div style={{ fontSize: 24, textAlign: "center", marginBottom: 10 }}>📐</div>
            <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 10, textAlign: "center" }}>
              No zones yet
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 7, fontSize: 12, color: "#cbd5e1" }}>
              <div><span style={{ color: "#f97316", fontWeight: 700 }}>1.</span> Click <strong style={{ color: "#fff" }}>+ Draw Zone</strong> below</div>
              <div><span style={{ color: "#f97316", fontWeight: 700 }}>2.</span> Click the image to place corners</div>
              <div><span style={{ color: "#f97316", fontWeight: 700 }}>3.</span> Click the <span style={{ color: "#22c55e", fontWeight: 700 }}>● green</span> first corner to close</div>
              <div><span style={{ color: "#94a3b8", fontWeight: 700 }}>✏</span> Drag corners afterwards to fine-tune</div>
            </div>
          </div>
        )}

        {/* ── Drawing mode banner (top of canvas) ── */}
        {mode === "drawing" && (
          <div style={{
            position: "absolute", top: 0, left: 0, right: 0,
            background: "rgba(249,115,22,0.93)",
            color: "#fff", padding: "9px 16px",
            fontSize: 13, fontWeight: 600,
            display: "flex", alignItems: "center", gap: 8,
          }}>
            <span style={{ animation: "pulse 1.2s ease-in-out infinite", fontSize: 10 }}>●</span>
            {drawingBanner}
          </div>
        )}

        {/* ── Success toast ── */}
        {successMsg && (
          <div style={{
            position: "absolute", bottom: 12, left: "50%",
            transform: "translateX(-50%)",
            background: "#059669", color: "#fff",
            borderRadius: 8, padding: "8px 16px",
            fontSize: 13, fontWeight: 600,
            boxShadow: "0 4px 12px rgba(0,0,0,.3)",
            animation: "fadeIn .3s ease",
            whiteSpace: "nowrap",
          }}>
            ✓ {successMsg}
          </div>
        )}
      </div>

      {/* ── Controls below canvas ── */}
      <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {mode === "idle" && (
          <button onClick={startDrawing} style={BT("#1a1a2e", "#fff")}>
            + Draw Zone
          </button>
        )}
        {mode === "drawing" && (
          <>
            <button onClick={undoPoint} disabled={currentPts.length === 0}
              style={{ ...BT("#374151", "#fff"), opacity: currentPts.length ? 1 : 0.4 }}>
              ↩ Undo last point
            </button>
            <button onClick={cancelDrawing} style={BT("#6b7280", "#fff")}>
              Cancel
            </button>
          </>
        )}
        {(mode === "drawing" || mode === "pending") && zones.length === 0 && mode !== "pending" && (
          <span style={{ fontSize: 12, color: "#94a3b8", marginLeft: 4 }}>
            Tip: you can draw as many zones as you need
          </span>
        )}
        {mode === "idle" && zones.length > 0 && (
          <span style={{ fontSize: 12, color: "#6b7280" }}>
            Drag any orange/red corner to reposition it
          </span>
        )}
      </div>

      {/* ── Naming form (inline, after polygon is closed) ── */}
      {mode === "pending" && (
        <div style={{
          marginTop: 12, padding: "16px 18px",
          background: "#f0fdf4", borderRadius: 8, border: "1px solid #86efac",
        }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: "#15803d", marginBottom: 12 }}>
            ✓ Shape drawn! Give this zone a name and type.
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
            <FormField label="Zone name" hint='e.g. "Scaffolding Area" or "Site Entrance"'>
              <input
                autoFocus
                placeholder='e.g. Scaffolding Area'
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                onKeyDown={e => e.key === "Enter" && confirmZone()}
                style={INP}
              />
            </FormField>
            <FormField label="Zone type" hint="What rule applies inside this zone?">
              <select
                value={form.rule}
                onChange={e => setForm(f => ({ ...f, rule: e.target.value as NamingForm["rule"] }))}
                style={{ ...INP, width: "auto" }}
              >
                <option value="no_entry">🚫 No Entry — alert anyone inside, no exceptions</option>
                <option value="require_ppe">⚠️ Require PPE — alert if specific gear is missing</option>
              </select>
            </FormField>
            {form.rule === "require_ppe" && (
              <FormField label="Required PPE" hint='Comma-separated, e.g. "hardhat, vest, face_shield"'>
                <input
                  placeholder="hardhat, vest"
                  value={form.ppe}
                  onChange={e => setForm(f => ({ ...f, ppe: e.target.value }))}
                  style={INP}
                />
              </FormField>
            )}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button onClick={confirmZone} disabled={!form.name.trim()}
              style={{ ...BT("#059669", "#fff"), opacity: form.name.trim() ? 1 : 0.5 }}>
              Save Zone
            </button>
            <button onClick={discardPending} style={BT("#dc2626", "#fff")}>
              Discard shape
            </button>
          </div>
        </div>
      )}

      {/* ── Zone list ── */}
      {zones.length > 0 && mode !== "pending" && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ background: "#1a1a2e", color: "#fff", borderRadius: "50%", width: 20, height: 20, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11 }}>
              {zones.length}
            </span>
            Zone{zones.length > 1 ? "s" : ""} configured
            <span style={{ fontWeight: 400, color: "#9ca3af", marginLeft: 4, fontSize: 11 }}>
              — drag any corner handle to fine-tune the shape
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {zones.map((z, i) => {
              const c = COLORS[z.rule] ?? FALLBACK;
              return (
                <div key={z.id} style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "8px 12px", background: "#fff",
                  borderRadius: 7, borderLeft: `3px solid ${c.stroke}`,
                  boxShadow: "0 1px 3px rgba(0,0,0,.06)",
                }}>
                  <div style={{ width: 10, height: 10, borderRadius: "50%", background: c.stroke, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <span style={{ fontWeight: 700, fontSize: 13 }}>{z.name}</span>
                    <span style={{ fontSize: 11, color: "#6b7280", marginLeft: 8 }}>
                      {z.rule === "no_entry"
                        ? "No entry — CRITICAL alert for anyone inside"
                        : `Requires: ${z.required_ppe.length ? z.required_ppe.join(", ") : "hardhat, vest"}`}
                      {" · "}{z.points.length} corners
                    </span>
                  </div>
                  <button onClick={() => removeZone(i)} title="Delete zone"
                    style={{ background: "none", border: "none", color: "#dc2626", cursor: "pointer", fontSize: 18, lineHeight: 1, padding: "0 4px" }}>
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

// ── Tiny helpers ──────────────────────────────────────────────────────────────

function FormField({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <label style={{ fontSize: 11, fontWeight: 700, color: "#374151" }}>{label}</label>
      {children}
      {hint && <span style={{ fontSize: 10, color: "#9ca3af" }}>{hint}</span>}
    </div>
  );
}

function BT(bg: string, color: string): React.CSSProperties {
  return { padding: "7px 16px", borderRadius: 6, border: "none", background: bg, color, fontWeight: 600, fontSize: 13, cursor: "pointer", whiteSpace: "nowrap" as const };
}

const INP: React.CSSProperties = {
  padding: "7px 10px", borderRadius: 6, border: "1px solid #d1d5db", fontSize: 13, minWidth: 200,
};
