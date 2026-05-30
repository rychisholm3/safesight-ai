/**
 * SetupWizard — friendly 3-step onboarding shown on first login.
 *
 * Step 1 · Pick a source
 *   Shows detected webcams AND video files in data/input_videos/.
 *   Each card has a live thumbnail.  Falls back to a manual URL field.
 *
 * Step 2 · Draw safety zones
 *   Loads a snapshot from the chosen source.  Uses ZoneCanvas for
 *   interactive polygon drawing with step-by-step in-canvas guidance.
 *
 * Step 3 · Ready!
 *   Summary + copy-able pipeline run command.
 *
 * Re-opens any time via the ⚙ Setup button in the dashboard header.
 */
import { useEffect, useState } from "react";
import type { CameraInfo, VideoFileInfo } from "./api";
import { fetchCameras, fetchCameraSnapshot, fetchVideoFiles, fetchVideoSnapshot, saveZones } from "./api";
import type { DrawnZone } from "./ZoneCanvas";
import { ZoneCanvas } from "./ZoneCanvas";

// ── Types ─────────────────────────────────────────────────────────────────────

type Step = "source" | "zones" | "done";

interface SourceOption {
  kind: "camera" | "video";
  label: string;
  id: string;          // camera index (as string) or file path
  meta: string;        // "1920×1080" or "15.6 s"
}

// ── Main wizard ───────────────────────────────────────────────────────────────

export function SetupWizard({ onDone }: { onDone: () => void }) {
  const [step,        setStep]        = useState<Step>("source");
  const [sources,     setSources]     = useState<SourceOption[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [selected,    setSelected]    = useState<SourceOption | null>(null);
  const [customSrc,   setCustomSrc]   = useState("");
  const [snapshotUrl, setSnapshotUrl] = useState<string | null>(null);
  const [loadingSnap, setLoadingSnap] = useState(false);
  const [snapError,   setSnapError]   = useState(false);
  const [zones,       setZones]       = useState<DrawnZone[]>([]);
  const [saving,      setSaving]      = useState(false);
  const [saveError,   setSaveError]   = useState(false);
  const [copied,      setCopied]      = useState(false);

  // Load cameras + video files in parallel
  useEffect(() => {
    Promise.allSettled([fetchCameras(), fetchVideoFiles()])
      .then(([cams, vids]) => {
        const opts: SourceOption[] = [];
        if (cams.status === "fulfilled") {
          cams.value.forEach((c: CameraInfo) =>
            opts.push({ kind: "camera", id: String(c.index), label: c.label, meta: `${c.width}×${c.height}` })
          );
        }
        if (vids.status === "fulfilled") {
          vids.value.forEach((v: VideoFileInfo) =>
            opts.push({ kind: "video", id: v.path, label: v.name, meta: `${v.duration_s}s video` })
          );
        }
        setSources(opts);
        if (opts.length > 0) setSelected(opts[0]);
      })
      .finally(() => setLoading(false));
  }, []);

  // Fetch snapshot when advancing to zones step
  function goToZones() {
    setStep("zones");
    setSnapError(false);
    const src = selected ?? (customSrc.trim() ? { kind: "video" as const, id: customSrc.trim(), label: customSrc, meta: "" } : null);
    if (!src) return;
    setLoadingSnap(true);
    const p = src.kind === "camera"
      ? fetchCameraSnapshot(Number(src.id))
      : fetchVideoSnapshot(src.id);
    p.then(url => { setSnapshotUrl(url); setLoadingSnap(false); })
     .catch(() => { setSnapError(true); setLoadingSnap(false); });
  }

  async function finish() {
    setSaving(true); setSaveError(false);
    try {
      await saveZones({
        required_ppe: ["hardhat", "vest"],
        zones: zones.map(z => ({
          id: z.id, name: z.name, polygon: z.points, rule: z.rule,
          ...(z.rule === "require_ppe" ? { required_ppe: z.required_ppe } : {}),
        })),
      });
      localStorage.setItem("safesight_setup_done", "1");
      setStep("done");
    } catch {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  }

  function skipAndClose() {
    localStorage.setItem("safesight_setup_done", "1");
    onDone();
  }

  const activeId = selected?.id ?? customSrc.trim();
  const runCmd   = `python -m src.pipeline --source ${activeId || "0"} --model models/safesight-ppe.pt`;

  function copyCmd() {
    navigator.clipboard.writeText(runCmd).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2500); });
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(5,5,20,0.85)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 200, padding: 16, overflowY: "auto",
    }}>
      <div style={{
        background: "#fff", borderRadius: 16, width: "100%",
        maxWidth: step === "zones" ? 920 : 700,
        display: "flex", flexDirection: "column",
        boxShadow: "0 32px 80px rgba(0,0,0,.55)",
        maxHeight: "95vh", overflow: "hidden",
      }}>
        {/* ── Header ── */}
        <div style={{ background: "#1a1a2e", color: "#fff", padding: "22px 28px 18px", borderRadius: "16px 16px 0 0" }}>
          <div style={{ fontWeight: 800, fontSize: 18, letterSpacing: 0.3, marginBottom: 14 }}>
            SafeSight AI &nbsp;·&nbsp; Setup
          </div>
          <StepBar step={step} />
        </div>

        {/* ── Body ── */}
        <div style={{ flex: 1, overflowY: "auto", padding: "28px 28px 8px" }}>
          {step === "source" && (
            <SourceStep
              sources={sources} loading={loading}
              selected={selected} setSelected={setSelected}
              customSrc={customSrc} setCustomSrc={v => { setCustomSrc(v); setSelected(null); }}
            />
          )}
          {step === "zones" && (
            <ZonesStep
              snapshotUrl={snapshotUrl} loadingSnap={loadingSnap} snapError={snapError}
              zones={zones} setZones={setZones}
            />
          )}
          {step === "done" && (
            <DoneStep
              activeId={activeId} zones={zones}
              runCmd={runCmd} copied={copied} onCopy={copyCmd}
            />
          )}
        </div>

        {/* ── Footer ── */}
        <div style={{
          padding: "14px 28px", borderTop: "1px solid #e5e7eb",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          background: "#fafafa", borderRadius: "0 0 16px 16px", gap: 10,
        }}>
          {/* Left */}
          <div>
            {step === "zones" && (
              <button onClick={() => setStep("source")} style={GHOST_BTN}>← Back</button>
            )}
            {step === "source" && (
              <button onClick={skipAndClose} style={{ ...GHOST_BTN, color: "#9ca3af" }}>Skip setup</button>
            )}
          </div>
          {/* Right */}
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {saveError && <span style={{ fontSize: 12, color: "#dc2626" }}>Save failed — is the API running?</span>}
            {step === "source" && (
              <button
                onClick={goToZones}
                disabled={!activeId}
                style={PRIMARY_BTN(!!activeId)}
              >
                Next: Draw safety zones →
              </button>
            )}
            {step === "zones" && (
              <>
                <button onClick={() => { finish(); }} disabled={saving} style={PRIMARY_BTN(!saving)}>
                  {saving ? "Saving…" : zones.length === 0 ? "Save & finish →" : `Save ${zones.length} zone${zones.length > 1 ? "s" : ""} & finish →`}
                </button>
              </>
            )}
            {step === "done" && (
              <button onClick={onDone} style={PRIMARY_BTN(true)}>Open Dashboard →</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Step 1: Source selection ──────────────────────────────────────────────────

function SourceStep({
  sources, loading, selected, setSelected, customSrc, setCustomSrc,
}: {
  sources: SourceOption[];
  loading: boolean;
  selected: SourceOption | null;
  setSelected: (s: SourceOption) => void;
  customSrc: string;
  setCustomSrc: (v: string) => void;
}) {
  const cameras = sources.filter(s => s.kind === "camera");
  const videos  = sources.filter(s => s.kind === "video");

  return (
    <div>
      <H2>👋 Welcome! Let's get SafeSight watching your site.</H2>
      <P>
        First, pick what SafeSight should analyze. It will watch this feed in real time
        and alert you whenever someone is missing safety gear or enters a restricted area.
      </P>

      {loading ? (
        <div style={CENTER_LOADER}>
          <Spinner /> <div style={{ marginTop: 12, color: "#94a3b8", fontSize: 13 }}>Looking for cameras and videos…</div>
        </div>
      ) : (
        <>
          {/* Cameras */}
          {cameras.length > 0 && (
            <section style={{ marginBottom: 22 }}>
              <SectionLabel icon="🎥" title="Live Cameras" desc="Feeds from webcams connected to this computer" />
              <SourceGrid sources={cameras} selected={selected} onSelect={setSelected} kind="camera" />
            </section>
          )}

          {/* Video files */}
          {videos.length > 0 && (
            <section style={{ marginBottom: 22 }}>
              <SectionLabel icon="📁" title="Test Videos" desc="Video files found in data/input_videos/ — great for testing" />
              <SourceGrid sources={videos} selected={selected} onSelect={setSelected} kind="video" />
            </section>
          )}

          {cameras.length === 0 && videos.length === 0 && (
            <div style={{
              padding: "18px 20px", background: "#fff7ed", borderRadius: 8,
              border: "1px solid #fed7aa", marginBottom: 20,
            }}>
              <div style={{ fontWeight: 700, color: "#c2410c", marginBottom: 4 }}>No cameras or video files found</div>
              <div style={{ fontSize: 13, color: "#78350f" }}>
                Connect a webcam or add a .mp4 file to <code>data/input_videos/</code>, then use the field below.
              </div>
            </div>
          )}

          {/* Custom / RTSP */}
          <div style={{
            padding: "16px 18px", background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0",
          }}>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>
              Or enter a custom source
            </div>
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
              Works with RTSP streams, IP cameras, webcam indexes (0, 1, 2…), and full file paths.
            </div>
            <input
              type="text"
              placeholder="rtsp://192.168.1.64/stream1   or   data/input_videos/site.mp4   or   0"
              value={customSrc}
              onChange={e => setCustomSrc(e.target.value)}
              style={{
                width: "100%", padding: "9px 12px", borderRadius: 7,
                border: `1px solid ${customSrc.trim() ? "#3b82f6" : "#d1d5db"}`,
                fontSize: 13, boxSizing: "border-box",
                outline: customSrc.trim() ? "2px solid #bfdbfe" : "none",
              }}
            />
          </div>
        </>
      )}
    </div>
  );
}

function SectionLabel({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
      <span style={{ fontSize: 16 }}>{icon}</span>
      <span style={{ fontWeight: 700, fontSize: 14 }}>{title}</span>
      <span style={{ fontSize: 12, color: "#94a3b8" }}>— {desc}</span>
    </div>
  );
}

function SourceGrid({ sources, selected, onSelect, kind }: {
  sources: SourceOption[];
  selected: SourceOption | null;
  onSelect: (s: SourceOption) => void;
  kind: "camera" | "video";
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: 12 }}>
      {sources.map(src => (
        <SourceCard key={src.id} source={src} selected={selected?.id === src.id} onSelect={() => onSelect(src)} kind={kind} />
      ))}
    </div>
  );
}

function SourceCard({ source, selected, onSelect, kind }: {
  source: SourceOption; selected: boolean; onSelect: () => void; kind: "camera" | "video";
}) {
  const [thumb, setThumb] = useState<string | null>(null);
  const [thumbErr, setThumbErr] = useState(false);

  useEffect(() => {
    const p = kind === "camera"
      ? fetchCameraSnapshot(Number(source.id))
      : fetchVideoSnapshot(source.id);
    p.then(setThumb).catch(() => setThumbErr(true));
  }, [source.id, kind]);

  return (
    <div
      onClick={onSelect}
      style={{
        borderRadius: 10, overflow: "hidden", cursor: "pointer", position: "relative",
        border: selected ? "2.5px solid #3b82f6" : "2px solid #e5e7eb",
        boxShadow: selected ? "0 0 0 3px #bfdbfe" : "0 1px 3px rgba(0,0,0,.08)",
        transition: "border .15s, box-shadow .15s",
        userSelect: "none",
      }}
    >
      {/* Thumbnail */}
      <div style={{ aspectRatio: "16/9", background: "#1e293b", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {thumb
          ? <img src={thumb} style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} alt={source.label} />
          : thumbErr
            ? <span style={{ fontSize: 28 }}>{kind === "camera" ? "📷" : "🎬"}</span>
            : <Spinner />
        }
      </div>
      {/* Label */}
      <div style={{ padding: "8px 10px", background: "#fff" }}>
        <div style={{ fontWeight: 700, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {kind === "video" ? "📹 " : "🎥 "}{source.label}
        </div>
        <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 1 }}>{source.meta}</div>
      </div>
      {/* Check badge */}
      {selected && (
        <div style={{
          position: "absolute", top: 8, right: 8,
          width: 22, height: 22, borderRadius: "50%",
          background: "#3b82f6", color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, fontWeight: 800,
        }}>✓</div>
      )}
    </div>
  );
}

// ── Step 2: Zone drawing ──────────────────────────────────────────────────────

function ZonesStep({ snapshotUrl, loadingSnap, snapError, zones, setZones }: {
  snapshotUrl: string | null; loadingSnap: boolean; snapError: boolean;
  zones: DrawnZone[]; setZones: (z: DrawnZone[]) => void;
}) {
  return (
    <div>
      <H2>Mark your safety zones <Muted>(optional but recommended)</Muted></H2>
      <P>
        Zones let you draw custom boundaries on the camera view. Zones are in addition
        to the default rule — <strong>every person without a hardhat or vest is always flagged</strong>,
        whether inside a zone or not.
      </P>

      {/* Zone type explainer */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 20 }}>
        {[
          { icon: "🚫", color: "#ef4444", title: "No Entry", rule: "no_entry", desc: "Anyone inside triggers a CRITICAL alert — even with full PPE. Good for dangerous machinery areas." },
          { icon: "⚠️", color: "#f59e0b", title: "Require PPE", rule: "require_ppe", desc: "Alert only if the worker is missing specific gear. Good for zones needing extra protection." },
          { icon: "👷", color: "#3b82f6", title: "Site-wide (automatic)", rule: null, desc: "No zone needed. Every person detected without hardhat + vest is warned automatically." },
        ].map(t => (
          <div key={t.title} style={{ padding: "10px 12px", background: "#f9fafb", borderRadius: 7, borderLeft: `3px solid ${t.color}` }}>
            <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 3 }}>{t.icon} {t.title}</div>
            <div style={{ fontSize: 11, color: "#6b7280", lineHeight: 1.5 }}>{t.desc}</div>
          </div>
        ))}
      </div>

      {loadingSnap ? (
        <div style={CENTER_LOADER}>
          <Spinner />
          <div style={{ marginTop: 12, color: "#94a3b8", fontSize: 13 }}>Loading camera view…</div>
        </div>
      ) : snapError || !snapshotUrl ? (
        <div style={{
          padding: "32px", textAlign: "center", background: "#f8fafc",
          borderRadius: 8, border: "2px dashed #e2e8f0",
        }}>
          <div style={{ fontSize: 32, marginBottom: 10 }}>📷</div>
          <div style={{ fontWeight: 600, fontSize: 14, color: "#374151" }}>Snapshot unavailable</div>
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
            You can draw zones later using the <strong>Edit Zones</strong> button in the dashboard header.
          </div>
        </div>
      ) : (
        <ZoneCanvas imageUrl={snapshotUrl} zones={zones} onZonesChange={setZones} />
      )}
    </div>
  );
}

// ── Step 3: Done ──────────────────────────────────────────────────────────────

function DoneStep({ activeId, zones, runCmd, copied, onCopy }: {
  activeId: string; zones: DrawnZone[];
  runCmd: string; copied: boolean; onCopy: () => void;
}) {
  return (
    <div>
      <div style={{ textAlign: "center", padding: "4px 0 20px" }}>
        <div style={{ fontSize: 48 }}>🎉</div>
        <H2 style={{ textAlign: "center", marginTop: 10 }}>SafeSight is configured!</H2>
        <P style={{ textAlign: "center" }}>
          Here's everything that's set up and ready to go.
        </P>
      </div>

      {/* Summary */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 24 }}>
        {[
          { icon: "🎥", label: "Monitoring source", value: activeId || "—", ok: !!activeId },
          { icon: "🗺️", label: "Safety zones", value: zones.length === 0 ? "None (can add later)" : `${zones.length} zone${zones.length > 1 ? "s" : ""}`, ok: true },
          { icon: "👷", label: "Hardhat + vest", value: "Required everywhere", ok: true },
          { icon: "🚨", label: "Civilians (no PPE)", value: "Automatically alerted", ok: true },
        ].map(row => (
          <div key={row.label} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 14px", background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb",
          }}>
            <span style={{ fontSize: 20 }}>{row.icon}</span>
            <div>
              <div style={{ fontSize: 10, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>{row.label}</div>
              <div style={{ fontWeight: 700, fontSize: 13, color: row.ok ? "#1f2937" : "#ef4444" }}>{row.value}</div>
            </div>
            <span style={{ marginLeft: "auto", fontSize: 16 }}>{row.ok ? "✅" : "⚠️"}</span>
          </div>
        ))}
      </div>

      {/* Run command */}
      <div style={{ background: "#0f172a", borderRadius: 10, padding: "14px 18px", marginBottom: 18 }}>
        <div style={{ fontSize: 11, color: "#475569", fontWeight: 700, letterSpacing: 0.6, marginBottom: 8 }}>
          STEP 1 — Paste this in your terminal to start monitoring:
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <code style={{ flex: 1, color: "#7dd3fc", fontSize: 13, fontFamily: "monospace", wordBreak: "break-all" }}>
            {runCmd}
          </code>
          <button
            onClick={onCopy}
            style={{
              padding: "6px 14px", borderRadius: 6, border: "1px solid #334155",
              background: copied ? "#059669" : "#1e293b", color: "#fff",
              fontSize: 12, cursor: "pointer", fontWeight: 700, whiteSpace: "nowrap",
              transition: "background .2s",
            }}
          >
            {copied ? "✓ Copied!" : "Copy"}
          </button>
        </div>
      </div>

      <div style={{
        padding: "12px 16px", background: "#eff6ff", borderRadius: 8,
        border: "1px solid #bfdbfe", fontSize: 13, color: "#1d4ed8", lineHeight: 1.6,
      }}>
        <strong>Step 2</strong> — Keep this browser tab open. The dashboard updates live
        as the pipeline runs and will show every violation with a snapshot and timestamp.
        <br />
        <span style={{ color: "#3b82f6" }}>
          You can edit or add zones at any time using the <strong>Edit Zones</strong> button in the header.
        </span>
      </div>
    </div>
  );
}

// ── Shared UI atoms ───────────────────────────────────────────────────────────

function StepBar({ step }: { step: Step }) {
  const steps: { key: Step; label: string; num: number }[] = [
    { key: "source", label: "Choose source", num: 1 },
    { key: "zones",  label: "Draw zones",    num: 2 },
    { key: "done",   label: "Ready",         num: 3 },
  ];
  const idx = steps.findIndex(s => s.key === step);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
      {steps.map((s, i) => (
        <div key={s.key} style={{ display: "flex", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6,
            padding: "4px 12px", borderRadius: 20, fontSize: 12, fontWeight: 600,
            background: i === idx ? "#3b82f6" : i < idx ? "#1e3a5f" : "#2d2d4e",
            color: i === idx ? "#fff" : i < idx ? "#93c5fd" : "#475569",
          }}>
            <span style={{
              width: 18, height: 18, borderRadius: "50%", display: "inline-flex",
              alignItems: "center", justifyContent: "center",
              background: i === idx ? "#fff" : i < idx ? "#3b82f6" : "#374151",
              color: i === idx ? "#3b82f6" : i < idx ? "#fff" : "#9ca3af",
              fontSize: 10, fontWeight: 800,
            }}>
              {i < idx ? "✓" : s.num}
            </span>
            {s.label}
          </div>
          {i < steps.length - 1 && (
            <div style={{ width: 20, height: 2, background: i < idx ? "#3b82f6" : "#2d2d4e", margin: "0 -1px" }} />
          )}
        </div>
      ))}
    </div>
  );
}

function Spinner() {
  return (
    <div style={{ width: 28, height: 28, border: "3px solid #e2e8f0",
      borderTopColor: "#3b82f6", borderRadius: "50%",
      animation: "spin 0.7s linear infinite", margin: "0 auto" }} />
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span style={{ fontWeight: 400, color: "#94a3b8", fontSize: 16 }}>{children}</span>;
}

function H2({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <h2 style={{ fontSize: 20, fontWeight: 800, margin: "0 0 6px", color: "#0f172a", ...style }}>{children}</h2>;
}

function P({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <p style={{ fontSize: 14, color: "#64748b", margin: "0 0 20px", lineHeight: 1.65, ...style }}>{children}</p>;
}

const CENTER_LOADER: React.CSSProperties = { textAlign: "center", padding: "48px 0" };

const GHOST_BTN: React.CSSProperties = {
  padding: "8px 18px", borderRadius: 8, border: "1px solid #d1d5db",
  background: "#fff", color: "#374151", fontSize: 13, fontWeight: 600, cursor: "pointer",
};

function PRIMARY_BTN(enabled: boolean): React.CSSProperties {
  return {
    padding: "10px 24px", borderRadius: 8, border: "none",
    background: enabled ? "#3b82f6" : "#93c5fd",
    color: "#fff", fontSize: 13, fontWeight: 700,
    cursor: enabled ? "pointer" : "not-allowed",
    transition: "background .15s",
  };
}
