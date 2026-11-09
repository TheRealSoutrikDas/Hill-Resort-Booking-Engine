import { expect, test, type Page } from "@playwright/test";
import { EVENTS, GM, GUEST, STAFF, addDays, adminTuesday, logIn, soldOutFriday } from "./helpers";

const inr = (paise: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(paise / 100);

async function openInventory(page: Page, from: string, to: string) {
  await logIn(page, STAFF.email, STAFF.password);
  await page.getByRole("link", { name: "Admin" }).click();
  await expect(page).toHaveURL("/admin/inventory");
  const toolbar = page.locator("main").getByLabel("From", { exact: true }).first();
  await toolbar.fill(from);
  await page.locator("main").getByLabel("To", { exact: true }).first().fill(to);
}

test("a price change reaches the guest's quote", async ({ page }) => {
  const night = adminTuesday(test.info().project.name);
  await openInventory(page, night, addDays(night, 1));
  const form = page.getByRole("form", { name: "Set a price" });
  await form.getByLabel("Room type").selectOption("DLX");
  await form.getByLabel("Rate plan").selectOption("RO");
  await form.getByLabel("From").fill(night);
  await form.getByLabel("To (inclusive)").fill(night);
  await form.getByLabel(/Price per room per night/).fill("12345");
  await form.getByRole("button", { name: "Set price" }).click();
  await expect(form.getByRole("status")).toHaveText("1 night changed.");
  await expect(page.getByTestId(`cell-DLX-${night}`)).toContainText("₹12,345");

  // The guest's price for that night comes from the new rate (GST added by the backend).
  const quote = await (
    await page.request.post("/api/quotes", {
      data: { check_in: night, check_out: addDays(night, 1), lines: [{ room_type: "DLX", rate_plan: "RO", units: 1, guests: 2 }] },
      headers: { Origin: new URL(page.url()).origin },
    })
  ).json();
  expect(quote.subtotal_paise).toBe(1_234_500);
  await page.goto(`/rooms/DLX?check_in=${night}&check_out=${addDays(night, 1)}&guests=2`);
  await expect(page.getByText(inr(quote.total_paise)).first()).toBeVisible();
});

test("blacking out asks first, closes the nights for guests, and reopening restores them", async ({ page }) => {
  const night = addDays(adminTuesday(test.info().project.name), 1); // the Wednesday
  await openInventory(page, night, night);
  const form = page.getByRole("form", { name: "Black out or reopen" });
  await form.getByLabel("From").fill(night);
  await form.getByLabel("To (inclusive)").fill(night);
  await form.getByRole("button", { name: "Black out" }).click();
  await expect(form.getByText("Black out 1 night for all room types?")).toBeVisible();
  await form.getByRole("button", { name: "Keep them open" }).click();
  await expect(page.getByTestId(`cell-DLX-${night}`)).not.toContainText("Closed");

  await form.getByRole("button", { name: "Black out" }).click();
  await form.getByRole("button", { name: "Yes, black out" }).click();
  await expect(form.getByRole("status")).toContainText("5 nights changed.");
  await expect(page.getByTestId(`cell-DLX-${night}`)).toContainText("Closed");

  const guestView = await page.context().newPage();
  await guestView.goto(`/rooms?check_in=${night}&check_out=${addDays(night, 1)}&guests=2`);
  await expect(guestView.getByText("Everything is booked for these dates.").filter({ visible: true })).toBeVisible();

  await form.getByLabel("Reopen").check();
  await form.getByRole("button", { name: "Reopen" }).click();
  await expect(form.getByRole("status")).toContainText("5 nights changed.");
  await guestView.reload();
  await expect(guestView.getByRole("button", { name: "Add Deluxe Room, Room Only" })).toBeVisible();
});

test("an allotment below what is sold is refused, night by night", async ({ page }) => {
  const friday = soldOutFriday();
  await openInventory(page, friday, addDays(friday, 1));
  const form = page.getByRole("form", { name: "Set the web allotment" });
  await form.getByLabel("Room type").selectOption("DLX");
  await form.getByLabel("From").fill(friday);
  await form.getByLabel("To (inclusive)").fill(addDays(friday, 1));
  await form.getByLabel(/Rooms for web booking/).fill("2");
  await form.getByRole("button", { name: "Set allotment" }).click();
  const alert = form.getByRole("alert");
  await expect(alert).toContainText("cannot go below what is already sold or held");
  await expect(alert.getByRole("listitem")).toHaveCount(2);
  await expect(alert).toContainText(`${friday}: 8 sold and 0 held, so at least 8`);
});

test("create a promo code, use it, switch it off", async ({ page }) => {
  const code = `E2E${Date.now().toString(36).toUpperCase()}`.slice(0, 32);
  await logIn(page, STAFF.email, STAFF.password);
  await page.goto("/admin/promos");
  const form = page.getByRole("form", { name: "Create a promo code" });
  await form.getByLabel(/^Code/).fill(code.toLowerCase());
  await form.getByLabel(/^Percent off/).fill("15");
  await form.getByRole("button", { name: "Create code" }).click();
  await expect(form.getByRole("status")).toHaveText(`${code} created.`);
  const row = page.getByRole("row", { name: new RegExp(`^${code}`) });
  await expect(row).toContainText("Works");

  const night = adminTuesday(test.info().project.name);
  const quote = (promo: string) =>
    page.request.post("/api/quotes", {
      data: { check_in: night, check_out: addDays(night, 1), promo_code: promo, lines: [{ room_type: "EVR", rate_plan: "RO", units: 1, guests: 2 }] },
      headers: { Origin: new URL(page.url()).origin },
    });
  expect((await (await quote(code)).json()).promo.percent_off).toBe(15);

  await row.getByRole("button", { name: `Switch off ${code}` }).click();
  await expect(row).toContainText("Switched off");
  expect((await quote(code)).status()).toBe(422);
});

test("a limit below the uses already made is refused, with the lowest allowed", async ({ page }) => {
  await logIn(page, STAFF.email, STAFF.password);
  await page.goto("/admin/promos");
  const row = page.getByRole("row", { name: /^COFFEE20/ });
  await expect(row).toContainText("Limit reached");
  await row.getByRole("button", { name: "Edit COFFEE20" }).click();
  await row.getByLabel(/^Limit/).fill("3");
  await row.getByRole("button", { name: "Save" }).click();
  await expect(row.getByRole("alert")).toContainText("The lowest limit allowed now is 5.");
});

test("the daily export downloads a CSV", async ({ page }) => {
  await logIn(page, STAFF.email, STAFF.password);
  await page.goto("/admin/export");
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: /^Download bookings-\d{4}-\d{2}-\d{2}\.csv$/ }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^bookings-\d{4}-\d{2}-\d{2}\.csv$/);
  const text = await (await import("node:fs/promises")).readFile((await file.path())!, "utf8");
  expect(text.split("\n")[0]).toMatch(/^booking_id,line_number,status,guest_name/);
});

test("the GM has Admin; the events team and guests do not", async ({ page }) => {
  await logIn(page, GM.email, GM.password);
  await expect(page.getByRole("link", { name: "Admin" })).toBeVisible();

  await page.context().clearCookies();
  await logIn(page, EVENTS.email, EVENTS.password);
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
  await page.goto("/admin/inventory");
  await expect(page.getByText("Admin is for the reservations team and the GM.")).toBeVisible();

  await page.context().clearCookies();
  await logIn(page, GUEST.email, GUEST.password);
  await page.goto("/admin/promos");
  await expect(page.getByText("This page is for CompanyA staff.")).toBeVisible();

  await page.context().clearCookies();
  await page.goto("/admin/export");
  await expect(page).toHaveURL(/\/login\?next=%2Fadmin%2Fexport/);
});
