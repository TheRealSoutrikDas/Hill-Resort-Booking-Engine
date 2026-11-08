import { expect, test } from "@playwright/test";

test("home page shows the resort and its rooms from the API", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/CompanyA/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Chikkamagaluru");
  const rooms = page.locator("#rooms li");
  await expect(rooms).toHaveCount(5);
  await expect(page.getByRole("heading", { name: "Pool Villa" })).toBeVisible();
  await expect(page.getByText("Villa, for up to 6 guests")).toBeVisible();
});

test("the API is reached through this site, not directly", async ({ page }) => {
  const response = await page.request.get("/api/rooms");
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(body.rooms.length).toBe(5);
});

test("no sideways scrolling and the skip link works", async ({ page }) => {
  await page.goto("/");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
});

test("an unknown page says so", async ({ page }) => {
  const response = await page.goto("/no-such-page");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});
