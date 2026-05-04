# CLAUDE.md — neurawork/ Subdir

## Scope

Dieses Subdir gehört Neurawork. Innerhalb von `neurawork/` gilt:

- **Ignoriere die Root-CLAUDE.md** (Stage-State-Machine `tests3/lib/stage.py probe` etc.). Die ist Vexa-Upstream-Workflow für deren Release-Prozess — nicht für unsere Test-Deployments.
- **Keine Änderungen an Files außerhalb `neurawork/`**. Upstream-Code bleibt unangetastet, damit `git fetch upstream main` konfliktfrei mergen kann.
- Additions in `neurawork/` sind explizit erlaubt und Zweck dieses Forks.

## Zweck dieses Forks

Vexa Calendar-Service (`services/calendar-service/`) ist im Upstream-Code vorhanden, aber als "NO-SHIP for 0.10" aus `deploy/compose/docker-compose.yml` und beiden Helm-Charts (`vexa-lite`, `vexa`) ausgeschlossen.

Wir wollen den Service ohne Warten auf offizielles Ship (vermutlich 0.11+, kein Datum) ausprobieren. Strategie:

- Upstream-Files unverändert
- `neurawork/docker-compose.override.yml` aktiviert calendar-service via additive Service-Definition
- Test lokal via `docker compose -f deploy/compose/docker-compose.yml -f neurawork/docker-compose.override.yml up`

## Sync mit Upstream

```bash
git fetch upstream
git checkout main && git merge --ff-only upstream/main && git push origin main
git checkout neurawork && git rebase main
```

Bei Konflikten in `neurawork/`-Files: lokal lösen. Konflikte in Upstream-Files dürfen nie auftreten (s. Scope).

## Companion-Repo

Das produktive K8s-Deployment läuft aus `nashtrader/vexa-k8s` (`charts/vexa-lite/` vendored Chart). Dieser Fork ist **nur Test-Sandbox** — falls Calendar-Service ship-ready, würde ein eigenes Helm-Template in `vexa-k8s` ergänzt, nicht hier.
