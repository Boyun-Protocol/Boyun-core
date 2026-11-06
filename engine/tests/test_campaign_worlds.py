from copy import deepcopy
import json

import pytest

from decision_lab.campaign_worlds import CampaignWorld, campaign_plan, campaign_request, decide_campaign
from decision_lab.campaign_orchestration import run_campaign_experiment, replay_campaign_experiment
from test_jev import Transport, client, response


def package(steps=None):
    return {'schema_version': 'campaign-world.v1', 'id': 'test-campaign',
            'start_time': '2026-11-02T12:00:00+04:00', 'decision_seconds': steps or [0, 60, 3600, 7200],
            'market': {'cash_cents': 500000, 'token_units': 800000, 'fee_bps': 30, 'max_slippage_bps': 1000},
            'token': {'decimals': 0, 'total_supply_units': 1000000, 'circulating_supply_units': 1000000,
                      'provenance': 'Synthetic test allocation'},
            'actors': [{'id': actor, 'role': actor, 'goal': 'Manage hypothetical own risk and cash.',
                        'cash_cents': 100000, 'token_units': 100000 if actor != 'retail' else 0,
                        'max_buy_cents': 10000, 'campaign_ids': ['exposure'] if actor == 'founder' else []}
                       for actor in ('founder', 'mm', 'retail')],
            'campaigns': [{'id': 'exposure', 'price_cents': 29900, 'delay_seconds': 60,
                           'duration_seconds': 3600, 'delivery_bps': 10000,
                           'public_text': 'Hypothetical paid visibility, not a demand guarantee.',
                           'source_ref': 'test assumption', 'evidence_status': 'assumed', 'audience': ['public']}],
            'signals': [{'id': 'review', 'sender': 'founder', 'recipients': ['mm'], 'text': 'PRIVATE: review exposure timing.'}],
            'events': [{'id': 'news', 'event_second': 60, 'available_second': 3600,
                        'text': 'DELAYED public news', 'source_ref': 'test assumption', 'audience': ['public'],
                        'occurrence_bps': 10000}],
            'assumptions': ['No historical calibration; fictional accounting test.']}


def evidence(value, *, commitments=None, stress=None, sample_actions=True):
    from decision_lab.campaign_evidence import campaign_evidence_context, campaign_evidence_targets
    from decision_lab.agent_worlds import digest
    if stress is not None:
        from decision_lab.campaign_stress import stress_package
        value = stress_package(value, stress)
    context = campaign_evidence_context(value, commitments=commitments, stress=stress, sample_actions=sample_actions)
    targets = campaign_evidence_targets(context)
    assumption = {'status': 'assumed', 'depends_on': [],
                  'rationale': 'Fictional finite wallet, event and behavior fixtures isolate conserved settlement and sampling mechanics.',
                  'sensitivity': 'Tests vary fees, balances, delivery endpoints, time, trade choices and activity weights.',
                  'falsification': 'Reject any claim that test fixtures estimate real-world behavior or prices.'}
    return {'schema_version': 'simulation-evidence.v1', 'as_of': value['start_time'],
            'target_sha256': digest(context), 'sources': [],
            'claims': [
                {**assumption, 'id': 'inputs', 'kind': 'input', 'statement': 'Synthetic test inputs, not measured populations.'},
                {**assumption, 'id': 'scores', 'kind': 'probability', 'statement': 'Controlled synthetic action/delivery scores.',
                 'probability_kind': 'assumed_probability', 'uncertainty': 'Test-only weights, not calibrated event odds.'},
                {'id': 'mechanics', 'kind': 'mechanism', 'status': 'derived', 'statement': 'Integer ledger and finite action settlement.',
                 'depends_on': ['inputs', 'scores'], 'method': 'Use implemented finite ledger and campaign rules; reject unaffordable fills.'},
                {'id': 'results', 'kind': 'outcome', 'status': 'derived', 'statement': 'Conditional synthetic checkpoint outputs.',
                 'depends_on': ['mechanics'], 'method': 'Read executed fills, balances and AMM quotes; costs do not create demand.'},
            ],
            'bindings': {target: 'results' if kind == 'outcome' else 'scores' if kind == 'probability' else 'inputs'
                         for target, kind in targets.items()}}


def decisions(engine, overrides=None):
    overrides = overrides or {}
    return [{'actor_id': actor, 'observation_sha256': engine.observation(actor)['observation_sha256'],
             'action_id': overrides.get(actor, {}).get('action_id', 'wait'),
             'signal_id': overrides.get(actor, {}).get('signal_id', 'silent')} for actor in engine.actors]


def test_campaign_cost_is_not_a_price_pump_and_private_signal_is_next_step():
    engine = CampaignWorld(package())
    first = engine.observation('mm')
    checkpoint = engine.advance(decisions(engine, {'founder': {'action_id': 'campaign_exposure', 'signal_id': 'signal_review'}}))
    assert checkpoint['market_before'] == checkpoint['market_after']
    assert not first['coordination']
    assert 'PRIVATE' in json.dumps(engine.observation('mm'))
    retail = engine.observation('retail')
    assert 'PRIVATE' not in json.dumps(retail)
    assert retail['visible_campaigns'][0]['status'] == 'active'
    assert 'DELAYED' not in json.dumps(retail)
    assert engine.ledger.accounts['services'].cash_cents == 29900
    assert 'campaign_exposure' not in engine.menu('founder')[0]
    assert engine.ledger.totals() == engine.initial_totals
    engine.advance(decisions(engine))
    assert 'DELAYED' in json.dumps(engine.observation('retail'))
    engine.advance(decisions(engine))
    assert engine.observation('retail')['visible_campaigns'][0]['status'] == 'expired'


def test_failed_delivery_is_hidden_before_due_and_never_fabricates_visibility():
    value = package()
    value['campaigns'][0].update(delivery_bps=0, delay_seconds=3600)
    engine = CampaignWorld(value)
    engine.advance(decisions(engine, {'founder': {'action_id': 'campaign_exposure'}}))
    assert engine.observation('founder')['own_campaign_commitments'][0]['status'] == 'pending'
    assert 'delivery_succeeds' not in json.dumps(engine.observation('founder'))
    engine.advance(decisions(engine))
    assert engine.observation('founder')['own_campaign_commitments'][0]['status'] == 'failed'
    assert not engine.observation('retail')['visible_campaigns']


def test_actual_trades_move_market_preserve_assets_and_keep_memory():
    engine = CampaignWorld(package())
    assert 'sell_2500' in engine.menu('founder')[0]
    checkpoint = engine.advance(decisions(engine, {'retail': {'action_id': 'buy_10000'}}))
    assert checkpoint['market_after']['price_usd_exact'] != checkpoint['market_before']['price_usd_exact']
    assert engine.observation('retail')['own_balance']['token_units'] > 0
    assert engine.market_summary['cumulative_volume_cents'] == 10000
    assert engine.observation('retail')['own_recent_memory'][0]['settlement']['status'] == 'executed'
    assert engine.ledger.totals() == engine.initial_totals


def test_invalid_barrier_is_atomic():
    engine = CampaignWorld(package())
    original = engine.observation('founder')
    proposed = decisions(engine, {'retail': {'action_id': 'campaign_exposure'}})
    with pytest.raises(ValueError, match='menu'):
        engine.advance(proposed)
    assert original == engine.observation('founder')
    assert not engine.orders and engine.index == 0


def test_event_sampling_is_reproducible_and_never_leaks_unrealized_events():
    value = package()
    value['events'][0]['occurrence_bps'] = 0
    engine = CampaignWorld(value)
    assert not engine.realized_events
    assert engine.realized_events == CampaignWorld(value).realized_events
    for _ in range(3):
        engine.advance(decisions(engine))
    assert 'DELAYED' not in json.dumps(engine.observation('retail'))


def test_native_wire_fixture_reacts_to_visibility_not_hidden_future():
    calls = []
    def transport(**kwargs):
        payload = json.loads(kwargs['body'])
        calls.append(payload)
        actor = payload['state']['actor']['id']
        choice = 'wait'
        if actor == 'founder' and payload['state']['step'] == 0:
            choice = 'campaign_exposure'
        if actor == 'retail' and payload['state']['visible_campaigns']:
            choice = 'buy_2500'
        return json.dumps(response(payload, choice)).encode()
    engine = CampaignWorld(package())
    for _ in range(4):
        engine.advance([decide_campaign(engine, actor, client(transport))['decision'] for actor in engine.actors])
    assert len(calls) == 12
    assert engine.summary['retail']['bought_cents'] > 0
    assert engine.summary['founder']['campaign_spend_cents'] == 29900


def test_thousand_turn_streamed_run_replays_without_unbounded_context(tmp_path):
    value = package([0] + list(range(60, 60 * 172, 60)))
    calls = []
    def transport(**kwargs):
        calls.append(kwargs)
        payload = json.loads(kwargs['body'])
        state = payload['state']
        menu = payload['questions'].get('action', {}).get('criteria', {})
        choice = 'sell_2500' if state['step'] % 2 else 'buy_2500'
        if state['actor']['id'] == 'founder' and state['step'] == 0:
            choice = 'campaign_exposure'
        if choice not in menu:
            choice = 'wait'
        result = response(payload, choice)
        if state['actor']['id'] == 'founder' and state['step'] == 0:
            result['answers']['coordination'].update(choice='signal_review',
                probabilities={'signal_review': 1.0, 'silent': 0.0})
        return json.dumps(result).encode()
    result = run_campaign_experiment(package=value, client=client(transport), output_dir=tmp_path / 'run',
                                     worlds=4, max_calls=2064, evidence_register=evidence(value))
    assert result['status'] == 'completed', result
    assert result['completed_calls'] == len(calls) == 2064
    assert result['completed_steps'] == 688
    assert replay_campaign_experiment(tmp_path / 'run') == {'verified_steps': 688, 'verified_worlds': 4, 'model_calls': 0}
    sizes = [len(json.dumps(json.loads(call['body'])['state'])) for call in calls]
    assert max(sizes) < 20000
    assert result['world_summaries'][0]['actor_summaries']['retail']['bought_cents'] > 0
    assert result['world_summaries'][0]['actor_summaries']['retail']['sold_cents'] > 0
    assert result['world_summaries'][0]['actor_summaries']['founder']['campaign_spend_cents'] == 29900
    last_request = json.loads(calls[-1]['body'])['state']
    assert last_request['market_summary']['executed_trades'] > 400
    assert last_request['public_state_memory'][0]['before']['second'] > 0
    assert 'PRIVATE' not in json.dumps(last_request)
    checkpoint = tmp_path / 'run/world-0000-step-00000.checkpoint.json'
    saved = json.loads(checkpoint.read_text())
    saved['balances_after']['retail']['cash_cents'] += 1
    checkpoint.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='replay mismatch'):
        replay_campaign_experiment(tmp_path / 'run')


def test_call_budget_and_failure_preserve_evidence_without_retry(tmp_path):
    transport = Transport()
    with pytest.raises(ValueError, match='budget'):
        run_campaign_experiment(package=package(), client=client(transport), output_dir=tmp_path / 'small',
                                 worlds=1, max_calls=11)
    assert not transport.calls and not (tmp_path / 'small').exists()
    def failure(**kwargs):
        raise RuntimeError('SECRET error')
    result = run_campaign_experiment(package=package(), client=client(failure), output_dir=tmp_path / 'failed',
                                     worlds=1, max_calls=12, evidence_register=evidence(package()))
    assert result['status'] == 'failed' and result['attempted_calls'] == 1 and result['completed_calls'] == 0
    assert 'SECRET' not in json.dumps(result)
    assert (tmp_path / 'failed/call-000001.dispatch.json').exists()
    assert replay_campaign_experiment(tmp_path / 'failed')['verified_steps'] == 0


def test_cli_plan_requires_no_credentials(capsys, tmp_path):
    from decision_lab.cli import main
    source = tmp_path / 'package.json'
    source.write_text(json.dumps(package()))
    assert main(['campaign', 'plan', '--input', str(source), '--worlds', '200', '--max-calls', '2400']) == 0
    assert json.loads(capsys.readouterr().out)['required_calls'] == 2400


@pytest.mark.parametrize('field', ['campaigns', 'signals'])
def test_choice_identifiers_cannot_overflow_native_bounds(field):
    value = package()
    value[field][0]['id'] = 'a' * 48
    with pytest.raises(ValueError, match='choice budget'):
        CampaignWorld(value)
