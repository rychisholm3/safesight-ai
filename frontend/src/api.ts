import type { SafeEvent, Stats, ZonesConfig } from "./types";

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
