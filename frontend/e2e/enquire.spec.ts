import { expect, request, test } from "@playwright/test";
import { GUEST, STAFF, logIn } from "./helpers";

const MESSAGE = "We are planning a wedding in February 2027 for about 150 guests. Is the estate free?";

test("send an enquiry, get a reference, and it reaches the staff inbox", async ({ page, baseURL }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Enquire" }).click();
  await page.getByLabel("Your name").fill("Anika Shetty");
  await page.getByLabel("Email", { exact: true }).fill("anika@example.com");
  await page.getByLabel("Your message").fill(MESSAGE);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Send enquiry" }).click();

  const received = page.getByRole("region", { name: "Thank you" });
  await expect(received).toContainText("Thank you. Our team will reply to you soon.");
  const reference = (await received.locator("strong").textContent())!.trim();
  expect(reference).toMatch(/^ENQ-\d+$/);
  await expect(received).not.toContainText("wedding"); // no classification is shown (A-122)

  // Staff can see it, with the message as written.
  const staff = await request.newContext({ baseURL, extraHTTPHeaders: { Origin: new URL(baseURL!).origin } });
  await staff.post("/api/auth/login", { data: { email: STAFF.email, password: STAFF.password } });
  const detail = await (await staff.get(`/api/enquiries/${reference}`)).json();
  expect(detail.message).toBe(MESSAGE);
  expect(detail.contact_email).toBe("anika@example.com");
  await staff.dispose();

  await page.getByRole("button", { name: "Send another enquiry" }).click();
  await expect(page.getByLabel("Your message")).toHaveValue("");
  await expect(page.getByLabel("Your name")).toHaveValue("");
});

test("an email or a phone is needed, and consent", async ({ page }) => {
  await page.goto("/enquire");
  await page.getByLabel("Your name").fill("Anika Shetty");
  await page.getByLabel("Your message").fill(MESSAGE);
  await page.getByRole("button", { name: "Send enquiry" }).click();
  await expect(page.getByText("Please give an email or a phone number so we can reply.")).toHaveCount(2);
  await expect(page.getByText("Please agree so we can reply to you.")).toBeVisible();
  await expect(page).toHaveURL("/enquire");
});

test("a phone number alone is enough", async ({ page }) => {
  await page.goto("/enquire");
  await page.getByLabel("Your name").fill("Ravi Kumar");
  await page.getByLabel("Phone", { exact: true }).fill("+91 98450 12345");
  await page.getByLabel("Your message").fill("Do you have a room for two on Saturday?");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Send enquiry" }).click();
  await expect(page.getByRole("region", { name: "Thank you" })).toContainText("ENQ-");
});

test("the message has a live limit of 2000 characters", async ({ page }) => {
  await page.goto("/enquire");
  await expect(page.getByText("2000 characters left")).toBeVisible();
  await page.getByLabel("Your message").fill("x".repeat(2005));
  await expect(page.getByText("5 characters over the limit")).toBeVisible();
  await page.getByRole("button", { name: "Send enquiry" }).click();
  await expect(page.getByText("Please keep your message under 2000 characters.")).toBeVisible();
});

test("the backend's checks reach the right field (invalid email)", async ({ page }) => {
  await page.goto("/enquire");
  await page.getByLabel("Your name").fill("Anika Shetty");
  await page.getByLabel("Email", { exact: true }).fill("not-an-email");
  await page.getByLabel("Your message").fill(MESSAGE);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Send enquiry" }).click();
  await expect(page.getByText("Please check your email address.")).toBeVisible();
});

test("signed-in guests find their name and email filled in", async ({ page }) => {
  await logIn(page, GUEST.email, GUEST.password, "/enquire");
  // Next.js keeps the page just left (the login form) mounted but hidden, so look at
  // visible fields only.
  await expect(page.getByLabel("Your name")).toHaveValue("Demo Guest");
  await expect(page.getByLabel("Email", { exact: true }).filter({ visible: true })).toHaveValue(GUEST.email);
});

test("too many enquiries says how long to wait", async ({ page }) => {
  await page.route("**/api/enquiries", (route) =>
    route.fulfill({
      status: 429,
      headers: { "Content-Type": "application/json", "Retry-After": "1800" },
      body: JSON.stringify({ error: { code: "rate_limited", message: "Too many requests.", details: null } }),
    }),
  );
  await page.goto("/enquire");
  await page.getByLabel("Your name").fill("Anika Shetty");
  await page.getByLabel("Email", { exact: true }).fill("anika@example.com");
  await page.getByLabel("Your message").fill(MESSAGE);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Send enquiry" }).click();
  await expect(page.locator("form").getByRole("alert")).toHaveText("Too many attempts. Try again in 30 minutes.");
});

test("sold-out dates point to the enquiry form", async ({ page }) => {
  const { soldOutFriday, addDays } = await import("./helpers");
  const friday = soldOutFriday();
  await page.goto(`/rooms?check_in=${friday}&check_out=${addDays(friday, 2)}&guests=2`);
  await page.getByRole("link", { name: "send us an enquiry" }).filter({ visible: true }).click();
  await expect(page).toHaveURL("/enquire");
});
