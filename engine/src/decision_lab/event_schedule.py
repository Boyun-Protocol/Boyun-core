"""Normalize researched session starts without inventing agenda-item outcomes."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def calendar_sessions(calendar):
    start = datetime.fromisoformat(calendar['simulation_start'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(calendar['simulation_end'].replace('Z', '+00:00'))
    zone = ZoneInfo(calendar['session_timezone'])
    events = []
    for session in calendar['sessions']:
        for time in session['times']:
            local = datetime.fromisoformat(session['date'] + 'T' + time).replace(tzinfo=zone)
            utc = local.astimezone(timezone.utc)
            if not start <= utc <= end:
                raise ValueError('session outside the reviewed simulation horizon')
            events.append({'id': f'assembly-{session["date"]}-{time.replace(":", "")}',
                           'elapsed_seconds': int((utc - start).total_seconds()),
                           'local_time': local.isoformat(), 'utc_time': utc.isoformat(),
                           'source_id': 'assembly-four-week-agenda', 'source_page': session['source_page'],
                           'topic': session['topic'], 'evidence_type': 'dated_schedule_not_actual_outcome',
                           'asof_status': 'source_dated_before_launch_but_capture_after_cutoff',
                           'outcome': None, 'token_demand_probability': None})
    identifiers = [event['id'] for event in events]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('duplicate calendar session')
    return sorted(events, key=lambda event: event['elapsed_seconds'])
