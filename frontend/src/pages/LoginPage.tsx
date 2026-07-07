import { useState } from "react";
import { login, register } from "../lib/api";
import { useAuth } from "../context/AuthContext";

const FIELD: React.CSSProperties = {
  width: "100%", padding: "10px 12px", borderRadius: 6,
  border: "1px solid #d1d5db", fontSize: 14, boxSizing: "border-box",
};
const BTN: React.CSSProperties = {
  width: "100%", padding: "11px", borderRadius: 6, border: "none",
  background: "#1a1a2e", color: "#fff", fontSize: 14,
  fontWeight: 600, cursor: "pointer", marginTop: 4,
};
const ERR: React.CSSProperties = {
  background: "#fef2f2", border: "1px solid #fca5a5",
  borderRadius: 6, padding: "10px 12px", color: "#dc2626", fontSize: 13,
};

export function LoginPage() {
  const { signIn, signInAsGuest } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [orgName, setOrgName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const tokens = mode === "login"
        ? await login(email, password)
        : await register(orgName, email, password);
      await signIn(tokens);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", background: "#f5f6fa",
    }}>
      <div style={{
        background: "#fff", borderRadius: 12, padding: "40px 36px",
        width: 380, boxShadow: "0 4px 24px rgba(0,0,0,0.08)",
      }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{ fontWeight: 800, fontSize: 22, color: "#1a1a2e", letterSpacing: 0.5 }}>
            SafeSight AI
          </div>
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
            Construction Safety Monitoring
          </div>
        </div>

        {/* Tab toggle */}
        <div style={{
          display: "flex", background: "#f3f4f6", borderRadius: 8,
          padding: 3, marginBottom: 24,
        }}>
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              onClick={() => { setMode(m); setError(null); }}
              style={{
                flex: 1, padding: "7px 0", borderRadius: 6, border: "none",
                background: mode === m ? "#fff" : "transparent",
                boxShadow: mode === m ? "0 1px 4px rgba(0,0,0,0.1)" : "none",
                fontWeight: mode === m ? 600 : 400, fontSize: 13,
                color: mode === m ? "#1a1a2e" : "#6b7280", cursor: "pointer",
              }}
            >
              {m === "login" ? "Sign In" : "Create Account"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {mode === "register" && (
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 5 }}>
                Organisation Name
              </label>
              <input
                style={FIELD} required value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Acme Construction Ltd"
              />
            </div>
          )}

          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 5 }}>
              Email
            </label>
            <input
              style={FIELD} type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </div>

          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#374151", display: "block", marginBottom: 5 }}>
              Password
            </label>
            <input
              style={FIELD} type="password" required value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === "register" ? "At least 8 characters" : "••••••••"}
            />
          </div>

          {error && <div style={ERR}>{error}</div>}

          <button type="submit" style={BTN} disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        {mode === "register" && (
          <p style={{ fontSize: 11, color: "#9ca3af", textAlign: "center", marginTop: 16, lineHeight: 1.5 }}>
            Creating an account starts a new organisation.
            Your role will be Safety Officer.
          </p>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "20px 0 4px" }}>
          <div style={{ flex: 1, height: 1, background: "#e5e7eb" }} />
          <span style={{ fontSize: 11, color: "#9ca3af" }}>or</span>
          <div style={{ flex: 1, height: 1, background: "#e5e7eb" }} />
        </div>

        <button
          onClick={signInAsGuest}
          style={{
            width: "100%", padding: "11px", borderRadius: 6,
            border: "1px solid #d1d5db", background: "#fff",
            color: "#6b7280", fontSize: 14, fontWeight: 500,
            cursor: "pointer",
          }}
        >
          Continue as Guest
        </button>
        <p style={{ fontSize: 11, color: "#9ca3af", textAlign: "center", marginTop: 8, lineHeight: 1.5 }}>
          Demo mode — no account needed. Data is read-only.
        </p>
      </div>
    </div>
  );
}
