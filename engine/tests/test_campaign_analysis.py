from copy import deepcopy

from decision_lab.campaign_analysis import analyze_world, analyze_worlds, distribution
from decision_lab.committed_campaigns import CommittedCampaignWorld
from test_campaign_worlds import package, decisions


def test_paid_marketing_loss_cannot_hide_behind_flat_founder_cash():
    value = package()
    value['actors'][1]['id'] = 'marketing-partner'
    value['signals'][0]['recipients'] = ['marketing-partner']
    plan = [{'payer': 'founder', 'campaign_id': 'exposure', 'order_second': 0}]
    engine = CommittedCampaignWorld(value, 31, plan)
    checkpoints = []
    for _ in value['decision_seconds']:
        engine.prepare_step()
        checkpoints.append(engine.advance(decisions(engine)))
    result = analyze_world(checkpoints)
    assert result['controlled_liquid_cash_change_cents'] == -29900
    assert result['campaign_cost_cents'] == 29900
    assert result['trade_attempts'] == 0
    assert result['rejection_fraction'] is None
    assert result['turnover_hhi'] is None
    assert result['sampled_max_drawdown_fraction'] == 0
    assert analyze_worlds([result])['worlds_with_controlled_cash_loss'] == 1


def test_drawdown_uses_running_peak_not_just_terminal_return():
    engine = CommittedCampaignWorld(package(), 31, [{'payer': 'founder', 'campaign_id': 'exposure', 'order_second': 0}])
    engine.prepare_step()
    initial = engine.advance(decisions(engine))
    engine.prepare_step()
    second = engine.advance(decisions(engine))
    initial['market_before']['market_cap_usd_exact'] = '100'
    initial['market_after']['market_cap_usd_exact'] = '200'
    second['market_before']['market_cap_usd_exact'] = '200'
    second['market_after']['market_cap_usd_exact'] = '150'
    result = analyze_world([initial, second])
    assert result['terminal_return_fraction'] == .5
    assert result['sampled_max_drawdown_fraction'] == .25


def test_four_worlds_are_not_thousands_of_independent_observations():
    engine = CommittedCampaignWorld(package(), 31, [{'payer': 'founder', 'campaign_id': 'exposure', 'order_second': 0}])
    engine.prepare_step()
    result = analyze_world([engine.advance(decisions(engine))])
    summary = analyze_worlds([deepcopy(result) for _ in range(4)])
    assert summary['n_worlds'] == 4
    assert summary['controlled_cash_change_cents']['n_worlds'] == 4
    assert 'dependent observations' in summary['sample_unit']
    assert distribution([])['median'] is None
