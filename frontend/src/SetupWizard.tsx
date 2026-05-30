/**
 * SetupWizard — first-time onboarding flow shown before the dashboard.
 *
 * Step 1 · Camera Selection
 *   Probes /cameras, shows thumbnail cards, user picks one source.
 *   Falls back to a manual path/URL field if no cameras are detected.
 *
 * Step 2 · Safety Zones
 *   Loads a live snapshot from the selected camera and lets the user
 *   draw polygon zones (ZoneCanvas). Saves to zones.json on completion.
 *
 * Step 3 · Done
 *   Shows the pipeline command to copy-paste, plus a summary.
 */
import { useEffect, useState } from "react";
import type { CameraInfo } from "./api";
import { fetchCameras, fetchCameraSnapshot, saveZones } from "./api";
import type { DrawnZone } from "./ZoneCanvas";
import { ZoneCanvas } from "./ZoneCanvas";

// ── Types ─────────────────────────────────────────────────────────────────────

type Step = "cameras" | "zones" | "done";

// ── Main wizard ───────────────────────────────────────────────────────────────

interface Props {
  onDone: () => void;
}

export function SetupWizard({ onDone }: Props) {
  const [step,           setStep]           = useState<Step>("cameras");
  const [cameras,        setCameras]        = useState<CameraInfo[]>([]);
  const [loadingCameras, setLoadingCameras] = useState(true);
  // Selected source: camera index (number) or custom string ("rtsp://…", "path/to/file.mp4")
  const [source,         setSource]         = useState<number | string | null>(null);
  const [customSource,   setCustomSource]   = useState("");
  const [snapshotUrl,    setSnapshotUrl]    = useState<string | null>(null);
  const [loadingSnap,    setLoadingSnap]    = useState(false);
  const [zones,          setZones]          = useState<DrawnZone[]>([]);
  const [saving,         setSaving]         = useState(false);
  const [copied,         setCopied]         = useState(false);

  // Probe cameras on mount
  useEffect(() => {
    fetchCameras()
      .then((cams) => {
        setCameras(cams);
        if (cams.length > 0) setSource(cams[0].index);
      })
      .catch(() => {})
      .finally(() => setLoadingCameras(false));
  }, []);

  // Load snapshot when advancing to the zones step
  function goToZones() {
    if (typeof source === "number") {
      setLoadingSnap(true);
      fetchCameraSnapshot(source)
        .then((url) => { setSnapshotUrl(url); setLoadingSnap(false); })
        .catch(() => setLoadingSnap(false));
    }
    setStep("zones");
  }

  async function finish() {
    setSaving(true);
    try {
      await saveZones({
        required_ppe: ["hardhat", "vest"],
        zones: zones.map((z) => ({
          id:           z.id,
          name:         z.name,
          polygon:      z.points,
          rule:         z.rule,
          ...(z.rule === "require_ppe" ? { required_ppe: z.required_ppe } : {}),
        })),
      });
      localStorage.setItem("safesight_setup_done", "1");
      setStep("done");
    } catch {
      setSaving(false);
    }
  }

  const activeSource = typeof source === "number" ? source : customSource.trim() || null;
  const runCommand   = `python -m src.pipeline --source ${activeSource ?? 0} --model models/safesight-ppe.pt`;

  function copyCommand() {
    navigator.clipboard.writeText(runCommand).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  // ── Layout ──────────────────────────────────────────────────────────────────
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(10,10,20,0.82)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 200, padding: 16,
    }}>
      <div style={{
        background: "#fff", borderRadius: 14,
        width: "100%", maxWidth: step === "zones" ? 900 : 680,
        maxHeight: "94vh", display: "flex", flexDirection: "column",
        overflow: "hidden", boxShadow: "0 24px 64px rgba(0,0,0,.5)",
      }}>
        {/* Header */}
        <div style={{
          padding: "20px 28px 16px",
          background: "#1a1a2e", color: "#fff",
          borderRadius: "14px 14px 0 0",
        }}>
          <div style={{ fontWeight: 800, fontSize: 20, letterSpacing: 0.3 }}>
            SafeSight AI Setup
          </div>
          <StepBar current={step} />
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
          {step === "cameras" && (
            <CameraStep
              cameras={cameras}
              loading={loadingCameras}
              source={source}
              setSource={setSource}
              customSource={customSource}
              setCustomSource={setCustomSource}
            />
          )}
          {step === "zones" && (
            <ZoneStep
              snapshotUrl={snapshotUrl}
              loadingSnap={loadingSnap}
              zones={zones}
              setZones={setZones}
            />
          )}
          {step === "done" && (
            <DoneStep
              source={activeSource}
              zones={zones}
              runCommand={runCommand}
              copied={copied}
              onCopy={copyCommand}
            />
          )}
        </div>

        {/* Footer buttons */}
        <div style={{
          padding: "14px 28px",
          borderTop: "1px solid #e5e7eb",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          background: "#fafafa",
          borderRadius: "0 0 14px 14px",
        }}>
          <div>
            {step === "zones" && (
              <button onClick={() => setStep("cameras")} style={ghostBtn}>
                ← Back
              </button>
            )}
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {step === "cameras" && (
              <>
                <button onClick={() => { setStep("done"); localStorage.setItem("safesight_setup_done", "1"); }} style={ghostBtn}>
                  Skip setup
                </button>
                <button
                  onClick={goToZones}
                  disabled={!source && !customSource.trim()}
                  style={primaryBtn(!!source || !!customSource.trim())}
                >
                  Continue →
                </button>
              </>
            )}
            {step === "zones" && (
              <>
                <button onClick={() => { finish(); }} disabled={saving} style={primaryBtn(!saving)}>
                  {saving ? "Saving…" : zones.length === 0 ? "Save & Continue →" : `Save ${zones.length} zone${zones.length > 1 ? "s" : ""} →`}
                </button>
              </>
            )}
            {step === "done" && (
              <button onClick={onDone} style={primaryBtn(true)}>
                Open Dashboard →
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Step 1: Camera selection ──────────────────────────────────────────────────

function CameraStep({
  cameras, loading, source, setSource, customSource, setCustomSource,
}: {
  cameras: CameraInfo[];
  loading: boolean;
  source: number | string | null;
  setSource: (s: number | string | null) => void;
  customSource: string;
  setCustomSource: (s: string) => void;
}) {
  return (
    <div>
      <h2 style={h2}>Which camera should SafeSight monitor?</h2>
      <p style={sub}>
        SafeSight will watch this feed in real time and alert you to safety violations.
      </p>

      {loading ? (
        <div style={{ textAlign: "center", padding: "40px 0", color: "#9ca3af", fontSize: 14 }}>
          <Spinner />
          <div style={{ marginTop: 12 }}>Detecting cameras…</div>
        </div>
      ) : cameras.length === 0 ? (
        <div style={{
          padding: "20px", background: "#fff7ed", borderRadius: 8,
          border: "1px solid #fed7aa", marginBottom: 16,
        }}>
          <div style={{ fontWeight: 600, color: "#c2410c", marginBottom: 4 }}>No cameras detected</div>
          <div style={{ fontSize: 13, color: "#78350f" }}>
            Make sure a webcam is connected, or enter a file path / RTSP URL below.
          </div>
        </div>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
          gap: 12, marginBottom: 20,
        }}>
          {cameras.map((cam) => (
            <CameraCard
              key={cam.index}
              camera={cam}
              selected={source === cam.index}
              onSelect={() => setSource(cam.index)}
            />
          ))}
        </div>
      )}

      {/* Custom source input */}
      <div style={{
        padding: "14px 16px", background: "#f8fafc", borderRadius: 8,
        border: "1px solid #e2e8f0",
      }}>
        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
          Or enter a custom source
        </div>
        <input
          type="text"
          placeholder="rtsp://192.168.1.64/stream1  or  data/input_videos/site.mp4"
          value={customSource}
          onChange={(e) => {
            setCustomSource(e.target.value);
            if (e.target.value.trim()) setSource(e.target.value.trim());
          }}
          style={{
            width: "100%", padding: "8px 12px", borderRadius: 6,
            border: "1px solid #d1d5db", fontSize: 13, boxSizing: "border-box",
          }}
        />
        <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
          Supports webcam index (0, 1…), RTSP streams, and local video files
        </div>
      </div>
    </div>
  );
}

function CameraCard({
  camera, selected, onSelect,
}: {
  camera: CameraInfo;
  selected: boolean;
  onSelect: () => void;
}) {
  const [thumb, setThumb] = useState<string | null>(null);

  useEffect(() => {
    fetchCameraSnapshot(camera.index)
      .then(setThumb)
      .catch(() => {});
  }, [camera.index]);

  return (
    <div
      onClick={onSelect}
      style={{
        borderRadius: 8, overflow: "hidden", cursor: "pointer", position: "relative",
        border: selected ? "2.5px solid #3b82f6" : "2px solid #e5e7eb",
        boxShadow: selected ? "0 0 0 3px #bfdbfe" : "none",
        transition: "border .15s, box-shadow .15s",
      }}
    >
      {/* Thumbnail */}
      <div style={{ aspectRatio: "16/9", background: "#1e293b", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {thumb
          ? <img src={thumb} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} alt={camera.label} />
          : <Spinner />
        }
      </div>
      {/* Label */}
      <div style={{ padding: "8px 10px", background: "#fff" }}>
        <div style={{ fontWeight: 700, fontSize: 13 }}>{camera.label}</div>
        <div style={{ fontSize: 11, color: "#9ca3af" }}>{camera.width}×{camera.height}</div>
      </div>
      {/* Selected tick */}
      {selected && (
        <div style={{
          position: "absolute", top: 8, right: 8,
          width: 22, height: 22, borderRadius: "50%",
          background: "#3b82f6", color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, fontWeight: 700,
        }}>
          ✓
        </div>
      )}
    </div>
  );
}

// ── Step 2: Zone drawing ──────────────────────────────────────────────────────

function ZoneStep({
  snapshotUrl, loadingSnap, zones, setZones,
}: {
  snapshotUrl: string | null;
  loadingSnap: boolean;
  zones: DrawnZone[];
  setZones: (z: DrawnZone[]) => void;
}) {
  return (
    <div>
      <h2 style={h2}>Draw safety zones  <span style={{ fontWeight: 400, color: "#9ca3af" }}>(optional)</span></h2>
      <p style={sub}>
        Paint areas on the camera view. SafeSight will alert when someone enters a
        <strong style={{ color: "#ef4444" }}> No Entry</strong> zone, or enters a
        <strong style={{ color: "#f59e0b" }}> PPE Required</strong> zone without the right gear.
        Workers anywhere on site without a hardhat or vest are always flagged.
      </p>
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr",
        gap: 10, marginBottom: 18,
      }}>
        {[
          { icon: "🚫", color: "#ef4444", title: "No Entry", desc: "Even with full PPE — triggers CRITICAL alert for anyone inside" },
          { icon: "⚠️", color: "#f59e0b", title: "Require PPE", desc: "Alert if a worker enters without the required gear for that area" },
          { icon: "👷", color: "#3b82f6", title: "Global (no zone needed)", desc: "Any person on site without hardhat + vest is always warned" },
        ].map((t) => (
          <div key={t.title} style={{ padding: "10px 12px", background: "#f9fafb", borderRadius: 7, borderLeft: `3px solid ${t.color}` }}>
            <div style={{ fontWeight: 700, fontSize: 13 }}>{t.icon} {t.title}</div>
            <div style={{ fontSize: 11, color: "#6b7280", marginTop: 3 }}>{t.desc}</div>
          </div>
        ))}
      </div>

      {loadingSnap ? (
        <div style={{ textAlign: "center", padding: "60px 0", color: "#9ca3af" }}>
          <Spinner />
          <div style={{ marginTop: 12, fontSize: 13 }}>Loading camera snapshot…</div>
        </div>
      ) : snapshotUrl ? (
        <ZoneCanvas imageUrl={snapshotUrl} zones={zones} onZonesChange={setZones} />
      ) : (
        <div style={{
          padding: "40px", textAlign: "center", background: "#f8fafc",
          borderRadius: 8, border: "2px dashed #e2e8f0", color: "#94a3b8",
        }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📷</div>
          <div style={{ fontSize: 14 }}>Camera snapshot unavailable</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>
            You can still draw zones later using the Zone Editor in the dashboard.
          </div>
        </div>
      )}
    </div>
  );
}

// ── Step 3: Done ──────────────────────────────────────────────────────────────

function DoneStep({
  source, zones, runCommand, copied, onCopy,
}: {
  source: number | string | null;
  zones: DrawnZone[];
  runCommand: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div>
      <div style={{ textAlign: "center", paddingTop: 8, paddingBottom: 24 }}>
        <div style={{ fontSize: 52 }}>🎉</div>
        <h2 style={{ ...h2, textAlign: "center", marginTop: 8 }}>You're all set!</h2>
        <p style={{ ...sub, textAlign: "center" }}>
          SafeSight is configured and ready to monitor your site.
        </p>
      </div>

      {/* Summary chips */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 24, justifyContent: "center" }}>
        <Chip label="Camera" value={source !== null ? String(source) : "—"} color="#3b82f6" />
        <Chip label="Zones" value={String(zones.length)} color={zones.length > 0 ? "#059669" : "#9ca3af"} />
        <Chip label="Global PPE" value="hardhat + vest" color="#7c3aed" />
        <Chip
          label="Civilians (no PPE)"
          value="⚡ ALERTED"
          color="#ef4444"
        />
      </div>

      {/* Run command */}
      <div style={{
        background: "#0f172a", borderRadius: 8, padding: "14px 16px",
        marginBottom: 20,
      }}>
        <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontWeight: 600, letterSpacing: 0.5 }}>
          START THE PIPELINE — run this in your terminal:
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <code style={{
            flex: 1, color: "#7dd3fc", fontSize: 13, fontFamily: "monospace",
            wordBreak: "break-all",
          }}>
            {runCommand}
          </code>
          <button
            onClick={onCopy}
            style={{
              padding: "5px 12px", borderRadius: 5, border: "1px solid #334155",
              background: copied ? "#059669" : "#1e293b", color: "#fff",
              fontSize: 12, cursor: "pointer", fontWeight: 600, whiteSpace: "nowrap",
            }}
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>

      <div style={{
        padding: "12px 16px", background: "#eff6ff", borderRadius: 8,
        border: "1px solid #bfdbfe", fontSize: 13, color: "#1d4ed8",
      }}>
        💡 The dashboard updates live — keep it open while the pipeline runs in your terminal.
        You can edit zones any time via the <strong>Edit Zones</strong> button in the header.
      </div>
    </div>
  );
}

// ── Misc sub-components ───────────────────────────────────────────────────────

function StepBar({ current }: { current: Step }) {
  const steps: { key: Step; label: string }[] = [
    { key: "cameras", label: "1  Cameras" },
    { key: "zones",   label: "2  Zones"   },
    { key: "done",    label: "3  Done"    },
  ];
  const idx = steps.findIndex((s) => s.key === current);
  return (
    <div style={{ display: "flex", gap: 0, marginTop: 14, alignItems: "center" }}>
      {steps.map((s, i) => (
        <div key={s.key} style={{ display: "flex", alignItems: "center" }}>
          <div style={{
            padding: "3px 12px", borderRadius: 20, fontSize: 12, fontWeight: 600,
            background: i === idx ? "#3b82f6" : i < idx ? "#1e3a5f" : "#2d2d4e",
            color: i === idx ? "#fff" : i < idx ? "#93c5fd" : "#64748b",
          }}>
            {i < idx ? "✓ " : ""}{s.label}
          </div>
          {i < steps.length - 1 && (
            <div style={{ width: 20, height: 1, background: i < idx ? "#3b82f6" : "#2d2d4e" }} />
          )}
        </div>
      ))}
    </div>
  );
}

function Chip({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ textAlign: "center", minWidth: 90, padding: "6px 14px", background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
      <div style={{ fontWeight: 700, fontSize: 15, color }}>{value}</div>
      <div style={{ fontSize: 10, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5, marginTop: 2 }}>{label}</div>
    </div>
  );
}

function Spinner() {
  return (
    <div style={{
      width: 28, height: 28, border: "3px solid #e2e8f0",
      borderTopColor: "#3b82f6", borderRadius: "50%",
      animation: "spin 0.7s linear infinite", margin: "0 auto",
    }} />
  );
}

// ── Shared styles ─────────────────────────────────────────────────────────────

const h2: React.CSSProperties = {
  fontSize: 20, fontWeight: 700, margin: "0 0 6px", color: "#0f172a",
};
const sub: React.CSSProperties = {
  fontSize: 14, color: "#64748b", margin: "0 0 20px", lineHeight: 1.6,
};
const ghostBtn: React.CSSProperties = {
  padding: "8px 16px", borderRadius: 7, border: "1px solid #d1d5db",
  background: "#fff", color: "#374151", fontSize: 13, fontWeight: 600, cursor: "pointer",
};
function primaryBtn(enabled: boolean): React.CSSProperties {
  return {
    padding: "9px 22px", borderRadius: 7, border: "none",
    background: enabled ? "#3b82f6" : "#93c5fd",
    color: "#fff", fontSize: 13, fontWeight: 700,
    cursor: enabled ? "pointer" : "not-allowed",
    opacity: enabled ? 1 : 0.7,
  };
}
