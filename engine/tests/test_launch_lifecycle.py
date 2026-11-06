from copy import deepcopy

import pytest

from decision_lab.launch_lifecycle import LaunchLifecycle, validate_lifecycle
from decision_lab.launch_decision_policy import HORIZON, decision_schedule


def example():
    return {
        'schema_version': 'launch-lifecycle.v1', 'id': 'fictional-lifecycle',
        'start_time': '2026-11-02T08:00:00Z', 'decision_seconds': decision_schedule(),
        'supply': 1000000000, 'curve_inventory': 793100000,
        'virtual_cash_cents': 270000, 'virtual_tokens': 1073000000,
        'fee_bps': 100, 'max_slippage_bps': 3000,
        'founder': {'id': 'founder', 'capital_cents': 5000000, 'reserve_cents': 1000000,
                    'position_cents': 500000, 'upfront_cents': 500000,
                    'loss_budget_cents': 1000000, 'response_delay_seconds': 600},
        'actors': [
            {'id': 'founder', 'role': 'founder', 'goal': 'Preserve controlled cash.', 'cash_cents': 0, 'ticket_cents': 10000},
            {'id': 'retail', 'role': 'retail', 'goal': 'Manage own funds.', 'cash_cents': 1000000, 'ticket_cents': 100000},
            {'id': 'mm', 'role': 'mm', 'goal': 'Inventory-capped team-directed maker.', 'cash_cents': 200000, 'ticket_cents': 20000},
        ],
        'kol_ids': [], 'kol_cash_cents': 0, 'kol_supply_bps': 0,
        'events': [], 'campaigns': [], 'regime': 'BEAR', 'activity_multiplier': 1,
        'assumptions': ['Fictional finite actor balances and static fee sensitivity, not an observed token.'],
    }


def choices(engine, overrides=None):
    overrides = overrides or {}
    return {actor: overrides.get(actor, 'wait') for actor in engine.actors}


def test_fourteen_days_are_executed_and_state_is_conserved_without_phantom_pool_cash():
    engine = LaunchLifecycle(example(), seed=31)
    assert engine.cash_total() == 6200000
    assert engine.token_total() == 1000000000
    assert engine.wallets['founder']['tokens'] == 0
    observed_seconds = []
    while engine.index < len(engine.schedule):
        second = engine.second
        engine.prepare()
        checkpoint = engine.advance(choices(engine))
        assert checkpoint['second'] == second
        observed_seconds.append(second)
        assert engine.cash_total() == 6200000 and engine.token_total() == 1000000000
    assert checkpoint['second'] == HORIZON
    assert set(example()['decision_seconds']) <= set(observed_seconds)
    assert engine.wallets['reserve']['cash_cents'] == 1000000
    assert engine.wallets['founder']['cash_cents'] == 3250000
    assert engine.phase == 'curve'


def test_migration_uses_only_real_collected_cash_and_has_no_free_founder_or_kol_tokens():
    value = example()
    value['kol_ids'] = ['retail']
    value['kol_supply_bps'] = 300
    value['actors'][1]['ticket_cents'] = 1000000
    engine = LaunchLifecycle(value, seed=31)
    engine.prepare()
    assert engine.wallets['retail']['tokens'] == 30000000
    checkpoint = engine.advance(choices(engine, {'retail': 'buy_all'}))
    assert engine.phase == 'pool'
    assert engine.wallets['venue']['cash_cents'] < 1000000
    assert engine.wallets['founder']['tokens'] > 0
    assert any(event['kind'] == 'migration' for event in checkpoint['events'])
    assert engine.cash_total() == 6200000 and engine.token_total() == 1000000000


def test_matched_branches_share_exact_prefix_and_keep_trading_after_founder_exit():
    engine = LaunchLifecycle(example(), seed=4)
    engine.prepare()
    engine.advance(choices(engine, {'retail': 'buy_all'}))
    paused, exited = engine.fork('pause-and-observe'), engine.fork('staged-exit')
    assert paused.chain_hash == exited.chain_hash
    assert paused.seed == exited.seed
    exited.trigger_response(3600)
    paused.trigger_response(3600)
    assert 4200 in exited.schedule and 6900 in exited.schedule
    while exited.index < len(exited.schedule):
        exited.prepare()
        exited.advance(choices(exited))
    assert exited.history[-1]['second'] == HORIZON
    assert exited.wallets['founder']['tokens'] == 0
    assert exited.wallets['reserve']['cash_cents'] == 1000000
    assert exited.response['tranches_completed'] == 4


def test_wait_does_not_fabricate_turnover_and_campaign_payment_is_not_a_price_pump():
    value = example()
    value['campaigns'] = [{'id': 'info', 'due_second': 0, 'expires_second': 3600,
                           'delivery_bps': 10000, 'text': 'Hypothetical paid information is available.'}]
    engine = LaunchLifecycle(value)
    engine.prepare()
    price = engine.market()['price_usd_exact']
    checkpoint = engine.advance(choices(engine))
    assert engine.market()['price_usd_exact'] == price
    assert engine.market()['total_volume_cents'] == 250000
    assert checkpoint['campaigns'][0]['status'] == 'active'


def test_information_isolation_and_compact_memory_keep_own_decisions_and_public_history():
    engine = LaunchLifecycle(example())
    engine.prepare()
    engine.advance(choices(engine, {'founder': 'pause_mm'}))
    engine.prepare()
    public = engine.observation('retail')
    private = engine.observation('mm')
    assert public['coordination'] == [] and private['coordination']
    assert public['memory']['own_last_choice'] == 'wait'
    assert public['market']['total_volume_cents'] == 250000


def test_unaffordable_or_unauthorized_orders_are_atomic():
    engine = LaunchLifecycle(example())
    engine.prepare()
    before = deepcopy(engine.wallets)
    with pytest.raises(ValueError, match='choice'):
        engine.advance(choices(engine, {'retail': 'pause_mm'}))
    assert engine.wallets == before and engine.index == 0


def test_simultaneous_quotes_can_reject_later_orders_instead_of_promising_fills():
    value = example()
    value['max_slippage_bps'] = 0
    engine = LaunchLifecycle(value)
    engine.prepare()
    checkpoint = engine.advance(choices(engine, {'retail': 'buy_all', 'mm': 'buy_all'}))
    outcomes = [item['status'] for item in checkpoint['settlements'] if item.get('reason') == 'actor_choice']
    assert 'rejected_slippage' in outcomes
    assert engine.cash_total() == 6200000


@pytest.mark.parametrize('mutation', ['reserve', 'horizon', 'supply', 'budget'])
def test_invalid_worlds_fail_closed(mutation):
    value = example()
    if mutation == 'reserve':
        value['founder']['reserve_cents'] = 5000001
    elif mutation == 'horizon':
        value['decision_seconds'] = [0, 3600]
    elif mutation == 'supply':
        value['curve_inventory'] = 1100000000
    else:
        value['founder']['upfront_cents'] = 4900000
    with pytest.raises(ValueError):
        validate_lifecycle(value)
