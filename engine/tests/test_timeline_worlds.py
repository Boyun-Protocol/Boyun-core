from copy import deepcopy
import json

import pytest

from decision_lab.timeline_worlds import TimelineWorld, actor_trajectory, replay_timeline, validate_timeline
from decision_lab.timeline_orchestration import run_timeline
from decision_lab.jev import JevActorModel, prepare_actor_request
from test_agent_worlds import spec, proposal
from test_jev import Transport, client


def package():
    world = spec()
    world['rounds'] = 3
    world['events'] = []
    return {'schema_version': 'timeline-world.v1', 'world': world,
            'start_time': '2026-11-02T12:00:00+04:00', 'decision_seconds': [0, 900, 3600],
            'events': [{'id': 'private-plan', 'event_second': 0, 'available_second': 0,
                        'text': 'Private whale plan: review exposure.', 'source_ref': 'test assumption',
                        'evidence_status': 'assumed_stress', 'occurrence_bps': 10000, 'audience': ['whale']},
                       {'id': 'late-news', 'event_second': 60, 'available_second': 1000,
                        'text': 'Assumed public news, delayed delivery.', 'source_ref': 'test assumption',
                        'evidence_status': 'assumed_stress', 'occurrence_bps': 10000, 'audience': ['public']}]}


def test_clock_private_observations_and_late_delivery():
    engine = TimelineWorld(package())
    first = engine.observations()
    assert 'Private whale plan' in json.dumps(first['whale'])
    assert 'Private whale plan' not in json.dumps(first['retail'])
    assert 'Assumed public news' not in json.dumps(first)
    assert '2026-11-02T12:00:00+04:00' in json.dumps(first)
    for observation in first.values():
        prepare_actor_request(observation)
    engine.advance([proposal(observation) for observation in first.values()])
    second = engine.observations()
    assert 'Assumed public news' not in json.dumps(second)
    engine.advance([proposal(observation) for observation in second.values()])
    third = engine.observations()
    assert 'Assumed public news' in json.dumps(third['retail'])
    assert '2026-11-02T13:00:00+04:00' in json.dumps(third)


def test_trading_changes_fresh_menus_market_and_replays():
    engine = TimelineWorld(package(), seed=7)
    first = engine.observations()
    engine.advance([proposal(observation, 'buy' if actor == 'whale' else 'hold',
                             10000 if actor == 'whale' else 0)
                    for actor, observation in first.items()])
    second = engine.observations()
    assert second['whale']['balance']['token_units'] > 0
    assert first['whale']['public_market'] != second['whale']['public_market']
    assert any(action['kind'] == 'sell' for action in prepare_actor_request(second['whale'])['actions'].values())
    assert engine.snapshot()['previous_barrier_volume_cents'] == 10000
    assert second['whale']['observation_sha256'] != first['whale']['observation_sha256']
    for _ in range(2):
        engine.advance([proposal(observation) for observation in engine.observations().values()])
    report = engine.timeline_report()
    assert replay_timeline(report) == report
    assert report['financial_report']['initial_totals'] == report['financial_report']['ending_totals']
    retail = actor_trajectory(report, 'retail')
    assert 'Private whale plan' not in json.dumps(retail)
    assert 'initial_cash_cents": 200000' not in json.dumps(retail)
    assert retail['edges'][0]['duration_seconds'] == 900
    tampered = deepcopy(report)
    tampered['final_market']['pool_cash_cents'] += 1
    with pytest.raises(ValueError, match='replay mismatch'):
        replay_timeline(tampered)


def test_seeded_events_reproduce_and_zero_probability_is_absent():
    value = package()
    value['events'][0]['occurrence_bps'] = 0
    first = TimelineWorld(value, seed=7)
    second = TimelineWorld(value, seed=7)
    assert first.realized_events == second.realized_events
    assert all(event['id'] != 'private-plan' for event in first.realized_events)


@pytest.mark.parametrize('change', [
    lambda value: value.update(decision_seconds=[0, 900, 900]),
    lambda value: value.update(start_time='2026-11-02T12:00:00'),
    lambda value: value['events'][0].update(available_second=-1),
    lambda value: value['events'][0].update(occurrence_bps=10001),
    lambda value: value['events'][0].update(audience=['missing']),
    lambda value: value['world'].update(rounds=16),
])
def test_invalid_plan_fails_before_inference(change):
    value = package()
    change(value)
    with pytest.raises(ValueError):
        validate_timeline(value)


def test_native_jev_fixture_runs_fresh_barriers_and_preserves_receipts(tmp_path):
    transport = Transport(choice='buy_2500bps')
    manifest = run_timeline(package=package(), client=JevActorModel(client=client(transport)),
                            output_dir=tmp_path / 'run', max_calls=9)
    assert manifest['status'] == 'completed'
    assert manifest['attempted_calls'] == len(transport.calls) == 9
    report = json.loads((tmp_path / 'run/result.json').read_text())
    assert replay_timeline(report) == report
    assert len({json.loads(call['body'])['state']['observation_sha256'] for call in transport.calls}) == 9
    assert 'test-private-key' not in ''.join(path.read_text() for path in (tmp_path / 'run').glob('*.json'))


def test_budget_and_failures_never_retry_or_silently_complete(tmp_path):
    transport = Transport()
    model = JevActorModel(client=client(transport))
    with pytest.raises(ValueError, match='budget'):
        run_timeline(package=package(), client=model, output_dir=tmp_path / 'too-small', max_calls=8)
    assert not transport.calls and not (tmp_path / 'too-small').exists()

    def failure(**kwargs):
        raise ValueError('untrusted secret-bearing error')

    manifest = run_timeline(package=package(), client=JevActorModel(client=client(failure)),
                            output_dir=tmp_path / 'failed', max_calls=9)
    assert manifest['status'] == 'failed'
    assert manifest['attempted_calls'] == 1 and manifest['completed_barriers'] == 0
    assert 'secret-bearing' not in json.dumps(manifest)
    assert (tmp_path / 'failed/call-001.dispatch.json').exists()


def test_browser_export_is_self_contained_and_excludes_other_actors_private_notes():
    from decision_lab.timeline_presentation import timeline_html
    engine = TimelineWorld(package())
    for _ in range(3):
        engine.advance([proposal(observation) for observation in engine.observations().values()])
    page = timeline_html(engine.timeline_report(), 'retail')
    assert 'Private whale plan' not in page
    assert 'timeline-world.v1' not in page
    assert '<script src=' not in page and '<link ' not in page
    assert 'previous_barrier_volume_cents' in page
    assert 'No reasoning trace' in page


def test_export_rejects_response_not_matching_the_actor_path():
    from decision_lab.timeline_presentation import timeline_html
    engine = TimelineWorld(package())
    observation = engine.observations()['retail']
    engine.advance([proposal(item) for item in engine.observations().values()])
    forged = proposal(observation)
    forged['reason'] = 'Forged advice not returned by recorded decision'
    with pytest.raises(ValueError, match='does not match'):
        timeline_html(engine.timeline_report(), 'retail', [{'value': forged, 'receipt': {}}])


def test_oversized_future_observations_reject_before_paid_dispatch(tmp_path):
    value = package()
    value['events'] = [{**value['events'][0], 'id': f'event-{index}',
                        'text': 'x' * 1600, 'audience': ['public']} for index in range(16)]
    transport = Transport()
    with pytest.raises(ValueError, match='observation budget'):
        run_timeline(package=value, client=JevActorModel(client=client(transport)),
                     output_dir=tmp_path / 'oversized', max_calls=9)
    assert not transport.calls and not (tmp_path / 'oversized').exists()


def test_cli_replay_and_html_export_are_offline_and_refuse_overwrite(tmp_path):
    from decision_lab.cli import main
    engine = TimelineWorld(package())
    for _ in range(3):
        engine.advance([proposal(observation) for observation in engine.observations().values()])
    source = tmp_path / 'result.json'
    source.write_text(json.dumps(engine.timeline_report()))
    output = tmp_path / 'retail.json'
    assert main(['timeline', 'replay', '--input', str(source), '--actor', 'retail',
                 '--output', str(output)]) == 0
    assert json.loads(output.read_text())['actor_id'] == 'retail'
    page = tmp_path / 'retail.html'
    arguments = ['timeline', 'export', '--input', str(source), '--actor', 'retail', '--output', str(page)]
    assert main(arguments) == 0
    before = page.read_bytes()
    assert main(arguments) == 2
    assert page.read_bytes() == before
