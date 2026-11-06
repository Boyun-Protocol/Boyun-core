from copy import deepcopy
import json

import pytest

from decision_lab.lifecycle_runs import SpendGuard, lifecycle_request, run_lifecycle, replay_lifecycle
from decision_lab.launch_lifecycle import LaunchLifecycle
from test_launch_lifecycle import example
from test_jev import client, response


def test_two_dollar_guard_reserves_before_dispatch_and_retains_uncertain_cost():
    guard = SpendGuard('2.00')
    reservation = guard.reserve({'state': 'x' * 1000})
    assert guard.reserved_micro_usd > 0
    guard.settle(reservation, {'usage': {'input_tokens': 200}})
    assert guard.spent_micro_usd > 0 and guard.reserved_micro_usd == 0
    with pytest.raises(ValueError, match='budget'):
        guard.reserve({'state': 'x' * 50000000})
    assert guard.spent_micro_usd <= 2000000


def test_compact_requests_keep_actor_memory_and_hide_private_team_information():
    engine = LaunchLifecycle(example())
    engine.prepare()
    engine.messages.append({'recipient': 'mm', 'sender': 'founder', 'choice': 'PRIVATE_COMMAND', 'available_second': 0})
    retail = lifecycle_request(engine, 'retail', 'jev-1.14.0')
    mm = lifecycle_request(engine, 'mm', 'jev-1.14.0')
    assert 'PRIVATE_COMMAND' not in json.dumps(retail)
    assert 'PRIVATE_COMMAND' in json.dumps(mm)
    assert retail['state']['memory']['own_last_choice'] is None
    assert len(json.dumps(retail)) < 5000


def test_full_offline_reference_executes_every_hour_saves_states_and_replays(tmp_path):
    root = tmp_path / 'reference'
    result = run_lifecycle(package=example(), output_dir=root, seed=31, mode='offline_reference')
    assert result['status'] == 'completed'
    assert result['model_calls'] == 0
    assert result['summary']['last_second'] == 1209600
    assert result['summary']['reserve_cents'] == 1000000
    assert replay_lifecycle(root)['verified_steps'] >= len(example()['decision_seconds'])
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest['mode'] == 'offline_reference_not_jev'


def test_native_fixture_cost_receipts_and_actions_replay_without_new_inference(tmp_path):
    calls = []
    def transport(**kwargs):
        payload = json.loads(kwargs['body'])
        calls.append(payload)
        return json.dumps(response(payload, 'wait')).encode()
    root = tmp_path / 'native-fixture'
    result = run_lifecycle(package=example(), output_dir=root, seed=31,
                           mode='jev', client=client(transport), spend_guard=SpendGuard('2'),
                           evidence_register=reference_register(example()))
    assert result['status'] == 'completed', result
    assert result['model_calls'] == len(calls) > 300
    assert result['summary']['last_second'] == 1209600
    assert replay_lifecycle(root)['verified_steps'] >= len(example()['decision_seconds'])
    saved = json.loads((root / 'step-00001.json').read_text())
    saved['checkpoint']['balances_after']['founder']['cash_cents'] += 1
    (root / 'step-00001.json').write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='replay'):
        replay_lifecycle(root)


def reference_register(package):
    from decision_lab.agent_worlds import digest
    from decision_lab.lifecycle_runs import lifecycle_targets
    from test_simulation_evidence import register
    value = register()
    value['target_sha256'] = digest(package)
    value['claims'][0]['statement'] = 'All inputs are explicit finite-wallet synthetic sensitivity fixtures.'
    value['claims'].append({**deepcopy(value['claims'][0]), 'id': 'scores', 'kind': 'probability',
                            'probability_kind': 'model_score', 'uncertainty': 'Uncalibrated synthetic decisions.'})
    value['bindings'] = {target: 'closing-cash' if kind == 'outcome' else 'scores' if kind == 'probability' else 'capital'
                         for target, kind in lifecycle_targets(package).items()}
    return value


def test_native_run_without_evidence_or_insufficient_budget_never_dispatches(tmp_path):
    calls = []
    def transport(**kwargs):
        calls.append(kwargs)
        raise AssertionError('should not dispatch')
    for register, cap in ((None, '2'), (reference_register(example()), '0.000001')):
        destination = tmp_path / str(len(calls))
        with pytest.raises(ValueError):
            run_lifecycle(package=example(), output_dir=destination, seed=31, mode='jev',
                           client=client(transport), spend_guard=SpendGuard(cap), evidence_register=register)
        assert not calls and not destination.exists()
