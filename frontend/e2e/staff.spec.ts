import { expect, test, type Page } from "@playwright/test";
import { EVENTS, GM, GUEST, STAFF, logIn, openStay, sendEnquiry } from "./helpers";

// The backend runs with CLASSIFIER_BACKEND=keyword for these tests (README), so routing
// is deterministic. Each test sends its own enquiry through the public API.

function villaMessage() {
  const { checkIn, checkOut } = openStay();
  const fmt = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  return `Is a villa free ${fmt(checkIn)} to ${fmt(checkOut)} for 2 adults?`;
}

async function openEnquiry(page: Page, reference: string) {
  await page.goto(`/staff/enquiries/${reference}`);
  await expect(page.getByRole("heading", { level: 1, name: reference })).toBeVisible();
}

test("each team opens on its own lane, and a new enquiry is in it", async ({ page }) => {
  await page.goto("/");
  const ref = await sendEnquiry(page, villaMessage(), "Lane Tester");
  await logIn(page, STAFF.email, STAFF.password);
  await page.getByRole("link", { name: "Staff" }).click();
  await expect(page.getByRole("tab", { name: /Room booking/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel").getByRole("link", { name: ref })).toBeVisible();

  await page.context().clearCookies();
  await logIn(page, EVENTS.email, EVENTS.password, "/staff/inbox");
  await expect(page.getByRole("tab", { name: /Wedding/ })).toHaveAttribute("aria-selected", "true");

  await page.context().clearCookies();
  await logIn(page, GM.email, GM.password, "/staff/inbox");
  await expect(page.getByRole("tab", { name: /Complaint/ })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: /Unsorted/ }).click();
  await expect(page).toHaveURL(/tab=unsorted/);
});

test("the message sits beside what was understood", async ({ page }) => {
  await page.goto("/");
  const message = villaMessage();
  const ref = await sendEnquiry(page, message);
  await logIn(page, STAFF.email, STAFF.password);
  await openEnquiry(page, ref);
  const msg = page.getByRole("region", { name: "Message" });
  await expect(msg).toContainText(message);
  const understood = page.getByRole("region", { name: "What was understood" });
  await expect(understood).toContainText("Room booking");
  await expect(understood).toContainText("Check-in");
  await understood.getByText("What each check said").click();
  await expect(understood).toContainText("Keyword check");
});

test("an Unsorted enquiry says why", async ({ page }) => {
  await page.goto("/");
  const ref = await sendEnquiry(page, "Do you sell your coffee beans online?");
  await logIn(page, STAFF.email, STAFF.password);
  await openEnquiry(page, ref);
  await expect(page.getByText("Why it is in Unsorted")).toBeVisible();
  await expect(page.getByText("It is not a booking, event or complaint.")).toBeVisible();
});

test("correcting the category moves the lane and records who did it", async ({ page }) => {
  await page.goto("/");
  const ref = await sendEnquiry(page, "Planning our wedding in February 2027 for 150 guests.");
  await logIn(page, EVENTS.email, EVENTS.password);
  await openEnquiry(page, ref);
  const correct = page.getByRole("region", { name: "Correct" });
  await correct.getByLabel("Category").selectOption("corporate_offsite");
  await correct.getByRole("button", { name: "Save correction" }).click();
  await expect(page.getByRole("region", { name: "What was understood" })).toContainText("Offsite");
  await expect(page.getByRole("region", { name: "History" })).toContainText(
    "Events Team corrected category from Wedding to Company offsite",
  );
  // A correction ends re-runs, so nothing overwrites a person's work (A-125).
  await expect(page.getByRole("region", { name: "Run the classification again" })).toHaveCount(0);
});

test("moving to another lane keeps the category", async ({ page }) => {
  await page.goto("/");
  const ref = await sendEnquiry(page, villaMessage());
  await logIn(page, STAFF.email, STAFF.password);
  await openEnquiry(page, ref);
  const route = page.getByRole("region", { name: "Move to another lane" });
  await route.getByLabel("Lane").selectOption("unsorted");
  await route.getByRole("button", { name: "Move" }).click();
  const understood = page.getByRole("region", { name: "What was understood" });
  await expect(understood).toContainText("Unsorted");
  await expect(understood).toContainText("Room booking"); // the category
  await expect(page.getByRole("region", { name: "History" })).toContainText("moved");
});

test("a reply cannot be sent while placeholders remain; once filled, it is recorded", async ({ page }) => {
  await page.goto("/");
  const ref = await sendEnquiry(page, "Can you share wedding packages and photos of the lawn?");
  await logIn(page, EVENTS.email, EVENTS.password);
  await openEnquiry(page, ref);
  const reply = page.getByRole("region", { name: "Reply" });
  await expect(reply.getByRole("list", { name: "Placeholders still in the reply" })).toBeVisible();
  await expect(reply.getByRole("button", { name: "Send reply" })).toBeDisabled();
  const text = "Dear guest,\n\nThank you. Our events team will send our wedding packages today.\n\nEvents team";
  await reply.getByLabel("Reply text").fill(text);
  await expect(reply.getByRole("button", { name: "Send reply" })).toBeEnabled();
  await reply.getByRole("button", { name: "Send reply" }).click();
  const sent = page.getByRole("region", { name: "Reply sent" });
  await expect(sent).toContainText("Simulated: nothing was sent to the guest.");
  await expect(sent).toContainText("our wedding packages today");
});

test("running the classification again is recorded", async ({ page }) => {
  await page.goto("/");
  const ref = await sendEnquiry(page, villaMessage());
  await logIn(page, STAFF.email, STAFF.password);
  await openEnquiry(page, ref);
  await page.getByRole("button", { name: "Run again" }).click();
  await expect(page.getByRole("region", { name: "History" })).toContainText("ran the classification again");
});

test("only the GM approves a classification", async ({ page }) => {
  await page.goto("/");
  const ref = await sendEnquiry(page, villaMessage());
  await logIn(page, STAFF.email, STAFF.password);
  await openEnquiry(page, ref);
  await expect(page.getByRole("button", { name: "Approve classification" })).toHaveCount(0);

  await page.context().clearCookies();
  await logIn(page, GM.email, GM.password);
  await openEnquiry(page, ref);
  await page.getByRole("button", { name: "Approve classification" }).click();
  await expect(page.getByRole("region", { name: "Approved" })).toContainText("General Manager");
  await expect(page.getByRole("region", { name: "Correct" })).toHaveCount(0); // fixed now
});

test("a complaint alerts the GM, who acknowledges it; others only see it", async ({ page }) => {
  await page.goto("/");
  const ref = await sendEnquiry(page, "The room was dirty and nobody answered the phone at night.");
  await logIn(page, STAFF.email, STAFF.password, "/staff/alerts");
  const row = page.getByRole("listitem").filter({ has: page.getByRole("link", { name: ref }) });
  await expect(row).toContainText("Open");
  await expect(row.getByRole("button", { name: /Acknowledge/ })).toHaveCount(0);

  await page.context().clearCookies();
  await logIn(page, GM.email, GM.password, "/staff/alerts");
  await row.getByRole("button", { name: `Acknowledge alert for ${ref}` }).click();
  await expect(row).toContainText("Acknowledged by General Manager");
});

test("metrics show counts out of totals", async ({ page }) => {
  await logIn(page, GM.email, GM.password, "/staff/metrics");
  await expect(page.getByRole("heading", { name: "How routing went" })).toBeVisible();
  await expect(page.getByText("Sent to Unsorted")).toBeVisible();
  await expect(page.getByText(/ of \d+ \(\d+%\)|none yet/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "AI accuracy, checked by the GM" })).toBeVisible();
});

test("the staff pages are for staff", async ({ page }) => {
  await logIn(page, GUEST.email, GUEST.password, "/staff/inbox");
  await expect(page.getByText("This page is for CompanyA staff.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Staff" })).toHaveCount(0);
  await page.context().clearCookies();
  await page.goto("/staff/metrics");
  await expect(page).toHaveURL(/\/login\?next=%2Fstaff%2Fmetrics/);
});
