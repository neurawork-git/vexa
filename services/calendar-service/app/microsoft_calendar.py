"""Microsoft 365 Calendar API client — auth, event listing, meeting URL extraction.

Architecture mirrors google_calendar.py. Differences from Google:
- OAuth: Microsoft identity platform v2.0 (login.microsoftonline.com/common)
- Refresh token ROTATES on each refresh — must persist new refresh_token from response
- Events: Microsoft Graph /me/calendarView with startDateTime+endDateTime
- Time format: {dateTime, timeZone} object instead of Google's RFC3339 string
- Teams URL: event.onlineMeeting.joinUrl (clean) + body fallback (HTML, regex-scan)

CONFIGURATION
This module loads even without MICROSOFT_CLIENT_ID/SECRET set in env.
Top-level callers (sync.py, main.py route handlers) MUST gate API calls
behind is_configured() — otherwise httpx will POST empty credentials
and surface confusing 400s. See is_configured() docstring.
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("calendar-service.microsoft")

AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CALENDAR_VIEW_URL = f"{GRAPH_BASE}/me/calendarView"

SCOPES = ["Calendars.ReadWrite", "User.Read", "offline_access"]


class MicrosoftNotConfigured(RuntimeError):
    """Raised when Microsoft Calendar API is called but env vars are missing."""


class MicrosoftRefreshTokenExpired(RuntimeError):
    """Raised on 400 invalid_grant — user must reconnect."""


class MicrosoftAccessTokenExpired(RuntimeError):
    """Raised on 401 — caller should refresh and retry."""


class MicrosoftPermissionDenied(RuntimeError):
    """Raised on 403 — typically Tenant Admin Consent missing for Calendars.ReadWrite."""


def is_configured() -> bool:
    """True if env has both MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET."""
    return bool(os.getenv("MICROSOFT_CLIENT_ID") and os.getenv("MICROSOFT_CLIENT_SECRET"))


def get_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the Microsoft OAuth2 authorization URL."""
    scope = " ".join(SCOPES)
    params = {
        "response_type": "code",
        "response_mode": "query",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "prompt": "select_account",
    }
    query = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items())
    return f"{AUTHORIZE_URL}?{query}"


async def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> tuple[str, str, int]:
    """Exchange authorization code for access + refresh tokens.

    Returns (access_token, refresh_token, expires_in).
    """
    if not is_configured():
        raise MicrosoftNotConfigured("MICROSOFT_CLIENT_ID or MICROSOFT_CLIENT_SECRET not set")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "scope": " ".join(SCOPES),
            },
        )
        if resp.status_code == 400:
            body = resp.json()
            if body.get("error") == "invalid_grant":
                raise MicrosoftRefreshTokenExpired(body.get("error_description", "invalid_grant"))
        resp.raise_for_status()
        data = resp.json()
        return (
            data["access_token"],
            data["refresh_token"],
            int(data.get("expires_in", 3600)),
        )


async def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> tuple[str, str, int]:
    """Exchange refresh_token for fresh access_token.

    CRITICAL: Microsoft rotates the refresh_token on each refresh call.
    Returns (access_token, NEW_refresh_token, expires_in). Caller MUST
    persist the new refresh_token — using the old one on the next call
    will fail with invalid_grant.

    Raises MicrosoftRefreshTokenExpired on 400 invalid_grant.
    """
    if not is_configured():
        raise MicrosoftNotConfigured("MICROSOFT_CLIENT_ID or MICROSOFT_CLIENT_SECRET not set")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "scope": " ".join(SCOPES),
            },
        )
        if resp.status_code == 400:
            body = resp.json()
            if body.get("error") == "invalid_grant":
                raise MicrosoftRefreshTokenExpired(body.get("error_description", "invalid_grant"))
        resp.raise_for_status()
        data = resp.json()
        # Microsoft should always return a new refresh_token, but fall back
        # to the old one defensively to avoid losing access on unexpected responses.
        new_refresh_token = data.get("refresh_token") or refresh_token
        return (
            data["access_token"],
            new_refresh_token,
            int(data.get("expires_in", 3600)),
        )


async def list_events(
    access_token: str,
    time_min: Optional[datetime] = None,
    time_max: Optional[datetime] = None,
    max_results: int = 50,
) -> dict:
    """Fetch events from Microsoft Graph calendarView.

    Returns dict with 'value' list of event objects.
    Raises MicrosoftAccessTokenExpired on 401.
    Raises MicrosoftPermissionDenied on 403 (likely missing tenant admin consent).
    """
    if not is_configured():
        raise MicrosoftNotConfigured("MICROSOFT_CLIENT_ID or MICROSOFT_CLIENT_SECRET not set")

    params: dict[str, str] = {
        "$select": "id,subject,start,end,isOnlineMeeting,onlineMeeting,body,location,isCancelled",
        "$top": str(max_results),
        "$orderby": "start/dateTime",
    }
    if time_min:
        params["startDateTime"] = time_min.isoformat()
    if time_max:
        params["endDateTime"] = time_max.isoformat()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            CALENDAR_VIEW_URL,
            params=params,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": 'outlook.timezone="UTC"',
            },
        )
        if resp.status_code == 401:
            raise MicrosoftAccessTokenExpired("Microsoft access token expired or invalid")
        if resp.status_code == 403:
            raise MicrosoftPermissionDenied(
                "Microsoft Graph 403 — likely missing tenant admin consent for Calendars.ReadWrite"
            )
        resp.raise_for_status()
        return resp.json()


# --- Meeting URL extraction ---

# Reuse Google's URL patterns — keep DRY. If we add a third provider, refactor into
# shared `_meeting_url.py`. YAGNI for now.
from app.google_calendar import MEETING_URL_PATTERNS, detect_platform  # noqa: E402


def extract_meeting_url(event: dict) -> Optional[str]:
    """Extract a meeting URL from a Microsoft Graph calendar event object."""
    # 1. onlineMeeting.joinUrl — cleanest source, present when isOnlineMeeting=True
    online_meeting = event.get("onlineMeeting") or {}
    join_url = online_meeting.get("joinUrl")
    if join_url:
        return join_url

    # 2. body.content HTML regex-scan (Teams/Zoom/GMeet links in invite body)
    body_content = (event.get("body") or {}).get("content", "") or ""
    for pattern in MEETING_URL_PATTERNS:
        match = pattern.search(body_content)
        if match:
            return match.group(0)

    # 3. location.displayName scan
    location = (event.get("location") or {}).get("displayName", "") or ""
    for pattern in MEETING_URL_PATTERNS:
        match = pattern.search(location)
        if match:
            return match.group(0)

    return None


def parse_event_time(event: dict, key: str) -> Optional[datetime]:
    """Parse start or end time from a Microsoft Graph event.

    Graph returns {dateTime: '...', timeZone: '...'}.
    With 'Prefer: outlook.timezone="UTC"' header the dateTime comes without
    a Z suffix — we attach UTC explicitly. For non-UTC responses we attempt
    zoneinfo; Windows-style tz names (e.g. 'W. Europe Standard Time') may
    not be in the IANA database, in which case we fall back to UTC + log a
    warning rather than dropping the event.
    """
    time_info = event.get(key) or {}
    dt_str = time_info.get("dateTime")
    if not dt_str:
        return None

    tz_name = time_info.get("timeZone", "UTC")

    # Fast path: UTC (expected with the Prefer header)
    if tz_name in ("UTC", "utc", ""):
        try:
            dt = datetime.fromisoformat(dt_str.rstrip("Z"))
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # IANA timezone via zoneinfo
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            tz = ZoneInfo(tz_name)
            dt = datetime.fromisoformat(dt_str.rstrip("Z"))
            return dt.replace(tzinfo=tz).astimezone(timezone.utc)
        except ZoneInfoNotFoundError:
            logger.warning(
                "Unknown timezone '%s' in Microsoft event (Windows-style tz name?). "
                "Falling back to UTC — event time may be off by the UTC offset.",
                tz_name,
            )
            dt = datetime.fromisoformat(dt_str.rstrip("Z"))
            return dt.replace(tzinfo=timezone.utc)
    except Exception:
        # Last resort: treat as UTC
        try:
            dt = datetime.fromisoformat(dt_str.rstrip("Z"))
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
