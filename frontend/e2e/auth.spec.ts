import { expect, test } from "@playwright/test";
import { GUEST, STAFF, logIn, uniqueEmail } from "./helpers";

// Runs against the real backend, started with relaxed rate limits (README).

test("sign up, land signed in, log out", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Full name").fill("Meera Nair");
  await page.getByLabel("Email", { exact: true }).fill(uniqueEmail("signup"));
  await page.getByLabel("Password", { exact: true }).fill("a-long-password-1");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL("/");
  await expect(page.getByText("Meera", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page.getByRole("link", { name: "Log in" })).toBeVisible();
  // The session is really gone, not just hidden.
  expect((await page.request.get("/api/auth/me")).status()).toBe(401);
});

test("sign-up checks are shown next to the right field", async ({ page }) => {
  await page.goto("/signup");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Enter your name.")).toBeVisible();
  await expect(page.getByText("Use 10 to 128 characters.")).toBeVisible();
  await expect(page.getByText("Please agree so we can manage your bookings.")).toBeVisible();
  await expect(page).toHaveURL("/signup");
});

test("a taken email offers to log in instead", async ({ page }) => {
  await page.goto("/signup?next=/privacy");
  await page.getByLabel("Full name").fill("Someone Else");
  await page.getByLabel("Email", { exact: true }).fill(GUEST.email);
  await page.getByLabel("Password", { exact: true }).fill("a-long-password-1");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  const alert = page.locator("form").getByRole("alert");
  await expect(alert).toContainText("already exists");
  await expect(alert.getByRole("link", { name: "Log in instead" })).toHaveAttribute(
    "href",
    "/login?next=%2Fprivacy",
  );
});

test("the backend's own checks reach the field (invalid phone)", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Full name").fill("Meera Nair");
  await page.getByLabel("Email", { exact: true }).fill(uniqueEmail("phone"));
  await page.getByLabel("Password", { exact: true }).fill("a-long-password-1");
  await page.getByLabel("Phone (optional)").fill("call me");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Enter a valid phone number.")).toBeVisible();
});

test("wrong password gives one message, then logging in works", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(GUEST.email);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("Email or password is incorrect.");
  await logIn(page, GUEST.email, GUEST.password);
  await expect(page.getByText(GUEST.name, { exact: true })).toBeVisible();
});

test("a session survives a reload", async ({ page }) => {
  await logIn(page, GUEST.email, GUEST.password);
  await page.reload();
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
});

test("after logging in you return to where you were", async ({ page }) => {
  await logIn(page, GUEST.email, GUEST.password, "/privacy");
  await expect(page).toHaveURL("/privacy");
});

test("a crafted next link cannot send you to another site", async ({ page }) => {
  for (const next of ["https://evil.example/", "//evil.example/", "/\\evil.example"]) {
    await page.context().clearCookies();
    await logIn(page, GUEST.email, GUEST.password, next);
    await expect(page).toHaveURL("/");
  }
});

test("staff log in on the same page", async ({ page }) => {
  await logIn(page, STAFF.email, STAFF.password);
  await expect(page.getByText("Reservations", { exact: true })).toBeVisible();
});

test("too many attempts says how long to wait", async ({ page }) => {
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({
      status: 429,
      headers: { "Content-Type": "application/json", "Retry-After": "600" },
      body: JSON.stringify({ error: { code: "rate_limited", message: "Too many requests.", details: null } }),
    }),
  );
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(GUEST.email);
  await page.getByLabel("Password", { exact: true }).fill("whatever-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("Too many attempts. Try again in 10 minutes.");
});

test("the backend being down is explained", async ({ page }) => {
  await page.route("**/api/auth/login", (route) => route.abort("connectionrefused"));
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(GUEST.email);
  await page.getByLabel("Password", { exact: true }).fill("whatever-password");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.locator("form").getByRole("alert")).toContainText("could not reach our booking system");
});
