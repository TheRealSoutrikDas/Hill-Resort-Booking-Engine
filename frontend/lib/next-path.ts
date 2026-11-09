// Where to go after logging in (A-158). Only a path on this site is followed, so a
// crafted link such as /login?next=https://evil.example cannot send someone away.
const PROBE = "http://same-site.invalid";

export function safeNextPath(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\")) return "/";
  try {
    const url = new URL(raw, PROBE); // also catches tricks such as "/\t/evil.example"
    if (url.origin !== PROBE) return "/";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}

export function loginHref(next: string): string {
  return `/login?next=${encodeURIComponent(safeNextPath(next))}`;
}

export function signupHref(next: string): string {
  return `/signup?next=${encodeURIComponent(safeNextPath(next))}`;
}
