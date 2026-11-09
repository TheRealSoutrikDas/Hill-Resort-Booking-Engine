// A search and the rooms chosen for it, kept in the address bar (step 26): dates,
// guests, and lines as `sel=PLV.RO.1.2,DLX.BB.2.4` (room type, plan, rooms, guests).
// It survives a reload, can be shared, and sign-in can carry it in `next` (A-171).

export const HORIZON_DAYS = 180; // the backend's booking_horizon_days (A-164)
export const MAX_NIGHTS = 14; // max_stay_nights
export const MAX_ROOMS = 4; // max_units_per_booking (A-165)
export const MAX_GUESTS = 20;
const TIME_ZONE = "Asia/Kolkata";

export type Line = { roomType: string; ratePlan: string; units: number; guests: number };
export type Search = { checkIn: string | null; checkOut: string | null; guests: number };

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const CODE = /^[A-Z0-9_]{1,32}$/;

/** Today in the resort's time zone, as YYYY-MM-DD (the backend works in IST). */
export function todayInIndia(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE }).format(now);
}

export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export function nightsBetween(checkIn: string, checkOut: string): number {
  return Math.round((Date.parse(`${checkOut}T00:00:00Z`) - Date.parse(`${checkIn}T00:00:00Z`)) / 86_400_000);
}

type Params = { get(name: string): string | null } | Record<string, string | string[] | undefined>;

function read(params: Params, name: string): string | null {
  if (typeof (params as URLSearchParams).get === "function") return (params as URLSearchParams).get(name);
  const value = (params as Record<string, string | string[] | undefined>)[name];
  return Array.isArray(value) ? (value[0] ?? null) : (value ?? null);
}

export function parseSearch(params: Params): Search {
  const checkIn = read(params, "check_in");
  const checkOut = read(params, "check_out");
  const guests = Number.parseInt(read(params, "guests") ?? "2", 10);
  return {
    checkIn: checkIn && DATE.test(checkIn) ? checkIn : null,
    checkOut: checkOut && DATE.test(checkOut) ? checkOut : null,
    guests: Number.isFinite(guests) && guests >= 1 && guests <= MAX_GUESTS ? guests : 2,
  };
}

export function parseLines(params: Params): Line[] {
  const raw = read(params, "sel");
  if (!raw) return [];
  const lines: Line[] = [];
  for (const part of raw.split(",").slice(0, 10)) {
    const [roomType, ratePlan, units, guests] = part.split(".");
    const u = Number.parseInt(units ?? "", 10);
    const g = Number.parseInt(guests ?? "", 10);
    if (CODE.test(roomType ?? "") && CODE.test(ratePlan ?? "") && u >= 1 && u <= MAX_ROOMS && g >= 1 && g <= 100) {
      lines.push({ roomType: roomType!, ratePlan: ratePlan!, units: u, guests: g });
    }
  }
  return lines;
}

export function searchQuery(search: Search, lines: Line[] = []): string {
  const q = new URLSearchParams();
  if (search.checkIn) q.set("check_in", search.checkIn);
  if (search.checkOut) q.set("check_out", search.checkOut);
  q.set("guests", String(search.guests));
  if (lines.length) q.set("sel", lines.map((l) => `${l.roomType}.${l.ratePlan}.${l.units}.${l.guests}`).join(","));
  return q.toString();
}

/** The checks the backend also makes, so an obvious mistake needs no round trip. */
export function datesProblem(checkIn: string, checkOut: string, today: string): string | null {
  if (checkIn < today) return "Check-in cannot be in the past.";
  if (checkOut <= checkIn) return "Check-out must be after check-in.";
  if (nightsBetween(checkIn, checkOut) > MAX_NIGHTS) return `Stays can be up to ${MAX_NIGHTS} nights.`;
  if (checkIn > addDays(today, HORIZON_DAYS)) return `Bookings open ${HORIZON_DAYS} days ahead.`;
  return null;
}

export function stayLabel(checkIn: string, checkOut: string): string {
  const fmt = new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
  const n = nightsBetween(checkIn, checkOut);
  return `${fmt.format(new Date(`${checkIn}T00:00:00Z`))} to ${fmt.format(new Date(`${checkOut}T00:00:00Z`))}, ${n} ${n === 1 ? "night" : "nights"}`;
}
