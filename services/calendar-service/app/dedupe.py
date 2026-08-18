"""Org-wide meeting identity — kept import-free so it stays testable on its own."""

from typing import Optional


def dedupe_key(platform: Optional[str], meeting_url: Optional[str]) -> Optional[str]:
    """Org-wide identity of a meeting: two calendar events with the same key are the
    SAME meeting, even when they belong to different users.

    Two colleagues both connecting their calendar means the same company meeting sits
    in both calendars as two CalendarEvent rows. Without this key each row spawns its
    own bot and the meeting gets two Vexa participants. Upstream does not solve this —
    there a meeting row is per user by design.

    Normalisation stays deliberately shallow (case + trailing slash): Teams carries
    meaningful query parameters (context, tenant), so stripping the query would fuse
    genuinely different meetings into one.
    """
    if not meeting_url:
        return None
    return f"{(platform or '').strip().lower()}|{meeting_url.strip().rstrip('/').lower()}"
