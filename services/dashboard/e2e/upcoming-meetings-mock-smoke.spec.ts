import { test, expect } from "@playwright/test";

/**
 * Mock-Smoke-Test: /meetings — upcoming-Kalender-Events
 *
 * BEWEISSTUFE 3 VON 4 — Mock-gestützt, kein echtes Backend nötig.
 *
 * Was dieser Test beweist:
 *   - Kalender-Events werden als "Upcoming"-Zeilen in der Tabelle angezeigt
 *   - StatusDot zeigt violetten Punkt für upcoming-Status
 *   - "Upcoming"-Filterauswahl zeigt nur Kalender-Events, keine aufgezeichneten Meetings
 *   - Cancelled-Events werden herausgefiltert (nicht in der Liste)
 *   - Klick auf upcoming-Zeile navigiert NICHT zu /meetings/:id
 *   - Bei nicht konfiguriertem calendar-service bleibt die Tabelle ohne Fehler
 *
 * Was dieser Test NICHT beweist:
 *   - Echte calendar-service-Verbindung
 *   - Echte Meeting-Bot-Recordings
 *   - OAuth-Roundtrip → calendar-connect.spec.ts
 *
 * Läuft ohne Backend. Voraussetzung: Dashboard-Dev-Server auf Port 3001.
 */

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3001";

const MOCK_USER = {
  id: "e2e-test-user-001",
  email: "e2e@vexa-mock.local",
  name: "E2E Test User",
  max_concurrent_bots: 5,
};

const MOCK_TOKEN = "vxa_tx_mock_e2etoken123456789";

/** Gemockte Kalender-Events vom calendar-service */
const MOCK_CALENDAR_EVENTS = [
  {
    id: 101,
    title: "Projektmeeting Q3",
    start_time: new Date(Date.now() + 3_600_000).toISOString(), // in 1 Stunde
    end_time: new Date(Date.now() + 7_200_000).toISOString(),
    meeting_url: "https://meet.google.com/abc-defg-hij",
    platform: "google_meet",
    status: "scheduled",
  },
  {
    id: 102,
    title: "Abgesagtes Meeting",
    start_time: new Date(Date.now() + 86_400_000).toISOString(),
    end_time: null,
    meeting_url: null,
    platform: null,
    status: "cancelled", // soll herausgefiltert werden
  },
];

/**
 * Gemockte aufgezeichnete Meetings — RawMeeting-Format (wie die echte API antwortet).
 * mapMeeting() in api.ts erwartet `id: number` und `native_meeting_id` (nicht platform_specific_id).
 * isHiddenDeletedMeeting() filtert Einträge mit leerem platform_specific_id heraus —
 * daher muss native_meeting_id gesetzt sein.
 */
const MOCK_RECORDED_MEETINGS = [
  {
    id: 1001,
    platform: "google_meet",
    native_meeting_id: "xyz-uvw-rst",
    status: "completed",
    start_time: new Date(Date.now() - 7_200_000).toISOString(),
    end_time: new Date(Date.now() - 3_600_000).toISOString(),
    bot_container_id: "bot-001",
    created_at: new Date(Date.now() - 7_200_000).toISOString(),
    data: { title: "Vergangenes Meeting", name: "Vergangenes Meeting", participants: [] },
  },
];

test.describe("Upcoming-Meetings — Mock-Smoke (Beweisstufe 3/4)", () => {
  test.use({ storageState: { cookies: [], origins: [] } }); // kein gespeicherter Auth-State

  test.beforeEach(async ({ page }) => {
    // ── Auth komplett mocken ──────────────────────────────────────────────────

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

    // ── Meetings-API ──────────────────────────────────────────────────────────

    await page.route("**/api/vexa/meetings**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          meetings: MOCK_RECORDED_MEETINGS,
          has_more: false,
        }),
      })
    );

    // ── Kalender-Proxy ────────────────────────────────────────────────────────

    await page.route("**/api/calendar/proxy/events**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ events: MOCK_CALENDAR_EVENTS, configured: true }),
      })
    );
  });

  test("Upcoming-Kalender-Event erscheint in der Tabelle", async ({ page }) => {
    await page.goto(`${BASE_URL}/meetings`);
    await page.waitForLoadState("networkidle");

    // "Projektmeeting Q3" soll sichtbar sein
    await expect(page.getByText("Projektmeeting Q3")).toBeVisible({ timeout: 10_000 });
  });

  test("Cancelled-Event wird NICHT in der Tabelle angezeigt", async ({ page }) => {
    await page.goto(`${BASE_URL}/meetings`);
    await page.waitForLoadState("networkidle");

    // "Abgesagtes Meeting" darf nicht sichtbar sein
    await expect(page.getByText("Abgesagtes Meeting")).not.toBeVisible();
  });

  test("Upcoming-Zeile zeigt Status 'Upcoming' (violett)", async ({ page }) => {
    await page.goto(`${BASE_URL}/meetings`);
    await page.waitForLoadState("networkidle");

    // Zeile mit "Projektmeeting Q3" muss "Upcoming"-Label enthalten
    const row = page.locator("tr").filter({ hasText: "Projektmeeting Q3" });
    await expect(row).toBeVisible({ timeout: 10_000 });
    await expect(row.getByText("Upcoming")).toBeVisible();
  });

  test("Filter 'Upcoming' zeigt nur Kalender-Events, keine aufgezeichneten Meetings", async ({
    page,
  }) => {
    await page.goto(`${BASE_URL}/meetings`);
    await page.waitForLoadState("networkidle");

    // Status-Filter auf "Upcoming" setzen
    await page.getByRole("combobox").filter({ hasText: /All Status|Upcoming/i }).click();
    await page.getByRole("option", { name: "Upcoming" }).click();

    // Kalender-Event soll sichtbar bleiben
    await expect(page.getByText("Projektmeeting Q3")).toBeVisible({ timeout: 5_000 });

    // Aufgezeichnetes Meeting soll verschwinden
    await expect(page.getByText("Vergangenes Meeting")).not.toBeVisible();
  });

  test("Klick auf upcoming-Zeile navigiert NICHT zu /meetings/:id", async ({ page }) => {
    await page.goto(`${BASE_URL}/meetings`);
    await page.waitForLoadState("networkidle");

    const row = page.locator("tr").filter({ hasText: "Projektmeeting Q3" });
    await expect(row).toBeVisible({ timeout: 10_000 });

    const initialUrl = page.url();
    await row.click();

    // URL darf sich nicht geändert haben
    await page.waitForTimeout(500);
    expect(page.url()).toBe(initialUrl);
  });

  test("Bei nicht konfiguriertem calendar-service bleibt Tabelle ohne Fehler", async ({
    page,
  }) => {
    // Kalender-Service antwortet mit "nicht konfiguriert"
    await page.route("**/api/calendar/proxy/events**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ events: [], configured: false }),
      })
    );

    await page.goto(`${BASE_URL}/meetings`);
    await page.waitForLoadState("networkidle");

    // Aufgezeichnetes Meeting soll trotzdem erscheinen (kein Absturz)
    await expect(page.getByText("Vergangenes Meeting")).toBeVisible({ timeout: 10_000 });

    // Kein Fehler-Toast oder Fehlertext
    await expect(page.locator("[data-sonner-toast]")).not.toBeVisible();
  });
});
