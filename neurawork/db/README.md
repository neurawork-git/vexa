# neurawork/db/

Versioned SQL migrations applied to the Vexa Supabase database for
neurawork's production cluster. **Not** upstream-shipped — local
mitigations or schema additions that work around upstream gaps until
we either fork the upstream service or upstream ships the proper fix.

## Convention

- File pattern: `YYYY-MM-DD_<short_description>.sql`
- Each file: idempotent (safe to re-run), wrapped in `BEGIN; ... COMMIT;`, header comment with BACKGROUND + STRATEGY + follow-up reference.
- Apply via: `kubectl --context thecluster -n vexa exec <pod-with-psycopg2> -- python3 -c "..."` or psql equivalent. Document exact apply command in PR.

## Active migrations

| Date       | File                                              | Purpose                                                       | Replace when                                                  |
|------------|---------------------------------------------------|---------------------------------------------------------------|----------------------------------------------------------------|
| 2026-05-28 | `2026-05-28_normalize_transcript_language.sql`    | Whisper long-form lang names → ISO-639-1 via trigger + fixup. | meeting-api Code-Fix shipped (own fork or upstream).           |
