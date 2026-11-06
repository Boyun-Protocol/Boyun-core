from collections import Counter
from copy import deepcopy
from fractions import Fraction
import json

import pytest

from decision_lab.campaign_stress import stress_action, stress_config, stress_package
from decision_lab.campaign_worlds import CampaignWorld
from decision_lab.campaign_orchestration import run_campaign_experiment, replay_campaign_experiment, summarize_campaign_experiment
from test_campaign_worlds import package, evidence
from test_jev import client, response


def scored(engine, actor):
    actions = engine.menu(actor)[0]
    scores = {key: 0 for key in actions}
    scores['wait'] = .8
    buys = [key for key, value in actions.items() if value['kind'] == 'buy']
    sells = [key for key, value in actions.items() if value['kind'] == 'sell']
    for keys in (buys, sells):
        if keys:
            scores[keys[0]] = .1
        else:
            scores['wait'] += .1
    return {'answers': {'action': {'choice': 'wait', 'confidence': .9, 'probabilities': scores}}}


def transport(**kwargs):
    payload = json.loads(kwargs['body'])
    result = response(payload, 'wait')
    if 'action' in result['answers']:
        scores = {key: 0 for key in payload['questions']['action']['criteria']}
        scores['wait'] = .8
        for prefix in ('buy_', 'sell_'):
            keys = [key for key in scores if key.startswith(prefix)]
            if keys:
                scores[keys[0]] = .1
            else:
                scores['wait'] += .1
        result['answers']['action']['probabilities'] = scores
    return json.dumps(result).encode()


def test_weights_multiply_odds_not_claimed_observed_frequency():
    engine = CampaignWorld(package())
    answer = scored(engine, 'founder')
    _, metadata = stress_action(engine, 'founder', answer, stress_config())
    weights = {key: Fraction(value) for key, value in metadata['normalized_weights_exact'].items()}
    assert weights['buy_2500'] == Fraction(1, 4)
    assert weights['sell_2500'] == Fraction(1, 4)
    assert weights['wait'] == Fraction(1, 2)
    assert weights['buy_2500'] / weights['wait'] == 4 * Fraction(1, 10) / Fraction(8, 10)
    assert answer == scored(engine, 'founder')
    assert metadata == stress_action(engine, 'founder', answer, stress_config())[1]


def test_seeded_stress_draws_increase_both_buys_and_sells():
    engine = CampaignWorld(package())
    answer = scored(engine, 'founder')
    original, stress = Counter(), Counter()
    for seed in range(3000):
        engine.seed = seed
        selected, metadata = stress_action(engine, 'founder', answer, stress_config())
        original[metadata['unbuffed_same_draw_action']] += 1
        stress[selected] += 1
    assert stress['buy_2500'] > original['buy_2500'] * 2
    assert stress['sell_2500'] > original['sell_2500'] * 2
    assert stress['wait'] < original['wait']


def test_ticket_caps_increase_without_minting_cash_or_tokens():
    original = package()
    before = deepcopy(original)
    stressed = stress_package(original, stress_config(ticket_multiplier=5))
    assert original == before
    assert stressed['actors'][0]['max_buy_cents'] == original['actors'][0]['max_buy_cents'] * 5
    engine = CampaignWorld(stressed)
    assert engine.initial_totals == CampaignWorld(original).initial_totals
    assert engine.menu('founder')[0]['buy_10000']['amount'] <= original['actors'][0]['cash_cents']
    assert 'sell_2500' not in engine.menu('retail')[0]
    assert 'ARTIFICIAL LOAD TEST' in json.dumps(engine.observation('retail'))


def test_zero_provider_weight_is_not_replaced_with_fabricated_demand():
    engine = CampaignWorld(package())
    answer = scored(engine, 'founder')
    answer['answers']['action']['probabilities'] = {key: int(key == 'wait') for key in engine.menu('founder')[0]}
    assert stress_action(engine, 'founder', answer, stress_config())[0] == 'wait'


def test_long_stress_run_trades_conserves_and_replays_with_policy_evidence(tmp_path):
    config = stress_config()
    value = package([0] + list(range(60, 60 * 172, 60)))
    root = tmp_path / 'stress'
    result = run_campaign_experiment(package=value, client=client(transport), output_dir=root,
                                     worlds=4, max_calls=2064, stress=config,
                                     evidence_register=evidence(value, stress=config))
    assert result['status'] == 'completed', result
    assert result['completed_calls'] == 2064
    saved_package = json.loads((root / 'package.json').read_text())
    assert saved_package['actors'][0]['max_buy_cents'] == value['actors'][0]['max_buy_cents'] * 2
    assert replay_campaign_experiment(root)['verified_steps'] == 688
    summary = summarize_campaign_experiment(root)
    assert summary['completed_actor_calls'] == 2064
    assert summary['settlement_counts']['buy:executed'] > 0
    assert summary['settlement_counts']['sell:executed'] > 0
    assert summary['executed_volume_cents'] > 0
    assert summary['provider_action_counts'] == {'wait': 2064}
    totals = CampaignWorld(value).initial_totals
    for world in result['world_summaries']:
        assert sum(balance['cash_cents'] for balance in world['balances'].values()) == totals[0]
        assert sum(balance['token_units'] for balance in world['balances'].values()) == totals[1]
        assert world['actor_summaries']['retail']['bought_cents'] > 0
        assert world['actor_summaries']['retail']['sold_cents'] > 0
    path = root / 'call-000001.response.json'
    saved = json.loads(path.read_text())
    assert saved['answers']['action']['choice'] == 'wait'
    assert saved['stress_policy']['confidence_gate'].startswith('bypassed')
    saved['stress_policy']['draw_uint53'] += 1
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='sampling replay'):
        replay_campaign_experiment(root)


@pytest.mark.parametrize('value', [0, 6, True, 1.5])
def test_invalid_multipliers_fail_closed(value):
    with pytest.raises(ValueError):
        stress_config(buy_multiplier=value)


def test_cli_stress_plan_is_explicit_and_offline(tmp_path, capsys):
    from decision_lab.cli import main
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(package()))
    base = ['campaign', 'plan', '--input', str(source), '--worlds', '200', '--max-calls', '2400']
    assert main(base + ['--stress', '--buy-multiplier', '5']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['stress_policy']['buy_multiplier'] == 5 and result['model_calls'] == 0
    assert main(base + ['--buy-multiplier', '5']) == 2
