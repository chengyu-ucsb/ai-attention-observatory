"""Stable Monday edition identity, separate from discovery and publication time.

Discovery covers the previous complete UTC Monday–Sunday week. Its edition is
always the following Monday, even when composition or publication finishes later.
"""
import datetime as dt
from zoneinfo import ZoneInfo

from collection_window import previous_week, publication_date


def monday_for_window(window):
    """Return the Monday following an explicitly covered complete UTC week."""
    start = publication_date(window.get('from'))
    end = publication_date(window.get('to'))
    if (window.get('timezone') != 'UTC' or start is None or end is None
            or start.weekday() != 0 or end - start != dt.timedelta(days=6)):
        raise ValueError('An edition requires a complete Monday–Sunday UTC publication window')
    return (end + dt.timedelta(days=1)).isoformat()


def canonical_edition_date(root, date, *, publication_window=None):
    """Return a stable Monday key; archive ordering and retry days cannot move it.

    ``root`` is retained for callers of the earlier archive-dependent helper.
    Existing non-Monday URLs are handled by the archive migration/alias layer,
    not by changing the identity of future editions.
    """
    if publication_window is not None:
        return monday_for_window(publication_window)
    return (previous_week(date)[1] + dt.timedelta(days=1)).isoformat()



def edition_release_open(edition_date, now=None):
    """A Monday edition cannot go live before Monday starts in Eastern time.

    Source discovery may already have rolled over at midnight UTC on Sunday
    evening Eastern. This lower bound applies to the edition's fixed Monday,
    while allowing later recovery or corrections without moving that identity.
    """
    monday = publication_date(edition_date)
    if monday is None or monday.weekday() != 0:
        raise ValueError('Edition release requires a Monday edition date')
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise ValueError('Publication clock must include a timezone-aware datetime')
    opens = dt.datetime.combine(monday, dt.time.min, ZoneInfo('America/New_York'))
    return now >= opens


def _after_monday_time(now, hour, minute):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(now, dt.datetime):
        now = dt.datetime.combine(now, dt.time(12), dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Publication clock must include a timezone')
    monday = dt.date.fromisoformat(canonical_edition_date(None, now))
    deadline = dt.datetime.combine(monday, dt.time(hour, minute), ZoneInfo('America/New_York'))
    return now >= deadline


def publication_cutoff(now=None):
    """Allow the bounded compact synthesis at 11:30 a.m. Eastern on Monday."""
    return _after_monday_time(now, 11, 30)


def release_cutoff(now=None):
    """Publish a coverage notice no earlier than Monday 12:05 p.m. Eastern."""
    return _after_monday_time(now, 12, 5)
