import { expect, type Page } from "@playwright/test";

export const GUEST = { email: "guest@example.com", password: "Guest-Demo-2026", name: "Demo" }; // seeded as "Demo Guest"; the header shows the first name
export const STAFF = { email: "reservations@example.com", password: "Reservations-Demo-2026" };

/** A fresh email per test run, so sign-up tests can run again and again. */
export function uniqueEmail(tag: string): string {
  return `e2e-${tag}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

export async function logIn(page: Page, email: string, password: string, next = "/") {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
}

// Dates the seed sets up, as rules relative to today in India (backend app/seed/plan.py):
// the first Friday 14+ days ahead is sold out (Friday and Saturday nights).
const DAY = 86_400_000;
export function todayInIndia(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}
export function addDays(iso: string, days: number): string {
  return new Date(Date.parse(`${iso}T00:00:00Z`) + days * DAY).toISOString().slice(0, 10);
}
function firstWeekdayOnOrAfter(iso: string, weekday: number): string {
  // weekday: 0 = Monday ... 6 = Sunday, as Python's date.weekday()
  const d = new Date(`${iso}T00:00:00Z`);
  const offset = (weekday - ((d.getUTCDay() + 6) % 7) + 7) % 7;
  return addDays(iso, offset);
}
export function soldOutFriday(): string {
  return firstWeekdayOnOrAfter(addDays(todayInIndia(), 14), 4);
}
/** An open weekday stay well clear of the seeded sold-out and one-left weekends. */
export function openStay(): { checkIn: string; checkOut: string } {
  const monday = firstWeekdayOnOrAfter(addDays(todayInIndia(), 3), 0);
  return { checkIn: monday, checkOut: addDays(monday, 2) };
}

/**
 * A one-night Thursday stay for test number `n`. Thursdays avoid everything the seed
 * sets up on purpose (sold-out Friday and Saturday, one-left Friday, Monday to
 * Wednesday blackout), so a booking test always finds rooms. Reseed before a run.
 */
export function thursdayStay(n: number): { checkIn: string; checkOut: string } {
  const first = firstWeekdayOnOrAfter(addDays(todayInIndia(), 3), 3);
  const checkIn = addDays(first, 7 * n);
  return { checkIn, checkOut: addDays(checkIn, 1) };
}
