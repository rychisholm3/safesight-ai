export interface SafeEvent {
  event_id: string;
  event_type: "missing_ppe" | "zone_intrusion";
  track_id: number;
  zone_id: string | null;
  missing_ppe: string[];
  severity: "WARNING" | "CRITICAL";
  start_frame: number;
  end_frame: number | null;
  snapshot_path: string | null;
  created_at: string;
}

export interface Zone {
  id: string;
  name: string;
  polygon: [number, number][];
  rule: "no_entry" | "require_ppe";
  required_ppe?: string[];
}

export interface ZonesConfig {
  required_ppe: string[];
  zones: Zone[];
}

export interface Stats {
  total: number;
  open: number;
  closed: number;
  by_type: Record<string, number>;
}
