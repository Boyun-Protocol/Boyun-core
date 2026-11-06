import json
from pathlib import Path

from decision_lab.event_schedule import calendar_sessions
from decision_lab.launch_decision_policy import decision_schedule, HORIZON


def test_real_calendar_conversion_and_full_horizon_coverage():
    root = Path(__file__).resolve().parents[2]
    calendar = json.loads((root/'engine/examples/MACRON_EVENT_CALENDAR.json').read_text())
    sessions = calendar_sessions(calendar)
    assert len(sessions) == 29
    assert sessions[0]['elapsed_seconds'] == 0
    assert sessions[1]['elapsed_seconds'] == 6*3600
    assert sessions[2]['elapsed_seconds'] == 12*3600+1800
    assert sessions[-1]['elapsed_seconds'] == HORIZON
    assert all(event['outcome'] is None and event['token_demand_probability'] is None for event in sessions)
    schedule = decision_schedule(event['elapsed_seconds'] for event in sessions)
    assert len(schedule) == 362
    assert all(hour*3600 in schedule for hour in range(337))
