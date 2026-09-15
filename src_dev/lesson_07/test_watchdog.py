"""Tests for watchdog.py. Every one uses a fake `now` — never a real sleep.

Run with:  python3 -m pytest src_dev/lesson_07/test_watchdog.py -v
or, with no pytest installed:  python3 src_dev/lesson_07/test_watchdog.py
"""

from watchdog import Watchdog, evaluate_stream


def test_fresh_just_received():
    assert evaluate_stream(last_rx=100.0, now=100.5) == 'fresh'


def test_stale_after_one_second():
    assert evaluate_stream(last_rx=100.0, now=101.5) == 'stale'


def test_lost_after_three_seconds():
    assert evaluate_stream(last_rx=100.0, now=103.5) == 'lost'


def test_boundary_at_exactly_one_second_is_already_stale():
    # 1.0s old is no longer < FRESH_S, so the boundary belongs to "stale".
    assert evaluate_stream(last_rx=100.0, now=101.0) == 'stale'


def test_watchdog_tracks_multiple_streams_independently():
    wd = Watchdog(['gps', 'link'])
    wd.mark_received('gps', now=0.0)
    wd.mark_received('link', now=0.0)

    # link goes quiet for a long time; gps gets a fresh message right
    # before the check, so the two must disagree at the exact same instant.
    wd.mark_received('gps', now=10.0)

    assert wd.status('gps', now=10.3) == 'fresh'
    assert wd.status('link', now=10.3) == 'lost'


def test_age_reports_seconds_since_last_message():
    wd = Watchdog(['gps'])
    wd.mark_received('gps', now=50.0)
    assert wd.age('gps', now=52.5) == 2.5


def test_recovering_returns_to_fresh():
    # A stream that went stale isn't stuck — a new message clears it,
    # same as gps_window.py would see if the killed publisher restarted.
    wd = Watchdog(['gps'])
    wd.mark_received('gps', now=0.0)
    assert wd.status('gps', now=2.0) == 'stale'

    wd.mark_received('gps', now=2.0)
    assert wd.status('gps', now=2.3) == 'fresh'


if __name__ == '__main__':
    # Lets you sanity-check this file without pytest installed.
    import sys

    tests = [obj for name, obj in sorted(globals().items()) if name.startswith('test_')]
    for test in tests:
        test()
        print(f'PASS: {test.__name__}')
    print(f'\n{len(tests)} tests passed.')
    sys.exit(0)
