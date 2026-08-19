"""org-wide dedupe — one meeting, one bot, even when several users hold it.

Stock behaviour is per-user: dedup and the unique active index are keyed
``(user_id, platform, platform_specific_id)`` and the spawn lock is
``pg_advisory_xact_lock(user_id)``. Two colleagues who both connect the calendar that
carries the same company meeting therefore get one bot each, and the meeting gets two
participants. ``AUTO_JOIN_ORG_WIDE_DEDUPE=1`` collapses that for a single-org self-host.

The default must stay per-user — a hosted tenant wants a transcript per user — so the
first test here is the one that pins the OLD behaviour.

Drives the SHIPPED ``auto_join_tick`` over the in-memory fakes, OFFLINE.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from meeting_api.bot_spawn.auto_join import auto_join_tick, due_rows
from meeting_api.bot_spawn.fakes import FakeRuntimeClient, InMemoryMeetingRepo

PLAT, NID = "google_meet", "abc-defg-hij"
NOW = datetime(2026, 7, 10, 15, 0, 0, tzinfo=timezone.utc)

_NO_GATE = lambda: None  # noqa: E731 — tests bypass the STT capability gate


def _seed(repo, *, mid, user_id, native=NID, platform=PLAT, at=None):
    at = at or NOW + timedelta(seconds=30)  # inside the 60s lead window
    repo._meetings[mid] = {
        "id": mid, "user_id": user_id, "platform": platform,
        "native_meeting_id": native, "platform_specific_id": native,
        "status": "scheduled", "bot_container_id": None, "start_time": None, "end_time": None,
        "data": {"title": "Runway", "auto_join": True, "scheduled_at": at.isoformat()},
        "created_at": "2026-07-08T09:00:00Z", "updated_at": "2026-07-08T09:00:00Z",
    }
    return mid


async def _tick(repo, runtime, **kw):
    kw.setdefault("transcribe_gate", _NO_GATE)
    kw.setdefault("now", NOW)
    kw.setdefault("token_secret", "s")
    kw.setdefault("redis_url", "redis://r")
    kw.setdefault("allow_uncapped", True)
    return await auto_join_tick(repo, runtime, **kw)


async def test_default_still_spawns_one_bot_per_user():
    """The stock contract: two users, same meeting, two bots. Changing this by default
    would silently drop a hosted tenant's second transcript."""
    repo, runtime = InMemoryMeetingRepo(), FakeRuntimeClient()
    _seed(repo, mid=1, user_id=1)
    _seed(repo, mid=2, user_id=3)
    counters = await _tick(repo, runtime)
    assert counters["due"] == 2
    assert counters["spawned"] == 2
    assert len(runtime.specs) == 2


async def test_org_wide_dedupe_spawns_one_bot_for_a_shared_meeting():
    """The prod duplicate this exists for: meetings 498 (user 1) and 500 (user 3), both
    'Vexa - Runway', spawned 0.5s apart into the same Google Meet."""
    repo, runtime = InMemoryMeetingRepo(), FakeRuntimeClient()
    _seed(repo, mid=1, user_id=1)
    _seed(repo, mid=2, user_id=3)
    counters = await _tick(repo, runtime, org_wide_dedupe=True)
    assert counters["due"] == 1
    assert counters["spawned"] == 1
    assert len(runtime.specs) == 1
    # The lowest user id wins, so the transcript owner is stable across sweeps.
    assert repo._meetings[1]["status"] == "requested"
    assert repo._meetings[2]["status"] == "scheduled"


def test_winner_is_the_lowest_user_id_regardless_of_row_order():
    """Insertion order must not decide the owner — a calendar sync that runs in a
    different order between ticks would otherwise hand the transcript to someone else."""
    repo = InMemoryMeetingRepo()
    _seed(repo, mid=9, user_id=3)
    _seed(repo, mid=2, user_id=1)
    rows = list(repo._meetings.values())
    for ordering in (rows, list(reversed(rows))):
        kept = due_rows(ordering, now=NOW, org_wide_dedupe=True)
        assert [r["user_id"] for r in kept] == [1]


def test_different_meetings_are_never_collapsed():
    """Dedupe keys on (platform, native id). Two genuinely different meetings starting at
    the same minute must both keep their bot."""
    repo = InMemoryMeetingRepo()
    _seed(repo, mid=1, user_id=1, native="abc-defg-hij")
    _seed(repo, mid=2, user_id=1, native="zzz-yyyy-xxx")
    _seed(repo, mid=3, user_id=2, native="abc-defg-hij", platform="teams")
    kept = due_rows(list(repo._meetings.values()), now=NOW, org_wide_dedupe=True)
    assert len(kept) == 3
