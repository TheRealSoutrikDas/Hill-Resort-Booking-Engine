import type { FullConfig } from "@playwright/test";

/**
 * Checks the setup once before any test, so a misconfigured backend gives one clear
 * message instead of dozens of failures:
 *  - the API answers through the frontend (API_URL is right and the backend is up);
 *  - the API trusts the frontend's origin (CORS_ORIGINS includes it), which every
 *    log in, booking and enquiry from the browser needs.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:3000";
  const origin = new URL(baseURL).origin;

  let rooms: Response;
  try {
    rooms = await fetch(`${baseURL}/api/rooms`);
  } catch {
    throw new Error(`The frontend is not answering at ${baseURL}. Build it and run \`npm run start\`.`);
  }
  if (!rooms.ok) {
    throw new Error(
      `GET /api/rooms through the frontend returned ${rooms.status}. Is the backend running, and was the frontend built with the right API_URL?`,
    );
  }

  // A write without a session: a trusted origin gets 401, an untrusted one 403 csrf_failed.
  const probe = await fetch(`${baseURL}/api/auth/logout`, { method: "POST", headers: { Origin: origin } });
  if (probe.status === 403) {
    throw new Error(
      `The backend refuses writes from ${origin}. Start it with CORS_ORIGINS=${origin} (see README, "Run the frontend").`,
    );
  }
}
