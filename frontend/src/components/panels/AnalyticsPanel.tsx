import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AnalyticsScore, AnalyticsWorkerStat, DayBucket,
  HeatmapPoint, ScoreDay, ZoneStat,
} from "../../lib/api";
import {
  fetchAnalyticsScore, fetchHeatmapPoints, fetchScoreHistory,
  fetchViolationsByWorker, fetchViolationsByZone, fetchViolationsDaily,
} from "../../lib/api";

// ── Score gauge (SVG arc) ─────────────────────────────────────────────────────

const CIRCUM = 2 * Math.PI * 80;          // full circle circumference
const ARC    = (270 / 360) * CIRCUM;      // 270° arc length
const GAP    = CIRCUM - ARC;

function scoreColor(s: number) {
  if (s >= 75) return "#22c55e";
  if (s >= 50) return "#f59e0b";
  return "#ef4444";
}

function ScoreGauge({ score, prevScore }: { score: number; prevScore: number }) {
  const filled   = (score / 100) * ARC;
  const color    = scoreColor(score);
  const delta    = score - prevScore;
  const arrow    = delta > 1 ? "↑" : delta < -1 ? "↓" : "→";
  const arrowClr = delta > 1 ? "#22c55e" : delta < -1 ? "#ef4444" : "#6b7280";
  return (
    <div style={{ textAlign: "center", position: "relative", width: 180, flexShrink: 0 }}>
      <svg viewBox="0 0 200 200" width={180} height={180}>
        {/* track */}
        <circle cx="100" cy="100" r="80" fill="none" stroke="#e5e7eb" strokeWidth="14"
          strokeDasharray={`${ARC} ${GAP}`} strokeLinecap="round"
          transform="rotate(135 100 100)" />
        {/* score arc */}
        {score > 0 && (
          <circle cx="100" cy="100" r="80" fill="none" stroke={color} strokeWidth="14"
            strokeDasharray={`${filled} ${CIRCUM - filled}`} strokeLinecap="round"
            transform="rotate(135 100 100)"
            style={{ transition: "stroke-dasharray .6s ease" }} />
        )}
        <text x="100" y="95" textAnchor="middle" fontSize="38" fontWeight="700"
          fill={color} fontFamily="system-ui">{Math.round(score)}</text>
        <text x="100" y="118" textAnchor="middle" fontSize="13" fill="#6b7280"
          fontFamily="system-ui">/ 100</text>
      </svg>
      <div style={{ marginTop: -8, fontSize: 14, color: arrowClr, fontWeight: 700 }}>
        {arrow} {Math.abs(delta).toFixed(1)} vs prev 7d
      </div>
    </div>
  );
}

// ── Category breakdown bars ────────────────────────────────────────────────────

function CatBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
        <span style={{ color: "#374151" }}>{label}</span>
        <span style={{ fontWeight: 700, color }}>{value.toFixed(1)}</span>
      </div>
      <div style={{ background: "#e5e7eb", borderRadius: 4, height: 8 }}>
        <div style={{ height: 8, borderRadius: 4, background: color,
          width: `${value}%`, transition: "width .5s ease" }} />
      </div>
    </div>
  );
}

// ── 7-day stacked bar chart ────────────────────────────────────────────────────

function DayChart({ buckets }: { buckets: DayBucket[] }) {
  if (!buckets.length) return (
    <div style={{ textAlign: "center", padding: "32px 0", color: "#9ca3af", fontSize: 14 }}>
      No violation data in the selected window.
    </div>
  );
  const maxTotal = Math.max(...buckets.map((b) => b.total), 1);
  const BAR_W = 36;
  const GAP_W = 12;
  const H = 140;
  const W = buckets.length * (BAR_W + GAP_W) + GAP_W;
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H + 28}`} style={{ overflow: "visible" }}>
      {buckets.map((b, i) => {
        const x = GAP_W + i * (BAR_W + GAP_W);
        const ppeH  = (b.ppe / maxTotal) * H;
        const zoneH = (b.zone / maxTotal) * H;
        const nmH   = (b.near_miss / maxTotal) * H;
        const label = b.date.slice(5); // MM-DD
        return (
          <g key={b.date}>
            <rect x={x} y={H - ppeH} width={BAR_W} height={ppeH} fill="#fbbf24" rx={2} />
            <rect x={x} y={H - ppeH - zoneH} width={BAR_W} height={zoneH} fill="#f87171" rx={2} />
            <rect x={x} y={H - ppeH - zoneH - nmH} width={BAR_W} height={nmH} fill="#a855f7" rx={2} />
            <text x={x + BAR_W / 2} y={H + 14} textAnchor="middle" fontSize="10" fill="#9ca3af"
              fontFamily="system-ui">{label}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Heatmap canvas ─────────────────────────────────────────────────────────────

function Heatmap({ points }: { points: HeatmapPoint[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !points.length) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs) || 1;
    const minY = Math.min(...ys), maxY = Math.max(...ys) || 1;
    const rangeX = maxX - minX || 1, rangeY = maxY - minY || 1;

    // draw heat blobs on a black canvas
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    for (const p of points) {
      const cx = ((p.x - minX) / rangeX) * (W - 60) + 30;
      const cy = ((p.y - minY) / rangeY) * (H - 60) + 30;
      const r  = p.severity === "CRITICAL" ? 40 : 28;
      const g  = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
      g.addColorStop(0,   "rgba(255,255,255,0.9)");
      g.addColorStop(0.4, "rgba(255,255,255,0.5)");
      g.addColorStop(1,   "rgba(255,255,255,0)");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    // remap brightness → color gradient (green→yellow→red)
    const img = ctx.getImageData(0, 0, W, H);
    for (let i = 0; i < img.data.length; i += 4) {
      const v = img.data[i];
      if (v < 6) { img.data[i + 3] = 0; continue; }
      const t = Math.min(v / 220, 1);
      img.data[i]     = Math.round(t < 0.5 ? t * 2 * 255 : 255);
      img.data[i + 1] = Math.round(t < 0.5 ? 200 : (1 - (t - 0.5) * 2) * 200);
      img.data[i + 2] = 0;
      img.data[i + 3] = Math.round(60 + t * 195);
    }
    ctx.putImageData(img, 0, 0);
  }, [points]);

  return (
    <div style={{ position: "relative", background: "#111827", borderRadius: 10, overflow: "hidden" }}>
      <canvas ref={canvasRef} width={760} height={380}
        style={{ display: "block", width: "100%", height: "auto" }} />
      {!points.length && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center",
          justifyContent: "center", color: "#6b7280", fontSize: 14 }}>
          No position data yet — violations need bounding-box data to appear here.
        </div>
      )}
      <div style={{ position: "absolute", bottom: 8, right: 12, display: "flex", gap: 8,
        fontSize: 11, color: "#e5e7eb" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, borderRadius: 2, background: "#22c55e", display: "inline-block" }} />
          Low
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, borderRadius: 2, background: "#f59e0b", display: "inline-block" }} />
          Medium
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 12, height: 12, borderRadius: 2, background: "#ef4444", display: "inline-block" }} />
          High
        </span>
      </div>
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

export function AnalyticsPanel() {
  const [score,    setScore]    = useState<AnalyticsScore | null>(null);
  const [history,  setHistory]  = useState<ScoreDay[]>([]);
  const [daily,    setDaily]    = useState<DayBucket[]>([]);
  const [byZone,   setByZone]   = useState<ZoneStat[]>([]);
  const [byWorker, setByWorker] = useState<AnalyticsWorkerStat[]>([]);
  const [heatmap,  setHeatmap]  = useState<HeatmapPoint[]>([]);
  const [tab,      setTab]      = useState<"overview" | "heatmap">("overview");
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetchAnalyticsScore(),
      fetchScoreHistory(30),
      fetchViolationsDaily(7),
      fetchViolationsByZone(),
      fetchViolationsByWorker(10),
      fetchHeatmapPoints(),
    ])
      .then(([sc, hist, day, zone, worker, heat]) => {
        setScore(sc); setHistory(hist); setDaily(day);
        setByZone(zone); setByWorker(worker); setHeatmap(heat);
        setError(null);
      })
      .catch(() => setError("Failed to load analytics data"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); const id = setInterval(load, 60_000); return () => clearInterval(id); }, [load]);

  if (loading && !score) return (
    <div style={{ textAlign: "center", padding: "60px 0", color: "#9ca3af", fontSize: 14 }}>
      Computing analytics…
    </div>
  );
  if (error) return (
    <div style={{ textAlign: "center", padding: "60px 0", color: "#dc2626", fontSize: 14 }}>{error}</div>
  );

  const void_history = history; // kept for future trend mini-chart

  return (
    <div>
      {/* Sub-tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["overview", "heatmap"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "4px 16px", borderRadius: 20, cursor: "pointer", fontSize: 12,
            border: "1px solid #d1d5db", fontWeight: tab === t ? 600 : 400,
            background: tab === t ? "#1a1a2e" : "#fff",
            color: tab === t ? "#fff" : "#374151",
          }}>
            {t === "overview" ? "Overview" : "Heatmap"}
          </button>
        ))}
      </div>

      {tab === "heatmap" ? (
        <div>
          <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 12 }}>
            Spatial distribution of violations across the camera field of view. Each point is the centre of a detected violation bounding box.
          </div>
          <Heatmap points={heatmap} />
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 8 }}>
            {heatmap.length} violation position{heatmap.length !== 1 ? "s" : ""} plotted
          </div>
        </div>
      ) : (
        <div>
          {/* Score + categories */}
          <div style={{ display: "flex", gap: 20, marginBottom: 20,
            background: "#fff", borderRadius: 10, padding: "20px 24px",
            boxShadow: "0 1px 4px rgba(0,0,0,.07)", alignItems: "center", flexWrap: "wrap" }}>
            {score && <ScoreGauge score={score.score} prevScore={score.prev_score} />}
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 12 }}>
                Score breakdown (last 7 days)
              </div>
              {score && (
                <>
                  <CatBar label="PPE compliance" value={score.ppe_score} color="#fbbf24" />
                  <CatBar label="Zone compliance" value={score.zone_score} color="#f87171" />
                  <CatBar label="Near-miss safety" value={score.near_miss_score} color="#a855f7" />
                </>
              )}
            </div>
            {score && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 140 }}>
                {[
                  { label: "PPE violations",  value: score.ppe_7d,          color: "#fbbf24" },
                  { label: "Zone violations",  value: score.zone_7d,         color: "#f87171" },
                  { label: "Near misses",      value: score.near_miss_7d,    color: "#a855f7" },
                  { label: "Total (7d)",       value: score.violations_7d,   color: "#374151" },
                ].map(({ label, value, color }) => (
                  <div key={label}>
                    <div style={{ fontWeight: 700, fontSize: 18, color }}>{value}</div>
                    <div style={{ fontSize: 11, color: "#9ca3af" }}>{label}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 7-day chart */}
          <div style={{ background: "#fff", borderRadius: 10, padding: "16px 20px",
            boxShadow: "0 1px 4px rgba(0,0,0,.07)", marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 4 }}>
              Violations — last 7 days
            </div>
            <div style={{ display: "flex", gap: 16, fontSize: 11, color: "#9ca3af", marginBottom: 12 }}>
              <span><span style={{ color: "#fbbf24" }}>■</span> Missing PPE</span>
              <span><span style={{ color: "#f87171" }}>■</span> Zone intrusion</span>
              <span><span style={{ color: "#a855f7" }}>■</span> Near miss</span>
            </div>
            <DayChart buckets={daily} />
          </div>

          {/* Zone + worker breakdown */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div style={{ background: "#fff", borderRadius: 10, padding: "16px 20px",
              boxShadow: "0 1px 4px rgba(0,0,0,.07)" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 10 }}>
                Violations by zone
              </div>
              {byZone.length === 0 ? (
                <div style={{ fontSize: 13, color: "#9ca3af" }}>No zone data yet.</div>
              ) : byZone.map((z) => (
                <div key={z.zone_id} style={{ display: "flex", alignItems: "center",
                  justifyContent: "space-between", padding: "6px 0",
                  borderBottom: "1px solid #f3f4f6" }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500, color: "#1f2937" }}>{z.zone_id}</div>
                    {z.critical_count > 0 && (
                      <div style={{ fontSize: 11, color: "#b91c1c" }}>{z.critical_count} critical</div>
                    )}
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: "#374151" }}>{z.total}</div>
                </div>
              ))}
            </div>

            <div style={{ background: "#fff", borderRadius: 10, padding: "16px 20px",
              boxShadow: "0 1px 4px rgba(0,0,0,.07)" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 10 }}>
                Top workers by violations
              </div>
              {byWorker.length === 0 ? (
                <div style={{ fontSize: 13, color: "#9ca3af" }}>No worker data yet.</div>
              ) : byWorker.slice(0, 8).map((w) => (
                <div key={w.track_id} style={{ display: "flex", alignItems: "center",
                  gap: 10, padding: "5px 0", borderBottom: "1px solid #f3f4f6" }}>
                  <div style={{ width: 28, height: 28, borderRadius: "50%", background: "#fef2f2",
                    border: "1.5px solid #f87171", display: "flex", alignItems: "center",
                    justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#b91c1c",
                    flexShrink: 0 }}>
                    #{w.track_id}
                  </div>
                  <div style={{ flex: 1, fontSize: 12, color: "#6b7280" }}>
                    {w.most_common_type.replace("_", " ")}
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: "#374151" }}>
                    {w.violation_count}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
