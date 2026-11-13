"""Publication cutoff; discovery windows remain the previous complete UTC week."""
import datetime as dt
import json
from zoneinfo import ZoneInfo


def publication_cutoff(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(now, dt.datetime):
        now = dt.datetime.combine(now, dt.time(12), dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Publication clock must include a timezone')
    utc_date = now.astimezone(dt.timezone.utc).date()
    monday = utc_date - dt.timedelta(days=utc_date.weekday())
    deadline = dt.datetime.combine(monday, dt.time(11, 30), ZoneInfo('America/New_York'))
    return now >= deadline


def canonical_edition_date(root, date):
    """Upgrade a coverage notice at its existing permanent URL."""
    from collection_window import window_metadata
    window = window_metadata(date)
    for path in sorted((root / 'data/approved-issues').glob('????-??-??.json'), reverse=True):
        issue = json.loads(path.read_text())
        if (issue.get('status') == 'published'
                and window_metadata(issue['edition_date']) == window
                and (issue.get('publication_window') or window) == window):
            return issue['edition_date']
    return date
