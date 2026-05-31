import { useEffect, useRef, useState } from "react";
import { askCopilot, type CopilotMessage } from "./api";

// ── Suggested starter questions per role ──────────────────────────────────────
const STARTERS: Record<string, string[]> = {
  safety_officer: [
    "Which workers have the most violations in the last 24 hours?",
    "What OSHA codes are we most frequently violating?",
    "Which zone has the highest risk score right now?",
  ],
  site_manager: [
    "What should my supervisors focus on today?",
    "Are any zones showing a rising risk trend?",
    "Summarise this week's safety performance.",
  ],
  executive: [
    "What is our total OSHA fine exposure this week?",
    "How does our safety score compare to last week?",
    "Which site area represents the biggest compliance risk?",
  ],
  auditor: [
    "List all zone intrusion events with OSHA citations.",
    "Which events have the lowest detection confidence?",
    "Provide a full audit trail of PPE violations in the last 7 days.",
  ],
};

const DEFAULT_STARTERS = [
  "What is the current site risk level?",
  "Are there any repeat offenders today?",
  "Which zone needs the most attention right now?",
];

const ROLE_LABEL: Record<string, string> = {
  safety_officer: "Safety Officer",
  site_manager:   "Site Manager",
  executive:      "Executive",
  auditor:        "Auditor",
};

// ── Types ─────────────────────────────────────────────────────────────────────

interface DisplayMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  suggested?: string[];
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CopilotPanel({ userRole }: { userRole: string }) {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const bottomRef               = useRef<HTMLDivElement>(null);
  const inputRef                = useRef<HTMLTextAreaElement>(null);

  const starters = STARTERS[userRole] ?? DEFAULT_STARTERS;

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setInput("");
    setError(null);

    const userMsg: DisplayMessage = {
      id:      crypto.randomUUID(),
      role:    "user",
      content: trimmed,
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    // Build history for the API (only user/assistant text, no metadata)
    const history: CopilotMessage[] = messages.map((m) => ({
      role:    m.role,
      content: m.content,
    }));

    try {
      const res = await askCopilot(trimmed, history, userRole);
      const aiMsg: DisplayMessage = {
        id:        crypto.randomUUID(),
        role:      "assistant",
        content:   res.answer,
        suggested: res.suggested_questions,
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  function clearChat() {
    setMessages([]);
    setError(null);
  }

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={styles.icon}>🤖</span>
          <div>
            <div style={styles.title}>AI Safety Copilot</div>
            <div style={styles.subtitle}>Powered by Claude · Live site data</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={styles.roleBadge}>{ROLE_LABEL[userRole] ?? userRole}</span>
          {messages.length > 0 && (
            <button onClick={clearChat} style={styles.clearBtn} title="Clear conversation">
              ✕ Clear
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div style={styles.messages}>
        {messages.length === 0 && !loading && (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>💬</div>
            <p style={styles.emptyTitle}>Ask anything about your site safety</p>
            <p style={styles.emptyHint}>I have access to live violation data, zone risks, and OSHA references.</p>
            <div style={styles.starterGrid}>
              {starters.map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  style={styles.starterBtn}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              ...styles.messageRow,
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            {msg.role === "assistant" && <div style={styles.avatarAI}>🤖</div>}
            <div
              style={{
                ...styles.bubble,
                ...(msg.role === "user" ? styles.bubbleUser : styles.bubbleAI),
              }}
            >
              <MessageContent text={msg.content} isUser={msg.role === "user"} />

              {/* Suggested follow-up questions */}
              {msg.suggested && msg.suggested.length > 0 && (
                <div style={styles.suggestions}>
                  <div style={styles.suggestLabel}>Suggested follow-ups</div>
                  {msg.suggested.map((q) => (
                    <button
                      key={q}
                      onClick={() => sendMessage(q)}
                      style={styles.suggestChip}
                      disabled={loading}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {msg.role === "user" && <div style={styles.avatarUser}>👤</div>}
          </div>
        ))}

        {/* Thinking indicator */}
        {loading && (
          <div style={{ ...styles.messageRow, justifyContent: "flex-start" }}>
            <div style={styles.avatarAI}>🤖</div>
            <div style={{ ...styles.bubble, ...styles.bubbleAI }}>
              <ThinkingDots />
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={styles.errorBanner}>
            ⚠ {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={styles.inputRow}>
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about violations, zones, OSHA compliance… (Enter to send)"
          rows={2}
          style={styles.textarea}
          disabled={loading}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={!input.trim() || loading}
          style={{
            ...styles.sendBtn,
            opacity: (!input.trim() || loading) ? 0.45 : 1,
          }}
        >
          {loading ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

/** Render assistant text with newlines preserved. */
function MessageContent({ text, isUser }: { text: string; isUser: boolean }) {
  if (isUser) return <span style={{ fontSize: 14 }}>{text}</span>;
  // Split on double-newlines for paragraphs, single for line-breaks
  const paragraphs = text.split(/\n\n+/);
  return (
    <div style={{ fontSize: 14, lineHeight: 1.65 }}>
      {paragraphs.map((p, i) => (
        <p key={i} style={{ margin: i > 0 ? "10px 0 0" : 0, whiteSpace: "pre-wrap" }}>
          {p}
        </p>
      ))}
    </div>
  );
}

function ThinkingDots() {
  return (
    <div style={{ display: "flex", gap: 4, alignItems: "center", padding: "4px 2px" }}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            width: 6, height: 6, borderRadius: "50%",
            background: "#94a3b8",
            animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
          40% { transform: translateY(-5px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  container: {
    display:       "flex",
    flexDirection: "column",
    height:        "calc(100vh - 130px)",
    background:    "#fff",
    borderRadius:  10,
    border:        "1px solid #e5e7eb",
    overflow:      "hidden",
    boxShadow:     "0 1px 6px rgba(0,0,0,0.06)",
  },
  header: {
    background:     "#1a1a2e",
    color:          "#fff",
    padding:        "14px 20px",
    display:        "flex",
    alignItems:     "center",
    justifyContent: "space-between",
    flexShrink:     0,
  },
  icon:  { fontSize: 22 },
  title: { fontWeight: 700, fontSize: 15, letterSpacing: 0.3 },
  subtitle: { fontSize: 11, color: "#94a3b8", marginTop: 1 },
  roleBadge: {
    background:   "#3b82f6",
    color:        "#fff",
    borderRadius: 20,
    padding:      "3px 10px",
    fontSize:     11,
    fontWeight:   600,
    letterSpacing: 0.4,
  },
  clearBtn: {
    background:   "transparent",
    border:       "1px solid #4b5563",
    color:        "#9ca3af",
    borderRadius: 20,
    padding:      "3px 10px",
    fontSize:     11,
    cursor:       "pointer",
  },
  messages: {
    flex:       1,
    overflowY:  "auto",
    padding:    "16px 20px",
    display:    "flex",
    flexDirection: "column",
    gap:        12,
  },
  emptyState: {
    flex:       1,
    display:    "flex",
    flexDirection: "column",
    alignItems: "center",
    padding:    "40px 20px",
    textAlign:  "center",
  },
  emptyIcon:  { fontSize: 36, marginBottom: 12 },
  emptyTitle: { fontSize: 16, fontWeight: 600, color: "#1f2937", margin: "0 0 6px" },
  emptyHint:  { fontSize: 13, color: "#6b7280", margin: "0 0 20px" },
  starterGrid: {
    display:   "flex",
    flexDirection: "column",
    gap:       8,
    width:     "100%",
    maxWidth:  520,
  },
  starterBtn: {
    background:   "#f8fafc",
    border:       "1px solid #e2e8f0",
    borderRadius: 8,
    padding:      "10px 14px",
    fontSize:     13,
    color:        "#374151",
    cursor:       "pointer",
    textAlign:    "left",
    lineHeight:   1.4,
    transition:   "background 0.15s",
  },
  messageRow: {
    display:    "flex",
    alignItems: "flex-end",
    gap:        8,
  },
  avatarAI: {
    fontSize:   18,
    flexShrink: 0,
    marginBottom: 2,
  },
  avatarUser: {
    fontSize:   16,
    flexShrink: 0,
    marginBottom: 2,
  },
  bubble: {
    maxWidth:     "78%",
    borderRadius: 12,
    padding:      "10px 14px",
    wordBreak:    "break-word",
  },
  bubbleUser: {
    background:         "#1a1a2e",
    color:              "#f1f5f9",
    borderBottomRightRadius: 4,
  },
  bubbleAI: {
    background:         "#f1f5f9",
    color:              "#1f2937",
    borderBottomLeftRadius: 4,
    border:             "1px solid #e2e8f0",
  },
  suggestions: {
    marginTop:    10,
    paddingTop:   10,
    borderTop:    "1px solid #e2e8f0",
  },
  suggestLabel: {
    fontSize:     10,
    color:        "#94a3b8",
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginBottom: 6,
  },
  suggestChip: {
    display:      "block",
    width:        "100%",
    marginBottom: 4,
    background:   "#fff",
    border:       "1px solid #d1d5db",
    borderRadius: 6,
    padding:      "6px 10px",
    fontSize:     12,
    color:        "#3b82f6",
    cursor:       "pointer",
    textAlign:    "left",
  },
  errorBanner: {
    background:   "#fef2f2",
    border:       "1px solid #fca5a5",
    borderRadius: 8,
    padding:      "10px 14px",
    fontSize:     13,
    color:        "#dc2626",
  },
  inputRow: {
    display:    "flex",
    gap:        8,
    padding:    "12px 16px",
    borderTop:  "1px solid #e5e7eb",
    background: "#fafafa",
    flexShrink: 0,
  },
  textarea: {
    flex:        1,
    resize:      "none",
    border:      "1px solid #d1d5db",
    borderRadius: 8,
    padding:     "8px 12px",
    fontSize:    14,
    fontFamily:  "system-ui, sans-serif",
    lineHeight:  1.5,
    outline:     "none",
    background:  "#fff",
  },
  sendBtn: {
    background:   "#1a1a2e",
    color:        "#fff",
    border:       "none",
    borderRadius: 8,
    padding:      "8px 20px",
    fontSize:     14,
    fontWeight:   600,
    cursor:       "pointer",
    alignSelf:    "flex-end",
    minWidth:     70,
  },
};
