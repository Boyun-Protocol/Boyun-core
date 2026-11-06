"""Bounded launch estimator: sampled actor decisions over a pump.fun-style curve and pool.

This is an estimate engine, not a settlement adapter. Buys and sells move a constant-product
curve (and a pool after the curve completes) with integer lamports and token base units; actor
actions are drawn from supplied probabilities with named SHA-256 draws, so a run replays exactly.

Every limitation is declared in ``LIMITATIONS`` and repeated in the rendered report.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib

LAMPORTS = 10**9
TOKEN_UNITS = 10**6
SUPPLY = 1_000_000_000 * TOKEN_UNITS
CURVE_TOKENS = 793_100_000 * TOKEN_UNITS
VIRTUAL_SOL = 30 * LAMPORTS
VIRTUAL_TOKENS = 1_073_000_000 * TOKEN_UNITS

LIMITS = {'worlds': 100_000, 'seed': 10**9, 'amount': 10**9}
LIMITATIONS = [
    'Estimate only: no venue adapter, no queue position, no partial fills, no MEV.',
    'Dynamic fee tiers are not modelled; the confirmed 100 bps base fee is used on both sides.',
    'Actors act once, at launch; no buyer arrives after the cast.',
    'One decision round per actor; no repeated trading or messaging.',
    'Probabilities are provider decision scores, not calibrated real-world odds.',
]

DEFAULTS = {
    'venue': 'curve',
    'sol_usd': 90,
    'fee_bps': 100,
    'founder_capital_usd': 50_000,
    'bootstrap_usd': 5_000,
    'kol_cash_usd': 3_000,
    'kol_supply_bps': 300,
    'pool_usd': 20_000,
    'pool_supply_bps': 4_000,
    'founder_supply_bps': 6_000,
    'half_life_hours': 12,
    'capital_usd': {'large_buyer': 52_500, 'retail_momentum': 775, 'retail_skeptical': 775,
                    'retail_patient': 775, 'attention_trader': 2_600},
    'kol_actors': ('kol_a', 'kol_b', 'kol_c', 'kol_d'),
    'seed': 7,
    'worlds': 20_000,
}


def _error(path, reason):
    raise ValueError(f'{path}: {reason}')


def _integer(value, path, low, high):
    if type(value) is not int or type(value) is bool or not low <= value <= high:
        _error(path, 'integer outside bounds')
    return value


def validate_params(params):
    """Return a complete parameter set; every override is range-checked."""
    merged = deepcopy(DEFAULTS)
    for key, value in params.items():
        if key not in DEFAULTS:
            _error('$', f'unknown parameter {key}')
        merged[key] = deepcopy(value)
    if merged['venue'] not in ('curve', 'pool'):
        _error('$.venue', 'curve or pool required')
    _integer(merged['sol_usd'], '$.sol_usd', 1, 100_000)
    _integer(merged['fee_bps'], '$.fee_bps', 0, 2_000)
    _integer(merged['founder_capital_usd'], '$.founder_capital_usd', 1, LIMITS['amount'])
    _integer(merged['bootstrap_usd'], '$.bootstrap_usd', 1, merged['founder_capital_usd'])
    _integer(merged['kol_cash_usd'], '$.kol_cash_usd', 0, merged['founder_capital_usd'])
    _integer(merged['kol_supply_bps'], '$.kol_supply_bps', 0, 10_000)
    _integer(merged['pool_usd'], '$.pool_usd', 1, LIMITS['amount'])
    _integer(merged['pool_supply_bps'], '$.pool_supply_bps', 1, 9_900)
    _integer(merged['founder_supply_bps'], '$.founder_supply_bps', 0, 10_000)
    if merged['pool_supply_bps'] + merged['founder_supply_bps'] > 10_000:
        _error('$.founder_supply_bps', 'pool and founder supply cannot exceed the token supply')
    if merged['kol_supply_bps'] > merged['founder_supply_bps']:
        _error('$.kol_supply_bps', 'creator allocation must come from the founder holding')
    _integer(merged['half_life_hours'], '$.half_life_hours', 1, 720)
    _integer(merged['seed'], '$.seed', 0, LIMITS['seed'])
    _integer(merged['worlds'], '$.worlds', 1, LIMITS['worlds'])
    capital = merged['capital_usd']
    if type(capital) is not dict or not capital:
        _error('$.capital_usd', 'bounded actor capital map required')
    for actor, amount in capital.items():
        if type(actor) is not str or not actor:
            _error('$.capital_usd', 'actor key must be text')
        _integer(amount, f'$.capital_usd.{actor}', 0, LIMITS['amount'])
    if type(merged['kol_actors']) is not tuple or not merged['kol_actors']:
        _error('$.kol_actors', 'declared holder actors required')
    return merged


def usd_to_lamports(usd, sol_usd):
    return int(usd * LAMPORTS // sol_usd)


def lamports_to_usd(lamports, sol_usd):
    return lamports * sol_usd / LAMPORTS


def buy(curve, quote_lamports, fee_bps):
    """Spend quote lamports on the curve at the current reserves; return tokens received."""
    net = quote_lamports * (10_000 - fee_bps) // 10_000
    tokens = curve['virtual_tokens'] * net // (curve['virtual_sol'] + net)
    if tokens > curve['real_left']:
        tokens = curve['real_left']
    curve['sold'] += tokens
    curve['real_left'] -= tokens
    curve['virtual_sol'] += net
    curve['virtual_tokens'] -= tokens
    return tokens


def sell(curve, tokens, fee_bps):
    """Redeem token base units for lamports, on the pool once migrated, otherwise on the curve."""
    if curve['migrated']:
        reserve_sol, reserve_tokens = curve['pool_sol'], curve['pool_tokens']
        out = reserve_sol * tokens // (reserve_tokens + tokens)
        curve['pool_sol'] = reserve_sol - out
        curve['pool_tokens'] = reserve_tokens + tokens
    else:
        out = curve['virtual_sol'] * tokens // (curve['virtual_tokens'] + tokens)
        curve['virtual_sol'] -= out
        curve['virtual_tokens'] += tokens
        curve['sold'] -= tokens
        curve['real_left'] += tokens
    return out * (10_000 - fee_bps) // 10_000


def migrate(curve):
    curve['migrated'] = True
    curve['pool_sol'] = curve['virtual_sol']
    curve['pool_tokens'] = SUPPLY - curve['sold']


def _draw(seed, world, actor, slot=0):
    raw = hashlib.sha256(f'{seed}|{world}|{actor}|{slot}'.encode()).digest()
    return int.from_bytes(raw, 'big') % 10_000


def sample_action(probabilities, seed, world, actor):
    """Draw one action in ascending action order, using integer basis points."""
    roll = _draw(seed, world, actor)
    names = sorted(probabilities)
    threshold = 0
    for action in names:
        threshold += int(round(probabilities[action] * 10_000))
        if roll < threshold:
            return action
    return names[-1]


def price_of(curve):
    """Curve price in lamports per token base unit."""
    if curve['migrated']:
        return curve['pool_sol'] / max(1, curve['pool_tokens'])
    return curve['virtual_sol'] / max(1, curve['virtual_tokens'])


def estimate_launch(probabilities, params=None, with_worlds=False):
    """Run every sampled world once; return the distribution and the scenario groups."""
    params = validate_params(params or {})
    if type(probabilities) is not dict or not probabilities:
        _error('$.probabilities', 'per-actor probability maps required')
    for actor, probs in probabilities.items():
        if type(probs) is not dict or not probs:
            _error(f'$.probabilities.{actor}', 'bounded probability map required')
        total = sum(int(round(v * 10_000)) for v in probs.values())
        if abs(total - 10_000) > 2:
            _error(f'$.probabilities.{actor}', 'probabilities must sum to one')
    sol, fee = params['sol_usd'], params['fee_bps']
    bootstrap = params['bootstrap_usd']
    kol_tokens = SUPPLY * params['kol_supply_bps'] // 10_000 // len(params['kol_actors'])
    capital = params['capital_usd']
    nets, proceeds, worlds, migrated = [], [], [], 0
    for world in range(params['worlds']):
        if params['venue'] == 'curve':
            curve = {'sold': 0, 'real_left': CURVE_TOKENS, 'virtual_sol': VIRTUAL_SOL,
                     'virtual_tokens': VIRTUAL_TOKENS, 'migrated': False, 'pool_sol': 0,
                     'pool_tokens': 0}
            founder_tokens = buy(curve, usd_to_lamports(bootstrap, sol), fee)
            if curve['real_left'] == 0:
                migrate(curve)
        else:
            # an existing pool: the team deposits liquidity and starts with a declared holding
            curve = {'sold': 0, 'real_left': 0, 'virtual_sol': 0, 'virtual_tokens': 0,
                     'migrated': True,
                     'pool_sol': usd_to_lamports(bootstrap, sol),
                     'pool_tokens': SUPPLY * params['pool_supply_bps'] // 10_000}
            founder_tokens = (SUPPLY * params['founder_supply_bps'] // 10_000
                              - kol_tokens * len(params['kol_actors']))
            if founder_tokens < 0:
                _error('$.founder_supply_bps', 'founder holding smaller than the creator allocation')
        volume_usd = float(bootstrap)
        holdings = {actor: kol_tokens for actor in params['kol_actors']}
        chosen, deployed = {}, 0.0
        for actor in sorted(probabilities):
            action = sample_action(probabilities[actor], params['seed'], world, actor)
            chosen[actor] = action
            if actor in capital:
                fraction = {'buy_small': .25, 'buy_half': .5, 'buy_all': 1.0}.get(action, 0.0)
                if fraction:
                    usd = capital[actor] * fraction
                    deployed += usd
                    quote = usd_to_lamports(usd, sol)
                    if curve['migrated']:
                        tokens = curve['pool_tokens'] * quote // (curve['pool_sol'] + quote)
                        curve['pool_sol'] += quote
                        curve['pool_tokens'] -= tokens
                    else:
                        tokens = buy(curve, quote, fee)
                        if curve['real_left'] == 0:
                            migrate(curve)
                    volume_usd += usd
                    holdings[actor] = holdings.get(actor, 0) + tokens
            else:
                fraction = {'sell_half': .5, 'sell_all': 1.0}.get(action, 0.0)
                if fraction:
                    volume_usd += lamports_to_usd(price_of(curve) * kol_tokens * fraction, sol)
                    sell(curve, int(kol_tokens * fraction), fee)
        tranche = founder_tokens // 4
        cash_lamports = sum(sell(curve, tranche, fee) for _ in range(4))
        cash = lamports_to_usd(cash_lamports, sol)
        if params['venue'] == 'pool':
            # the team owns the liquidity it deposited; withdrawing it at exit is cash back
            cash += lamports_to_usd(curve['pool_sol'], sol)
        net = cash - (bootstrap + params['kol_cash_usd'])
        bucket = ('no outside money' if deployed < 1000 else
                  'moderate outside money' if deployed < 20_000 else 'whale outside money')
        nets.append(net)
        proceeds.append(cash)
        migrated += 1 if curve['migrated'] else 0
        worlds.append({'world': world, 'bucket': bucket,
                       'kol_dump': any(chosen.get(k) == 'sell_all' for k in params['kol_actors']),
                       'migrated': curve['migrated'], 'deployed_usd': round(deployed, 2),
                       'net_cash_usd': round(net), 'proceeds_usd': round(cash)})
    summary = _summarise(nets, proceeds, worlds, migrated, params)
    if not with_worlds:
        summary.pop('worlds_rows', None)
    return summary


def _percentile(values, fraction):
    position = int(len(values) * fraction)
    return values[min(len(values) - 1, position)]


def _summarise(nets, proceeds, worlds, migrated, params):
    sorted_nets = sorted(nets)
    sorted_proceeds = sorted(proceeds)
    summary = {
        'params': params,
        'worlds': len(nets),
        'exit_hour': params['half_life_hours'] * 2,
        'migration_share': round(migrated / len(nets), 4),
        'profit_count': sum(1 for value in nets if value > 0),
        'net_quantiles': {name: round(_percentile(sorted_nets, q))
                          for name, q in (('p01', .01), ('p05', .05), ('p10', .10), ('p25', .25),
                                          ('p50', .50), ('p75', .75), ('p90', .90), ('p95', .95),
                                          ('p99', .99))},
        'net_min': round(sorted_nets[0]), 'net_max': round(sorted_nets[-1]),
        'net_mean': round(sum(nets) / len(nets)),
        'proceeds_quantiles': {name: round(_percentile(sorted_proceeds, q))
                               for name, q in (('p05', .05), ('p50', .50), ('p95', .95))},
        'limitations': list(LIMITATIONS),
    }
    if params['venue'] == 'curve':
        probe = {'sold': 0, 'real_left': CURVE_TOKENS, 'virtual_sol': VIRTUAL_SOL,
                 'virtual_tokens': VIRTUAL_TOKENS, 'migrated': False, 'pool_sol': 0,
                 'pool_tokens': 0}
        bought = buy(probe, usd_to_lamports(params['bootstrap_usd'], params['sol_usd']),
                     params['fee_bps'])
        summary['bootstrap_supply_pct'] = round(bought / SUPPLY * 100, 2)
    else:
        summary['bootstrap_supply_pct'] = None
    summary['net_cash_usd'] = {'p50': summary['net_quantiles']['p50'],
                               'mean': summary['net_mean'],
                               'share_positive': round(summary['profit_count'] / len(nets), 4)}
    if worlds:
        if worlds is not None:
            summary['worlds_rows'] = worlds
        groups = {}
        for row in worlds:
            key = (row['bucket'], 'KOL sells all' if row['kol_dump'] else 'KOLs hold')
            if params['venue'] == 'curve':
                key = key + ('migrated' if row['migrated'] else 'stayed on curve',)
            groups.setdefault(key, []).append(row['net_cash_usd'])
        scenarios = []
        for key, values in groups.items():
            values.sort()
            scenarios.append({'scenario': ' + '.join(key), 'share': round(len(values) / len(worlds), 4),
                              'out_of_100': round(len(values) / len(worlds) * 100),
                              'p05': round(_percentile(values, .05)),
                              'p50': round(_percentile(values, .5)),
                              'p95': round(_percentile(values, .95)),
                              'share_positive': round(sum(1 for v in values if v > 0) / len(values), 3)})
        summary['scenarios'] = sorted(scenarios, key=lambda row: -row['share'])
        buckets = {}
        for row in worlds:
            entry = buckets.setdefault(row['bucket'], {'n': 0, 'profit': 0, 'nets': []})
            entry['n'] += 1
            entry['profit'] += 1 if row['net_cash_usd'] > 0 else 0
            entry['nets'].append(row['net_cash_usd'])
        for name, entry in buckets.items():
            entry['nets'].sort()
            entry['share'] = round(entry['n'] / len(worlds), 4)
            entry['p05'] = round(_percentile(entry['nets'], .05))
            entry['p50'] = round(_percentile(entry['nets'], .5))
            entry['p95'] = round(_percentile(entry['nets'], .95))
            del entry['nets']
        summary['by_bucket'] = buckets
    return summary


def sensitivity(probabilities, base=None, grid=None, worlds=5_000):
    """Re-run the estimate across declared parameter overrides; each row is a labelled arm."""
    base = validate_params(base or {})
    grid = grid or {'sol_usd': (60, 90, 200), 'half_life_hours': (12, 24, 48),
                    'bootstrap_usd': (3_000, 5_000, 7_000)}
    rows = []
    for key, values in grid.items():
        for value in values:
            params = dict(base)
            params[key] = value
            params['worlds'] = min(worlds, base['worlds'])
            result = estimate_launch(probabilities, params)
            rows.append({'parameter': key, 'value': value,
                         'net_p50': result['net_quantiles']['p50'],
                         'net_p90': result['net_quantiles']['p90'],
                         'share_positive': result['net_cash_usd']['share_positive'],
                         'migration_share': result['migration_share'],
                         'exit_hour': result['exit_hour']})
    return {'base': base, 'worlds_per_arm': min(worlds, base['worlds']),
            'arms': sorted(rows, key=lambda row: (row['parameter'], row['value']))}
