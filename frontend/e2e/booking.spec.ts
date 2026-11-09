import { expect, test, type Page } from "@playwright/test";
import { GUEST, STAFF, logIn, thursdayStay } from "./helpers";

// Each test books its own Thursday (desktop weeks 0 to 11, phone 12 to 23), so tests
// never compete for rooms. Reseed the database before a run (README).
let count = 0;
function stay() {
  const offset = test.info().project.name === "phone" ? 12 : 0;
  return thursdayStay(offset + (count++ % 12));
}

async function chooseVilla(page: Page, checkIn: string, checkOut: string) {
  await page.goto(`/rooms?check_in=${checkIn}&check_out=${checkOut}&guests=2`);
  await page.getByRole("button", { name: "Add Deluxe Room, Bed and Breakfast" }).click();
  await expect(page.getByRole("complementary").getByText("Total")).toBeVisible();
}

async function startBooking(page: Page) {
  const { checkIn, checkOut } = stay();
  await logIn(page, GUEST.email, GUEST.password);
  await chooseVilla(page, checkIn, checkOut);
  await page.getByRole("button", { name: "Book these rooms" }).click();
  await expect(page).toHaveURL(/\/book\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("timer")).toContainText("Rooms held for you for");
}

async function saveGuest(page: Page) {
  // Prefilled from the account (guest_suggestion).
  await expect(page.getByLabel("Guest name")).toHaveValue("Demo Guest");
  await page.getByRole("button", { name: "Save guest details" }).click();
  await expect(page.getByRole("button", { name: "Change guest details" })).toBeVisible();
}

test("book, add the guest, pay, see the confirmation", async ({ page }) => {
  await startBooking(page);
  const total = (await page.getByRole("button", { name: /^Pay / }).count()) === 0;
  expect(total).toBe(true); // no paying before the guest's details are saved
  await saveGuest(page);
  await page.getByRole("button", { name: /^Pay ₹/ }).click();
  await expect(page).toHaveURL(/\/bookings\/[A-Z0-9-]+$/);
  await expect(page.getByRole("heading", { name: "Your booking is confirmed" })).toBeVisible();
  await expect(page.getByText("Paid in full")).toBeVisible();
  const reference = page.url().split("/").pop()!;
  const api = await page.request.get(`/api/bookings/${reference}`);
  expect((await api.json()).status).toBe("confirmed");
});

test("signing in mid-way brings you back to your rooms", async ({ page }) => {
  const { checkIn, checkOut } = stay();
  await chooseVilla(page, checkIn, checkOut);
  await page.getByRole("button", { name: "Log in to book" }).click();
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.getByLabel("Email", { exact: true }).fill(GUEST.email);
  await page.getByLabel("Password", { exact: true }).fill(GUEST.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/rooms\?.*sel=DLX\.BB\.1\.2/);
  await page.getByRole("button", { name: "Book these rooms" }).click();
  await expect(page).toHaveURL(/\/book\//);
});

test("a declined card can be tried again", async ({ page }) => {
  await startBooking(page);
  await saveGuest(page);
  await page.getByLabel("Card is declined").check();
  await page.getByRole("button", { name: /^Pay ₹/ }).click();
  await expect(page.getByText("The payment was declined and you were not charged.")).toBeVisible();
  await page.getByLabel("Payment succeeds").check();
  await page.getByRole("button", { name: /^Pay ₹/ }).click();
  await expect(page.getByRole("heading", { name: "Your booking is confirmed" })).toBeVisible();
});

test("a provider timeout is not a charge; trying again works", async ({ page }) => {
  await startBooking(page);
  await saveGuest(page);
  await page.getByLabel("Provider does not answer").check();
  await page.getByRole("button", { name: /^Pay ₹/ }).click();
  await expect(page.getByText("The payment provider did not answer, so you were not charged.")).toBeVisible();
  await page.getByLabel("Payment succeeds").check();
  await page.getByRole("button", { name: /^Pay ₹/ }).click();
  await expect(page.getByRole("heading", { name: "Your booking is confirmed" })).toBeVisible();
});

test("a double click pays once: every request carries the same key", async ({ page }) => {
  await startBooking(page);
  await saveGuest(page);
  const keys: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/payment")) keys.push(r.headers()["idempotency-key"] ?? "");
  });
  await page.getByRole("button", { name: /^Pay ₹/ }).dblclick();
  await expect(page.getByRole("heading", { name: "Your booking is confirmed" })).toBeVisible();
  expect(keys.length).toBeGreaterThanOrEqual(1);
  expect(new Set(keys).size).toBe(1);
  expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
});

test("the same key sent again returns the same booking, not a second charge", async ({ page }) => {
  await startBooking(page);
  await saveGuest(page);
  const holdId = page.url().split("/").pop()!;
  const csrf = (await (await page.request.get("/api/auth/me")).json()).csrf_token;
  const origin = new URL(page.url()).origin;
  const send = () =>
    page.request.post(`/api/holds/${holdId}/payment`, {
      data: { simulate: "success" },
      headers: { "Idempotency-Key": "e2e-same-key-" + holdId, "X-CSRF-Token": csrf, Origin: origin },
    });
  const first = await (await send()).json();
  const second = await (await send()).json();
  expect(first.status).toBe("confirmed");
  expect(second.booking_reference).toBe(first.booking_reference);
});

test("a promo code that has expired is explained; a valid one discounts", async ({ page }) => {
  const { checkIn, checkOut } = stay();
  await chooseVilla(page, checkIn, checkOut);
  const summary = page.getByRole("complementary");
  await summary.getByLabel("Promo code").fill("monsoon15");
  await summary.getByRole("button", { name: "Apply" }).click();
  await expect(summary.getByRole("alert")).toBeVisible();
  await expect(summary.getByText("Total")).toBeVisible(); // still priced, without the code
  await summary.getByLabel("Promo code").fill("WELCOME10");
  await summary.getByRole("button", { name: "Apply" }).click();
  await expect(summary.getByText("WELCOME10 applied")).toBeVisible();
  await expect(summary.getByText("Promo WELCOME10 (10% off)")).toBeVisible();
});

test("cancelling releases the rooms and offers them again", async ({ page }) => {
  await startBooking(page);
  const holdId = page.url().split("/").pop()!;
  await page.getByRole("button", { name: "Cancel and release the rooms" }).click();
  await expect(page.getByRole("heading", { name: "You cancelled this booking" })).toBeVisible();
  expect((await (await page.request.get(`/api/holds/${holdId}`)).json()).status).toBe("released");
  await page.getByRole("link", { name: "Check these rooms again" }).click();
  await expect(page.getByRole("complementary")).toContainText("1 x Deluxe Room, Bed and Breakfast, 2 guests");
});

test("when the 10 minutes run out the page says so", async ({ page }) => {
  await page.clock.install();
  await startBooking(page);
  await page.clock.fastForward("10:30");
  await expect(page.getByRole("heading", { name: "Your 10 minutes are up" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Check these rooms again" })).toHaveAttribute("href", /sel=DLX\.BB\.1\.2/);
});

test("staff accounts cannot book", async ({ page }) => {
  const { checkIn, checkOut } = stay();
  await logIn(page, STAFF.email, STAFF.password);
  await chooseVilla(page, checkIn, checkOut);
  await expect(page.getByRole("button", { name: "Book these rooms" })).toBeDisabled();
  await expect(page.getByText("Staff accounts cannot make bookings.")).toBeVisible();
});

test("a booking page needs you to be signed in", async ({ page }) => {
  await page.goto("/bookings/CA-NOPE");
  await expect(page).toHaveURL(/\/login\?next=%2Fbookings%2FCA-NOPE/);
});
