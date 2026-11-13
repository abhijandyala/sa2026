import { defineConfig, devices } from "@playwright/test";

// Browser check of the judge path (handbook p.17). First run needs: npx playwright install chromium
export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  use: { baseURL: "http://localhost:4173" },
  webServer: {
    command: "npm run build && npx vite preview --port 4173 --strictPort",
    port: 4173,
    reuseExistingServer: true,
  },
  projects: [
    { name: "laptop-1280x720", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 720 } } },
    { name: "phone-375", use: { ...devices["Pixel 5"], viewport: { width: 375, height: 812 } } },
  ],
});
