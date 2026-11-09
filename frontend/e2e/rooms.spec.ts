import { expect, test } from "@playwright/test";
import { addDays, openStay, soldOutFriday, todayInIndia } from "./helpers";

test("search from the home page shows rooms with prices for those dates", async ({ page }) => {
  const { checkIn, checkOut } = openStay();
  await page.goto("/");
  await page.getByLabel("Check-in").fill(checkIn);
  await page.getByLabel("Check-out").fill(checkOut);
  await page.getByLabel("Guests").fill("2");
  await page.getByRole("button", { name: "Check availability" }).click();
  await expect(page).toHaveURL(new RegExp(`/rooms\\?check_in=${checkIn}&check_out=${checkOut}&guests=2`));
  await expect(page.getByRole("heading", { name: "Deluxe Room" })).toBeVisible();
  await expect(page.getByText("left for these dates").first()).toBeVisible();
  await expect(page.getByText("GST included").first()).toBeVisible();
});

test("obvious date mistakes are caught before searching", async ({ page }) => {
  const { checkIn } = openStay();
  await page.goto("/");
  await page.getByLabel("Check-in").fill(checkIn);
  await page.getByLabel("Check-out").fill(addDays(checkIn, 20));
  await page.getByRole("button", { name: "Check availability" }).click();
  await expect(page.getByRole("form", { name: "Search rooms" }).getByRole("alert")).toHaveText(
    "Stays can be up to 14 nights.",
  );
  await expect(page).toHaveURL("/");
});

test("the backend's date rules are shown when a link breaks them", async ({ page }) => {
  const past = addDays(todayInIndia(), -3);
  await page.goto(`/rooms?check_in=${past}&check_out=${addDays(past, 1)}&guests=2`);
  await expect(page.getByRole("main").getByRole("alert")).toHaveText("Check-in cannot be in the past.");
});

test("sold-out dates say so and offer nothing to add", async ({ page }) => {
  const friday = soldOutFriday();
  await page.goto(`/rooms?check_in=${friday}&check_out=${addDays(friday, 2)}&guests=2`);
  // Streamed content can briefly exist twice (a hidden copy before it is swapped in).
  await expect(page.getByText("Everything is booked for these dates.").filter({ visible: true })).toBeVisible();
  await expect(page.getByText("Sold out for these dates").filter({ visible: true })).toHaveCount(5);
  await expect(page.getByRole("button", { name: /^Add / })).toHaveCount(0);
});

test("choose rooms of two types; the total comes from the backend and survives a reload", async ({ page }) => {
  const { checkIn, checkOut } = openStay();
  await page.goto(`/rooms?check_in=${checkIn}&check_out=${checkOut}&guests=4`);
  await page.getByRole("button", { name: "Add Plantation Villa, Bed and Breakfast" }).click();
  await page.getByRole("button", { name: "Add Deluxe Room, Room Only" }).click();
  const summary = page.getByRole("complementary");
  await expect(summary).toContainText("1 x Plantation Villa, Bed and Breakfast, 4 guests");
  await expect(summary).toContainText("1 x Deluxe Room, Room Only, 1 guest");
  await expect(summary.getByText("Total")).toBeVisible();
  const total = await summary.locator("dl > div").last().textContent();

  // The same choice priced directly by the API gives the same total.
  const api = await page.request.post("/api/quotes", {
    data: {
      check_in: checkIn,
      check_out: checkOut,
      lines: [
        { room_type: "PLV", rate_plan: "BB", units: 1, guests: 4 },
        { room_type: "DLX", rate_plan: "RO", units: 1, guests: 1 },
      ],
    },
    headers: { Origin: new URL(page.url()).origin },
  });
  const price = await api.json();
  const rupees = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 })
    .format(price.total_paise / 100);
  expect(total).toContain(rupees);

  await expect(page).toHaveURL(/sel=PLV\.BB\.1\.4%2CDLX\.RO\.1\.1/);
  await page.reload();
  await expect(page.getByRole("complementary")).toContainText("1 x Plantation Villa, Bed and Breakfast, 4 guests");
});

test("no more than four rooms in one booking", async ({ page }) => {
  const { checkIn, checkOut } = openStay();
  await page.goto(`/rooms?check_in=${checkIn}&check_out=${checkOut}&guests=8`);
  await page.getByRole("button", { name: "Add Deluxe Room, Room Only" }).click();
  const more = page.getByRole("group", { name: "Rooms of Deluxe Room" }).getByRole("button", { name: "One room more" });
  await more.click();
  await more.click();
  await more.click();
  await expect(page.getByRole("group", { name: "Rooms of Deluxe Room" })).toContainText("4 rooms");
  await expect(more).toBeDisabled();
  await expect(page.getByRole("button", { name: "Add Estate View Room, Room Only" })).toBeDisabled();
  await expect(page.getByText("That is the most rooms for one booking (4).")).toBeVisible();
});

test("a room's page lists its plans and hands a choice to the results", async ({ page }) => {
  const { checkIn, checkOut } = openStay();
  await page.goto(`/rooms/PLV?check_in=${checkIn}&check_out=${checkOut}&guests=2`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Plantation Villa");
  await page.getByRole("link", { name: "Choose Bed and Breakfast" }).click();
  await expect(page.getByRole("complementary")).toContainText("1 x Plantation Villa, Bed and Breakfast, 2 guests");
});

test("an unknown room shows the not-found page", async ({ page }) => {
  // The page streams, so the status is already 200 when the room turns out not to exist;
  // Next.js still shows the not-found page and marks it noindex (D-50).
  await page.goto("/rooms/NOPE");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await expect(page.locator('meta[name="robots"][content*="noindex"]')).not.toHaveCount(0);
});

test("on a phone the total stays in view while choosing", async ({ page, isMobile }) => {
  test.skip(!isMobile, "phone layout only");
  const { checkIn, checkOut } = openStay();
  await page.goto(`/rooms?check_in=${checkIn}&check_out=${checkOut}&guests=2`);
  await page.getByRole("button", { name: "Add Deluxe Room, Room Only" }).click();
  const bar = page.getByRole("link", { name: /1 room, ₹.*Review your stay/ });
  await expect(bar).toBeVisible();
  await bar.click();
  await expect(page.getByRole("heading", { name: "Your stay" })).toBeInViewport();
});
