# neurawork/ — Vexa Calendar-Service Test-Sandbox

Fork von [Vexa-ai/vexa](https://github.com/Vexa-ai/vexa) mit additive Test-Setup für den noch nicht offiziell shipped `calendar-service`.

## Warum

Calendar-Service auto-joined Bots zu Calendar-Events (Google Calendar Sync via OAuth, configurable lead time). Code seit 2026-04-05 in upstream main, aber `deploy/compose/docker-compose.yml` markiert ihn als "NO-SHIP for 0.10". Auch Helm-Charts (`vexa-lite`, `vexa`) haben kein Template.

Kein offizielles Ship-Datum bekannt — 0.11-Milestone (58 open) listet kein Calendar-Issue. Eigener Test über diesen Fork.

## Was ist in `neurawork/`

| Datei | Zweck |
|-------|-------|
| `CLAUDE.md` | Scope-Regeln für Claude Code in diesem Subdir |
| `README.md` | Dieses Dokument |
| `calendar.compose.yml` | Compose-Overlay aktiviert calendar-service (nicht `docker-compose.override.yml` — upstream `.gitignore` blockt diesen Namen) |
| `.env.example` | Required Env-Vars (Google OAuth Credentials) |

## Setup

1. **Env vorbereiten**:
   ```bash
   cp neurawork/.env.example deploy/compose/.env
   # Werte für GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, BOT_API_TOKEN eintragen
   ```

2. **Stack hochfahren** mit Overlay:
   ```bash
   docker compose \
     -f deploy/compose/docker-compose.yml \
     -f neurawork/calendar.compose.yml \
     up -d --build
   ```

3. **Health-Check**:
   ```bash
   curl http://localhost:8050/health
   curl http://localhost:8000/calendar/status?user_id=1
   ```

## Test-Flow

1. User in `users` DB anlegen + `data` JSONB mit Google OAuth refresh token füllen (Dashboard OAuth-Flow oder manuell)
2. `POST /calendar/connect?user_id=1` → trigger initial sync
3. `GET /calendar/events?user_id=1` → upcoming events
4. Calendar-Event mit Meeting-URL erstellen (Zoom/Meet/Teams)
5. Innerhalb `SYNC_INTERVAL_SECONDS` (default 300) sollte Bot scheduled werden
6. Logs prüfen: `docker compose logs -f calendar-service`

## Sync mit Upstream

Siehe `CLAUDE.md` Sync-Section.

## Production-Deployment

Falls Tests greifen: Calendar-Service in [`nashtrader/vexa-k8s`](https://github.com/nashtrader/vexa-k8s) als eigenes Helm-Template ergänzen — NICHT in diesem Fork. Dieser Fork bleibt Sandbox.
