"""Arithmetic summaries of realized worlds, not model-written scenario odds.

Event-path membership follows the simulator's publication times and actual
external draws. Favorable follow-up confirms a separate claim; it does not
retroactively confirm the initial catalyst. Cash groups are disjoint bins.
"""
from math import ceil


CASH_GROUPS = (
    ('severe_loss', 'Loss greater than $5,000'),
    ('loss', 'Loss of up to $5,000'),
    ('modest_profit', 'Break-even to under $20,000 profit'),
    ('large_profit', '$20,000 profit or more'),
)


def _statistics(values):
    if not values:
        return dict.fromkeys(('mean_cents', 'median_cents', 'p05_cents', 'p95_cents'))
    ordered = sorted(values)
    def quantile(fraction):
        return ordered[max(0, ceil(fraction * len(ordered)) - 1)]
    return {'mean_cents': sum(values) / len(values), 'median_cents': quantile(.5),
            'p05_cents': quantile(.05), 'p95_cents': quantile(.95)}


def _event_groups(scenario):
    if not scenario['news_enabled']:
        return [('news_disabled', 'News events disabled')]
    if scenario['horizon_hours'] < 1:
        return [('news_not_reached', 'News publication not reached')]
    if scenario['horizon_hours'] < 96:
        return [('confirmed_pending', 'Confirmed catalyst; follow-up not reached'),
                ('rumor_pending', 'Unconfirmed catalyst; follow-up not reached')]
    return [('confirmed_positive', 'Confirmed catalyst + positive separate claim'),
            ('confirmed_contradicted', 'Confirmed catalyst + later contradiction'),
            ('rumor_positive', 'Unconfirmed catalyst + positive separate claim'),
            ('rumor_contradicted', 'Unconfirmed catalyst + later contradiction')]


def _event_id(world, scenario):
    if not scenario['news_enabled']:
        return 'news_disabled'
    if scenario['horizon_hours'] < 1:
        return 'news_not_reached'
    draws = world['external_draws']
    initial = 'confirmed' if draws['catalyst_draw_bps'] < scenario['catalyst_probability_bps'] else 'rumor'
    followup = ('pending' if scenario['horizon_hours'] < 96 else
                'positive' if draws['followup_draw_bps'] < scenario['followup_positive_probability_bps'] else 'contradicted')
    return initial + '_' + followup


def _cash_id(profit):
    if profit < -500_000:
        return 'severe_loss'
    if profit < 0:
        return 'loss'
    if profit < 2_000_000:
        return 'modest_profit'
    return 'large_profit'


def _group(rows, labels, assignment):
    members = {key: [] for key, _ in labels}
    for world in rows:
        members[assignment(world)].append(world['net_profit_cents'])
    return [{'id': key, 'label': label, 'count': len(members[key]),
             'frequency': len(members[key]) / len(rows), **_statistics(members[key])}
            for key, label in labels]


def summarize_scenarios(result, scenario):
    """Group the same realized worlds on two axes without double-counting either.

    Zero-observation groups have null cash statistics. Means use every world,
    not an unweighted mean of group means. All quantiles use nearest rank,
    matching the existing report UI (including the lower middle for even N).
    """
    rows = result['worlds']
    if not rows or len(rows) != result['world_count']:
        raise ValueError('nonempty, consistent world results required')
    if any(type(row['net_profit_cents']) is not int for row in rows):
        raise ValueError('integer cash outcomes required')
    fields = sorted(rows[0]['cash_bridge'])
    return {'schema_version': 'scenario-overview.v1', 'world_count': len(rows),
            'quantile_method': 'nearest_rank',
            'event_paths': _group(rows, _event_groups(scenario), lambda world: _event_id(world, scenario)),
            'cash_outcomes': _group(rows, CASH_GROUPS, lambda world: _cash_id(world['net_profit_cents'])),
            'overall': {**_statistics([world['net_profit_cents'] for world in rows]),
                        'mean_ending_cash_cents': sum(world['project_cash_cents'] for world in rows) / len(rows)},
            'cash_bridge': [{'field': field,
                             **{key: value for key, value in _statistics([world['cash_bridge'][field] for world in rows]).items()
                                if key in {'mean_cents', 'median_cents'}}} for field in fields]}
