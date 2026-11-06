"""Hand-calculated lending accounting, adversarial events and replay checks."""
from copy import deepcopy
from fractions import Fraction as F
import json
from pathlib import Path

import pytest

from decision_lab.lending import LendingPool, replay_lending


def settings():
    path = Path(__file__).resolve().parents[2] / 'engine/examples/near-lending/proposed-settings.json'
    return json.loads(path.read_text())


def pool(*, custom=None):
    return LendingPool(custom or settings(), {
        'alice':{'usdc':600,'near':0}, 'bob':{'usdc':400,'near':0},
        'borrower':{'usdc':100,'near':2000}, 'liquidator':{'usdc':1000,'near':0},
    }, market_usdc=10000)


def rounded_down(actual, exact, units):
    """Accrual rounds down to 1e-12; never above exact, at most `units` grid steps below."""
    return exact - F(units, 10**12) <= actual <= exact


def fund(p):
    p.apply('supply-a','supply',actor='alice',usdc=600)
    p.apply('supply-b','supply',actor='bob',usdc=400)
    p.apply('price','oracle',near_usd=1,usdc_usd=1,observed_second=0)
    p.apply('collateral','post_collateral',actor='borrower',near=2000)


def test_unfunded_and_invalid_actions_are_atomic_and_retryable():
    p = pool()
    before = p.snapshot()
    with pytest.raises(ValueError):
        p.apply('retry','supply',actor='alice',usdc=601)
    assert p.snapshot() == before
    assert not p.journal
    p.apply('retry','supply',actor='alice',usdc=600)
    for bad in (True,1.1,-1,'NaN','1/2'):
        before = p.snapshot()
        with pytest.raises(ValueError):
            p.apply('bad','withdraw',actor='alice',usdc=bad)
        assert p.snapshot() == before
    with pytest.raises(ValueError):
        p.apply('extra','withdraw',actor='alice',usdc=1,secret=True)


def test_deposit_is_not_revenue_and_lending_does_not_mint_cash():
    p = pool(); totals = p._totals(); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=500)
    assert p.state['cash'] == 500
    assert p.principal() == 500
    assert sum(p.state['suppliers'].values()) == 1000
    assert p.state['protocol_cash'] == 0
    assert p.state['reserve'] == 10000
    assert p.state['treasury'] == 90000
    assert p._totals() == totals


def test_claims_queue_fifo_and_points_exclude_only_queued_portion():
    p = pool(); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=1000)
    p.apply('qa','withdraw',actor='alice',usdc=200)
    p.apply('qb','withdraw',actor='bob',usdc=100)
    p.apply('day','advance',second=86400)
    # 1000 principal: Alice's eligible claim is 400, Bob's 300, total claims 1000.
    assert p.state['points']['alice'] == 400
    assert p.state['points']['bob'] == 300
    assert p.queued('alice') == 200
    assert p.queued('bob') == 100
    p.apply('return','repay',actor='borrower',usdc=100)
    interest = F(1000)*F(1,2)/365  # Full utilization: 50% APR, accrued on the 1e-12 grid.
    principal_paid = 100-interest
    assert rounded_down(200-p.queued('alice'), principal_paid + F(5, 10**12), 5)
    assert p.queued('bob') == 100  # FIFO, not pro rata.
    assert p.state['cash'] == 0
    assert p.state['principal_losses'] == 0  # Illiquidity alone isn't a loss.


def test_interest_is_receivable_until_collected_and_paid_once():
    s = settings()
    for key in ('base_borrow_apr_bps','borrow_apr_at_kink_bps','borrow_apr_at_full_utilization_bps'):
        s['interest'][key] = 3650
    p = pool(custom=s); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=400)
    p.apply('day','advance',second=86400)
    loan = p.state['loans']['borrower']
    assert p.debt(loan) == F('400.4')
    assert loan['protocol_interest'] == F('0.06')
    assert sum(loan['supplier_interest'].values()) == F('0.34')
    assert p.state['protocol_cash'] == 0
    assert p.state['cash'] == 600
    totals = p._totals()
    p.apply('partial','repay',actor='borrower',usdc='0.2')
    assert loan['principal'] == 400
    assert p.debt(loan) == F('400.2')
    assert p.state['protocol_cash'] == F('0.03')
    assert p.state['cash'] == 600
    p.apply('rest','repay',actor='borrower',usdc='400.2')
    assert p.debt(loan) == 0
    assert p.state['cash'] == 1000
    assert p.state['wallets']['alice']['usdc'] == F('0.204')
    assert p.state['wallets']['bob']['usdc'] == F('0.136')
    assert p.state['protocol_cash'] == F('0.06')
    assert p._totals() == totals


def test_split_accrual_matches_within_rounding_dust_and_never_mints():
    a,b = pool(),pool()
    for p in (a,b):
        fund(p); p.apply('loan','borrow',actor='borrower',usdc=400)
    a.apply('day','advance',second=86400)
    for hour in range(1,25):
        b.apply(f'hour-{hour}','advance',second=3600*hour)
    la, lb = a.state['loans']['borrower'], b.state['loans']['borrower']
    assert la['principal'] == lb['principal']
    assert rounded_down(lb['protocol_interest'], la['protocol_interest'] + F(1, 10**12), 24)
    for owner, claim in la['supplier_interest'].items():
        assert rounded_down(lb['supplier_interest'][owner], claim + F(1, 10**12), 24)
    for owner, points in a.state['points'].items():
        assert rounded_down(b.state['points'][owner], points + F(1, 10**12), 24)
    assert a.state['cash'] == b.state['cash'] and a.state['suppliers'] == b.state['suppliers']
    assert a._totals() == b._totals()


def test_stale_oracle_blocks_risky_actions_but_allows_repay_and_addition():
    p = pool(); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=400)
    p.apply('later','advance',second=61)
    for kind,kwargs in [('borrow',{'actor':'borrower','usdc':1}),
                         ('remove_collateral',{'actor':'borrower','near':1}),
                         ('liquidate',{'actor':'liquidator','borrower':'borrower','max_repay_usdc':100,
                           'market_near_usd':1,'impact_bps':0,'execution_cost_usdc':0})]:
        before = p.snapshot()
        with pytest.raises(ValueError,match='fresh oracle'):
            p.apply('blocked',kind,**kwargs)
        assert p.snapshot() == before
    p.apply('pay','repay',actor='borrower',usdc=1)
    p.apply('refresh','oracle',near_usd=1,usdc_usd=1,observed_second=61)
    p.apply('remove','remove_collateral',actor='borrower',near=1)
    p.apply('add','post_collateral',actor='borrower',near=1)


def test_origination_cap_uses_total_debt_and_collateral_not_wallet_value():
    p = pool(); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=1000)
    before = p.snapshot()
    with pytest.raises(ValueError,match='insufficient|cash'):
        p.apply('unfunded','borrow',actor='borrower',usdc=1)
    assert p.snapshot() == before
    q = pool(); fund(q)
    q.apply('lower','oracle',near_usd='0.4',usdc_usd=1,observed_second=0)
    with pytest.raises(ValueError,match='LTV'):
        q.apply('ltv','borrow',actor='borrower',usdc=401)
    assert q.principal() == 0
    s = settings(); s['market']['initial_per_borrower_principal_cap_usdc']=100
    q = pool(custom=s); fund(q)
    with pytest.raises(ValueError,match='cap'):
        q.apply('cap','borrow',actor='borrower',usdc=101)


def test_funded_partial_liquidation_and_unprofitable_quote_are_atomic():
    p = pool(); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=500)
    # HF = 1000*.65/500 = 1.3 initially; at price .38, HF=.988.
    p.apply('fall','oracle',near_usd='0.38',usdc_usd=1,observed_second=0)
    kwargs={'actor':'liquidator','borrower':'borrower','max_repay_usdc':500,
            'market_near_usd':'0.38','impact_bps':0,'execution_cost_usdc':0}
    before = p.snapshot()
    with pytest.raises(ValueError,match='unprofitable'):
        p.apply('badquote','liquidate',**{**kwargs,'impact_bps':1000})
    assert p.snapshot() == before
    r = p.apply('liq','liquidate',**kwargs)
    assert r['detail']['repaid'] == '250'
    assert p.principal() == 250
    assert p.state['wallets']['liquidator']['usdc'] == F('1012.5')
    assert p.health('borrower') > 1
    p.check()


def test_exhausted_collateral_loss_and_capped_compensation_replay():
    s = settings()
    s['loss_and_compensation']['reserve_usd_user_selected'] = 50
    s['loss_and_compensation']['team_other_initial_cash_usd'] = 99950
    p = pool(custom=s); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=1000)
    p.apply('crash','oracle',near_usd='0.1',usdc_usd=1,observed_second=0)
    p.apply('liq','liquidate',actor='liquidator',borrower='borrower',max_repay_usdc=1000,
            market_near_usd='0.1',impact_bps=0,execution_cost_usdc=0)
    assert p.state['loans']['borrower']['collateral'] == 0
    assert p.principal() == F(17000,21)  # 1000 - 200 / 1.05.
    before = p.snapshot()
    r = p.apply('loss','writeoff',borrower='borrower')
    assert p.state['principal_losses'] == F(17000,21)
    assert p.state['reserve'] == 0
    assert p.state['compensation'] == 50
    assert p.state['wallets']['alice']['usdc'] == 30
    assert p.state['wallets']['bob']['usdc'] == 20
    assert p.state['suppliers']['alice'] == F(800,7)
    after = p.snapshot()
    assert p.apply('loss','writeoff',borrower='borrower') == r
    assert p.snapshot() == after
    with pytest.raises(ValueError):
        p.apply('second-loss','writeoff',borrower='borrower')
    assert p.snapshot() == after
    assert replay_lending(p.report()).snapshot() == after
    assert before != after


def test_event_id_payload_tampering_and_report_tampering_are_rejected():
    p = pool(); fund(p)
    receipt = p.apply('loan','borrow',actor='borrower',usdc=500)
    p.apply('spend','spend',category='promotion',usdc=100)
    snapshot = p.snapshot()
    assert p.apply('loan','borrow',actor='borrower',usdc=500) == receipt
    assert p.snapshot() == snapshot
    with pytest.raises(ValueError,match='changed payload'):
        p.apply('loan','borrow',actor='borrower',usdc=499)
    report = p.report()
    assert replay_lending(report).snapshot() == snapshot
    report['events'][0]['detail']['supplied'] = '601'
    with pytest.raises(ValueError,match='replay mismatch'):
        replay_lending(report)
    report = p.report(); report['final_state']['reserve'] = '10001'
    with pytest.raises(ValueError,match='terminal state'):
        replay_lending(report)


def test_selected_spending_ceiling_cannot_consume_compensation_reserve():
    p = pool()
    p.apply('promote','spend',category='promotion',usdc=20000)
    p.apply('ops','spend',category='operations',usdc=30000)
    p.apply('partners','spend',category='partner_support_and_measurement',usdc=10000)
    assert p.state['treasury'] == 30000
    assert p.state['reserve'] == 10000
    assert p.state['protocol_cash'] == 0
    assert p._totals() == p.initial_totals
    before = p.snapshot()
    with pytest.raises(ValueError):
        p.apply('overspend','spend',category='promotion',usdc=1)
    assert p.snapshot() == before


def test_unsupported_policy_cannot_silently_run_as_another_policy():
    for section,key,value in [('withdrawal','policy','guaranteed_instant_exit'),
                              ('supplier_points','idle_supply_points',True),
                              ('supplier_points','cash_redemption_value','1')]:
        s = settings(); s[section][key] = value
        with pytest.raises(ValueError,match='unsupported'):
            pool(custom=s)


def test_full_90_day_hourly_accounting_is_replayable():
    p = pool(); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=400)
    for hour in range(1,2161):
        p.apply(f'hour-{hour}','advance',second=hour*3600)
    assert p.state['second'] == 90*86400
    assert rounded_down(p.state['points']['alice'], F(21600), 2160)
    assert rounded_down(p.state['points']['bob'], F(14400), 2160)
    assert rounded_down(p.debt(p.state['loans']['borrower']), 400+F(400)*F(3,50)*F(90,365), 5*2160)
    assert replay_lending(p.report()).snapshot() == p.snapshot()


def test_hourly_accrual_stays_on_fixed_grid_over_90_days():
    """Varying supplier shares must not grow exact-fraction denominators without bound."""
    p = pool(); fund(p)
    p.apply('loan','borrow',actor='borrower',usdc=500)
    totals = p._totals()
    for hour in range(1, 2161):
        p.apply(f'h{hour}','advance',second=3600*hour)
        if hour % 7 == 0:
            p.apply(f'px{hour}','oracle',near_usd=1,usdc_usd=1,observed_second=3600*hour)
            p.apply(f'r{hour}','repay',actor='borrower',usdc='0.37')
    grid = 10**12
    loan = p.state['loans']['borrower']
    for value in [*loan['supplier_interest'].values(), loan['protocol_interest'], *p.state['points'].values(),
                  *(w['usdc'] for w in p.state['wallets'].values())]:
        assert grid % value.denominator == 0
    assert p._totals() == totals
