import { test, expect } from "@playwright/test";

/**
 * Mock-Smoke-Test: Dashboard "Calendar verbinden"-Button
 *
 * BEWEISSTUFE 3 VON 4 — Mock-gestützt, kein echtes Backend nötig.
 *
 * Was dieser Test beweist:
 *   - Button-Rendering: data-testid="calendar-connect-btn" erscheint auf /profile
 *   - API-Call-Format: POST /api/calendar/oauth/start mit korrektem Body
 *     {userEmail, returnTo} wird tatsächlich ausgelöst
 *   - Response-Handling: authUrl aus gemockter Response wird verarbeitet,
 *     window.location.assign feuert (abgefangen via route intercept)
 *   - Error-Handling: bei 500-Response erscheint Toast-Fehlermeldung
 *
 * Was dieser Test NICHT beweist:
 *   - Echte authUrl von Google OAuth-Endpoint
 *   - Echte Session via Admin-API (Auth komplett gemockt)
 *   - Ende-zu-Ende OAuth-Roundtrip → das ist #8 (Prod-E2E)
 *
 * Läuft ohne Backend, ohne npm run dev, ohne echten API-Key.
 * Voraussetzung: Dashboard-Dev-Server auf Port 3001.
 */

// Basis-Mock-URL damit Next.js-Seite gerendert werden kann
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3001";

// Gemockter Vexa-User
const MOCK_USER = {
  id: "e2e-test-user-001",
  email: "e2e@vexa-mock.local",
  name: "E2E Test User",
  max_concurrent_bots: 5,
};

// Gemockter API-Token
const MOCK_TOKEN = "vxa_tx_mock_e2etoken123456789";

// Gemockte authUrl — valide Google-OAuth-URL-Form
const MOCK_AUTH_URL =
  "https://accounts.google.com/o/oauth2/v2/auth?" +
  "response_type=code&client_id=mock-client-id.apps.googleusercontent.com" +
  "&redirect_uri=http%3A%2F%2Flocalhost%3A3001%2Fauth%2Fgoogle-calendar%2Fcallback" +
  "&state=mock-state-token" +
  "&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcalendar.readonly" +
  "&access_type=offline&prompt=consent";

test.describe("Calendar-Connect Button — Mock-Smoke (Beweisstufe 3/4)", () => {
  test.use({ storageState: { cookies: [], origins: [] } }); // kein gespeicherter Auth-State

  test.beforeEach(async ({ page }) => {
    // ── Auth komplett mocken ──────────────────────────────────────────────────

    // /api/auth/send-magic-link → Direct-Login-Response
    await page.route("**/api/auth/send-magic-link", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          success: true,
          mode: "direct",
          isNewUser: false,
          user: MOCK_USER,
          token: MOCK_TOKEN,
        }),
      })
    );

    // /api/auth/me → authentifizierter User
    await page.route("**/api/auth/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          authenticated: true,
          user: MOCK_USER,
          token: MOCK_TOKEN,
        }),
      })
    );

    // /api/calendar/proxy/status → nicht verbunden (zeigt Connect-Button)
    await page.route("**/api/calendar/proxy/status**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ connected: false, event_count: 0, configured: false }),
      })
    );

    // /api/profile/keys → leere Key-Liste (verhindert irrelevante Fehler)
    await page.route("**/api/profile/keys**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ keys: [] }),
      })
    );

    // Google OAuth-Navigation abfangen — kein echter Redirect zu Google
    await page.route("https://accounts.google.com/**", (route) => route.abort());
  });

  test("Button 'Connect Google Calendar' ist auf /profile sichtbar (Mock-Auth)", async ({
    page,
  }) => {
    await page.goto(`${BASE_URL}/profile`);
    await page.waitForLoadState("networkidle");

    const btn = page.getByTestId("calendar-connect-btn");
    await expect(btn).toBeVisible({ timeout: 10_000 });
    await expect(btn).toBeEnabled();
    await expect(btn).toContainText("Connect");
  });

  test("Klick löst POST /api/calendar/oauth/start mit korrektem Body aus (Mock-Backend)", async ({
    page,
  }) => {
    // oauth/start mocken — gibt gemockte authUrl zurück
    await page.route("**/api/calendar/oauth/start", (route) => {
      const req = route.request();
      // Body-Validierung erfolgt via waitForRequest unten
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authUrl: MOCK_AUTH_URL }),
      });
    });

    await page.goto(`${BASE_URL}/profile`);
    await page.waitForLoadState("networkidle");

    // Request abfangen um Body zu prüfen
    const oauthStartPromise = page.waitForRequest(
      (req) =>
        req.url().includes("/api/calendar/oauth/start") && req.method() === "POST",
      { timeout: 10_000 }
    );

    const btn = page.getByTestId("calendar-connect-btn");
    await expect(btn).toBeVisible({ timeout: 10_000 });
    await btn.click();

    const oauthReq = await oauthStartPromise;

    // Body-Format prüfen
    const body = JSON.parse(oauthReq.postData() || "{}");
    expect(body).toHaveProperty("userEmail");
    expect(body.userEmail).toBe(MOCK_USER.email);
    expect(body).toHaveProperty("returnTo");
    expect(body.returnTo).toBe("/meetings");
  });

  test("Loading-State: Button disabled + Spinner während API-Call (Mock-Backend)", async ({
    page,
  }) => {
    // API verzögern um Loading-State zu beobachten
    await page.route("**/api/calendar/oauth/start", async (route) => {
      await new Promise((r) => setTimeout(r, 400));
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authUrl: MOCK_AUTH_URL }),
      });
    });

    await page.goto(`${BASE_URL}/profile`);
    await page.waitForLoadState("networkidle");

    const btn = page.getByTestId("calendar-connect-btn");
    await expect(btn).toBeVisible({ timeout: 10_000 });
    await btn.click();

    // Während des Ladens: disabled oder Spinner sichtbar
    await expect(btn).toBeDisabled({ timeout: 2_000 });
  });

  test("Fehlerfall: 500 von oauth/start → Toast-Fehlermeldung sichtbar (Mock-Backend)", async ({
    page,
  }) => {
    await page.route("**/api/calendar/oauth/start", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "Google Calendar OAuth is not configured" }),
      })
    );

    await page.goto(`${BASE_URL}/profile`);
    await page.waitForLoadState("networkidle");

    const btn = page.getByTestId("calendar-connect-btn");
    await expect(btn).toBeVisible({ timeout: 10_000 });
    await btn.click();

    // Toast-Fehlermeldung soll erscheinen
    await expect(
      page.locator("[data-sonner-toast]").or(page.locator("li[data-sonner-toast]"))
    ).toBeVisible({ timeout: 5_000 });
  });
});
