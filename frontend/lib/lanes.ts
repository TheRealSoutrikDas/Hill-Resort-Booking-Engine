// Plain words for the backend's enquiry terms (A-187).
import type { Me } from "./types";

export const LANES = [
  { key: "room_booking", label: "Room booking" },
  { key: "wedding", label: "Wedding" },
  { key: "corporate_offsite", label: "Offsite" },
  { key: "complaint", label: "Complaint" },
  { key: "unsorted", label: "Unsorted" },
] as const;
export const STATUSES = [
  { key: "pending", label: "Pending" },
  { key: "failed", label: "Failed" },
  { key: "replied", label: "Replied" },
] as const;

export const CATEGORIES: Record<string, string> = {
  room_booking: "Room booking",
  wedding: "Wedding",
  corporate_offsite: "Company offsite",
  complaint: "Complaint",
  other: "Something else",
};

export const REASONS: Record<string, string> = {
  low_confidence: "The AI was not confident.",
  disagreement: "The AI and the keyword check disagreed.",
  missing_fields: "Details needed to reply are missing.",
  invalid_output: "The AI's answer could not be used.",
  category_other: "It is not a booking, event or complaint.",
};

export const FIELD_LABELS: Record<string, string> = {
  check_in: "Check-in",
  check_out: "Check-out",
  event_month: "Event month",
  guests: "Guests",
  nights: "Nights",
  budget_inr: "Budget (rupees)",
  room_type: "Room type",
};

export const TEAMS: Record<string, string> = { reservations: "Reservations", events: "Events", gm: "GM" };

export function laneLabel(lane: string | null | undefined): string {
  if (!lane) return "Not yet sorted";
  return LANES.find((l) => l.key === lane)?.label ?? lane;
}

/** A-186: each team starts on its own lane. */
export function homeLane(me: Me | null): string {
  if (me?.is_gm) return "complaint";
  if (me?.team === "events") return "wedding";
  return "room_booking";
}

const when = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  hour: "numeric",
  minute: "2-digit",
  timeZone: "Asia/Kolkata",
});
export function atIndia(iso: string | null | undefined): string {
  return iso ? when.format(new Date(iso)) : "";
}

export function rateLabel(r: { count: number; out_of: number; value: number | null }): string {
  if (!r.out_of) return "none yet";
  return `${r.count} of ${r.out_of} (${Math.round((r.value ?? r.count / r.out_of) * 100)}%)`;
}
