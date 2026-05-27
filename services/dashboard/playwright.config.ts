import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config für vexa-dashboard E2E-Tests.
 *
 * Voraussetzungen:
 *   - Dashboard läuft auf localhost:3001 (npm run dev)
 *   - Vexa-Backend erreichbar (VEXA_API_URL, VEXA_ADMIN_API_KEY in .env.local)
 *   - KEIN SMTP → Direct-Login-Mode aktiv (kein Magic-Link-E-Mail nötig)
 *
 * Session-Strategie:
 *   global-setup.ts ruft POST /api/auth/send-magic-link auf (Direct-Login-Mode),
 *   erntet das vexa-token-Cookie und speichert den Browser-Storage-State unter
 *   playwright/.auth/user.json. Alle Tests laden diesen State → kein Login-Flow.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",

  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3001",
    storageState: "playwright/.auth/user.json",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    // Setup-Projekt: erzeugt Session-State (kein storageState hier)
    {
      name: "setup",
      testMatch: /global-setup\.ts/,
      use: { storageState: undefined },
    },
    // Haupt-Testprojekt: läuft nach Setup
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["setup"],
    },
  ],
});
