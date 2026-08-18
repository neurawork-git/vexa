"""One meeting, one bot — even when several users hold it in their calendar."""

from app.dedupe import dedupe_key


def test_same_meeting_across_users_shares_one_key():
    # The real duplicate from prod: meetings 498 (user 1) and 500 (user 3),
    # both "Vexa - Runway", spawned 0.5s apart.
    a = dedupe_key("google_meet", "https://meet.google.com/ceb-ayzv-ruu")
    b = dedupe_key("google_meet", "https://meet.google.com/ceb-ayzv-ruu/")
    assert a == b


def test_case_and_platform_are_normalised():
    assert dedupe_key("Google_Meet", "HTTPS://MEET.GOOGLE.COM/abc") == dedupe_key(
        "google_meet", "https://meet.google.com/abc"
    )


def test_teams_query_parameters_still_separate_meetings():
    # Teams encodes the meeting identity in the query string — stripping it would
    # fuse unrelated meetings into one and silence a bot that should have joined.
    one = dedupe_key("teams", "https://teams.microsoft.com/l/meetup-join/19:a@thread.v2/0?context=%7B%22Tid%22%3A%221%22%7D")
    two = dedupe_key("teams", "https://teams.microsoft.com/l/meetup-join/19:a@thread.v2/0?context=%7B%22Tid%22%3A%222%22%7D")
    assert one != two


def test_missing_url_has_no_key():
    # No URL means nothing to dedupe against — must never collide with another event.
    assert dedupe_key("google_meet", None) is None
    assert dedupe_key(None, None) is None


if __name__ == "__main__":
    test_same_meeting_across_users_shares_one_key()
    test_case_and_platform_are_normalised()
    test_teams_query_parameters_still_separate_meetings()
    test_missing_url_has_no_key()
    print("ok")
