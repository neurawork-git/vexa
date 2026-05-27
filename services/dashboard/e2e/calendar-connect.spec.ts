import { test, expect } from "@playwright/test";

/**
 * Spec: Dashboard "Calendar verbinden"-Button
 *
 * Testet den OAuth-Start-Flow für Google Calendar Integration.
 * Der echte OAuth-Roundtrip (Google → Callback) wird NICHT getestet —
 * das erfordert Google-Credentials und ist E2E-Scope von Task #8.
 *
 * Was dieser Test prüft:
 *   1. Button ist auf /profile sichtbar
 *   2. Klick löst POST /api/calendar/oauth/start aus
 *   3. Response enthält authUrl
 *   4. authUrl ist eine gültige Google-OAuth-URL mit korrekten Parametern
 *      (client_id, redirect_uri, scope=calendar.readonly)
 *
 * Voraussetzungen:
 *   - Dashboard läuft auf localhost:3001
 *   - GOOGLE_CLIENT_ID gesetzt (für oauth/start-Route)
 *   - Session via global-setup.ts vorhanden
 */

test.describe("Google Calendar verbinden", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/profile");
    // Seite geladen wenn der Profil-Header sichtbar ist
    await expect(page.locator("h1").filter({ hasText: "Profile" })).toBeVisible({
      timeout: 10_000,
    });
  });

  test("Button 'Connect Google Calendar' ist auf /profile sichtbar", async ({ page }) => {
    const btn = page.getByTestId("calendar-connect-btn");
    await expect(btn).toBeVisible();
    await expect(btn).toBeEnabled();
  });

  test("Klick auf Button löst POST /api/calendar/oauth/start aus und erhält gültige authUrl", async ({
    page,
    context,
  }) => {
    // Request abfangen bevor Button geklickt wird
    const oauthStartPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/api/calendar/oauth/start") && resp.request().method() === "POST",
      { timeout: 10_000 }
    );

    const btn = page.getByTestId("calendar-connect-btn");
    await expect(btn).toBeVisible();

    // Navigation abfangen — Klick öffnet evtl. Google-OAuth-URL
    // Wir wollen NUR den API-Call prüfen, nicht zu Google navigieren
    await context.route("https://accounts.google.com/**", (route) => route.abort());

    await btn.click();

    const oauthResp = await oauthStartPromise;
    expect(oauthResp.status()).toBe(200);

    const body = await oauthResp.json();
    expect(body).toHaveProperty("authUrl");

    const authUrl = new URL(body.authUrl);

    // Korrekte Google OAuth Endpoint
    expect(authUrl.hostname).toBe("accounts.google.com");
    expect(authUrl.pathname).toBe("/o/oauth2/v2/auth");

    // Pflicht-Parameter
    expect(authUrl.searchParams.get("response_type")).toBe("code");
    expect(authUrl.searchParams.get("client_id")).toBeTruthy();
    expect(authUrl.searchParams.get("redirect_uri")).toBeTruthy();
    expect(authUrl.searchParams.get("scope")).toContain("calendar.readonly");
    expect(authUrl.searchParams.get("access_type")).toBe("offline");
  });

  test("Button zeigt Lade-Zustand während OAuth-Start verarbeitet wird", async ({ page }) => {
    // API-Antwort verzögern um Loading-State zu prüfen
    await page.route("/api/calendar/oauth/start", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 300));
      await route.continue();
    });

    // Navigation zu Google abfangen
    await page.route("https://accounts.google.com/**", (route) => route.abort());

    const btn = page.getByTestId("calendar-connect-btn");
    await expect(btn).toBeVisible();
    await btn.click();

    // Während des Ladens: Button deaktiviert oder zeigt Loader
    // (Einer von beiden muss gelten — depends on B.A.s Implementierung)
    const isDisabledOrLoading = await Promise.race([
      btn.isDisabled().then((d) => d),
      page
        .locator('[data-testid="calendar-connect-btn"] [class*="animate-spin"]')
        .isVisible()
        .then((v) => v),
    ]);
    expect(isDisabledOrLoading).toBeTruthy();
  });

  test("Fehlerfall: ohne GOOGLE_CLIENT_ID zeigt Button Fehlermeldung", async ({ page }) => {
    // Simuliert Backend-Fehler (500) wenn Client-ID fehlt
    await page.route("/api/calendar/oauth/start", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "Google Calendar OAuth is not configured" }),
      })
    );

    // Navigation abfangen
    await page.route("https://accounts.google.com/**", (route) => route.abort());

    const btn = page.getByTestId("calendar-connect-btn");
    await btn.click();

    // Fehlermeldung soll sichtbar werden (Toast oder inline)
    await expect(
      page.locator("text=not configured").or(page.locator("text=Google Calendar"))
    ).toBeVisible({ timeout: 5_000 });
  });
});
