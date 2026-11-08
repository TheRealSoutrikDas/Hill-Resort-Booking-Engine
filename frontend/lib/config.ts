/**
 * The backend's base URL, for server code only (A-152). API_URL has no NEXT_PUBLIC_
 * prefix, so Next.js never puts it into browser code.
 */
export function apiUrl(): string {
  return (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}
