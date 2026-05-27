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
   # Werte für GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET eintragen
   # (KEIN globales BOT_API_TOKEN mehr — siehe "Bot-Auth (multi-tenant)" unten)
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

## Bot-Auth (multi-tenant)

Jeder User aktiviert den Calendar-Watcher für sich selbst. Die Autorisierung läuft
**pro User über die User-Tabelle**, nicht über eine globale Env-Var:

- **Calendar lesen**: Google-OAuth-`refresh_token` in `User.data.google_calendar.oauth`.
- **Bots launchen**: ein **pro User gemintetes** Vexa-API-Token (Scope `bot,tx,browser`)
  in `User.data.google_calendar.bot_token`. Beide werden beim Calendar-Connect im
  Dashboard (`/api/calendar/oauth/complete`) gesetzt.

`sync.py:schedule_upcoming_bots` löst das Token pro Event aus dem Owner-Record auf
(`X-API-Key`) → Bots laufen unter der Identität des jeweiligen Users (korrekte
Concurrency-Limits + Transcript-Ownership). Fehlt das `bot_token`, wird der User
übersprungen (Reconnect nötig) — kein globaler Service-Account.

## Test-Flow

1. Calendar via Dashboard-OAuth verbinden → setzt `oauth.refresh_token` **und**
   `bot_token` in `User.data.google_calendar` (für manuelles Setup beide Felder füllen)
2. `POST /calendar/connect?user_id=1` → trigger initial sync
3. `GET /calendar/events?user_id=1` → upcoming events
4. Calendar-Event mit Meeting-URL erstellen (Zoom/Meet/Teams)
5. Innerhalb `SYNC_INTERVAL_SECONDS` (default 300) sollte Bot scheduled werden
6. Logs prüfen: `docker compose logs -f calendar-service`

## Sync mit Upstream

Siehe `CLAUDE.md` Sync-Section.

## Production-Deployment

Falls Tests greifen: Calendar-Service in [`neurawork-git/vexa-k8s`](https://github.com/neurawork-git/vexa-k8s) als eigenes Helm-Template ergänzen — NICHT in diesem Fork. Dieser Fork bleibt Sandbox.
