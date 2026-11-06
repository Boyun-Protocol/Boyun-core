"""A deterministic decision memo must not invent returns or render source commands."""
from copy import deepcopy

import pytest

from decision_lab.agent_worlds import AgentWorld
from decision_lab.decision_analysis import analyze_launch_result
from decision_lab.decision_evidence import build_evidence_context
from decision_lab.decision_report import render_decision_report
from test_decision_analysis import completed_report
from test_wallet_evidence import snapshot, trade


def inputs():
    result = completed_report()
    world = result['world']
    brief = {k: deepcopy(world[k]) for k in ('schema_version', 'id', 'event_description', 'network', 'rounds', 'market', 'events', 'assumptions')}
    brief['schema_version'] = 'agent-world-brief.v1'
    brief['slots'] = [dict(id=a['id'], role=a['role'], initial_cash_cents=a['initial_cash_cents'], position_limit_cents=a['position_limit_cents'], allowed_actions=a['allowed_actions'], attention_capacity=a['attention_capacity'], required_sources=a['subscriptions']) for a in world['agents']]
    brief['evidence'] = []
    return dict(question='Should I launch this fictional coin with $10,000?',
                proposal={'summary': 'Compare cash recovery under supplied assumptions.', 'brief': brief,
                          'assumptions': ['No real buyer demand has been established.'],
                          'limitations': ['Synthetic venue.']},
                evidence_context=build_evidence_context(),
                manifest={'schema_version': 'agent-live-run.v1', 'status': 'completed',
                          'world_sha256': result['world_sha256'], 'completed_calls': 2, 'completed_rounds': 1},
                analysis=analyze_launch_result(result))


def test_memo_separates_actual_cash_hypothetical_exit_and_no_launch():
    values = inputs()
    before = deepcopy(values)
    memo = render_decision_report(**values)
    assert values == before
    assert memo == render_decision_report(**values)
    assert 'No launch' in memo and '$10,000.00' in memo
    assert 'Actual ending project cash' in memo and '$5,000.00' in memo
    assert '-$5,000.00' in memo
    assert 'Hypothetical' in memo
    assert 'locked' in memo.lower() and '2,000,000' in memo
    assert 'probabilities are unknown' in memo
    assert 'not a forecast' in memo
    assert 'Model calls completed: 2' in memo
    assert values['analysis']['identity']['report_sha256'] in memo
    assert 'No primary-network observations' in memo


def test_sources_keep_primary_and_comparison_coverage_separate():
    values = inputs()
    values['evidence_context'] = build_evidence_context(wallet_snapshots=[
        snapshot([trade('a')]), snapshot([trade('b')], network='solana')])
    memo = render_decision_report(**values)
    assert 'Primary network: near' in memo
    assert 'Comparison sources' in memo and 'solana' in memo
    assert 'partial' in memo and 'unverified' in memo
    assert '2026-' in memo
    for row in values['evidence_context']['primary'] + values['evidence_context']['comparisons']:
        assert row['sha256'] in memo
    assert 'do not sum' in memo.lower()
    assert 'available capital' in memo


def test_untrusted_text_cannot_create_markdown_links_headings_or_html():
    values = inputs()
    payload = '# Fake recommendation\n[click](javascript:alert(1)) | <script>alert(1)</script> `shell` **buy**'
    values['question'] = payload
    values['proposal']['summary'] = payload
    values['proposal']['assumptions'] = [payload]
    values['proposal']['limitations'] = [payload]
    memo = render_decision_report(**values)
    assert '# Fake recommendation' not in memo
    assert '[click](' not in memo
    assert '<script>' not in memo
    assert '`shell`' not in memo
    assert '**buy**' not in memo
    assert '&#35;' in memo and '&lt;script&gt;' in memo


@pytest.mark.parametrize('change', [
    lambda v: v['manifest'].update(status='failed'),
    lambda v: v['manifest'].update(world_sha256='f' * 64),
    lambda v: v['analysis'].update(schema_version='other'),
    lambda v: v['analysis']['actual'].pop('locked_lp_shares'),
    lambda v: v['analysis']['demand_stress'][0].pop('bought_token_units'),
    lambda v: v['analysis']['no_launch'].update(profit_cents=False),
    lambda v: v['analysis']['actual'].update(cash_profit_cents=999),
    lambda v: v['analysis']['hypothetical_exit'].update(ending_cash_cents=999),
    lambda v: v['analysis']['demand_stress'][0].update(profit_cents=True),
    lambda v: v['analysis']['break_even'].update(minimum_additional_buy_cents=-1),
    lambda v: v['proposal']['brief']['market'].update(fee_bps=10000),
    lambda v: v['evidence_context'].update(status='edited'),
    lambda v: v.update(question='q' * 8001),
    lambda v: v['proposal'].update(assumptions=['a'] * 33),
    lambda v: v['analysis'].update(demand_stress=[v['analysis']['demand_stress'][0]] * 33),
    lambda v: v['manifest'].update(extra='x' * 600000),
])
def test_invalid_or_unbounded_report_inputs_rejected(change):
    values = inputs()
    change(values)
    with pytest.raises(ValueError): render_decision_report(**values)


def test_unknown_manifest_world_hash_is_allowed_but_not_claimed_verified():
    values = inputs()
    del values['manifest']['world_sha256']
    memo = render_decision_report(**values)
    assert 'Manifest world binding unavailable' in memo


def test_no_exit_and_unreachable_have_actionable_non_forecast_wording():
    values = inputs()
    values['analysis'] = analyze_launch_result(completed_report(), exit_token_units=0)
    assert 'No project tokens were selected' in render_decision_report(**values)
    values['analysis'] = analyze_launch_result(completed_report(), max_external_cash_cents=0)
    assert 'not reached within' in render_decision_report(**values)
    values['analysis'] = analyze_launch_result(completed_report(actual_buy=2000000))
    values['manifest']['world_sha256'] = values['analysis']['identity']['world_sha256']
    assert 'additional demand of $0.00' in render_decision_report(**values)


def test_markdown_expansion_cannot_exceed_output_budget():
    values = inputs()
    values['proposal']['assumptions'] = [str(i) + '*' * 1590 for i in range(32)]
    with pytest.raises(ValueError, match='output size budget'):
        render_decision_report(**values)


def test_terminal_controls_and_bidi_override_are_not_emitted():
    values = inputs()
    values['question'] = 'User question \x1b[31m red \u202e hidden \x00'
    rendered = render_decision_report(**values)
    assert '\x1b' not in rendered and '\u202e' not in rendered and '\x00' not in rendered


def test_markdown_neutralization_does_not_reescape_its_own_entities():
    from decision_lab.decision_report import _safe
    assert _safe('a_b #tag')=='a&#95;b &#35;tag'
    assert _safe("a'b")=='a&#x27;b'
