import { test as setup, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

/**
 * Global Setup: erzeugt eine authentifizierte Browser-Session.
 *
 * Nutzt den Direct-Login-Mode des Dashboards:
 * Wenn SMTP nicht konfiguriert ist, gibt POST /api/auth/send-magic-link
 * direkt ein vexa-token-Cookie zurück — kein E-Mail-Klick nötig.
 *
 * Das Cookie wird als Playwright-Storage-State gespeichert und von
 * allen nachfolgenden Tests als `storageState` geladen.
 */

const AUTH_FILE = path.join(__dirname, "../playwright/.auth/user.json");
const TEST_EMAIL = process.env.E2E_TEST_EMAIL || "test@vexa-e2e.local";
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3001";

setup("authenticate", async ({ page }) => {
  // Prüfen ob Auth-State bereits existiert und frisch genug ist (< 20min alt)
  if (fs.existsSync(AUTH_FILE)) {
    const stat = fs.statSync(AUTH_FILE);
    const ageMs = Date.now() - stat.mtimeMs;
    if (ageMs < 20 * 60 * 1000) {
      console.log("[setup] Auth-State noch frisch, überspringe Login.");
      return;
    }
  }

  // Direct-Login-Mode: POST /api/auth/send-magic-link ohne SMTP
  const loginResp = await page.request.post(`${BASE_URL}/api/auth/send-magic-link`, {
    data: { email: TEST_EMAIL },
    headers: { "Content-Type": "application/json" },
  });

  if (!loginResp.ok()) {
    const body = await loginResp.text();
    throw new Error(
      `Direct-Login fehlgeschlagen (${loginResp.status()}): ${body}\n` +
        "Sicherstellen: Dashboard läuft, VEXA_ADMIN_API_KEY gesetzt, SMTP_HOST NICHT gesetzt."
    );
  }

  const data = await loginResp.json();
  if (!data.success || data.mode !== "direct") {
    throw new Error(
      `Unerwartete Login-Antwort: ${JSON.stringify(data)}\n` +
        "SMTP_HOST darf für E2E-Tests NICHT gesetzt sein (Direct-Login-Mode erforderlich)."
    );
  }

  // Cookie wurde server-seitig gesetzt — Browser-State jetzt speichern
  await page.goto(`${BASE_URL}/profile`);
  // Warten bis Auth-Check durch ist (Loader verschwindet)
  await page.waitForSelector('[data-testid="profile-page"], h1:has-text("Profile")', {
    timeout: 10_000,
  });

  await page.context().storageState({ path: AUTH_FILE });
  console.log(`[setup] Auth-State gespeichert für ${TEST_EMAIL}`);
});
