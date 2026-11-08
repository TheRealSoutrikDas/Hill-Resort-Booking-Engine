// Server components read public data straight from the backend (A-155). Nothing here
// carries a session: anything that needs one runs in the browser through `lib/api.ts`.
import { apiUrl } from "./config";
import { toApiError, unreachable } from "./errors";

export async function serverGet<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiUrl()}${path}`, { headers: { Accept: "application/json" } });
  } catch {
    throw unreachable();
  }
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}
