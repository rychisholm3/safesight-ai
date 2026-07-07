import { useCallback, useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from "recharts";
import { fetchCompliance, type ComplianceData } from "../../lib/api";

const TREND_ARROW: Record<string, string> = {
  RISING:  "↑",
  FALLING: "↓",
  STABLE:  "→",
};
const TREND_COLOR: Record<string, string> = {
  RISING:  "#059669",
  FALLING: "#dc2626",
  STABLE:  "#6b7280",
};

function GaugeCard({
  label, value, pass, suffix = "%",
}: { label: string; value: number; pass: boolean; suffix?: string }) {
  const color = value >= (label === "Zone" ? 95 : 90)
    ? "#059669"
    : value >= 70 ? "#d97706" : "#dc2626";

  return (
    <div style={{
      background: "#fff", borderRadius: 10, padding: "16px 20px",
      border: `1px solid ${color}44`, flex: 1, textAlign: "center",
    }}>
      <div style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
        {label} Compliance
      </div>
      <div style={{ fontSize: 34, fontWeight: 800, color }}>{value.toFixed(1)}{suffix}</div>
      <div style={{ fontSize: 10, color, fontWeight: 600, marginTop: 4 }}>
        {label === "Zone" ? (value >= 95 ? "✓ Above threshold" : "✗ Below 95%")
                          : (value >= 90 ? "✓ Above threshold" : "✗ Below 90%")}
      </div>
    </div>
  );
}

export function CompliancePanel() {
  const [data, setData]       = useState<ComplianceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    fetchCompliance()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div style={{ textAlign: "center", padding: 60, color: "#9ca3af" }}>
      Loading compliance data…
    </div>
  );
  if (error || !data) return (
    <div style={{ textAlign: "center", padding: 40, color: "#dc2626" }}>
      {error ?? "Failed to load compliance data."}
    </div>
  );

  const { status, history, forecast } = data;
  const isPass = status.pass_fail === "PASS";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Overall PASS/FAIL badge + worker count */}
      <div style={{
        display: "flex", alignItems: "center", gap: 16,
        background: isPass ? "#f0fdf4" : "#fef2f2",
        border: `1px solid ${isPass ? "#bbf7d0" : "#fecaca"}`,
        borderRadius: 10, padding: "14px 20px",
      }}>
        <div style={{
          fontSize: 22, fontWeight: 900, letterSpacing: 1,
          color: isPass ? "#059669" : "#dc2626",
        }}>
          {isPass ? "✓ PASS" : "✗ FAIL"}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>
            Site compliance status (last 24 hours)
          </div>
          <div style={{ fontSize: 12, color: "#6b7280" }}>
            {status.tracked_workers_24h} worker{status.tracked_workers_24h !== 1 ? "s" : ""} tracked ·
            PPE threshold 90% · Zone threshold 95%
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 11, color: "#6b7280" }}>Overall</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: isPass ? "#059669" : "#dc2626" }}>
            {status.overall_pct.toFixed(1)}%
          </div>
        </div>
      </div>

      {/* Gauge cards */}
      <div style={{ display: "flex", gap: 12 }}>
        <GaugeCard label="PPE"  value={status.ppe_pct}  pass={status.ppe_pct  >= 90} />
        <GaugeCard label="Zone" value={status.zone_pct} pass={status.zone_pct >= 95} />

        {/* Forecast card */}
        <div style={{
          background: "#fff", borderRadius: 10, padding: "16px 20px",
          border: "1px solid #e5e7eb", flex: 1, textAlign: "center",
        }}>
          <div style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
            Predicted Tomorrow
          </div>
          <div style={{
            fontSize: 34, fontWeight: 800,
            color: TREND_COLOR[forecast.trend],
          }}>
            {TREND_ARROW[forecast.trend]} {forecast.predicted_pct.toFixed(1)}%
          </div>
          <div style={{ fontSize: 10, color: TREND_COLOR[forecast.trend], fontWeight: 600, marginTop: 4 }}>
            {forecast.trend} ({forecast.trend_pct > 0 ? "+" : ""}{forecast.trend_pct.toFixed(1)} pp)
          </div>
        </div>
      </div>

      {/* 7-day history chart */}
      <div style={{
        background: "#fff", borderRadius: 10, border: "1px solid #e5e7eb",
        padding: "16px 20px",
      }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#374151", marginBottom: 14 }}>
          7-Day Compliance History
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={history} margin={{ top: 4, right: 16, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis
              dataKey="date"
              tickFormatter={(d) => d.slice(5)}
              tick={{ fontSize: 11, fill: "#6b7280" }}
            />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#6b7280" }} />
            <Tooltip
              formatter={(v: number, name: string) => [`${v.toFixed(1)}%`, name]}
              labelFormatter={(l) => `Date: ${l}`}
              contentStyle={{ fontSize: 12, borderRadius: 6 }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={90} stroke="#f0a500" strokeDasharray="4 2" label={{ value: "PPE 90%", position: "insideTopRight", fontSize: 9, fill: "#f0a500" }} />
            <ReferenceLine y={95} stroke="#dc2626" strokeDasharray="4 2" label={{ value: "Zone 95%", position: "insideTopRight", fontSize: 9, fill: "#dc2626" }} />
            <Line type="monotone" dataKey="ppe_pct"     name="PPE %"     stroke="#f0a500" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="monotone" dataKey="zone_pct"    name="Zone %"    stroke="#dc2626" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="monotone" dataKey="overall_pct" name="Overall %" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} strokeDasharray="5 2" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <button
        onClick={load}
        style={{
          alignSelf: "flex-end", fontSize: 12, padding: "6px 14px",
          borderRadius: 6, border: "1px solid #d1d5db", background: "#fff",
          cursor: "pointer", color: "#374151",
        }}
      >
        Refresh
      </button>
    </div>
  );
}
