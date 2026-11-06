"""Descriptive world-level analysis; no inference of population odds or causal effects."""
from collections import Counter
from fractions import Fraction
from statistics import median


def distribution(values):
    values = sorted(values)
    if not values:
        return {'n_worlds': 0, 'minimum': None, 'median': None, 'maximum': None}
    return {'n_worlds': len(values), 'minimum': values[0], 'median': median(values), 'maximum': values[-1]}


def analyze_world(checkpoints):
    if not checkpoints:
        raise ValueError('completed checkpoints required')
    initial = checkpoints[0]
    final = checkpoints[-1]
    actors = initial['balances_before']
    controlled = [actor for actor in ('founder', 'marketing-partner') if actor in actors]
    initial_cash = sum(actors[actor]['cash_cents'] for actor in controlled)
    initial_cash += sum(item['cost_cents'] for item in initial.get('committed_plan_execution', []) if item['payer'] in controlled)
    final_cash = sum(final['balances_after'][actor]['cash_cents'] for actor in controlled)
    peak = Fraction(initial['market_before']['market_cap_usd_exact'])
    worst_drawdown = Fraction(0)
    minimum_pool = initial['market_before']['cash_reserve_cents']
    attempts = filled = rejected = volume = cash_fees = token_fees = 0
    turnover_by_actor = Counter()
    campaign_cost = 0
    for checkpoint in checkpoints:
        for market in (checkpoint['market_before'], checkpoint['market_after']):
            cap = Fraction(market['market_cap_usd_exact'])
            peak = max(peak, cap)
            if peak:
                worst_drawdown = max(worst_drawdown, (peak - cap) / peak)
            minimum_pool = min(minimum_pool, market['cash_reserve_cents'])
        campaign_cost += sum(item['cost_cents'] for item in checkpoint.get('committed_plan_execution', []))
        for item in checkpoint['settlements']:
            if item['status'] == 'paid':
                campaign_cost += item['action']['cost_cents']
            if item['action']['kind'] not in ('buy', 'sell'):
                continue
            attempts += 1
            if item['status'] == 'rejected_at_execution':
                rejected += 1
            if item['status'] != 'executed':
                continue
            filled += 1
            fill = item['fill']
            volume += fill['cash_cents']
            cash_fees += fill['fee_cash_cents']
            token_fees += fill['fee_token_units']
            turnover_by_actor[item['actor_id']] += fill['cash_cents']
    orders = final['campaigns']
    initial_cap = Fraction(initial['market_before']['market_cap_usd_exact'])
    final_cap = Fraction(final['market_after']['market_cap_usd_exact'])
    return {'world': None, 'controlled_accounts': controlled,
            'controlled_liquid_cash_change_cents': final_cash - initial_cash,
            'accounting_scope': 'Founder plus marketing cash only; excludes remaining inventory, LP recovery and total economic profit.',
            'initial_market_cap_usd': float(initial_cap), 'final_market_cap_usd': float(final_cap),
            'terminal_return_fraction': float(final_cap / initial_cap - 1) if initial_cap else None,
            'sampled_max_drawdown_fraction': float(worst_drawdown),
            'drawdown_scope': 'Pre/post decision barriers, not every intrabarrier fill or continuous market path.',
            'minimum_sampled_pool_cash_cents': minimum_pool,
            'trade_attempts': attempts, 'filled_trades': filled, 'rejected_trades': rejected,
            'rejection_fraction': rejected / attempts if attempts else None,
            'volume_cents': volume, 'campaign_cost_cents': campaign_cost,
            'cash_fee_cents': cash_fees, 'token_fee_units': token_fees,
            'largest_actor_turnover_share': max(turnover_by_actor.values()) / volume if volume else None,
            'turnover_hhi': sum((value / volume) ** 2 for value in turnover_by_actor.values()) if volume else None,
            'campaign_orders': len(orders),
            'delivered_orders': sum(item['status'] in ('active', 'expired') for item in orders),
            'failed_orders': sum(item['status'] == 'failed' for item in orders),
            'pending_orders': sum(item['status'] == 'pending' for item in orders),
            'initial_checkpoint': initial['checkpoint_sha256'], 'final_checkpoint': final['checkpoint_sha256']}


def analyze_worlds(worlds):
    if not worlds:
        raise ValueError('world sample required')
    return {'schema_version': 'campaign-depth-analysis.v1', 'n_worlds': len(worlds),
            'sample_unit': 'seeded simulated world; actor calls and time points are dependent observations',
            'sample_status': 'descriptive only; no calibrated confidence intervals or tail odds',
            'controlled_cash_change_cents': distribution([world['controlled_liquid_cash_change_cents'] for world in worlds]),
            'sampled_max_drawdown_fraction': distribution([world['sampled_max_drawdown_fraction'] for world in worlds]),
            'minimum_sampled_pool_cash_cents': distribution([world['minimum_sampled_pool_cash_cents'] for world in worlds]),
            'worlds_with_controlled_cash_loss': sum(world['controlled_liquid_cash_change_cents'] < 0 for world in worlds),
            'trade_attempts': sum(world['trade_attempts'] for world in worlds),
            'rejected_trades': sum(world['rejected_trades'] for world in worlds),
            'edge_case_coverage': [
                {'case': 'No fills despite paid delivered campaigns',
                 'status': 'observed' if any(world['filled_trades'] == 0 and world['delivered_orders'] > 0 for world in worlds) else 'not observed',
                 'world_count': sum(world['filled_trades'] == 0 and world['delivered_orders'] > 0 for world in worlds)},
                {'case': 'Campaign delivery failure',
                 'status': 'observed' if any(world['failed_orders'] > 0 for world in worlds) else 'not observed',
                 'world_count': sum(world['failed_orders'] > 0 for world in worlds)},
                {'case': 'Trade rejected at execution',
                 'status': 'observed' if any(world['rejected_trades'] > 0 for world in worlds) else 'not observed',
                 'world_count': sum(world['rejected_trades'] > 0 for world in worlds)},
                {'case': 'Matched campaign-on/off causal ablation', 'status': 'not run', 'world_count': None},
                {'case': 'Late external-wallet arrival surge', 'status': 'unsupported', 'world_count': None},
                {'case': 'LP withdrawal during forced exit', 'status': 'unsupported', 'world_count': None},
                {'case': 'Combined outage, stale prices and forced exit', 'status': 'unsupported', 'world_count': None}],
            'unsupported': ['economic profit including inventory and LP recovery', 'independent empirical market observations',
                            'causal campaign ROI', 'calibrated market-regime effects', 'reliable p95/p99 or CVaR from four worlds'],
            'worlds': worlds}
