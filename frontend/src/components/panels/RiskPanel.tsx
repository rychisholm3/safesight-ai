import { useCallback, useEffect, useState } from "react";
import type { RiskSummary, WorkerRisk, ZoneRisk } from "../../lib/api";
import { fetchRepeatOffenders, fetchRiskSummary, fetchZoneRisks } from "../../lib/api";

// ── Colour maps ───────────────────────────────────────────────────────────────

const LEVEL_BG: Record<string, string> = {
  LOW:      "#f0fdf4",
  ELEVATED: "#fffbeb",
  HIGH:     "#fff7ed",
  CRITICAL: "#fef2f2",
};
const LEVEL_BORDER: Record<string, string> = {
  LOW:      "#86efac",
  ELEVATED: "#fcd34d",
  HIGH:     "#fb923c",
  CRITICAL: "#f87171",
};
const LEVEL_TEXT: Record<string, string> = {
  LOW:      "#15803d",
  ELEVATED: "#b45309",
  HIGH:     "#c2410c",
  CRITICAL: "#b91c1c",
};
const TREND_ARROW: Record<string, string> = {
  RISING:  "↑",
  STABLE:  "→",
  FALLING: "↓",
};
const TREND_COLOUR: Record<string, string> = {
  RISING:  "#dc2626",
  STABLE:  "#6b7280",
  FALLING: "#16a34a",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function SummaryBar({ summary }: { summary: RiskSummary }) {
  const lc = LEVEL_TEXT[summary.overall_risk_level] ?? "#374151";
  return (
    <div style={{
      display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 16,
      background: "#fff", borderRadius: 10, padding: "14px 18px",
      boxShadow: "0 1px 4px rgba(0,0,0,.07)",
    }}>
      <SummaryChip label="Site Risk" value={summary.overall_risk_level} color={lc} />
      <SummaryChip label="Score" value={`${summary.overall_risk_score}/100`} color={lc} />
      <SummaryChip label="24 h violations" value={String(summary.total_violations_24h)} color="#374151" />
      <SummaryChip label="7 d violations" value={String(summary.total_violations_7d)} color="#374151" />
      <SummaryChip label="Rising zones" value={String(summary.rising_risk_zones.length)} color={summary.rising_risk_zones.length > 0 ? "#dc2626" : "#15803d"} />
      <SummaryChip label="Repeat offenders" value={String(summary.repeat_offender_count)} color={summary.repeat_offender_count > 0 ? "#b45309" : "#15803d"} />
      {summary.highest_risk_zone && (
        <SummaryChip label="Hotspot zone" value={summary.highest_risk_zone} color="#7c3aed" />
      )}
    </div>
  );
}

function SummaryChip({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ textAlign: "center", minWidth: 80 }}>
      <div style={{ fontWeight: 700, fontSize: 15, color }}>{value}</div>
      <div style={{ fontSize: 10, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.4, marginTop: 2 }}>{label}</div>
    </div>
  );
}

function ZoneCard({ zone }: { zone: ZoneRisk }) {
  const bg     = LEVEL_BG[zone.risk_level]     ?? "#f9fafb";
  const border = LEVEL_BORDER[zone.risk_level] ?? "#d1d5db";
  const text   = LEVEL_TEXT[zone.risk_level]   ?? "#374151";
  const arrow  = TREND_ARROW[zone.trend]        ?? "→";
  const arrowC = TREND_COLOUR[zone.trend]       ?? "#6b7280";

  return (
    <div style={{
      background: bg, border: `1.5px solid ${border}`,
      borderRadius: 10, padding: "14px 16px",
    }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontWeight: 700, fontSize: 13, color: "#1f2937", flex: 1 }}>
          {zone.zone_id}
        </div>
        <span style={{ fontSize: 18, color: arrowC, marginRight: 6 }} title={`${zone.trend} (${zone.trend_pct > 0 ? "+" : ""}${zone.trend_pct.toFixed(0)}% vs last week)`}>
          {arrow}
        </span>
        <span style={{
          fontSize: 11, fontWeight: 700, color: text,
          background: border, borderRadius: 4, padding: "2px 7px",
        }}>
          {zone.risk_level}
        </span>
      </div>

      {/* Score bar */}
      <div style={{ background: "#e5e7eb", borderRadius: 4, height: 6, marginBottom: 10 }}>
        <div style={{
          height: 6, borderRadius: 4,
          width: `${zone.risk_score}%`,
          background: text,
          transition: "width .4s ease",
        }} />
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#6b7280" }}>
        <span><b style={{ color: "#1f2937" }}>{zone.violations_24h}</b> last 24 h</span>
        <span><b style={{ color: "#1f2937" }}>{zone.violations_7d}</b> this week</span>
        <span style={{ color: arrowC }}>
          {zone.trend_pct > 0 ? "+" : ""}{zone.trend_pct.toFixed(0)}% WoW
        </span>
      </div>
    </div>
  );
}

function OffenderRow({ worker }: { worker: WorkerRisk }) {
  const etype = worker.most_common_type.replace("_", " ");
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "10px 14px", background: "#fff",
      borderRadius: 8, border: "1px solid #fee2e2",
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: "50%",
        background: "#fef2f2", border: "1.5px solid #f87171",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontWeight: 700, fontSize: 13, color: "#b91c1c", flexShrink: 0,
      }}>
        #{worker.track_id}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#1f2937" }}>
          Worker #{worker.track_id}
        </div>
        <div style={{ fontSize: 11, color: "#6b7280" }}>
          {etype}{worker.most_common_zone ? ` · ${worker.most_common_zone}` : ""}
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#b91c1c" }}>
          {worker.violations_24h}
        </div>
        <div style={{ fontSize: 10, color: "#9ca3af" }}>violations / 24 h</div>
      </div>
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function RiskPanel() {
  const [summary,   setSummary]   = useState<RiskSummary | null>(null);
  const [zones,     setZones]     = useState<ZoneRisk[]>([]);
  const [offenders, setOffenders] = useState<WorkerRisk[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([fetchRiskSummary(), fetchZoneRisks(), fetchRepeatOffenders()])
      .then(([s, z, o]) => { setSummary(s); setZones(z); setOffenders(o); setError(null); })
      .catch(() => setError("Failed to load risk data"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  if (loading && !summary) {
    return (
      <div style={{ textAlign: "center", padding: "40px 0", color: "#9ca3af", fontSize: 14 }}>
        Computing risk scores…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: "center", padding: "40px 0", color: "#dc2626", fontSize: 14 }}>
        {error}
      </div>
    );
  }

  return (
    <div>
      {summary && <SummaryBar summary={summary} />}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12, marginBottom: 20 }}>
        {zones.length === 0 ? (
          <div style={{ gridColumn: "1/-1", textAlign: "center", padding: "32px 0", color: "#9ca3af", fontSize: 14 }}>
            No zone violation data yet — run the pipeline to start generating risk scores.
          </div>
        ) : (
          zones.map((z) => <ZoneCard key={z.zone_id} zone={z} />)
        )}
      </div>

      {offenders.length > 0 && (
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 8 }}>
            Repeat Offenders (3+ violations in 24 h)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {offenders.map((w) => <OffenderRow key={w.track_id} worker={w} />)}
          </div>
        </div>
      )}
    </div>
  );
}
