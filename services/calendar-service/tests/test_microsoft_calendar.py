"""Mock-Tests for microsoft_calendar.py.

No live Microsoft account available — all HTTP calls are intercepted by respx.
Run: pytest tests/test_microsoft_calendar.py -v
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone

import pytest
import respx
import httpx

FIXTURES = Path(__file__).parent / "fixtures" / "microsoft"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# TestNotConfiguredGuard
# ---------------------------------------------------------------------------

class TestNotConfiguredGuard:
    """All stateful functions must raise MicrosoftNotConfigured when env vars absent."""

    def setup_method(self):
        os.environ.pop("MICROSOFT_CLIENT_ID", None)
        os.environ.pop("MICROSOFT_CLIENT_SECRET", None)

    def teardown_method(self):
        os.environ.pop("MICROSOFT_CLIENT_ID", None)
        os.environ.pop("MICROSOFT_CLIENT_SECRET", None)

    def test_is_configured_false_without_env(self):
        from app.microsoft_calendar import is_configured
        assert is_configured() is False

    async def test_exchange_code_raises(self):
        from app.microsoft_calendar import exchange_code, MicrosoftNotConfigured
        with pytest.raises(MicrosoftNotConfigured):
            await exchange_code("", "", "code", "https://example.com/cb")

    async def test_refresh_access_token_raises(self):
        from app.microsoft_calendar import refresh_access_token, MicrosoftNotConfigured
        with pytest.raises(MicrosoftNotConfigured):
            await refresh_access_token("", "", "old_token")

    async def test_list_events_raises(self):
        from app.microsoft_calendar import list_events, MicrosoftNotConfigured
        with pytest.raises(MicrosoftNotConfigured):
            await list_events("some_token")


# ---------------------------------------------------------------------------
# TestExtractMeetingUrl
# ---------------------------------------------------------------------------

class TestExtractMeetingUrl:

    def test_join_url_from_online_meeting(self):
        from app.microsoft_calendar import extract_meeting_url
        event = load("event_with_online_meeting.json")
        url = extract_meeting_url(event)
        assert url is not None
        assert "teams.microsoft.com" in url

    def test_teams_url_from_body_html(self):
        from app.microsoft_calendar import extract_meeting_url
        event = load("event_with_body_html_teams.json")
        url = extract_meeting_url(event)
        assert url is not None
        assert "teams.microsoft.com" in url

    def test_zoom_url_from_body_html(self):
        from app.microsoft_calendar import extract_meeting_url
        event = load("event_with_body_zoom.json")
        url = extract_meeting_url(event)
        assert url is not None
        assert "zoom.us" in url

    def test_gmeet_url_from_body_html(self):
        from app.microsoft_calendar import extract_meeting_url
        event = {
            "onlineMeeting": None,
            "body": {"content": "Join: https://meet.google.com/abc-defg-hij"},
            "location": {"displayName": ""},
        }
        url = extract_meeting_url(event)
        assert url == "https://meet.google.com/abc-defg-hij"

    def test_url_from_location(self):
        from app.microsoft_calendar import extract_meeting_url
        event = {
            "onlineMeeting": None,
            "body": {"content": ""},
            "location": {"displayName": "https://zoom.us/j/12345678901"},
        }
        url = extract_meeting_url(event)
        assert url is not None
        assert "zoom.us" in url

    def test_returns_none_when_no_url(self):
        from app.microsoft_calendar import extract_meeting_url
        event = {
            "onlineMeeting": None,
            "body": {"content": "No meeting link here"},
            "location": {"displayName": "Conference Room A"},
        }
        assert extract_meeting_url(event) is None


# ---------------------------------------------------------------------------
# TestParseEventTime
# ---------------------------------------------------------------------------

class TestParseEventTime:

    def test_utc_datetime(self):
        from app.microsoft_calendar import parse_event_time
        event = {"start": {"dateTime": "2026-06-01T10:00:00", "timeZone": "UTC"}}
        dt = parse_event_time(event, "start")
        assert dt is not None
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 10

    def test_iana_timezone_converted_to_utc(self):
        from app.microsoft_calendar import parse_event_time
        # Europe/Berlin is UTC+2 in summer
        event = {"start": {"dateTime": "2026-06-01T12:00:00", "timeZone": "Europe/Berlin"}}
        dt = parse_event_time(event, "start")
        assert dt is not None
        assert dt.tzinfo is not None
        # Result should be UTC (10:00 or close, depending on DST)
        assert dt.hour in (9, 10)

    def test_windows_tz_name_fallback_to_utc(self):
        from app.microsoft_calendar import parse_event_time
        event = {"start": {"dateTime": "2026-06-01T10:00:00", "timeZone": "W. Europe Standard Time"}}
        dt = parse_event_time(event, "start")
        # Should not raise — returns UTC fallback
        assert dt is not None
        assert dt.tzinfo is not None

    def test_missing_datetime_returns_none(self):
        from app.microsoft_calendar import parse_event_time
        event = {"start": {}}
        assert parse_event_time(event, "start") is None

    def test_already_aware_iso_string(self):
        from app.microsoft_calendar import parse_event_time
        # Microsoft with Prefer header strips Z, but guard if it's present
        event = {"start": {"dateTime": "2026-06-01T10:00:00Z", "timeZone": "UTC"}}
        dt = parse_event_time(event, "start")
        assert dt is not None
        assert dt.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# TestAuthorizeUrl
# ---------------------------------------------------------------------------

class TestAuthorizeUrl:

    def test_scopes_in_url(self):
        from app.microsoft_calendar import get_authorize_url, SCOPES
        url = get_authorize_url("client-id-123", "https://example.com/callback", "state-xyz")
        for scope in SCOPES:
            assert scope in url

    def test_state_in_url(self):
        from app.microsoft_calendar import get_authorize_url
        url = get_authorize_url("client-id-123", "https://example.com/callback", "my-state-token")
        assert "my-state-token" in url

    def test_redirect_uri_in_url(self):
        from app.microsoft_calendar import get_authorize_url
        url = get_authorize_url("client-id-123", "https://example.com/cb", "state")
        assert "example.com" in url


# ---------------------------------------------------------------------------
# TestTokenExchange  (respx-mocked)
# ---------------------------------------------------------------------------

class TestTokenExchange:

    @respx.mock
    async def test_exchange_code_returns_three_tuple(self, ms_env):
        from app.microsoft_calendar import exchange_code, TOKEN_URL
        payload = load("token_response_success.json")
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=payload))

        access, refresh, expires = await exchange_code(
            "test-client-id", "test-client-secret", "auth-code-abc", "https://example.com/cb"
        )
        assert access == payload["access_token"]
        assert refresh == payload["refresh_token"]
        assert expires == 3600

    @respx.mock
    async def test_refresh_returns_rotated_token(self, ms_env):
        from app.microsoft_calendar import refresh_access_token, TOKEN_URL
        payload = load("token_response_success.json")
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=payload))

        access, new_refresh, expires = await refresh_access_token(
            "test-client-id", "test-client-secret", "old-refresh-token"
        )
        assert new_refresh == payload["refresh_token"]
        assert new_refresh != "old-refresh-token"

    @respx.mock
    async def test_invalid_grant_raises(self, ms_env):
        from app.microsoft_calendar import refresh_access_token, TOKEN_URL, MicrosoftRefreshTokenExpired
        payload = load("token_response_invalid_grant.json")
        respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json=payload))

        with pytest.raises(MicrosoftRefreshTokenExpired):
            await refresh_access_token(
                "test-client-id", "test-client-secret", "expired-refresh-token"
            )


# ---------------------------------------------------------------------------
# TestListEvents  (respx-mocked)
# ---------------------------------------------------------------------------

class TestListEvents:

    @respx.mock
    async def test_sends_correct_url_and_params(self, ms_env):
        from app.microsoft_calendar import list_events, CALENDAR_VIEW_URL
        respx.get(CALENDAR_VIEW_URL).mock(return_value=httpx.Response(200, json={"value": []}))

        result = await list_events("test-access-token")
        assert "value" in result
        request = respx.calls.last.request
        # httpx URL-encodes $ → %24; check decoded form
        url_str = str(request.url)
        assert "%24select" in url_str or "select" in url_str

    @respx.mock
    async def test_sends_prefer_header(self, ms_env):
        from app.microsoft_calendar import list_events, CALENDAR_VIEW_URL
        respx.get(CALENDAR_VIEW_URL).mock(return_value=httpx.Response(200, json={"value": []}))

        await list_events("test-access-token")
        request = respx.calls.last.request
        assert "UTC" in request.headers.get("Prefer", "")

    @respx.mock
    async def test_401_raises_access_token_expired(self, ms_env):
        from app.microsoft_calendar import list_events, CALENDAR_VIEW_URL, MicrosoftAccessTokenExpired
        respx.get(CALENDAR_VIEW_URL).mock(return_value=httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}}))

        with pytest.raises(MicrosoftAccessTokenExpired):
            await list_events("expired-token")

    @respx.mock
    async def test_403_raises_permission_denied(self, ms_env):
        from app.microsoft_calendar import list_events, CALENDAR_VIEW_URL, MicrosoftPermissionDenied
        respx.get(CALENDAR_VIEW_URL).mock(return_value=httpx.Response(403, json={"error": {"code": "ErrorAccessDenied"}}))

        with pytest.raises(MicrosoftPermissionDenied):
            await list_events("valid-token-no-consent")
