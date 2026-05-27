# E2E Tests — vexa-dashboard

Playwright-Tests für den Dashboard-Frontend-Flow.

## Voraussetzungen

1. **Dashboard lokal starten**: `npm run dev` (läuft auf Port 3001)
2. **Backend erreichbar**: Vexa API + Admin API müssen laufen (docker compose up -d)
3. **`.env.local` konfiguriert**:
   - `VEXA_API_URL`, `VEXA_ADMIN_API_KEY` gesetzt
   - `SMTP_HOST` **NICHT** gesetzt → Direct-Login-Mode für Tests
   - `GOOGLE_CLIENT_ID` gesetzt → Calendar OAuth Start funktioniert
4. **Playwright-Dependency installieren**:
   ```bash
   npm install --save-dev @playwright/test
   npx playwright install chromium
   ```

## Tests ausführen

```bash
# Alle E2E-Tests (headless)
npm run test:e2e

# Mit UI (interaktiv)
npm run test:e2e:ui

# Mit sichtbarem Browser
npm run test:e2e:headed
```

## Session-Strategie

Der Global-Setup (`e2e/global-setup.ts`) nutzt den **Direct-Login-Mode**:
- POST `/api/auth/send-magic-link` gibt ohne SMTP direkt ein `vexa-token`-Cookie zurück
- Der Browser-State wird in `playwright/.auth/user.json` gespeichert
- Alle Tests laden diesen State → kein manueller Login nötig
- Auth-State wird automatisch erneuert wenn er älter als 20 Minuten ist

## Specs

| Datei | Beschreibung |
|-------|-------------|
| `calendar-connect.spec.ts` | "Calendar verbinden"-Button auf /profile — OAuth-Start-Flow |

## Hinweise für B.A.

- Button muss `data-testid="calendar-connect-btn"` haben
- Button-Placement: `/profile` page
- Loading-State beim API-Call: Button disabled oder Spinner mit `animate-spin`-Klasse
