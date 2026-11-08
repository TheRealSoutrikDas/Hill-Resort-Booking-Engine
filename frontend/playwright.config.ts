import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the real backend (A-156). Before running:
//   backend:  uvicorn app.main:create_app --factory   (seeded: python -m app.seed --reset)
//   frontend: npm run build                            (Playwright starts `npm run start`)
const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "npm run start",
    url: baseURL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
