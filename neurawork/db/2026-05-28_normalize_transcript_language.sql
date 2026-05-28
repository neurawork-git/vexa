-- 2026-05-28: Normalize transcript language codes to ISO-639-1.
--
-- BACKGROUND
-- meeting_api.schemas.TranscriptionSegment.validate_language only
-- accepts ISO-639-1 short codes ('de', 'en', ...). Whisper's
-- language-detector writes long-form names ('german', 'english', ...).
-- _get_full_transcript_segments (collector/endpoints.py:189-198) wraps
-- construction in `except Exception` and silently drops invalid
-- segments → 1588 chunks were invisible to the dashboard as of
-- 2026-05-28.
--
-- STRATEGY
-- We can't ship a meeting-api code fix today (vexa-lite is upstream
-- monolith, no neurawork build pipeline yet). Instead:
-- (a) one-shot UPDATE normalizes existing long-form values
-- (b) BEFORE INSERT/UPDATE trigger keeps future writes ISO-only
--
-- This is a temporary mitigation. A proper fix lives in
-- _get_full_transcript_segments (or the whisper writer) and should
-- replace this trigger when neurawork forks vexa-lite or upstream
-- ships the fix. Follow-up tracked in neurawork/db/README.md.

BEGIN;

CREATE OR REPLACE FUNCTION normalize_transcript_language()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.language IS NULL THEN
        RETURN NEW;
    END IF;
    NEW.language := CASE lower(NEW.language)
        WHEN 'english'    THEN 'en'
        WHEN 'german'     THEN 'de'
        WHEN 'french'     THEN 'fr'
        WHEN 'spanish'    THEN 'es'
        WHEN 'italian'    THEN 'it'
        WHEN 'portuguese' THEN 'pt'
        WHEN 'dutch'      THEN 'nl'
        WHEN 'swedish'    THEN 'sv'
        WHEN 'norwegian'  THEN 'no'
        WHEN 'danish'     THEN 'da'
        WHEN 'polish'     THEN 'pl'
        WHEN 'russian'    THEN 'ru'
        WHEN 'ukrainian'  THEN 'uk'
        WHEN 'czech'      THEN 'cs'
        WHEN 'turkish'    THEN 'tr'
        WHEN 'japanese'   THEN 'ja'
        WHEN 'chinese'    THEN 'zh'
        WHEN 'korean'     THEN 'ko'
        WHEN 'arabic'     THEN 'ar'
        ELSE NEW.language
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_normalize_transcript_language ON transcriptions;

CREATE TRIGGER tr_normalize_transcript_language
BEFORE INSERT OR UPDATE ON transcriptions
FOR EACH ROW
EXECUTE FUNCTION normalize_transcript_language();

UPDATE transcriptions
SET language = CASE lower(language)
    WHEN 'english'    THEN 'en'
    WHEN 'german'     THEN 'de'
    WHEN 'french'     THEN 'fr'
    WHEN 'spanish'    THEN 'es'
    WHEN 'italian'    THEN 'it'
    WHEN 'portuguese' THEN 'pt'
    WHEN 'dutch'      THEN 'nl'
    WHEN 'swedish'    THEN 'sv'
    WHEN 'norwegian'  THEN 'no'
    WHEN 'danish'     THEN 'da'
    WHEN 'polish'     THEN 'pl'
    WHEN 'russian'    THEN 'ru'
    WHEN 'ukrainian'  THEN 'uk'
    WHEN 'czech'      THEN 'cs'
    WHEN 'turkish'    THEN 'tr'
    WHEN 'japanese'   THEN 'ja'
    WHEN 'chinese'    THEN 'zh'
    WHEN 'korean'     THEN 'ko'
    WHEN 'arabic'     THEN 'ar'
    ELSE language
END
WHERE lower(language) IN (
    'english','german','french','spanish','italian','portuguese','dutch',
    'swedish','norwegian','danish','polish','russian','ukrainian','czech',
    'turkish','japanese','chinese','korean','arabic'
);

COMMIT;

-- ────────────────────────────────────────────────────────────
-- Verification queries (run separately, post-COMMIT):
-- ────────────────────────────────────────────────────────────
-- SELECT language, COUNT(*) FROM transcriptions GROUP BY language ORDER BY 2 DESC;
-- SELECT tgname, tgenabled FROM pg_trigger WHERE tgname = 'tr_normalize_transcript_language';
