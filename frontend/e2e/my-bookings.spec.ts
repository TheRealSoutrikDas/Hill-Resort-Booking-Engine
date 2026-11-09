import { expect, test } from "@playwright/test";
import { GUEST, bookViaApi, logIn, thursdayStay, uniqueEmail } from "./helpers";

// Booking tests use Thursdays 0 to 23 (booking.spec.ts); these use 24 and 25.
const stay = () => thursdayStay(test.info().project.name === "phone" ? 25 : 24);

test("My bookings opens on Upcoming and has a tab per section", async ({ page }) => {
  await logIn(page, GUEST.email, GUEST.password);
  await page.getByRole("link", { name: "My bookings" }).click();
  await expect(page).toHaveURL("/my-bookings");
  await expect(page.getByRole("tab", { name: /Upcoming/ })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: /Past/ }).click();
  await expect(page.getByRole("tabpanel").getByRole("link").first()).toBeVisible(); // the seeded past stay
  await page.getByRole("tab", { name: /Current/ }).click();
  await expect(page.getByRole("tabpanel")).toHaveText("You are not staying with us right now.");
});

test("cancel asks twice, then the booking moves to Cancelled", async ({ page }) => {
  await logIn(page, GUEST.email, GUEST.password);
  const reference = await bookViaApi(page, stay());
  await page.goto(`/bookings/${reference}`);
  await page.getByRole("button", { name: "Cancel this booking" }).click();
  await expect(page.getByText(`Cancel booking ${reference}?`)).toBeVisible();
  await page.getByRole("button", { name: "Keep my booking" }).click();
  await expect(page.getByRole("heading", { name: "Your booking is confirmed" })).toBeVisible();

  await page.getByRole("button", { name: "Cancel this booking" }).click();
  await page.getByRole("button", { name: "Yes, cancel it" }).click();
  await expect(page.getByRole("heading", { name: "Booking cancelled" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Cancelled. A full refund is in progress.");
  expect((await (await page.request.get(`/api/bookings/${reference}`)).json()).status).toBe("cancelled");

  await page.goto("/my-bookings");
  await page.getByRole("tab", { name: /Cancelled/ }).click();
  await expect(page.getByRole("tabpanel").getByRole("link", { name: reference })).toBeVisible();
});

test("a past stay cannot be cancelled online", async ({ page }) => {
  await logIn(page, GUEST.email, GUEST.password);
  const all = await (await page.request.get("/api/me/bookings")).json();
  const past = all.find((b: { section: string }) => b.section === "past");
  await page.goto(`/bookings/${past.reference}`);
  await expect(page.getByText("Online cancellation closes the day before check-in.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Cancel this booking" })).toHaveCount(0);
});

test("a new account sees an invitation, not an empty list", async ({ page }) => {
  await page.goto("/signup?next=/my-bookings");
  await page.getByLabel("Full name").fill("New Guest");
  await page.getByLabel("Email", { exact: true }).fill(uniqueEmail("mybookings"));
  await page.getByLabel("Password", { exact: true }).fill("a-long-password-1");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("You have no bookings yet.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Find a room" })).toBeVisible();
});

test("My bookings needs you to be signed in", async ({ page }) => {
  await page.goto("/my-bookings");
  await expect(page).toHaveURL(/\/login\?next=%2Fmy-bookings/);
});

test("find a booking with its reference and email, view only", async ({ page }) => {
  await logIn(page, GUEST.email, GUEST.password);
  const all = await (await page.request.get("/api/me/bookings")).json();
  const upcoming = all.find((b: { section: string }) => b.section === "upcoming");
  await page.context().clearCookies();
  await page.goto("/");
  await page.getByRole("link", { name: "Find a booking" }).click();
  await page.getByLabel("Booking reference").fill(upcoming.reference.toLowerCase());
  await page.getByLabel("Email", { exact: true }).fill(GUEST.email);
  await page.getByRole("button", { name: "Find booking" }).click();
  const result = page.getByRole("region", { name: upcoming.reference });
  await expect(result).toBeVisible();
  await expect(result).not.toContainText(GUEST.email); // the email is masked
  await expect(result.getByRole("link", { name: "log in" })).toHaveAttribute(
    "href",
    `/login?next=%2Fbookings%2F${upcoming.reference}`,
  );
  await expect(page.getByRole("button", { name: /cancel/i })).toHaveCount(0);
});

test("a wrong email gets the same message as a wrong reference", async ({ page }) => {
  await page.goto("/find-booking");
  await page.getByLabel("Booking reference").fill("BK-NOPE1234");
  await page.getByLabel("Email", { exact: true }).fill("someone@example.com");
  await page.getByRole("button", { name: "Find booking" }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("No booking matches that reference and email.");
});

test("too many lookups says how long to wait", async ({ page }) => {
  await page.route("**/api/bookings/lookup", (route) =>
    route.fulfill({
      status: 429,
      headers: { "Content-Type": "application/json", "Retry-After": "300" },
      body: JSON.stringify({ error: { code: "rate_limited", message: "Too many requests.", details: null } }),
    }),
  );
  await page.goto("/find-booking");
  await page.getByLabel("Booking reference").fill("BK-AAAA1111");
  await page.getByLabel("Email", { exact: true }).fill("someone@example.com");
  await page.getByRole("button", { name: "Find booking" }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("Too many attempts. Try again in 5 minutes.");
});
