import { useCallback, useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";
import {
  fetchRootCauseAnalysis, fetchRootCauseSummary,
  type RootCauseAnalysisData, type RootCauseSummary,
} from "./api";

// ── Helpers ───────────────────────────────────────────────────────────────────

const RISK_COLOR: Record<string, string> = {
  CRITICAL: "#dc2626", HIGH: "#f97316", ELEVATED: "#d97706", LOW: "#6b7280",
};
const SEG_COLOR: Record<string, string> = {
  isolated: "#6b7280", recurring: "#d97706", chronic: "#dc2626",
};
const TYPE_LABEL: Record<string, string> = {
  missing_ppe: "Missing PPE", zone_intrusion: "Zone Intrusion",
  near_miss: "Near Miss", none: "None",
};

// ── Section header ────────────────────────────────────────────────────────────
function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#1f2937" }}>{title}</div>
      {subtitle && <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{subtitle}</div>}
    </div>
  );
}

// ── Time-of-day chart ─────────────────────────────────────────────────────────
function TimeOfDayChart({ data }: { data: RootCauseAnalysisData }) {
  const chartData = data.hour_buckets.map((b) => ({
    label:   b.label,
    count:   b.count,
    isPeak:  b.is_peak,
    period:  b.period,
    z_score: b.z_score,
  }));
  const mean = data.event_total / 24;

  return (
    <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb", padding: "16px 20px" }}>
      <SectionHeader
        title="Time-of-Day Violation Distribution"
        subtitle="Bars above the dashed line are statistically elevated (Z ≥ 1.0)"
      />
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="label" tick={{ fontSize: 9, fill: "#9ca3af" }} interval={3} />
          <YAxis tick={{ fontSize: 10, fill: "#6b7280" }} />
          <Tooltip
            formatter={(v: number, _n: string, props: { payload?: { period?: string; z_score?: number } }) => [
              `${v} violations (Z=${props.payload?.z_score ?? 0})`,
              props.payload?.period ?? "",
            ]}
            contentStyle={{ fontSize: 11, borderRadius: 6 }}
          />
          <ReferenceLine y={mean} stroke="#3b82f6" strokeDasharray="5 3"
            label={{ value: "avg", position: "insideTopRight", fontSize: 9, fill: "#3b82f6" }} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]}>
            {chartData.map((d, i) => (
              <Cell key={i} fill={d.isPeak ? "#dc2626" : "#94a3b8"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* Shift period risk cards */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 14 }}>
        {data.shift_periods.filter(s => s.count > 0).map((sp) => (
          <div key={sp.name} style={{
            borderRadius: 7, padding: "7px 12px", flex: "1 1 auto",
            background: RISK_COLOR[sp.risk_level] + "18",
            border: `1px solid ${RISK_COLOR[sp.risk_level]}44`,
          }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: RISK_COLOR[sp.risk_level], textTransform: "uppercase", letterSpacing: 0.4 }}>
              {sp.risk_level}
            </div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#1f2937", marginTop: 2 }}>{sp.name}</div>
            <div style={{ fontSize: 10, color: "#6b7280" }}>
              {sp.count} events · {sp.avg_per_hour}/hr
            </div>
            <div style={{ fontSize: 10, color: "#6b7280" }}>
              {TYPE_LABEL[sp.dominant_type] ?? sp.dominant_type}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Zone hotspot chart ────────────────────────────────────────────────────────
function ZoneHotspotChart({ data }: { data: RootCauseAnalysisData }) {
  if (data.zone_patterns.length === 0) {
    return (
      <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb", padding: "16px 20px" }}>
        <SectionHeader title="Zone Hotspots" />
        <div style={{ color: "#9ca3af", fontSize: 13, textAlign: "center", padding: 20 }}>
          No zone-specific events in this period.
        </div>
      </div>
    );
  }

  const chartData = data.zone_patterns.slice(0, 8).map((z) => ({
    name: z.zone_id.length > 14 ? z.zone_id.slice(0, 13) + "…" : z.zone_id,
    ppe:  z.ppe_count,
    zone: z.zone_count,
    nm:   z.nm_count,
    peak: z.peak_period ?? "",
  }));

  return (
    <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb", padding: "16px 20px" }}>
      <SectionHeader
        title="Zone Hotspot Analysis"
        subtitle="Stacked by violation type — location with peak times"
      />
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#9ca3af" }} />
          <YAxis tick={{ fontSize: 10, fill: "#6b7280" }} />
          <Tooltip
            formatter={(v: number, name: string) => [v, TYPE_LABEL[name] ?? name]}
            contentStyle={{ fontSize: 11, borderRadius: 6 }}
          />
          <Bar dataKey="ppe"  name="missing_ppe"    stackId="a" fill="#d97706" radius={[0, 0, 0, 0]} />
          <Bar dataKey="zone" name="zone_intrusion" stackId="a" fill="#dc2626" radius={[0, 0, 0, 0]} />
          <Bar dataKey="nm"   name="near_miss"      stackId="a" fill="#a855f7" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>

      {/* Zone detail rows */}
      {data.zone_patterns.slice(0, 5).map((z) => (
        <div key={z.zone_id} style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "5px 0", borderBottom: "1px solid #f1f5f9", fontSize: 12,
        }}>
          <span style={{ fontWeight: 600, color: "#1f2937" }}>{z.zone_id}</span>
          <span style={{ color: "#6b7280" }}>{z.count} events</span>
          {z.peak_period && (
            <span style={{ fontSize: 10, color: "#3b82f6" }}>peak: {z.peak_period}</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Worker pattern panel ──────────────────────────────────────────────────────
function WorkerPatternPanel({ data }: { data: RootCauseAnalysisData }) {
  const chronic  = data.worker_patterns.filter(w => w.segment === "chronic");
  const recurr   = data.worker_patterns.filter(w => w.segment === "recurring");
  const isolated = data.worker_patterns.filter(w => w.segment === "isolated");

  return (
    <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb", padding: "16px 20px" }}>
      <SectionHeader
        title="Worker Behaviour Patterns"
        subtitle="Segmented by violation frequency. Worker-type data requires HR system integration."
      />

      {/* Segment summary */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
        {[
          { label: "Chronic (5+)",    count: chronic.length,  color: "#dc2626", seg: "chronic" },
          { label: "Recurring (2-4)", count: recurr.length,   color: "#d97706", seg: "recurring" },
          { label: "Isolated (1)",    count: isolated.length, color: "#6b7280", seg: "isolated" },
        ].map(({ label, count, color }) => (
          <div key={label} style={{
            flex: 1, textAlign: "center", padding: "10px",
            borderRadius: 8, background: color + "15",
            border: `1px solid ${color}44`,
          }}>
            <div style={{ fontSize: 26, fontWeight: 800, color }}>{count}</div>
            <div style={{ fontSize: 10, color, fontWeight: 600 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Chronic workers */}
      {chronic.length > 0 && (
        <>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#dc2626", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
            Chronic Offenders — Immediate Attention Required
          </div>
          {chronic.slice(0, 5).map((w) => (
            <div key={w.track_id} style={{
              display: "flex", gap: 10, alignItems: "center",
              padding: "6px 0", borderBottom: "1px solid #fef2f2", fontSize: 12,
            }}>
              <span style={{
                fontWeight: 700, color: "#dc2626",
                background: "#fef2f2", borderRadius: 4, padding: "2px 7px",
              }}>#{w.track_id}</span>
              <span style={{ color: "#374151", flex: 1 }}>
                {w.violation_count} violations · {TYPE_LABEL[w.dominant_type] ?? w.dominant_type}
                {w.primary_zone ? ` · Zone: ${w.primary_zone}` : ""}
              </span>
              {w.peak_period && (
                <span style={{ fontSize: 10, color: "#6b7280" }}>peaks at {w.peak_period}</span>
              )}
            </div>
          ))}
        </>
      )}

      {data.worker_patterns.length === 0 && (
        <div style={{ color: "#9ca3af", fontSize: 13, textAlign: "center", padding: 20 }}>
          No worker violations in this period.
        </div>
      )}
    </div>
  );
}

// ── Root cause summary ────────────────────────────────────────────────────────
function SummaryPanel({ days }: { days: number }) {
  const [summary, setSummary]   = useState<RootCauseSummary | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  function generate() {
    setLoading(true);
    setError(null);
    fetchRootCauseSummary(days)
      .then(setSummary)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }

  return (
    <div style={{ background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb", padding: "16px 20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <SectionHeader
          title="Root Cause Summary"
          subtitle={summary?.generated_by === "claude" ? "Generated by Claude · AI-powered analysis" : "Deterministic analysis · Set ANTHROPIC_API_KEY for AI narrative"}
        />
        <button
          onClick={generate}
          disabled={loading}
          style={{
            fontSize: 12, padding: "6px 16px", borderRadius: 6,
            border: "none", background: loading ? "#e5e7eb" : "#1a1a2e",
            color: loading ? "#9ca3af" : "#fff", cursor: loading ? "default" : "pointer", fontWeight: 600,
          }}
        >
          {loading ? "Generating…" : summary ? "↺ Regenerate" : "Generate Summary"}
        </button>
      </div>

      {error && (
        <div style={{ color: "#dc2626", background: "#fef2f2", borderRadius: 6, padding: "8px 12px", fontSize: 12, marginBottom: 10 }}>
          {error}
        </div>
      )}

      {!summary && !loading && (
        <div style={{ textAlign: "center", padding: "30px 0", color: "#9ca3af", fontSize: 13 }}>
          Click "Generate Summary" to run root cause analysis
        </div>
      )}

      {summary && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Executive summary */}
          {summary.executive_summary && (
            <div style={{
              background: "#f8fafc", borderRadius: 8, padding: "12px 16px",
              borderLeft: "4px solid #3b82f6", fontSize: 13, color: "#1f2937", lineHeight: 1.6,
            }}>
              {summary.executive_summary}
            </div>
          )}

          {/* Root causes */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 }}>
              Root Causes Identified
            </div>
            {summary.root_causes.map((rc, i) => (
              <div key={i} style={{
                borderRadius: 7, border: "1px solid #e5e7eb",
                marginBottom: 6, overflow: "hidden",
              }}>
                <div style={{
                  padding: "7px 12px",
                  background: rc.type === "worker_pattern" ? "#fef2f2" : rc.type === "location_pattern" ? "#fffbeb" : "#eff6ff",
                  borderBottom: "1px solid #e5e7eb",
                  fontSize: 12, fontWeight: 700,
                  color: rc.type === "worker_pattern" ? "#dc2626" : rc.type === "location_pattern" ? "#d97706" : "#2563eb",
                }}>
                  {i + 1}. {rc.title}
                </div>
                <div style={{ padding: "7px 12px", fontSize: 12, color: "#374151", lineHeight: 1.5 }}>
                  {rc.evidence}
                </div>
              </div>
            ))}
          </div>

          {/* Recommendations */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 }}>
              Intervention Recommendations
            </div>
            {summary.recommendations.map((rec, i) => (
              <div key={i} style={{
                display: "flex", gap: 8, padding: "5px 0",
                borderBottom: "1px solid #f1f5f9", fontSize: 12, color: "#374151",
              }}>
                <span style={{
                  minWidth: 22, height: 22, borderRadius: "50%",
                  background: "#1a1a2e", color: "#fff",
                  fontSize: 10, fontWeight: 700,
                  display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                }}>{i + 1}</span>
                <span style={{ lineHeight: 1.5 }}>{rec}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────
export function RootCausePanel() {
  const [data, setData]       = useState<RootCauseAnalysisData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);
  const [days, setDays]       = useState(7);

  const load = useCallback((d: number) => {
    setLoading(true);
    setError(null);
    fetchRootCauseAnalysis(d)
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(days); }, [days, load]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12,
        background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb", padding: "10px 16px",
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>Analysis window</span>
        {[7, 14, 30].map((d) => (
          <button key={d}
            onClick={() => setDays(d)}
            style={{
              fontSize: 12, padding: "4px 12px", borderRadius: 20,
              border: "1px solid #d1d5db",
              background: days === d ? "#1a1a2e" : "#fff",
              color: days === d ? "#fff" : "#374151",
              cursor: "pointer", fontWeight: days === d ? 600 : 400,
            }}
          >{d} days</button>
        ))}
        {data && (
          <span style={{ fontSize: 11, color: "#9ca3af", marginLeft: "auto" }}>
            {data.event_total} events analysed
          </span>
        )}
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: 50, color: "#9ca3af" }}>Loading analysis…</div>
      )}
      {error && (
        <div style={{ padding: 20, color: "#dc2626", background: "#fef2f2", borderRadius: 8, fontSize: 13 }}>
          {error}
        </div>
      )}
      {!loading && data && (
        <>
          <TimeOfDayChart data={data} />
          <ZoneHotspotChart data={data} />
          <WorkerPatternPanel data={data} />
          <SummaryPanel days={days} />
        </>
      )}
    </div>
  );
}
