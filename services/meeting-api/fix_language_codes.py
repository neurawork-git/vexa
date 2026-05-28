"""
One-shot DB migration: normalize full language names → ISO codes in transcriptions table.

Run once after deploying the meeting-api fix:
  python fix_language_codes.py

Requires env vars: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
Optional: DB_SSL_MODE (default: prefer)
"""
import os
import sys
import psycopg2

LANGUAGE_LONG_TO_ISO = {
    "afrikaans": "af", "amharic": "am", "arabic": "ar", "assamese": "as",
    "azerbaijani": "az", "bashkir": "ba", "belarusian": "be", "bulgarian": "bg",
    "bengali": "bn", "tibetan": "bo", "breton": "br", "bosnian": "bs",
    "catalan": "ca", "czech": "cs", "welsh": "cy", "danish": "da",
    "german": "de", "greek": "el", "english": "en", "spanish": "es",
    "estonian": "et", "basque": "eu", "persian": "fa", "finnish": "fi",
    "faroese": "fo", "french": "fr", "galician": "gl", "gujarati": "gu",
    "hausa": "ha", "hawaiian": "haw", "hebrew": "he", "hindi": "hi",
    "croatian": "hr", "haitian creole": "ht", "hungarian": "hu", "armenian": "hy",
    "indonesian": "id", "icelandic": "is", "italian": "it", "japanese": "ja",
    "javanese": "jw", "georgian": "ka", "kazakh": "kk", "khmer": "km",
    "kannada": "kn", "korean": "ko", "latin": "la", "luxembourgish": "lb",
    "lingala": "ln", "lao": "lo", "lithuanian": "lt", "latvian": "lv",
    "malagasy": "mg", "maori": "mi", "macedonian": "mk", "malayalam": "ml",
    "mongolian": "mn", "marathi": "mr", "malay": "ms", "maltese": "mt",
    "myanmar": "my", "nepali": "ne", "dutch": "nl", "norwegian nynorsk": "nn",
    "norwegian": "no", "occitan": "oc", "punjabi": "pa", "polish": "pl",
    "pashto": "ps", "portuguese": "pt", "romanian": "ro", "russian": "ru",
    "sanskrit": "sa", "sindhi": "sd", "sinhala": "si", "slovak": "sk",
    "slovenian": "sl", "shona": "sn", "somali": "so", "albanian": "sq",
    "serbian": "sr", "sundanese": "su", "swedish": "sv", "swahili": "sw",
    "tamil": "ta", "telugu": "te", "tajik": "tg", "thai": "th",
    "turkmen": "tk", "tagalog": "tl", "turkish": "tr", "tatar": "tt",
    "ukrainian": "uk", "urdu": "ur", "uzbek": "uz", "vietnamese": "vi",
    "yiddish": "yi", "yoruba": "yo", "chinese": "zh", "cantonese": "yue",
}


def main():
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", 5432)),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        sslmode=os.environ.get("DB_SSL_MODE", "prefer"),
    )
    conn.autocommit = False
    cur = conn.cursor()

    total_updated = 0
    for long_name, iso_code in LANGUAGE_LONG_TO_ISO.items():
        cur.execute(
            "UPDATE transcriptions SET language = %s WHERE lower(language) = %s",
            (iso_code, long_name),
        )
        rows = cur.rowcount
        if rows:
            print(f"  {long_name!r:25s} → {iso_code!r:6s}  ({rows} rows)")
            total_updated += rows

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDone. {total_updated} rows updated.")


if __name__ == "__main__":
    missing = [v for v in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not os.environ.get(v)]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    main()
