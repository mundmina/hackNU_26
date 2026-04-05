import type { EnrichedTelemetry, FleetCard, HealthSnapshot, AlertItem } from "../types";

const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const API_BASE = `${RAW_BASE}/api`;

type HttpMethod = "GET" | "POST";

function translateApiError(message: string, status: number) {
  const normalized = message.trim();

  if (normalized === "Invalid credentials") return "Неверный логин или пароль";
  if (normalized === "Missing bearer token") return "Отсутствует токен авторизации";
  if (normalized === "Invalid or expired token") return "Токен недействителен или срок его действия истёк";
  if (normalized === "Locomotive not found") return "Локомотив не найден";
  if (normalized === "No telemetry data found") return "Данные телеметрии не найдены";
  if (normalized === "No telemetry available") return "Телеметрия недоступна";

  return normalized || `Ошибка запроса (${status})`;
}

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
    const contentType = response.headers.get("content-type") ?? "";
    let message = "";

    if (contentType.includes("application/json")) {
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      message = typeof body?.detail === "string" ? body.detail : "";
    } else {
      message = await response.text();
    }

    throw new Error(translateApiError(message, response.status));
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
