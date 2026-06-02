import type { SafeEvent, Stats, ZonesConfig } from "./types";

// ── OSHA Rule Engine ──────────────────────────────────────────────────────────

export interface OshaCode {
  code: string;
  title: string;
  description: string;
  fine_min_usd: number;
  fine_max_usd: number;
  willful_max_usd: number;
  corrective_actions: string[];
  plain_english: string;
  reference_url: string;
}

const BASE = import.meta.env.VITE_API_URL ?? "";
export const WS_URL = BASE
  ? BASE.replace(/^http/, "ws") + "/ws/events"
  : `ws://${window.location.host}/ws/events`;

// ── Token storage ────────────────────────────────────────────────────────────

const TOKEN_KEY = "safesight_access_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ── Authenticated fetch ──────────────────────────────────────────────────────

async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
  }
  return res;
}

// ── Auth endpoints ───────────────────────────────────────────────────────────

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserInfo {
  user_id: string;
  org_id: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export async function register(
  orgName: string, email: string, password: string
): Promise<AuthTokens> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ org_name: orgName, email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Registration failed" }));
    throw new Error(err.detail ?? "Registration failed");
  }
  return res.json();
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(err.detail ?? "Login failed");
  }
  return res.json();
}

export async function fetchMe(): Promise<UserInfo> {
  const res = await apiFetch("/auth/me");
  if (!res.ok) throw new Error("Not authenticated");
  return res.json();
}

// ── Existing endpoints (now authenticated) ───────────────────────────────────

export async function fetchEvents(params?: {
  event_type?: string;
  limit?: number;
}): Promise<SafeEvent[]> {
  const qs = new URLSearchParams();
  if (params?.event_type) qs.set("event_type", params.event_type);
  if (params?.limit) qs.set("limit", String(params.limit));
  const res = await apiFetch(`/events?${qs}`);
  if (!res.ok) throw new Error("Failed to fetch events");
  return res.json();
}

export async function fetchStats(): Promise<Stats> {
  const res = await apiFetch("/stats");
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}

export async function fetchZones(): Promise<ZonesConfig> {
  const res = await apiFetch("/zones");
  if (!res.ok) throw new Error("Failed to fetch zones");
  return res.json();
}

export async function saveZones(config: ZonesConfig): Promise<ZonesConfig> {
  const res = await apiFetch("/zones", {
    method: "PUT",
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error("Failed to save zones");
  return res.json();
}

// ── Notification preferences ─────────────────────────────────────────────────

export interface NotificationPrefs {
  user_id: string;
  email_enabled: boolean;
  sms_enabled: boolean;
  slack_enabled: boolean;
  teams_enabled: boolean;
  min_severity: "WARNING" | "CRITICAL";
  quiet_start: string | null;
  quiet_end: string | null;
  email_to: string | null;
  phone_number: string | null;
  slack_webhook: string | null;
  teams_webhook: string | null;
}

export async function fetchNotificationPrefs(): Promise<NotificationPrefs> {
  const res = await apiFetch("/notifications/prefs");
  if (!res.ok) throw new Error("Failed to fetch notification preferences");
  return res.json();
}

export async function saveNotificationPrefs(
  prefs: Omit<NotificationPrefs, "user_id">
): Promise<NotificationPrefs> {
  const res = await apiFetch("/notifications/prefs", {
    method: "PUT",
    body: JSON.stringify(prefs),
  });
  if (!res.ok) throw new Error("Failed to save notification preferences");
  return res.json();
}

// ── Risk engine ───────────────────────────────────────────────────────────────

export interface ZoneRisk {
  zone_id: string;
  risk_score: number;
  risk_level: "LOW" | "ELEVATED" | "HIGH" | "CRITICAL";
  trend: "RISING" | "STABLE" | "FALLING";
  trend_pct: number;
  violations_24h: number;
  violations_7d: number;
  violations_prev_7d: number;
  is_rising: boolean;
  computed_at: string;
}

export interface WorkerRisk {
  track_id: number;
  violation_count: number;
  violations_24h: number;
  most_common_type: string;
  most_common_zone: string | null;
  is_repeat_offender: boolean;
}

export interface RiskSummary {
  overall_risk_level: string;
  overall_risk_score: number;
  total_violations_24h: number;
  total_violations_7d: number;
  rising_risk_zones: string[];
  repeat_offender_count: number;
  highest_risk_zone: string | null;
}

export async function fetchZoneRisks(): Promise<ZoneRisk[]> {
  const res = await apiFetch("/risk/zones");
  if (!res.ok) throw new Error("Failed to fetch zone risks");
  return res.json();
}

export async function fetchRiskSummary(): Promise<RiskSummary> {
  const res = await apiFetch("/risk/summary");
  if (!res.ok) throw new Error("Failed to fetch risk summary");
  return res.json();
}

export async function fetchRepeatOffenders(): Promise<WorkerRisk[]> {
  const res = await apiFetch("/risk/workers/offenders");
  if (!res.ok) throw new Error("Failed to fetch repeat offenders");
  return res.json();
}

// ── Camera discovery ──────────────────────────────────────────────────────────

export interface CameraInfo {
  index: number;
  label: string;
  width: number;
  height: number;
}

export async function fetchCameras(): Promise<CameraInfo[]> {
  const res = await apiFetch("/cameras");
  if (!res.ok) throw new Error("Failed to list cameras");
  return res.json();
}

/** Fetch a JPEG snapshot from camera `index` and return a blob: URL. */
export async function fetchCameraSnapshot(index: number): Promise<string> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}/cameras/${index}/snapshot`, { headers });
  if (!res.ok) throw new Error(`Snapshot for camera ${index} failed`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export interface VideoFileInfo {
  path: string;
  name: string;
  filename: string;
  duration_s: number;
  width: number;
  height: number;
}

export async function fetchVideoFiles(): Promise<VideoFileInfo[]> {
  const res = await apiFetch("/cameras/video-files");
  if (!res.ok) throw new Error("Failed to list video files");
  return res.json();
}

export async function fetchOshaLookup(event: SafeEvent): Promise<OshaCode[]> {
  const qs = new URLSearchParams({ event_type: event.event_type });
  if (event.missing_ppe?.length) qs.set("missing_ppe", event.missing_ppe.join(","));
  // Use the stored zone_rule (now saved on every zone event at detection time)
  if (event.zone_rule) qs.set("zone_rule", event.zone_rule);
  const res = await apiFetch(`/osha/lookup?${qs}`);
  if (!res.ok) throw new Error("Failed to fetch OSHA codes");
  return res.json();
}

export async function fetchOshaCodes(): Promise<OshaCode[]> {
  const res = await apiFetch("/osha/codes");
  if (!res.ok) throw new Error("Failed to fetch OSHA codes");
  return res.json();
}

// ── Evidence & Explainability ─────────────────────────────────────────────────

export interface ExplanationItem {
  category: string;
  text: string;
  icon: string;
}

export async function fetchExplanation(eventId: string): Promise<ExplanationItem[]> {
  const res = await apiFetch(`/evidence/${eventId}/explanation`);
  if (!res.ok) throw new Error("Failed to fetch explanation");
  return res.json();
}

/** Returns a URL to the annotated snapshot (requires auth header — use blob URL). */
export async function fetchAnnotatedSnapshot(eventId: string): Promise<string> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}/evidence/${eventId}/annotated-snapshot`, { headers });
  if (!res.ok) throw new Error("Annotated snapshot not available");
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/** Triggers a PDF download by opening the endpoint in a new tab. */
export function downloadEvidencePdf(eventId: string): void {
  const token = getToken();
  // Open in iframe trick — pass token as query param won't work, use anchor with fetch
  const url = `${BASE}/evidence/${eventId}/report.pdf`;
  // Fetch it manually so we can attach auth header, then trigger download
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  fetch(url, { headers })
    .then((r) => r.blob())
    .then((blob) => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `safesight-evidence-${eventId.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    })
    .catch(() => alert("PDF generation failed — check the backend logs."));
}

// ── AI Safety Copilot ─────────────────────────────────────────────────────────

export interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

export interface CopilotResponse {
  answer: string;
  suggested_questions: string[];
}

export async function askCopilot(
  message: string,
  history: CopilotMessage[],
  role: string,
): Promise<CopilotResponse> {
  const res = await apiFetch("/copilot/ask", {
    method: "POST",
    body: JSON.stringify({ message, history, role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Copilot request failed" }));
    throw new Error(err.detail ?? "Copilot request failed");
  }
  return res.json();
}

/** Fetch a representative JPEG frame from a video file and return a blob: URL. */
export async function fetchVideoSnapshot(videoPath: string): Promise<string> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const qs = new URLSearchParams({ path: videoPath });
  const res = await fetch(`${BASE}/cameras/video-snapshot?${qs}`, { headers });
  if (!res.ok) throw new Error(`Video snapshot for "${videoPath}" failed`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
