import type { EnrichedTelemetry, FleetCard, HealthSnapshot, AlertItem } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type HttpMethod = "GET" | "POST";

async function request<T>(path: string, token?: string, init?: { method?: HttpMethod; body?: unknown }): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: init?.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: init?.body ? JSON.stringify(init.body) : undefined,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }

  if (response.headers.get("content-type")?.includes("application/json")) {
    return (await response.json()) as T;
  }

  return (await response.text()) as T;
}

export async function login(username: string, password: string) {
  return request<{ access_token: string; role: string }>("/auth/login", undefined, {
    method: "POST",
    body: { username, password },
  });
}

export async function fetchFleet(token: string) {
  return request<FleetCard[]>("/locomotives", token);
}

export async function fetchHealth(token: string, locomotiveId: string) {
  return request<HealthSnapshot>(`/locomotives/${locomotiveId}/health`, token);
}

export async function fetchHistory(token: string, locomotiveId: string, limit = 80) {
  return request<EnrichedTelemetry[]>(`/telemetry?locomotive_id=${locomotiveId}&page=1&page_size=${limit}`, token);
}

export async function fetchAlerts(token: string, locomotiveId: string) {
  return request<AlertItem[]>(`/alerts?locomotive_id=${locomotiveId}&limit=25`, token);
}

export function apiBase() {
  return API_BASE;
}
