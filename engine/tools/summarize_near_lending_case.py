"""Summarize a finished NEAR lending case run into decision-grade figures (JSON to stdout)."""
from collections import Counter, defaultdict
from fractions import Fraction as F
import json
from pathlib import Path
import statistics
import sys

GROUPS = {'friendly': ('partner_',), 'independent': ('ind_supplier',), 'looper': ('points_looper',),
          'borrowers': ('borrower_',), 'liquidators': ('liquidator_',)}


def group(actor):
    return next((g for g, prefixes in GROUPS.items() if actor.startswith(prefixes)), 'other')


def by_group(values):
    totals = defaultdict(float)
    for actor, value in values.items():
        totals[group(actor)] += value
    return dict(totals)


def checkpoint(daily, day):
    d = daily[min(day, len(daily)) - 1]
    return {'day': d['day'] + 1, 'near_usd': round(d['near_usd'], 3), 'supply_usdc': round(d['supply_usdc']),
            'borrowed_usdc': round(d['borrowed_usdc']), 'utilization': round(d['utilization'], 3),
            'borrow_apr': round(d['borrow_apr'], 4), 'queued_usdc': round(d['queued_usdc']),
            'supply_by_group': {k: round(v) for k, v in by_group(d['supply_by_actor']).items()},
            'aware_actors': d['aware_actors']}


def laya_check(decisions):
    model = [d for d in decisions if d.get('probabilities')]
    tops = [max(d['probabilities'].values()) for d in model]
    uniform = [1 / len(d['probabilities']) for d in model]
    lift = [t - u for t, u in zip(tops, uniform)]
    by_reason = defaultdict(Counter)
    for d in model:
        by_reason['daily' if d['reason'] == 'daily' else 'triggered'][d['choice']] += 1
    return {'model_decisions': len(model), 'mean_top_probability': round(statistics.mean(tops), 3),
            'mean_lift_over_uniform': round(statistics.mean(lift), 3),
            'share_top_below_0_6': round(sum(t < .6 for t in tops) / len(tops), 3),
            'choices_daily_vs_triggered': {k: dict(v) for k, v in by_reason.items()}}


def main(out):
    out = Path(out)
    daily = json.loads((out / 'daily.json').read_text())
    decisions = json.loads((out / 'decisions.json').read_text())
    campaign = json.loads((out / 'campaign.json').read_text())
    report = json.loads((out / 'kernel-report.json').read_text())
    final = report['final_state']
    events = [r['event'] for r in report['events']]
    liqs = [r for r in report['events'] if r['event']['kind'] == 'liquidate']
    withdrawals = [e for e in events if e['kind'] == 'withdraw']
    withdrawn = defaultdict(float)
    for e in withdrawals:
        withdrawn[e['payload']['actor']] += e['payload']['usdc']
    points = {a: float(F(v)) for a, v in final['points'].items() if F(v)}
    peak = max(daily, key=lambda d: d['utilization'])
    crash = [d for d in daily if 55 <= d['day'] <= 64]
    summary = {
        'checkpoints': [checkpoint(daily, n) for n in (1, 7, 14, 30, 60, 90)],
        'peak_utilization': {'day': peak['day'] + 1, 'utilization': round(peak['utilization'], 3)},
        'crash_window_days_56_65': [{'day': d['day'] + 1, 'near': round(d['near_usd'], 2),
                                     'borrowed': round(d['borrowed_usdc']), 'supply': round(d['supply_usdc']),
                                     'queued': round(d['queued_usdc'])} for d in crash],
        'liquidations': {'count': len(liqs), 'repaid_usdc': round(sum(float(F(r['detail']['repaid'])) for r in liqs)),
                         'liquidator_profit_usdc': round(sum(float(F(r['detail']['liquidator_profit_usdc'])) for r in liqs)),
                         'by_borrower': dict(Counter(r['event']['payload']['borrower'] for r in liqs))},
        'losses': {'principal': float(F(final['principal_losses'])), 'interest': float(F(final['interest_losses'])),
                   'compensation_paid': float(F(final['compensation'])), 'reserve_left': float(F(final['reserve']))},
        'withdrawal_requests': {'count': len(withdrawals),
                                'usdc_by_group': {k: round(v) for k, v in by_group(withdrawn).items()}},
        'protocol_interest_cash_usdc': round(float(F(final['protocol_cash'])), 2),
        'treasury_spending_usdc': {k: float(F(v)) for k, v in final['spending'].items()},
        'points_share_by_group': {k: round(v / sum(points.values()), 3) for k, v in by_group(points).items()},
        'campaign': [{'id': c['id'], 'status': c['status'], 'hour': c.get('delivered_hour', c.get('decided_hour'))}
                     for c in campaign],
        'team_choices': dict(Counter(d['choice'] for d in decisions if d['role'] == 'team')),
        'laya': laya_check(decisions),
    }
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
