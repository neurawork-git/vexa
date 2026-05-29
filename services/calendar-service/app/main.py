"""Calendar Service — Google Calendar + Microsoft 365 sync + bot scheduling."""

import os
import asyncio
import logging
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from meeting_api.database import get_db, init_db
from meeting_api.models import CalendarEvent
from admin_models.models import User
from app.sync import sync_user_calendar_google, sync_user_calendar_microsoft, schedule_upcoming_bots
from app import microsoft_calendar

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "300"))

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("calendar-service")

_VEXA_ENV = os.getenv("VEXA_ENV", "development")
_PUBLIC_DOCS = _VEXA_ENV != "production"
app = FastAPI(
    title="Calendar Service",
    description="Google Calendar + Microsoft 365 sync and auto-join scheduling",
    docs_url="/docs" if _PUBLIC_DOCS else None,
    redoc_url="/redoc" if _PUBLIC_DOCS else None,
    openapi_url="/openapi.json" if _PUBLIC_DOCS else None,
)


@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(sync_loop())


async def sync_loop():
    """Background loop: sync all connected calendars (Google + Microsoft) and schedule bots."""
    while True:
        try:
            from meeting_api.database import async_session_local
            async with async_session_local() as db:
                result = await db.execute(select(User))
                users = result.scalars().all()
                for user in users:
                    data = user.data or {}
                    if data.get("google_calendar", {}).get("oauth", {}).get("refresh_token"):
                        try:
                            await sync_user_calendar_google(user.id, db)
                        except Exception as e:
                            logger.error(f"Google sync failed user {user.id}: {e}")
                    if data.get("microsoft_calendar", {}).get("oauth", {}).get("refresh_token"):
                        try:
                            await sync_user_calendar_microsoft(user.id, db)
                        except Exception as e:
                            logger.error(f"Microsoft sync failed user {user.id}: {e}")

                await schedule_upcoming_bots(db)
        except Exception as e:
            logger.error(f"Sync loop error: {e}")

        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "calendar-service"}


# ============================================================
# Google Calendar endpoints
# ============================================================

@app.post("/calendar/connect")
async def connect_calendar(user_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """Trigger initial Google Calendar sync after OAuth connection."""
    count = await sync_user_calendar_google(user_id, db)
    return {"status": "connected", "events_synced": count}


@app.get("/calendar/status")
async def calendar_status(user_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """Check calendar connection status for both Google and Microsoft."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    gc = (user.data or {}).get("google_calendar", {})
    mc = (user.data or {}).get("microsoft_calendar", {})

    google_connected = bool(gc.get("oauth", {}).get("refresh_token"))
    ms_connected = bool(mc.get("oauth", {}).get("refresh_token"))

    google_event_count = 0
    ms_event_count = 0
    if google_connected or ms_connected:
        count_result = await db.execute(
            select(CalendarEvent).where(CalendarEvent.user_id == user_id)
        )
        all_events = count_result.scalars().all()
        google_event_count = sum(
            1 for e in all_events if not (e.external_event_id or "").startswith("microsoft:")
        )
        ms_event_count = sum(
            1 for e in all_events if (e.external_event_id or "").startswith("microsoft:")
        )

    return {
        "connected": google_connected,            # existing — Google
        "event_count": google_event_count,        # existing — Google
        "microsoft_connected": ms_connected,      # NEW
        "microsoft_event_count": ms_event_count,  # NEW
        "microsoft_configured": microsoft_calendar.is_configured(),  # NEW: dashboard reads for card-render
        "microsoft_last_error": mc.get("last_error"),                # NEW
    }
    # Additive shape — existing 'connected' + 'event_count' stay Google-scoped.
    # Refactor to nested {google:{...}, microsoft:{...}} is a follow-up.


@app.delete("/calendar/disconnect")
async def disconnect_calendar(user_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """Remove Google OAuth tokens and stop syncing."""
    from sqlalchemy import update
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = dict(user.data or {})
    user_data.pop("google_calendar", None)
    await db.execute(
        update(User).where(User.id == user_id).values(data=user_data)
    )
    await db.commit()
    return {"status": "disconnected"}


@app.get("/calendar/events")
async def list_events(user_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """List upcoming calendar events for a user."""
    # Only return future events without a scheduled bot. Once meeting_id is
    # set, the meetings-table row owns the display (active/completed/failed);
    # returning the event here would dupe-render the same meeting as both
    # "upcoming" (calendar-event) and the real status (meetings-row) — and
    # the upcoming-row is non-clickable (frontend gates router.push on
    # !isUpcoming in services/dashboard/src/app/meetings/page.tsx:401),
    # hiding the real transcript link.
    now = datetime.now(timezone.utc)  # start_time is DateTime(timezone=True)
    result = await db.execute(
        select(CalendarEvent)
        .where(
            CalendarEvent.user_id == user_id,
            CalendarEvent.meeting_id.is_(None),
            CalendarEvent.start_time > now,
            CalendarEvent.status != "cancelled",
        )
        .order_by(CalendarEvent.start_time)
    )
    events = result.scalars().all()
    return [
        {
            "id": e.id,
            "title": e.title,
            "start_time": e.start_time.isoformat() if e.start_time else None,
            "end_time": e.end_time.isoformat() if e.end_time else None,
            "meeting_url": e.meeting_url,
            "platform": e.platform,
            "status": e.status,
        }
        for e in events
    ]


@app.put("/calendar/preferences")
async def update_preferences(
    user_id: int = Query(...),
    auto_join: bool = True,
    lead_time_minutes: int = 2,
    db: AsyncSession = Depends(get_db),
):
    """Set auto-join and lead time preferences."""
    from sqlalchemy import update
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = dict(user.data or {})
    gc = user_data.get("google_calendar", {})
    gc["preferences"] = {
        "auto_join": auto_join,
        "lead_time_minutes": lead_time_minutes,
    }
    user_data["google_calendar"] = gc
    await db.execute(
        update(User).where(User.id == user_id).values(data=user_data)
    )
    await db.commit()
    return {"status": "updated", "preferences": gc["preferences"]}


# ============================================================
# Microsoft 365 Calendar endpoints
# ============================================================

@app.post("/calendar/microsoft/connect")
async def connect_microsoft_calendar(user_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """Trigger initial Microsoft 365 Calendar sync after OAuth connection."""
    if not microsoft_calendar.is_configured():
        raise HTTPException(status_code=503, detail="Microsoft Calendar is not configured on this server")
    count = await sync_user_calendar_microsoft(user_id, db)
    return {"status": "connected", "events_synced": count}


@app.delete("/calendar/microsoft/disconnect")
async def disconnect_microsoft_calendar(user_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """Remove Microsoft OAuth tokens and stop syncing."""
    from sqlalchemy import update
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = dict(user.data or {})
    user_data.pop("microsoft_calendar", None)
    await db.execute(
        update(User).where(User.id == user_id).values(data=user_data)
    )
    await db.commit()
    return {"status": "disconnected"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8050, reload=True)
