"""Calendar sync loop — polls Google + Microsoft Calendar, upserts events, schedules bots."""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from meeting_api.models import CalendarEvent
from admin_models.models import User
from app.google_calendar import (
    refresh_access_token,
    list_events,
    extract_meeting_url,
    detect_platform,
    parse_event_time,
)
from app import microsoft_calendar
from app.dedupe import dedupe_key

logger = logging.getLogger("calendar-service.sync")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
MEETING_API_URL = os.getenv("MEETING_API_URL", "http://meeting-api:8080")
DEFAULT_LEAD_TIME_MINUTES = int(os.getenv("DEFAULT_LEAD_TIME_MINUTES", "2"))
# No global bot token: each event's bot launches under its owner's own Vexa API
# token, resolved per-user from User.data["<provider>_calendar"]["bot_token"]
# (minted + stored at OAuth-connect time). Multi-tenant by design.


async def sync_user_calendar_google(user_id: int, db: AsyncSession) -> int:
    """Sync a single user's Google Calendar events. Returns count of upserted events."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(f"User {user_id} not found")
        return 0

    user_data = user.data or {}
    gc_data = user_data.get("google_calendar", {})
    oauth = gc_data.get("oauth", {})
    refresh_token = oauth.get("refresh_token")
    if not refresh_token:
        logger.info(f"User {user_id} has no Google Calendar refresh token")
        return 0

    # Refresh access token
    access_token, expires_in = await refresh_access_token(
        GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, refresh_token
    )

    # Get existing sync token for incremental sync
    existing_sync_token = gc_data.get("sync_token")

    time_min = datetime.now(timezone.utc)
    time_max = time_min + timedelta(days=7)

    api_response = await list_events(
        access_token,
        time_min=time_min,
        time_max=time_max,
        sync_token=existing_sync_token,
    )

    if api_response.get("fullSyncRequired"):
        logger.info(f"Full sync required for user {user_id}, clearing sync token")
        api_response = await list_events(
            access_token, time_min=time_min, time_max=time_max
        )

    events = api_response.get("items", [])
    next_sync_token = api_response.get("nextSyncToken")
    upserted = 0

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        # Skip cancelled events
        if event.get("status") == "cancelled":
            await db.execute(
                update(CalendarEvent)
                .where(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.external_event_id == event_id,
                )
                .values(status="cancelled")
            )
            continue

        start_time = parse_event_time(event, "start")
        if not start_time:
            continue  # All-day event, skip

        end_time = parse_event_time(event, "end")
        meeting_url = extract_meeting_url(event)
        platform = detect_platform(meeting_url) if meeting_url else None

        stmt = pg_insert(CalendarEvent).values(
            user_id=user_id,
            external_event_id=event_id,
            title=event.get("summary", ""),
            start_time=start_time,
            end_time=end_time,
            meeting_url=meeting_url,
            platform=platform,
            status="pending",
        ).on_conflict_do_update(
            constraint="uq_calendar_event_user_ext_id",
            set_={
                "title": event.get("summary", ""),
                "start_time": start_time,
                "end_time": end_time,
                "meeting_url": meeting_url,
                "platform": platform,
            },
        )
        await db.execute(stmt)
        upserted += 1

    # Save new sync token
    if next_sync_token:
        gc_data["sync_token"] = next_sync_token
        user_data["google_calendar"] = gc_data
        await db.execute(
            update(User).where(User.id == user_id).values(data=user_data)
        )

    await db.commit()
    logger.info(f"Synced {upserted} Google events for user {user_id}")
    return upserted


async def sync_user_calendar_microsoft(user_id: int, db: AsyncSession) -> int:
    """Sync a single user's Microsoft 365 Calendar events. Returns count of upserted events.

    Dormant until MICROSOFT_CLIENT_ID + MICROSOFT_CLIENT_SECRET are configured.
    Safe to call unconditionally — exits immediately if not configured.
    """
    if not microsoft_calendar.is_configured():
        return 0

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(f"User {user_id} not found")
        return 0

    user_data = user.data or {}
    mc_data = user_data.get("microsoft_calendar", {})
    oauth = mc_data.get("oauth", {})
    refresh_token = oauth.get("refresh_token")
    if not refresh_token:
        logger.info(f"User {user_id} has no Microsoft Calendar refresh token")
        return 0

    # Refresh access token.
    # CRITICAL: Microsoft rotates the refresh_token on every refresh call.
    # Persist the new token BEFORE any further API calls to avoid losing access
    # if the process crashes mid-sync.
    try:
        access_token, new_refresh_token, expires_in = await microsoft_calendar.refresh_access_token(
            MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, refresh_token
        )
    except microsoft_calendar.MicrosoftRefreshTokenExpired:
        logger.warning(
            f"Microsoft refresh token expired for user {user_id} — user must reconnect calendar"
        )
        return 0
    except microsoft_calendar.MicrosoftAccessTokenExpired:
        logger.error(f"Microsoft access token expired unexpectedly for user {user_id}")
        return 0

    # Persist rotated refresh token before any further API calls
    oauth["refresh_token"] = new_refresh_token
    mc_data["oauth"] = oauth
    user_data["microsoft_calendar"] = mc_data
    await db.execute(update(User).where(User.id == user_id).values(data=user_data))
    await db.commit()

    time_min = datetime.now(timezone.utc)
    time_max = time_min + timedelta(days=7)

    try:
        api_response = await microsoft_calendar.list_events(
            access_token,
            time_min=time_min,
            time_max=time_max,
        )
    except microsoft_calendar.MicrosoftPermissionDenied:
        logger.warning(
            f"Microsoft Graph permission denied for user {user_id} — "
            "likely missing tenant admin consent for Calendars.ReadWrite"
        )
        mc_data["last_error"] = "admin_consent_required"
        user_data["microsoft_calendar"] = mc_data
        await db.execute(update(User).where(User.id == user_id).values(data=user_data))
        await db.commit()
        return 0
    except microsoft_calendar.MicrosoftAccessTokenExpired:
        logger.error(f"Microsoft access token expired mid-sync for user {user_id}")
        return 0

    events = api_response.get("value", [])
    upserted = 0

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        # isCancelled is the Graph API cancelled-event signal
        if event.get("isCancelled"):
            # Use prefixed ID for namespace isolation against Google event IDs
            prefixed_id = f"microsoft:{event_id}"
            await db.execute(
                update(CalendarEvent)
                .where(
                    CalendarEvent.user_id == user_id,
                    CalendarEvent.external_event_id == prefixed_id,
                )
                .values(status="cancelled")
            )
            continue

        start_time = microsoft_calendar.parse_event_time(event, "start")
        if not start_time:
            continue  # All-day event (no dateTime), skip

        end_time = microsoft_calendar.parse_event_time(event, "end")
        meeting_url = microsoft_calendar.extract_meeting_url(event)
        platform = detect_platform(meeting_url) if meeting_url else None

        # Prefix external_event_id with "microsoft:" for namespace isolation —
        # Microsoft and Google event IDs can collide in the calendar_events table
        # (uq_calendar_event_user_ext_id constraint is per user+external_event_id).
        prefixed_id = f"microsoft:{event_id}"

        stmt = pg_insert(CalendarEvent).values(
            user_id=user_id,
            external_event_id=prefixed_id,
            title=event.get("subject", ""),
            start_time=start_time,
            end_time=end_time,
            meeting_url=meeting_url,
            platform=platform,
            status="pending",
        ).on_conflict_do_update(
            constraint="uq_calendar_event_user_ext_id",
            set_={
                "title": event.get("subject", ""),
                "start_time": start_time,
                "end_time": end_time,
                "meeting_url": meeting_url,
                "platform": platform,
            },
        )
        await db.execute(stmt)
        upserted += 1

    await db.commit()
    logger.info(f"Synced {upserted} Microsoft events for user {user_id}")
    return upserted


async def schedule_upcoming_bots(db: AsyncSession) -> int:
    """Check for pending events within lead time and schedule bots. Returns count scheduled."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(minutes=DEFAULT_LEAD_TIME_MINUTES)

    window = (
        CalendarEvent.start_time <= cutoff,
        CalendarEvent.start_time >= now - timedelta(minutes=5),
        CalendarEvent.meeting_url.isnot(None),
        CalendarEvent.platform.isnot(None),
    )

    result = await db.execute(
        select(CalendarEvent)
        .where(CalendarEvent.status == "pending", *window)
        # Deterministic winner when two users hold the same meeting: lowest user_id,
        # then lowest event id. Without an explicit order the winner flips between
        # ticks and the transcript owner becomes random.
        .order_by(CalendarEvent.user_id, CalendarEvent.id)
    )
    events = result.scalars().all()

    # A duplicate can arrive one tick later than its twin, so the claimed set must
    # survive across ticks — it is seeded from what is already scheduled in the same
    # window (the twin of a meeting carries the same start_time by definition).
    claimed_result = await db.execute(
        select(CalendarEvent.platform, CalendarEvent.meeting_url)
        .where(CalendarEvent.status == "scheduled", *window)
    )
    claimed = {
        key
        for platform, url in claimed_result.all()
        if (key := dedupe_key(platform, url)) is not None
    }

    scheduled = 0

    for event in events:
        key = dedupe_key(event.platform, event.meeting_url)
        if key in claimed:
            logger.info(
                f"Skipping event {event.id} (user {event.user_id}): another user's "
                f"calendar already sent a bot to {event.meeting_url}"
            )
            await db.execute(
                update(CalendarEvent)
                .where(CalendarEvent.id == event.id)
                .values(status="duplicate")
            )
            continue

        # Launch the bot under the EVENT OWNER's own Vexa API token — not a shared
        # service account. Per-user token enforces per-user concurrency limits and
        # correct transcript ownership. Token is minted + stored at OAuth-connect time.
        user_result = await db.execute(select(User).where(User.id == event.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            continue

        data = user.data or {}
        bot_token = (
            data.get("google_calendar", {}).get("bot_token")
            or data.get("microsoft_calendar", {}).get("bot_token")
        )
        # Multi-provider users have bot_token under whichever provider they
        # connected first. Fallback chain keeps single-provider users working.
        # Issue B will replace this with per-event provider-aware token resolution.
        if not bot_token:
            logger.warning(
                f"User {event.user_id} has no Vexa bot_token "
                f"(calendar reconnect needed to mint one) — skipping event {event.id}"
            )
            continue

        # Send meeting_url + platform — meeting-api's schema parser handles
        # native_meeting_id / passcode extraction (incl. Teams URL-decoding,
        # white-label / enterprise variants). Avoids per-platform regex drift
        # on this side. See services/meeting-api/meeting_api/schemas.py
        # `parse_meeting_url_if_provided` + `validate_meeting_or_agent`.
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{MEETING_API_URL}/bots",
                    json={
                        "platform": event.platform,
                        "meeting_url": event.meeting_url,
                        "bot_name": f"Vexa - {event.title or 'Calendar'}",
                    },
                    headers={"X-API-Key": bot_token},
                    timeout=30,
                )

            if resp.status_code in (200, 201):
                resp_data = resp.json()
                await db.execute(
                    update(CalendarEvent)
                    .where(CalendarEvent.id == event.id)
                    .values(
                        status="scheduled",
                        meeting_id=resp_data.get("id"),
                    )
                )
                scheduled += 1
                claimed.add(key)
                logger.info(f"Scheduled bot for event {event.id}: {event.title}")
            else:
                logger.error(f"Bot request failed for event {event.id}: {resp.status_code} {resp.text}")
                await db.execute(
                    update(CalendarEvent)
                    .where(CalendarEvent.id == event.id)
                    .values(status="failed")
                )
        except Exception as e:
            logger.error(f"Failed to schedule bot for event {event.id}: {e}")

    await db.commit()
    return scheduled
