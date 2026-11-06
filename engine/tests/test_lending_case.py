"""Case runner: opening funds, channel awareness, campaign delivery, triggers and resume."""
import json
from pathlib import Path

import pytest

from decision_lab.lending import fingerprint, replay_lending
from decision_lab.lending_case import TEAM_OPTIONS, run_case

CASE = Path(__file__).resolve().parents[2] / 'engine/examples/near-lending'
PREFERENCE = ('accept', 'supply', 'borrow', 'post', 'status_update', 'wait', 'no_action')


def load(name):
    return json.loads((CASE / name).read_text())


def path(prices):
    return {'path': [{'hour': i, 'near_close_scaled': p, 'usdc_usdt_close': 1.0}
                     for i, p in enumerate(prices)]}


class Client:
    """Scripted test client; never Laya. Picks the first preferred option offered."""
    def __init__(self, override=None):
        self.override = override or {}
        self.calls = []

    def evaluate(self, *, state, questions):
        options = questions['action']['criteria']
        self.calls.append((state.get('role'), tuple(options)))
        choice = next((o for o in self.override.get(state.get('role'), ()) if o in options), None)
        choice = choice or next(o for o in PREFERENCE if o in options)
        return {'answers': {'action': {'type': 'choice', 'choice': choice, 'confidence': 1,
                'probabilities': {k: int(k == choice) for k in options}}},
                'receipt': {'model': 'test_client_only_not_laya'}}


class Refuse:
    def evaluate(self, **_):
        raise AssertionError('cached run must not call the model')


def run(prices, client, days, **kw):
    return run_case(load('proposed-settings.json'), load('funded-cast-proposal.json'),
                    load('campaign-calendar.json'), path(prices), client, days=days, **kw)


def test_partners_deposit_1m_at_opening_and_outsiders_wait_for_delivery():
    result = run([4.0] * 48, Client(), days=2)
    first = result['pool'].journal
    supplies = [r for r in first if r['event']['kind'] == 'supply' and r['event']['id'].startswith('open-')]
    assert sum(r['event']['payload']['usdc'] for r in supplies) == 1_000_000
    whales = [d for d in result['decisions'] if d['actor'].startswith('ind_supplier_whale') and d['hour'] < 36]
    assert whales == []
    assert result['aware_since']['ind_supplier_retail'] == 0
    assert result['aware_since']['ind_supplier_whale_1'] == 36


def test_partner_decline_blocks_delivery_and_payment():
    result = run([4.0] * 72, Client({'distribution_partner': ('decline',)}), days=3)
    assert 'ind_supplier_whale_1' not in result['aware_since']
    assert 'partner_support_and_measurement' not in result['pool'].state['spending']
    assert {c['status'] for c in result['campaign'] if c['kind'] == 'partner'} == {'declined'}


def test_accepted_amplification_is_paid_only_on_delivery():
    result = run([4.0] * 48, Client(), days=2)
    assert result['pool'].state['spending']['partner_support_and_measurement'] == 10000
    delivered = [c for c in result['campaign'] if c['status'] == 'delivered']
    assert {c['id'] for c in delivered} >= {'launch_owned', 'amplify_ecosystem', 'amplify_defi'}


def test_crash_fires_triggers_liquidates_and_replays():
    prices = [4.0] * 30 + [4.0 - 0.15 * i for i in range(1, 19)] + [1.3] * 48
    result = run(prices, Client(), days=4)
    reasons = {d['reason'] for d in result['decisions']}
    assert 'near_move' in reasons
    kinds = [r['event']['kind'] for r in result['pool'].journal]
    assert 'liquidate' in kinds
    replay_lending(result['pool'].report())


def test_resume_reuses_cached_decisions_without_model_calls(tmp_path):
    cache = tmp_path / 'decisions.jsonl'
    first = run([4.0] * 48, Client(), days=2, cache_path=cache)
    again = run([4.0] * 48, Refuse(), days=2, cache_path=cache)
    assert first['calls']['new'] > 0 and again['calls']['new'] == 0
    assert fingerprint(first['pool'].state) == fingerprint(again['pool'].state)


def test_team_menu_is_communicate_and_spend_only():
    client = Client()
    run([4.0] * 24 * 8, client, days=8)
    team_menus = [opts for role, opts in client.calls if role == 'team']
    assert team_menus and all(set(o) <= set(TEAM_OPTIONS) for o in team_menus)


def test_rejects_short_price_path():
    with pytest.raises(ValueError):
        run([4.0] * 10, Client(), days=1)
