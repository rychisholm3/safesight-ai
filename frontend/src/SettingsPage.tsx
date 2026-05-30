import { useEffect, useState } from "react";
import type { NotificationPrefs } from "./api";
import { fetchNotificationPrefs, saveNotificationPrefs } from "./api";

const CARD: React.CSSProperties = {
  background: "#fff",
  borderRadius: 10,
  padding: "20px 24px",
  boxShadow: "0 1px 6px rgba(0,0,0,.07)",
  marginBottom: 16,
};
const LABEL: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: "#374151",
  display: "block",
  marginBottom: 5,
};
const INPUT: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid #d1d5db",
  fontSize: 13,
  boxSizing: "border-box",
};
const BTN_PRIMARY: React.CSSProperties = {
  padding: "9px 22px",
  borderRadius: 6,
  border: "none",
  background: "#1a1a2e",
  color: "#fff",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};
const SUCCESS: React.CSSProperties = {
  background: "#f0fdf4",
  border: "1px solid #86efac",
  borderRadius: 6,
  padding: "10px 14px",
  color: "#16a34a",
  fontSize: 13,
};
const ERR: React.CSSProperties = {
  background: "#fef2f2",
  border: "1px solid #fca5a5",
  borderRadius: 6,
  padding: "10px 14px",
  color: "#dc2626",
  fontSize: 13,
};

function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        aria-pressed={checked}
        style={{
          width: 40,
          height: 22,
          borderRadius: 11,
          border: "none",
          background: checked ? "#1a1a2e" : "#d1d5db",
          position: "relative",
          cursor: "pointer",
          flexShrink: 0,
          transition: "background .15s",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: 3,
            left: checked ? 21 : 3,
            width: 16,
            height: 16,
            borderRadius: "50%",
            background: "#fff",
            transition: "left .15s",
          }}
        />
      </button>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: "#1f2937" }}>{label}</div>
        {description && (
          <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>{description}</div>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div style={{ marginTop: 12 }}>
      <label style={LABEL}>{label}</label>
      <input
        style={INPUT}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  );
}

const EMPTY: Omit<NotificationPrefs, "user_id"> = {
  email_enabled: false,
  sms_enabled: false,
  slack_enabled: false,
  teams_enabled: false,
  min_severity: "WARNING",
  quiet_start: null,
  quiet_end: null,
  email_to: null,
  phone_number: null,
  slack_webhook: null,
  teams_webhook: null,
};

export function SettingsPage({ onClose }: { onClose: () => void }) {
  const [prefs, setPrefs] = useState<Omit<NotificationPrefs, "user_id">>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchNotificationPrefs()
      .then((p) => {
        setPrefs({
          email_enabled: p.email_enabled,
          sms_enabled: p.sms_enabled,
          slack_enabled: p.slack_enabled,
          teams_enabled: p.teams_enabled,
          min_severity: p.min_severity,
          quiet_start: p.quiet_start ?? "",
          quiet_end: p.quiet_end ?? "",
          email_to: p.email_to ?? "",
          phone_number: p.phone_number ?? "",
          slack_webhook: p.slack_webhook ?? "",
          teams_webhook: p.teams_webhook ?? "",
        } as Omit<NotificationPrefs, "user_id">);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const set = <K extends keyof typeof prefs>(k: K, v: (typeof prefs)[K]) =>
    setPrefs((p) => ({ ...p, [k]: v }));

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      const payload = {
        ...prefs,
        quiet_start:   prefs.quiet_start   || null,
        quiet_end:     prefs.quiet_end     || null,
        email_to:      prefs.email_to      || null,
        phone_number:  prefs.phone_number  || null,
        slack_webhook: prefs.slack_webhook || null,
        teams_webhook: prefs.teams_webhook || null,
      };
      await saveNotificationPrefs(payload);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.45)",
        zIndex: 200, display: "flex", alignItems: "flex-start",
        justifyContent: "center", padding: "40px 16px", overflowY: "auto",
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#f5f6fa", borderRadius: 14, width: "100%", maxWidth: 560,
          padding: "28px 28px 20px",
          boxShadow: "0 8px 40px rgba(0,0,0,.18)",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", marginBottom: 20 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 17, color: "#1a1a2e" }}>
              Notification Settings
            </div>
            <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>
              Choose where SafeSight sends alerts for your account
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              marginLeft: "auto", background: "none", border: "none",
              fontSize: 20, cursor: "pointer", color: "#9ca3af", lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "40px 0", color: "#9ca3af" }}>
            Loading…
          </div>
        ) : (
          <form onSubmit={handleSave}>
            {/* Severity threshold */}
            <div style={CARD}>
              <div style={{ fontWeight: 600, fontSize: 14, color: "#1f2937", marginBottom: 12 }}>
                Minimum Severity
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                {(["WARNING", "CRITICAL"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => set("min_severity", s)}
                    style={{
                      flex: 1, padding: "8px 0", borderRadius: 6,
                      border: `1.5px solid ${s === "CRITICAL" ? "#dc2626" : "#f59e0b"}`,
                      background: prefs.min_severity === s
                        ? (s === "CRITICAL" ? "#dc2626" : "#f59e0b")
                        : "#fff",
                      color: prefs.min_severity === s ? "#fff"
                        : (s === "CRITICAL" ? "#dc2626" : "#f59e0b"),
                      fontWeight: 600, fontSize: 13, cursor: "pointer",
                    }}
                  >
                    {s === "WARNING" ? "All (Warning+)" : "Critical Only"}
                  </button>
                ))}
              </div>
              <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 8 }}>
                SMS always sends critical-only regardless of this setting.
              </div>
            </div>

            {/* Email */}
            <div style={CARD}>
              <Toggle
                checked={prefs.email_enabled}
                onChange={(v) => set("email_enabled", v)}
                label="Email Alerts"
                description="Requires SAFESIGHT_SMTP_HOST to be configured on the server"
              />
              {prefs.email_enabled && (
                <Field
                  label="Send to email (leave blank to use account email)"
                  value={prefs.email_to ?? ""}
                  onChange={(v) => set("email_to", v)}
                  placeholder="alerts@yourcompany.com"
                  type="email"
                />
              )}
            </div>

            {/* SMS */}
            <div style={CARD}>
              <Toggle
                checked={prefs.sms_enabled}
                onChange={(v) => set("sms_enabled", v)}
                label="SMS Alerts (Critical only)"
                description="Requires Twilio credentials on the server"
              />
              {prefs.sms_enabled && (
                <Field
                  label="Phone number (E.164 format)"
                  value={prefs.phone_number ?? ""}
                  onChange={(v) => set("phone_number", v)}
                  placeholder="+14155552671"
                />
              )}
            </div>

            {/* Slack */}
            <div style={CARD}>
              <Toggle
                checked={prefs.slack_enabled}
                onChange={(v) => set("slack_enabled", v)}
                label="Slack Alerts"
                description="Paste your Slack Incoming Webhook URL below"
              />
              {prefs.slack_enabled && (
                <Field
                  label="Slack Webhook URL"
                  value={prefs.slack_webhook ?? ""}
                  onChange={(v) => set("slack_webhook", v)}
                  placeholder="https://hooks.slack.com/services/…"
                />
              )}
            </div>

            {/* Teams */}
            <div style={CARD}>
              <Toggle
                checked={prefs.teams_enabled}
                onChange={(v) => set("teams_enabled", v)}
                label="Microsoft Teams Alerts"
                description="Paste your Teams Incoming Webhook URL below"
              />
              {prefs.teams_enabled && (
                <Field
                  label="Teams Webhook URL"
                  value={prefs.teams_webhook ?? ""}
                  onChange={(v) => set("teams_webhook", v)}
                  placeholder="https://yourcompany.webhook.office.com/webhookb2/…"
                />
              )}
            </div>

            {/* Quiet hours */}
            <div style={CARD}>
              <div style={{ fontWeight: 600, fontSize: 14, color: "#1f2937", marginBottom: 4 }}>
                Quiet Hours (UTC)
              </div>
              <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 12 }}>
                No alerts will be sent between these times. Leave blank to always notify.
              </div>
              <div style={{ display: "flex", gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label style={LABEL}>Start</label>
                  <input
                    style={INPUT}
                    type="time"
                    value={prefs.quiet_start ?? ""}
                    onChange={(e) => set("quiet_start", e.target.value)}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={LABEL}>End</label>
                  <input
                    style={INPUT}
                    type="time"
                    value={prefs.quiet_end ?? ""}
                    onChange={(e) => set("quiet_end", e.target.value)}
                  />
                </div>
              </div>
            </div>

            {saved  && <div style={{ ...SUCCESS, marginBottom: 12 }}>Settings saved.</div>}
            {error  && <div style={{ ...ERR,     marginBottom: 12 }}>{error}</div>}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  padding: "9px 18px", borderRadius: 6,
                  border: "1px solid #d1d5db", background: "#fff",
                  color: "#374151", fontSize: 13, cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button type="submit" style={BTN_PRIMARY} disabled={saving}>
                {saving ? "Saving…" : "Save Settings"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
