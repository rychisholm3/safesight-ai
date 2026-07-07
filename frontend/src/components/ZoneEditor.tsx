/**
 * ZoneEditor — full zone management modal accessible from the dashboard header.
 *
 * Unlike the setup wizard this is the day-to-day zone management UI:
 *  • Auto-loads cameras and video files as snapshot sources (no manual file upload)
 *  • Loads existing zones.json on mount so existing zones are always shown
 *  • Uses ZoneCanvas for interactive polygon drawing / editing
 *  • Save button persists changes to zones.json immediately
 */
import { useCallback, useEffect, useState } from "react";
import type { CameraInfo, VideoFileInfo } from "../lib/api";
import {
  fetchCameraSnapshot, fetchCameras, fetchVideoFiles,
  fetchVideoSnapshot, fetchZones, saveZones,
} from "../lib/api";
import type { Zone, ZonesConfig } from "../types";
import type { DrawnZone } from "./ZoneCanvas";
import { ZoneCanvas } from "./ZoneCanvas";

// ── Conversion helpers ────────────────────────────────────────────────────────

function toDrawn(z: Zone): DrawnZone {
  return { id: z.id, name: z.name, rule: z.rule, required_ppe: z.required_ppe ?? [], points: z.polygon };
}
function toZone(d: DrawnZone): Zone {
  return {
    id: d.id, name: d.name, rule: d.rule, polygon: d.points,
    ...(d.rule === "require_ppe" ? { required_ppe: d.required_ppe } : {}),
  };
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props { onClose: () => void }

type SourceKind = "camera" | "video";
interface SourceOpt { kind: SourceKind; id: string; label: string }

export function ZoneEditor({ onClose }: Props) {
  const [sources,     setSources]     = useState<SourceOpt[]>([]);
  const [source,      setSource]      = useState<SourceOpt | null>(null);
  const [snapshotUrl, setSnapshotUrl] = useState<string | null>(null);
  const [loadingSnap, setLoadingSnap] = useState(false);
  const [zones,       setZones]       = useState<DrawnZone[]>([]);
  const [globalPPE,   setGlobalPPE]   = useState<string[]>(["hardhat", "vest"]);
  const [saving,      setSaving]      = useState(false);
  const [savedMsg,    setSavedMsg]    = useState(false);
  const [saveError,   setSaveError]   = useState(false);

  // Load cameras + video files + existing zones in parallel
  useEffect(() => {
    Promise.allSettled([fetchCameras(), fetchVideoFiles(), fetchZones()])
      .then(([cams, vids, zonesRes]) => {
        const opts: SourceOpt[] = [];
        if (cams.status === "fulfilled") {
          (cams.value as CameraInfo[]).forEach(c =>
            opts.push({ kind: "camera", id: String(c.index), label: `Camera ${c.index}` })
          );
        }
        if (vids.status === "fulfilled") {
          (vids.value as VideoFileInfo[]).forEach(v =>
            opts.push({ kind: "video", id: v.path, label: v.name })
          );
        }
        setSources(opts);
        const first = opts[0] ?? null;
        setSource(first);
        if (zonesRes.status === "fulfilled") {
          const cfg = zonesRes.value as ZonesConfig;
          setZones(cfg.zones.map(toDrawn));
          setGlobalPPE(cfg.required_ppe);
        }
        if (first) loadSnapshot(first);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadSnapshot = useCallback((src: SourceOpt) => {
    setSnapshotUrl(null);
    setLoadingSnap(true);
    const p = src.kind === "camera"
      ? fetchCameraSnapshot(Number(src.id))
      : fetchVideoSnapshot(src.id);
    p.then(url => { setSnapshotUrl(url); setLoadingSnap(false); })
     .catch(() => setLoadingSnap(false));
  }, []);

  function switchSource(src: SourceOpt) {
    setSource(src);
    loadSnapshot(src);
  }

  async function handleSave() {
    setSaving(true); setSaveError(false); setSavedMsg(false);
    try {
      await saveZones({ required_ppe: globalPPE, zones: zones.map(toZone) });
      setSavedMsg(true);
      setTimeout(() => setSavedMsg(false), 3000);
    } catch {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.65)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 16 }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{
        background: "#fff", borderRadius: 12, width: "95vw", maxWidth: 980,
        maxHeight: "92vh", display: "flex", flexDirection: "column", overflow: "hidden",
        boxShadow: "0 24px 64px rgba(0,0,0,.45)",
      }}>
        {/* ── Header ── */}
        <div style={{ padding: "14px 20px", background: "#1a1a2e", color: "#fff", display: "flex", alignItems: "center", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>Manage Safety Zones</div>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
              Draw zones on your camera view · drag corners to adjust · changes save to zones.json
            </div>
          </div>
          <button onClick={onClose} style={{ marginLeft: "auto", background: "none", border: "none", color: "#9ca3af", fontSize: 22, cursor: "pointer", lineHeight: 1 }}>×</button>
        </div>

        {/* ── Source bar ── */}
        {sources.length > 0 && (
          <div style={{ padding: "10px 20px", background: "#f8fafc", borderBottom: "1px solid #e5e7eb", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#374151" }}>View from:</span>
            {sources.map(src => (
              <button
                key={src.id}
                onClick={() => switchSource(src)}
                style={{
                  padding: "4px 12px", borderRadius: 20, fontSize: 12, fontWeight: 600,
                  border: "1px solid",
                  borderColor: source?.id === src.id ? "#3b82f6" : "#d1d5db",
                  background: source?.id === src.id ? "#eff6ff" : "#fff",
                  color: source?.id === src.id ? "#1d4ed8" : "#374151",
                  cursor: "pointer",
                }}
              >
                {src.kind === "camera" ? "🎥" : "📹"} {src.label}
              </button>
            ))}
            {loadingSnap && <span style={{ fontSize: 11, color: "#94a3b8" }}>Loading…</span>}
          </div>
        )}

        {/* ── Body ── */}
        <div style={{ flex: 1, overflowY: "auto", padding: "18px 20px" }}>
          {/* Instructions */}
          <div style={{
            padding: "10px 14px", background: "#eff6ff", borderRadius: 7,
            border: "1px solid #bfdbfe", fontSize: 12, color: "#1e40af",
            marginBottom: 14, lineHeight: 1.7,
          }}>
            <strong>How to use:</strong> Click <strong>+ Draw Zone</strong> on the canvas below, then click to place corners.
            When you have 3+ corners, click the <span style={{ color: "#16a34a", fontWeight: 700 }}>green first corner</span> to close the shape.
            Name it, pick the rule type, and click <strong>Save Zone</strong>.
            Drag any corner handle afterwards to fine-tune.
            Hit <strong>Save all zones</strong> when done.
          </div>

          {!snapshotUrl && !loadingSnap && sources.length === 0 && (
            <div style={{ padding: "40px 0", textAlign: "center", color: "#9ca3af", fontSize: 14 }}>
              <div style={{ fontSize: 36, marginBottom: 12 }}>📷</div>
              No cameras or video files detected.
              <br />Connect a webcam or add a .mp4 file to <code>data/input_videos/</code>.
            </div>
          )}

          {loadingSnap && (
            <div style={{ textAlign: "center", padding: "60px 0", color: "#94a3b8" }}>
              <div style={{ width: 32, height: 32, border: "3px solid #e2e8f0", borderTopColor: "#3b82f6", borderRadius: "50%", animation: "spin .7s linear infinite", margin: "0 auto 12px" }} />
              Loading snapshot…
            </div>
          )}

          {snapshotUrl && (
            <ZoneCanvas imageUrl={snapshotUrl} zones={zones} onZonesChange={setZones} />
          )}

          {/* Global PPE note */}
          <div style={{ marginTop: 18, padding: "10px 14px", background: "#f0fdf4", borderRadius: 7, border: "1px solid #86efac", fontSize: 12, color: "#15803d" }}>
            <strong>Global rule (always active):</strong> Every person detected without a <strong>hardhat</strong> or <strong>vest</strong> is flagged as a WARNING — no zone needed.
          </div>
        </div>

        {/* ── Footer ── */}
        <div style={{ padding: "12px 20px", borderTop: "1px solid #e5e7eb", display: "flex", alignItems: "center", gap: 12, background: "#fafafa" }}>
          <div style={{ flex: 1, fontSize: 12, color: "#6b7280" }}>
            {zones.length === 0
              ? "No zones configured — the global hardhat + vest rule still applies."
              : `${zones.length} zone${zones.length > 1 ? "s" : ""} configured`}
          </div>
          {savedMsg && <span style={{ fontSize: 12, color: "#059669", fontWeight: 600 }}>✓ Saved successfully!</span>}
          {saveError && <span style={{ fontSize: 12, color: "#dc2626" }}>Save failed — is the API running?</span>}
          <button onClick={onClose} style={{ padding: "8px 16px", borderRadius: 7, border: "1px solid #d1d5db", background: "#fff", color: "#374151", fontSize: 13, cursor: "pointer" }}>
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{ padding: "8px 20px", borderRadius: 7, border: "none", background: saving ? "#93c5fd" : "#3b82f6", color: "#fff", fontSize: 13, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer" }}
          >
            {saving ? "Saving…" : "Save all zones"}
          </button>
        </div>
      </div>
    </div>
  );
}
