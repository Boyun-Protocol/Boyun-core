from copy import deepcopy
from fractions import Fraction
import json

import pytest

from decision_lab.evolving_worlds import EvolvingWorld, evolving_actor_trajectory, replay_evolving
from decision_lab.timeline_orchestration import run_timeline
from decision_lab.jev import JevActorModel, prepare_actor_request
from decision_lab.timeline_presentation import timeline_html
from test_agent_worlds import proposal
from test_timeline_worlds import package
from test_jev import Transport, client


def evolving_package():
    value = package()
    value['schema_version'] = 'timeline-world.v2'
    value['token'] = {'symbol': 'MACRON-TEST', 'decimals': 6,
                      'total_supply_units': 3000000, 'circulating_supply_units': 2000000,
                      'volume_windows_seconds': [900, 3600],
                      'provenance': 'Explicit assumed test supply; not real MACRON supply'}
    return value


def step(engine, buyer=None, amount=10000):
    engine.advance([proposal(observation, 'buy' if actor == buyer else 'hold',
                             amount if actor == buyer else 0)
                    for actor, observation in engine.observations().items()])


def test_every_step_saves_pre_post_state_and_feeds_own_context_forward():
    engine = EvolvingWorld(evolving_package())
    step(engine, buyer='whale')
    record = engine.checkpoints[0]
    assert record['market_before']['pool_cash_cents'] != record['market_after']['pool_cash_cents']
    assert record['balances_after']['whale']['token_units'] > 0
    assert record['own_choices_by_actor']['whale']['action']['kind'] == 'buy'
    next_observation = engine.observations()['whale']
    memory = json.loads(next(item['text'] for item in next_observation['messages']
                             if item['id'].startswith('state-memory:')))
    assert memory['completed_barriers'][0]['market_after'] == record['market_after']
    assert next_observation['own_history'][0]['proposal']['action']['kind'] == 'buy'
    assert memory['completed_barriers'][0]['own_balance_after'] == record['balances_after']['whale']
    assert any(action['kind'] == 'sell' for action in prepare_actor_request(next_observation)['actions'].values())


def test_volume_windows_use_execution_time_and_real_elapsed_duration():
    engine = EvolvingWorld(evolving_package())
    step(engine, buyer='whale', amount=10000)
    assert engine.checkpoints[0]['market_after']['volume_windows_cents'] == {'900': 10000, '3600': 10000}
    step(engine, buyer='whale', amount=5000)
    assert engine.checkpoints[1]['market_before']['volume_windows_cents']['900'] == 0
    assert engine.checkpoints[1]['market_after']['volume_windows_cents']['900'] == 5000
    step(engine)
    final = engine.checkpoints[-1]['market_after']
    assert final['volume_windows_cents'] == {'900': 0, '3600': 5000}
    assert final['cumulative_volume_cents'] == 15000
    assert final['executed_trade_count'] == 2


def test_market_cap_and_fdv_follow_declared_supply_and_exact_price():
    engine = EvolvingWorld(evolving_package())
    step(engine, buyer='whale')
    state = engine.checkpoints[0]['market_after']
    assert Fraction(state['fdv_usd_exact']) * 2 == Fraction(state['market_cap_usd_exact']) * 3
    assert Fraction(state['price_usd_per_token_exact']) * 3 == Fraction(state['fdv_usd_exact'])


def test_replay_and_projection_retain_state_without_private_peer_context():
    engine = EvolvingWorld(evolving_package())
    step(engine, buyer='whale')
    step(engine)
    step(engine)
    report = engine.timeline_report()
    assert replay_evolving(report) == report
    projected = evolving_actor_trajectory(report, 'retail')
    serialized = json.dumps(projected)
    assert 'Private whale plan' not in serialized
    assert 'balances_before' not in serialized
    assert 'own_choices_by_actor' not in serialized
    assert projected['nodes'][0]['market_after']['executed_trade_count'] == 1
    page = timeline_html(report, 'retail')
    assert 'Private whale plan' not in page
    assert 'Saved token state before / after' in page
    altered = deepcopy(report)
    altered['checkpoints'][0]['market_after']['market_cap_usd_exact'] = '99999'
    with pytest.raises(ValueError, match='replay mismatch'):
        replay_evolving(altered)


def test_inference_saves_each_checkpoint_and_observation_bundle(tmp_path):
    transport = Transport(choice='buy_2500bps')
    result = run_timeline(package=evolving_package(), client=JevActorModel(client=client(transport)),
                          output_dir=tmp_path / 'run', max_calls=9)
    assert result['status'] == 'completed'
    assert len(list((tmp_path / 'run').glob('barrier-*.checkpoint.json'))) == 3
    assert len(list((tmp_path / 'run').glob('barrier-*.observations.json'))) == 3
    assert len(transport.calls) == 9
    state = json.loads(transport.calls[-1]['body'])['state']
    assert 'state-memory:3' in json.dumps(state)
    assert json.loads((tmp_path / 'run/result.json').read_text())['schema_version'] == 'timeline-world-results.v2'


@pytest.mark.parametrize('change', [
    lambda value: value['token'].update(circulating_supply_units=0),
    lambda value: value['token'].update(total_supply_units=1),
    lambda value: value['token'].update(volume_windows_seconds=[3600, 900]),
    lambda value: value['token'].update(decimals=True),
])
def test_bad_supply_and_window_definitions_reject(change):
    value = evolving_package()
    change(value)
    with pytest.raises(ValueError):
        EvolvingWorld(value)
