"""Load the frozen NEAR lending case runs and compute every figure the casebook quotes.

Read-only: no simulation, replay-free unless asked, no model calls. Each aggregate is derived
from the run outputs under engine/output/, so report text reconciles to the recorded data.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'engine/examples/near-lending'
OUTPUT = ROOT / 'engine/output'

# Memorable name + code: regime (C choppy / B bear), per-borrower cap (P50/P100, $K),
# borrow-rate curve (R2 = 2% base / R8 = 8% base) and actor model (L Laya / J Jev).
WORLDS = [
    {'key': 'first-light', 'name': 'First Light', 'code': 'C-P50-R2-L', 'dir': 'near-lending-case-v2-2026-11-05',
     'regime': 'choppy', 'cap': 50000, 'curve': 'cheap', 'model': 'Laya'},
    {'key': 'open-gate', 'name': 'Open Gate', 'code': 'C-P100-R2-L', 'dir': 'near-lending-case-cap100k-2026-11-05',
     'regime': 'choppy', 'cap': 100000, 'curve': 'cheap', 'model': 'Laya'},
    {'key': 'dear-money', 'name': 'Dear Money', 'code': 'C-P100-R8-L', 'dir': 'near-lending-case-cap100k-steep-2026-11-05',
     'regime': 'choppy', 'cap': 100000, 'curve': 'steep', 'model': 'Laya'},
    {'key': 'long-winter', 'name': 'Long Winter', 'code': 'B-P100-R8-L', 'dir': 'near-lending-case-steep-bear-2026-11-05',
     'regime': 'bear', 'cap': 100000, 'curve': 'steep', 'model': 'Laya'},
    {'key': 'cold-counter', 'name': 'Cold Counter', 'code': 'C-P100-R8-J', 'dir': 'near-lending-case-steep-jev-2026-11-05',
     'regime': 'choppy', 'cap': 100000, 'curve': 'steep', 'model': 'Jev'},
    {'key': 'empty-desk', 'name': 'Empty Desk', 'code': 'C-P100-R2-J', 'dir': 'near-lending-case-cap100k-jev-2026-11-05',
     'regime': 'choppy', 'cap': 100000, 'curve': 'cheap', 'model': 'Jev'},
]
ORIGINAL_BASELINE = 'near-lending-case-2026-11-05'
FAMILIES = {'partner_': 'Friendly partners', 'ind_supplier': 'Independent suppliers', 'points_looper': 'Points looper',
            'borrower_': 'Borrowers', 'liquidator_': 'Liquidators', 'team': 'Team', 'amplifier_': 'Distribution partners'}


def family(actor):
    return next((name for prefix, name in FAMILIES.items() if actor.startswith(prefix)), 'Other')


def read(path):
    return json.loads(Path(path).read_text())


def interest_totals(report):
    """Collected interest from repay/liquidation receipts plus receivables still owed at day 90."""
    collected = sum((F(e['detail']['paid_interest']) for e in report['events']
                     if e['event']['kind'] in ('repay', 'liquidate')), F(0))
    loans = report['final_state']['loans'].values()
    owed = sum((sum((F(v) for v in l['supplier_interest'].values()), F(0)) + F(l['protocol_interest']) for l in loans), F(0))
    return float(collected), float(owed)


def protocol_revenue(report):
    """Protocol's share: interest cash already collected plus its share still owed by borrowers."""
    state = report['final_state']
    owed = sum((F(l['protocol_interest']) for l in state['loans'].values()), F(0))
    return float(F(state['protocol_cash'])), float(owed)


def liquidation_days(report, days=90):
    counts, repaid = [0] * days, [0.0] * days
    for e in report['events']:
        if e['event']['kind'] == 'liquidate':
            day = int(e['event']['id'].split('-')[0][3:]) // 24
            counts[day] += 1
            repaid[day] += float(F(e['detail']['repaid']))
    return counts, repaid


def choice_mix(decisions):
    mix = defaultdict(Counter)
    for d in decisions:
        mix[family(d['actor'])][d['choice']] += 1
    return {k: dict(v) for k, v in mix.items()}


def decisiveness(decisions):
    scored = [d for d in decisions if d.get('probabilities')]
    tops = [max(d['probabilities'].values()) for d in scored]
    uniform = [1 / len(d['probabilities']) for d in scored]
    return {'scored': len(scored), 'mean_top': statistics.mean(tops), 'mean_uniform': statistics.mean(uniform),
            'share_below_0_6': sum(t < .6 for t in tops) / len(tops)}


def borrow_propensity(decisions):
    offered = [d for d in decisions if d['role'] == 'borrower' and 'borrow' in d['options'] and d.get('probabilities')]
    return {'offered': len(offered), 'chosen': sum(d['choice'] == 'borrow' for d in offered),
            'mean_score': statistics.mean(d['probabilities']['borrow'] for d in offered) if offered else None}


def load_world(spec):
    root = OUTPUT / spec['dir']
    report = read(root / 'kernel-report.json')
    daily, decisions = read(root / 'daily.json'), read(root / 'decisions.json')
    manifest, campaign, triggers = read(root / 'manifest.json'), read(root / 'campaign.json'), read(root / 'triggers.json')
    collected, owed = interest_totals(report)
    protocol_collected, protocol_owed = protocol_revenue(report)
    counts, repaid = liquidation_days(report)
    state = report['final_state']
    return {**spec, 'root': root, 'manifest': manifest, 'daily': daily, 'decisions': decisions,
            'campaign': campaign, 'triggers': triggers, 'interest_collected': collected, 'interest_owed': owed,
            'liq_counts': counts, 'liq_repaid': repaid, 'mix': choice_mix(decisions),
            'decisive': decisiveness(decisions), 'borrow': borrow_propensity(decisions),
            'protocol_collected': protocol_collected, 'protocol_owed': protocol_owed, 'reserve_left': float(F(state['reserve'])),
            'losses': float(F(state['principal_losses'])), 'compensation': float(F(state['compensation'])),
            'spending': {k: float(F(v)) for k, v in state['spending'].items()},
            'points': {k: float(F(v)) for k, v in state['points'].items() if F(v)},
            'liq_profit': sum(float(F(e['detail']['liquidator_profit_usdc'])) for e in report['events']
                              if e['event']['kind'] == 'liquidate'),
            'withdraw_requests': sum(1 for e in report['events'] if e['event']['kind'] == 'withdraw'),
            'reasons': Counter(d['reason'] for d in decisions)}


def load_all():
    worlds = [load_world(spec) for spec in WORLDS]
    identity = sha256(b''.join((OUTPUT / w['dir'] / 'manifest.json').read_bytes() for w in WORLDS)).hexdigest()
    paths = {name: read(CASE / f'price-path-{name}.json') for name in ('choppy-2025-08', 'bear-2025-11')}
    return {'worlds': {w['key']: w for w in worlds}, 'order': [w['key'] for w in worlds], 'identity': identity,
            'intake': read(CASE / 'intake.json'), 'cast': read(CASE / 'funded-cast-proposal.json'),
            'settings': read(CASE / 'proposed-settings.json'), 'calendar': read(CASE / 'campaign-calendar.json'),
            'paths': paths, 'evidence': read(CASE / 'evidence/manifest.json'),
            'original': read(OUTPUT / ORIGINAL_BASELINE / 'manifest.json')}


def at_day(world, key, day):
    return world['daily'][day - 1][key]
