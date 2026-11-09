import { expect, test, type Page } from "@playwright/test";

// Every link goes somewhere real and every photo loads with the right alt text (D-57,
// A-196). Public pages only: the signed-in pages are covered by their own specs.
const PUBLIC_PAGES = ["/", "/rooms", "/rooms/PLV", "/login", "/signup", "/enquire", "/find-booking", "/privacy"];
const ROOM_CODES = ["DLX", "EVR", "FST", "PLV", "PPV"];

async function visibleImagesLoad(page: Page) {
  const images = page.locator("img").filter({ visible: true });
  const count = await images.count();
  for (let i = 0; i < count; i++) {
    const image = images.nth(i);
    await image.scrollIntoViewIfNeeded();
    // A missing alt attribute is an error; an empty one marks a decorative photo.
    expect(await image.getAttribute("alt"), `alt on image ${i}`).not.toBeNull();
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0), {
        message: `image ${i} on ${page.url()} loads`,
      })
      .toBe(true);
  }
  return count;
}

for (const path of PUBLIC_PAGES) {
  test(`links on ${path} lead somewhere and its photos load`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await visibleImagesLoad(page);

    const hrefs = await page
      .locator("a[href]")
      .filter({ visible: true })
      .evaluateAll((links) => links.map((a) => a.getAttribute("href") ?? ""));
    expect(hrefs.length).toBeGreaterThan(0);
    for (const href of new Set(hrefs)) {
      if (href.startsWith("#")) {
        // An in-page link needs its target on this page.
        await expect(page.locator(`[id="${href.slice(1)}"]`), `target of ${href}`).toHaveCount(1);
        continue;
      }
      expect(href.startsWith("/"), `${href} stays on this site`).toBe(true);
      const response = await page.request.get(href.split("#")[0]);
      expect(response.status(), `${href} from ${path}`).toBeLessThan(400);
    }
  });
}

test("home page shows a photo of the estate and one for each room type", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("img", { name: "Coffee plantation under shade trees in morning fog" })).toBeVisible();
  const roomPhotos = page.locator("#rooms li img").filter({ visible: true });
  await expect(roomPhotos).toHaveCount(5);
  await visibleImagesLoad(page);
});

for (const code of ROOM_CODES) {
  test(`room page ${code} shows its three photos, labelled as samples`, async ({ page }) => {
    await page.goto(`/rooms/${code}`);
    const photos = page.getByRole("main").locator("img").filter({ visible: true });
    await expect(photos).toHaveCount(3);
    for (const alt of await photos.evaluateAll((imgs) => imgs.map((i) => i.getAttribute("alt")))) {
      expect(alt, "room photos describe what they show").toBeTruthy();
    }
    await expect(page.getByText("Sample photos, not of CompanyA.").filter({ visible: true })).toBeVisible();
    await visibleImagesLoad(page);
  });
}

test("photos are not links or buttons", async ({ page }) => {
  await page.goto("/");
  const clickablePhotos = await page.locator("a img, button img").count();
  expect(clickablePhotos).toBe(0);
});

test("the footer says the photos are samples", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("contentinfo")).toContainText("Photos are illustrative samples from Unsplash, not of CompanyA.");
});
