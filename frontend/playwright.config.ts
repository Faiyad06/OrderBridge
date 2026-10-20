import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

// Use OB_CHROMIUM or the container's preinstalled Chromium if present; otherwise Playwright's own
// browser (install once with `npx playwright install chromium`).
const chromium = process.env.OB_CHROMIUM ?? (existsSync("/opt/pw-browsers/chromium") ? "/opt/pw-browsers/chromium" : undefined);

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.OB_BASE_URL ?? "http://127.0.0.1:8000",
    launchOptions: chromium ? { executablePath: chromium } : {},
    viewport: { width: 1360, height: 900 },
  },
});
