import type { SafeEvent, Stats } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
export const WS_URL = BASE.replace(/^http/, "ws") + "/ws/events";

export async function fetchEvents(params?: {
  event_type?: string;
  limit?: number;
}): Promise<SafeEvent[]> {
  const qs = new URLSearchParams();
  if (params?.event_type) qs.set("event_type", params.event_type);
  if (params?.limit) qs.set("limit", String(params.limit));
  const res = await fetch(`${BASE}/events?${qs}`);
  if (!res.ok) throw new Error("Failed to fetch events");
  return res.json();
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${BASE}/stats`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}
