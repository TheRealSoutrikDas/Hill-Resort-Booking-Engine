"use client";

// The browser's API client. Calls go to `/api/*` on this site and are forwarded to the
// backend (A-152). Plain fetch with one small wrapper; no data-fetching library (A-155).
import { ApiError, toApiError, unreachable } from "./errors";
import type { Me } from "./types";

// The CSRF token comes with login and with GET /api/auth/me, and is sent back on every
// write. Kept in memory only: after a reload, `loadSession()` fetches it again.
let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export async function api<T>(
  path: string,
  options: { method?: Method; body?: unknown; signal?: AbortSignal; headers?: Record<string, string> } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: "same-origin",
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw unreachable();
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** The signed-in account, or null when signed out. Restores the CSRF token. */
export async function loadSession(): Promise<Me | null> {
  try {
    const me = await api<Me>("/api/auth/me");
    setCsrfToken(me.csrf_token);
    return me;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setCsrfToken(null);
      return null;
    }
    throw error;
  }
}
