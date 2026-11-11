"""Publication target in Eastern time; original publication eligibility stays UTC."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/New_York')


def publication_target(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('timezone_required')
    utc_day = now.astimezone(timezone.utc).date()
    monday = utc_day - timedelta(days=utc_day.weekday())
    target = datetime.combine(monday, time(12), ZONE)
    return {'timezone': ZONE.key, 'target_at': target.isoformat(),
            'target_collection_week': monday.isoformat(),
            'source_window': {'from': (monday-timedelta(days=7)).isoformat(),
                              'to': (monday-timedelta(days=1)).isoformat(), 'timezone': 'UTC'},
            'deadline_elapsed': now >= target,
            'schedule_basis': 'Target time; provider access, evidence gates and runner delays can defer publication'}
