/**
 * EventDetail — full violation detail modal with OSHA regulation cards,
 * industry resolution context, and supervisor escalation recommendations.
 */
import { useEffect, useState } from "react";
import type { SafeEvent } from "./types";
import { fetchOshaLookup } from "./api";
import type { OshaCode } from "./api";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ── Static enrichment data ────────────────────────────────────────────────────

interface ResolutionContext {
  howResolved: string;
  typicalTimeToResolve: string;
  supervisorAction: string;
  escalationTrigger: string;
}

function getResolutionContext(event: SafeEvent): ResolutionContext {
  const isPpe = event.event_type === "missing_ppe";
  const firstPpe = event.missing_ppe[0] ?? "";

  if (!isPpe) {
    // Zone intrusion
    if (event.zone_rule === "no_entry" || !event.zone_rule) {
      return {
        howResolved:
          "Sites that eliminated unauthorised zone entries combined physical barriers (solid fencing or jersey barriers, not just cones) with daily pre-shift briefings showing workers a colour-coded site map. The most effective sites also implemented a buddy system where no worker enters a hazard zone alone — the second person acts as both a witness and a deterrent.",
        typicalTimeToResolve: "Immediate — barriers and signage can be installed within hours. Sustained compliance typically achieved within 1–2 weeks with consistent enforcement.",
        supervisorAction:
          event.severity === "CRITICAL"
            ? "IMMEDIATE: Stop work in the affected zone. Escort the worker out of the restricted area. Conduct a 5-minute stand-down with the full crew to clarify zone boundaries. Document the incident in the safety log today."
            : "Before the next shift: brief the crew on zone boundaries and install additional visual markers at the entry point.",
        escalationTrigger:
          "Escalate to Project Manager if: the same worker is detected again within 48 hours, or if 3+ workers have been detected in the zone within 7 days. Issue a formal written warning and consider mandatory retraining before the worker returns to site.",
      };
    }
    return {
      howResolved:
        "Zones requiring PPE are most effectively managed by making the PPE accessible at the zone boundary — a PPE station with hooks for hard hats and vests right at the entry point removes the excuse of 'I forgot.' Several sites have reduced require-PPE zone violations by 80% within a month by combining entry-point PPE stations with a 'gear up before you step in' culture enforced by supervisors.",
      typicalTimeToResolve: "Days to weeks — compliance improves rapidly once PPE stations are installed at zone boundaries and supervisors consistently enforce entry requirements.",
      supervisorAction:
        "Before next entry: install a PPE station at the zone boundary. Brief all workers on the zone's PPE requirements. Check that all required PPE is available in all sizes.",
      escalationTrigger:
        "Escalate if the same worker repeatedly enters the zone without PPE, or if PPE is not available in appropriate sizes. Document all non-compliance incidents.",
    };
  }

  // PPE violations
  const contexts: Record<string, ResolutionContext> = {
    hardhat: {
      howResolved:
        "Construction sites that achieved 100% hard hat compliance typically used three measures together: a physical 'no hat, no entry' checkpoint at site entrances enforced by a dedicated safety monitor, a high-visibility hook rack at every site access point so workers have no excuse to forget, and weekly toolbox talks with real injury case studies. Sites that tried enforcement alone without making PPE convenient saw compliance rebound within days.",
      typicalTimeToResolve:
        "24–48 hours for immediate access improvements. Sustained 100% compliance typically takes 2–4 weeks of consistent enforcement combined with positive reinforcement.",
      supervisorAction:
        event.severity === "CRITICAL"
          ? "IMMEDIATELY: Direct the worker to put on their hard hat before continuing any work. Issue a verbal warning and log it. If the worker refuses, they must leave the work area."
          : "At next walkthrough: issue a verbal reminder and ensure hard hats are accessible at the point of work. Log the observation.",
      escalationTrigger:
        "Second offence: issue a formal written warning. Third offence: mandatory retraining and notify Project Manager. Zero-tolerance policy is standard practice on most large construction sites.",
    },
    vest: {
      howResolved:
        "High-visibility vest compliance improved dramatically on sites that required crews to don PPE at the site gate before clocking in — making it part of the morning routine rather than an afterthought. Sites that stored vests at the work area (where workers arrive already on-site without them) saw lower compliance. Some sites issue colour-coded vests by trade, which also helps identify who is in which area.",
      typicalTimeToResolve:
        "Behaviour change is achievable within 1 week when the PPE routine is embedded in the site entry process rather than enforced reactively.",
      supervisorAction:
        "Today: ensure high-visibility vests are available at the site entrance and at every active work area. Brief the morning crew on the requirement before work starts.",
      escalationTrigger:
        "Escalate if a worker is repeatedly detected without a vest, especially in areas with active vehicle traffic. Document each occurrence and issue formal warnings progressively.",
    },
    mask: {
      howResolved:
        "Respiratory compliance improved on sites that made a written Respiratory Protection Program (RPP) the first item reviewed in site orientation. Sites that saw sustained compliance conducted fit testing on day one, so workers knew their assigned respirator fit correctly — ill-fitting respirators are the #1 reason workers avoid wearing them. Regular air monitoring results posted at the site office also motivated compliance by making the hazard tangible.",
      typicalTimeToResolve:
        "An RPP can be written and implemented within a week. Fit testing and training within the same week. Full sustained compliance typically takes 2–3 weeks.",
      supervisorAction:
        "Before the next shift: identify the specific respiratory hazard in the area. Confirm appropriate respirators are available and fit-tested for all workers in the area.",
      escalationTrigger:
        "Escalate to Safety Officer if workers report the available respirators don't fit, if the hazard level is uncertain, or if any worker shows symptoms (coughing, dizziness) that may indicate over-exposure.",
    },
    gloves: {
      howResolved:
        "Hand protection compliance improved most where supervisors stopped asking 'are you wearing gloves?' and started requiring gloves be put on before tools were handed out. Sites that identified specific glove grades by task (cut-resistant for rebar, chemical-resistant for solvents, heat-resistant for welding) saw far better compliance than those with a generic 'wear gloves' policy — workers are more likely to wear PPE that they understand the reason for.",
      typicalTimeToResolve:
        "Task-specific glove requirements can be documented and communicated within 1–2 days. Compliance typically improves within the first week of consistent enforcement.",
      supervisorAction:
        "Today: verify that appropriate gloves for the specific task are available at the workstation. Specify in the pre-task plan which glove grade is required for each activity.",
      escalationTrigger:
        "Escalate if no appropriate gloves are available for a specific hazardous task — work should not proceed until correct PPE is on hand.",
    },
    safety_shoes: {
      howResolved:
        "Safety footwear compliance is rarely a day-to-day enforcement issue once it's established as a site entry requirement. Sites that incorporated footwear into the initial site orientation with a clear policy — 'steel-toe boots are required, no exceptions, no exceptions for subcontractors' — experienced very few ongoing violations. Pre-employment documentation (requiring workers to confirm they own compliant footwear before their first day) is the most effective prevention measure.",
      typicalTimeToResolve:
        "Immediate once the requirement is clearly communicated. Workers who don't have compliant footwear should not be permitted on site until they do.",
      supervisorAction:
        "Today: direct the worker to obtain ASTM-compliant safety footwear before returning to site. Do not permit them to continue work in non-compliant footwear.",
      escalationTrigger:
        "If the worker cannot obtain footwear due to cost, contact the site safety officer — some sites maintain a loaner supply for exactly this situation. Document all occurrences.",
    },
  };

  return (
    contexts[firstPpe] ?? {
      howResolved:
        "Consistent PPE compliance is best achieved by combining accessible equipment, clear communication of requirements, and positive reinforcement. Sites that hold brief daily PPE checks at the start of each shift — and recognise crews with 100% compliance — see sustained improvement within 2–4 weeks.",
      typicalTimeToResolve:
        "Typically 1–3 weeks for consistent compliance once requirements are clearly communicated and PPE is made accessible.",
      supervisorAction:
        "Ensure the required PPE is available in the work area. Brief the worker on the requirement and log the observation.",
      escalationTrigger:
        "Issue a formal written warning on the second offence and escalate to Project Manager on the third.",
    }
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtCurrency(n: number): string {
  return "$" + n.toLocaleString("en-US");
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleString();
}

function severityColor(s: string): string {
  return s === "CRITICAL" ? "#dc2626" : "#d97706";
}

function eventLabel(e: SafeEvent): string {
  if (e.event_type === "missing_ppe") {
    const items = e.missing_ppe.length ? e.missing_ppe.map(p => p.toUpperCase()).join(" + ") : "PPE";
    return `Missing ${items}`;
  }
  return `Zone Intrusion${e.zone_id ? ` — ${e.zone_id}` : ""}`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function OshaCard({ code }: { code: OshaCode }) {
  return (
    <div style={{ borderRadius: 8, border: "1px solid #e5e7eb", overflow: "hidden", background: "#fff" }}>
      {/* Card header */}
      <div style={{ background: "#1a1a2e", padding: "10px 16px", display: "flex", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", marginBottom: 2 }}>
            OSHA Regulation
          </div>
          <div style={{ fontSize: 15, fontWeight: 800, color: "#fff", letterSpacing: 0.3 }}>
            {code.code}
          </div>
          <div style={{ fontSize: 13, color: "#cbd5e1", marginTop: 2 }}>
            {code.title}
          </div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase" }}>
            Fine per violation
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "#fbbf24", marginTop: 2 }}>
            {fmtCurrency(code.fine_min_usd)} – {fmtCurrency(code.fine_max_usd)}
          </div>
          <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>
            Willful: up to {fmtCurrency(code.willful_max_usd)}
          </div>
        </div>
      </div>

      {/* Plain-English explanation */}
      <div style={{ padding: "12px 16px", background: "#f8fafc", borderBottom: "1px solid #e5e7eb" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
          What this means
        </div>
        <div style={{ fontSize: 13, color: "#374151", lineHeight: 1.6 }}>
          {code.plain_english}
        </div>
      </div>

      {/* Regulatory text */}
      <div style={{ padding: "10px 16px", borderBottom: "1px solid #e5e7eb" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
          Regulation text
        </div>
        <div style={{ fontSize: 12, color: "#6b7280", lineHeight: 1.6, fontStyle: "italic" }}>
          "{code.description}"
        </div>
      </div>

      {/* Corrective actions */}
      <div style={{ padding: "12px 16px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 8 }}>
          Corrective actions
        </div>
        <ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}>
          {code.corrective_actions.map((action, i) => (
            <li key={i} style={{ fontSize: 13, color: "#374151", lineHeight: 1.5 }}>{action}</li>
          ))}
        </ol>
      </div>

      {/* Footer */}
      {code.reference_url && (
        <div style={{ padding: "8px 16px", background: "#f8fafc", borderTop: "1px solid #e5e7eb" }}>
          <a href={code.reference_url} target="_blank" rel="noreferrer"
            style={{ fontSize: 12, color: "#3b82f6", textDecoration: "none", fontWeight: 500 }}>
            View full regulation on OSHA.gov →
          </a>
        </div>
      )}
    </div>
  );
}

function InfoBox({ icon, title, children, accentColor = "#3b82f6" }: {
  icon: string; title: string; children: React.ReactNode; accentColor?: string;
}) {
  return (
    <div style={{ borderRadius: 8, border: `1px solid`, borderColor: accentColor + "44", overflow: "hidden", background: "#fff" }}>
      <div style={{ padding: "9px 16px", background: accentColor + "18", borderBottom: `1px solid ${accentColor}33`, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <div style={{ fontSize: 12, fontWeight: 700, color: accentColor, textTransform: "uppercase", letterSpacing: 0.5 }}>
          {title}
        </div>
      </div>
      <div style={{ padding: "12px 16px", fontSize: 13, color: "#374151", lineHeight: 1.7 }}>
        {children}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  event: SafeEvent;
  onClose: () => void;
}

export function EventDetail({ event, onClose }: Props) {
  const [codes, setCodes]     = useState<OshaCode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchOshaLookup(event)
      .then(setCodes)
      .catch(() => setCodes([]))
      .finally(() => setLoading(false));
  }, [event.event_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const ctx        = getResolutionContext(event);
  const isOpen     = event.end_frame === null;
  const isPpe      = event.event_type === "missing_ppe";
  const sColor     = severityColor(event.severity);
  const snapshotFile = event.snapshot_path?.split(/[\\/]/).pop();

  // Use stored fine data if available, fall back to live lookup data
  const fineMin = event.fine_min_usd || (codes.length ? Math.max(...codes.map(c => c.fine_min_usd)) : 0);
  const fineMax = event.fine_max_usd || (codes.length ? Math.max(...codes.map(c => c.fine_max_usd)) : 0);

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: 16 }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div style={{
        background: "#f8fafc", borderRadius: 12,
        width: "96vw", maxWidth: 740, maxHeight: "93vh",
        display: "flex", flexDirection: "column", overflow: "hidden",
        boxShadow: "0 32px 80px rgba(0,0,0,.5)",
      }}>

        {/* ── Header ── */}
        <div style={{ background: "#1a1a2e", padding: "16px 20px", display: "flex", alignItems: "flex-start", gap: 14, flexShrink: 0 }}>
          <span style={{ fontSize: 28, lineHeight: 1 }}>{isPpe ? "🦺" : "⛔"}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: 17, color: "#fff" }}>{eventLabel(event)}</div>
            <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 3 }}>
              Worker #{event.track_id}
              {event.zone_id ? ` · Zone: ${event.zone_id}` : ""}
              {" · "}{fmtTime(event.created_at)}
            </div>
            {fineMax > 0 && (
              <div style={{ fontSize: 11, color: "#fbbf24", marginTop: 4, fontWeight: 600 }}>
                ⚖ Potential fine: {fmtCurrency(fineMin)} – {fmtCurrency(fineMax)} per violation
              </div>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 800, padding: "3px 10px", borderRadius: 5, background: sColor, color: "#fff", letterSpacing: 0.8, textTransform: "uppercase" }}>
              {event.severity}
            </span>
            <span style={{ fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 5, background: isOpen ? "#22c55e" : "#64748b", color: "#fff", letterSpacing: 0.5 }}>
              {isOpen ? "ACTIVE" : "CLOSED"}
            </span>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#9ca3af", fontSize: 24, cursor: "pointer", lineHeight: 1, marginLeft: 4 }}>×</button>
        </div>

        {/* ── Body ── */}
        <div style={{ flex: 1, overflowY: "auto", padding: "18px 20px", display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Snapshot */}
          {snapshotFile && (
            <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #e5e7eb" }}>
              <img
                src={`${BASE}/snapshots/${snapshotFile}`}
                alt="Violation snapshot"
                style={{ width: "100%", display: "block", maxHeight: 260, objectFit: "cover" }}
                onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
            </div>
          )}

          {/* Violation details grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10 }}>
            {[
              { label: "Event type",  value: isPpe ? "Missing PPE" : "Zone Intrusion" },
              { label: "Worker ID",   value: `#${event.track_id}` },
              { label: "Zone",        value: event.zone_id ?? "—" },
              { label: "Zone rule",   value: event.zone_rule ?? "—" },
              { label: "Start frame", value: String(event.start_frame) },
              { label: "End frame",   value: event.end_frame !== null ? String(event.end_frame) : "Ongoing" },
              ...(isPpe && event.missing_ppe.length ? [{ label: "Missing PPE", value: event.missing_ppe.join(", ") }] : []),
            ].map(({ label, value }) => (
              <div key={label} style={{ background: "#fff", borderRadius: 7, padding: "10px 14px", border: "1px solid #e5e7eb" }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "#1f2937", marginTop: 3 }}>{value}</div>
              </div>
            ))}
          </div>

          {/* How similar sites resolved this */}
          <InfoBox icon="🏗️" title="How similar sites resolved this" accentColor="#059669">
            <p style={{ margin: "0 0 8px" }}>{ctx.howResolved}</p>
            <div style={{ fontSize: 12, color: "#6b7280", display: "flex", gap: 6, alignItems: "center" }}>
              <span style={{ fontWeight: 700 }}>⏱ Typical resolution time:</span>
              <span>{ctx.typicalTimeToResolve}</span>
            </div>
          </InfoBox>

          {/* Supervisor recommendations */}
          <InfoBox
            icon={event.severity === "CRITICAL" ? "🚨" : "📋"}
            title={event.severity === "CRITICAL" ? "Immediate supervisor action required" : "Supervisor recommendation"}
            accentColor={event.severity === "CRITICAL" ? "#dc2626" : "#d97706"}
          >
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4, color: "#374151" }}>Action now:</div>
              {ctx.supervisorAction}
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 4, color: "#374151" }}>Escalation trigger:</div>
              {ctx.escalationTrigger}
            </div>
          </InfoBox>

          {/* OSHA cards */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>
              {loading
                ? "Loading OSHA regulations…"
                : `${codes.length} OSHA regulation${codes.length !== 1 ? "s" : ""} triggered`}
            </div>

            {loading && (
              <div style={{ textAlign: "center", padding: "24px 0", color: "#9ca3af" }}>
                <div style={{ width: 28, height: 28, border: "3px solid #e2e8f0", borderTopColor: "#3b82f6", borderRadius: "50%", animation: "spin .7s linear infinite", margin: "0 auto 10px" }} />
                Fetching OSHA regulations…
              </div>
            )}

            {!loading && codes.length === 0 && (
              <div style={{ padding: "20px", textAlign: "center", color: "#9ca3af", fontSize: 13, background: "#fff", borderRadius: 8, border: "1px solid #e5e7eb" }}>
                No specific OSHA codes matched. Consult your Safety Officer.
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {codes.map(code => <OshaCard key={code.code} code={code} />)}
            </div>
          </div>

          {/* Disclaimer */}
          {!loading && codes.length > 0 && (
            <div style={{ padding: "10px 14px", background: "#fffbeb", borderRadius: 7, border: "1px solid #fde68a", fontSize: 11, color: "#92400e" }}>
              <strong>Disclaimer:</strong> Fine amounts reflect the 2024 OSHA adjusted penalty schedule for serious violations.
              Actual fines depend on severity, employer history, good-faith abatement, and OSHA area office discretion.
              This is not legal advice — consult a qualified safety professional or your OSHA area office for compliance guidance.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
