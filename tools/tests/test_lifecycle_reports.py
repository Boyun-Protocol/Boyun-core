import importlib.util
import base64
import gzip
import json
import re
from pathlib import Path


spec = importlib.util.spec_from_file_location('lifecycle_reports', Path(__file__).parents[1] / 'build_lifecycle_reports.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def checkpoint():
    return {'second': 3600, 'step': 1, 'checkpoint_sha256': 'a' * 64,
            'market_after': {'market_cap_usd_exact': '1000', 'fdv_usd_exact': '1200',
                             'price_usd_exact': '1/1000', 'real_cash_cents': 100000,
                             'total_volume_cents': 40000, 'six_hour_signal': {'current_volume_cents': None,
                                 'fraction_of_peak_exact': None, 'exit_trigger': None}},
            'balances_after': {'founder': {'cash_cents': 3000000, 'tokens': 1000},
                               'reserve': {'cash_cents': 1000000, 'tokens': 0},
                               'retail': {'cash_cents': 5000, 'tokens': 5}},
            'choices': {'founder': 'pause_mm', 'retail': 'wait'}, 'settlements': [], 'response': None,
            'events': [], 'observations': {'founder': {'coordination': [{'choice': 'PRIVATE_TEAM_COMMAND'}],
                    'own_policy': {'reserve_cents': 1000000}, 'events': [], 'memory': {}},
                  'retail': {'coordination': [], 'events': [], 'memory': {'own_last_choice': 'buy_small'}}}}


def test_actor_projection_physically_excludes_private_peer_information():
    value = module.project_actor(checkpoint(), {}, 'retail')
    serialized = str(value)
    assert 'PRIVATE_TEAM_COMMAND' not in serialized
    assert 'reserve_cents' not in serialized and 'founder' not in serialized
    assert value['cash_cents'] == 5000
    assert value['memory']['own_last_choice'] == 'buy_small'


def test_unfinished_native_paths_have_no_fabricated_fourteen_day_result():
    data = {'native': {'status': 'partial_budget_limited', 'paths': [], 'budget': {'spent_estimate_micro_usd': 1000000}},
            'offline_reference': {'status': 'completed', 'paths': []}, 'paths': []}
    text = module.report_markdown(data)
    assert 'unfinished' in text.lower()
    assert 'not Jev' in text
    assert '12.' in text


def test_interactive_file_is_self_contained_and_mobile_aware():
    html = module.interactive_html({'actor': 'retail', 'paths': [], 'roles': {}})
    assert 'name="viewport"' in html and '<script src=' not in html
    assert 'Above $5M' in html and 'not calibrated' in html
    assert 'Maximum' not in html
    assert 'application/json' in html


def test_retail_projection_redacts_private_plan_budgets_and_response_labels():
    paths = [{'id': 'private-plan/staged-exit', 'case': 'private-plan', 'policy': 'staged-exit',
              'mode': 'native', 'regime': 'BULL', 'position_usd': 15000, 'upfront_usd': 10000,
              'status': 'completed', 'last_hour': 336, 'actors': {'retail': []}, 'rows': []}]
    projection = module.view_projection(paths, {'retail': {'id': 'retail'}}, 'retail')
    serialized = str(projection)
    assert '15000' not in serialized and '10000' not in serialized
    assert 'staged-exit' not in serialized and 'private-plan' not in serialized


def test_statistics_keep_denominators_and_drawdown_explicit():
    rows = [{'second': index * 3600, 'mc_usd': value} for index, value in enumerate([100, 200, 50])]
    result = module.path_statistics(rows, [{'actor': 'a', 'cash_cents': 100, 'side': 'buy', 'status': 'executed'},
                                          {'actor': 'b', 'cash_cents': 300, 'side': 'sell', 'status': 'executed'},
                                          {'actor': 'a', 'status': 'rejected_slippage'}],
                                    {'a': {'buy_small': 1, 'wait': 2}, 'b': {'sell_small': 1}})
    assert result['sampled_peak_to_trough_drawdown'] == .75
    assert result['trade_attempts'] == 3 and result['rejection_rate'] == 1 / 3
    assert result['largest_actor_turnover_share'] == .75
    assert module.path_statistics([], [], {})['rejection_rate'] is None


def test_branch_comparison_uses_same_timestamp_not_different_endpoints():
    base = {'case': 'case', 'mode': 'native', 'regime': 'BULL', 'position_usd': 5000, 'upfront_usd': 5000}
    paths = [{**base, 'policy': 'pause-and-observe', 'rows': [
        {'second': 0, 'founder_net_cash_usd': -5000}, {'second': 3600, 'founder_net_cash_usd': -7000}]},
        {**base, 'policy': 'staged-exit', 'rows': [
        {'second': 0, 'founder_net_cash_usd': -5000}, {'second': 1800, 'founder_net_cash_usd': -2000},
        {'second': 3600, 'founder_net_cash_usd': -3000}, {'second': 7200, 'founder_net_cash_usd': 1000}]}]
    result = module.matched_comparisons(paths)[0]
    assert result['second'] == 3600
    assert result['exit_minus_pause_cash_usd'] == 4000


def test_guidance_uses_only_permitted_own_data_and_does_not_invent_optimal_returns():
    point = {'tokens': 10, 'cash_cents': 500, 'executions': [{'status': 'rejected_slippage'}],
             'own_policy': None, 'memory': {}}
    result = module.node_guidance(point)
    assert 'slippage' in result['reason']
    assert 'guarantee' in result['limitation']


def test_campaign_delivery_and_publications_are_visible_events_not_price_shocks():
    saved = {'second': 3600, 'events': [], 'choices': {'kol-a': 'publish'},
             'campaigns': [{'id': 'kol-a', 'status': 'active', 'text': 'Conditional sponsored post.'}]}
    events = module.public_events(saved, [{'id': 'kol-a', 'due_second': 3600}])
    assert {event['kind'] for event in events} == {'campaign_delivery', 'public_post'}
    assert all('price' not in event for event in events)


def test_pdf_renders_warmup_nulls_and_keeps_explanations_with_charts(tmp_path):
    path = {'id': 'fixture/staged-exit', 'case': 'fixture', 'policy': 'staged-exit', 'mode': 'native',
            'regime': 'BULL', 'position_usd': 5000, 'upfront_usd': 5000, 'status': 'budget_exhausted',
            'last_hour': 6, 'summary': {'founder_net_cash_cents': -500000}, 'attempts': {'buy': 1},
            'rows': [{'second': second, 'hours': second / 3600, 'mc_usd': 1000, 'venue_cash_usd': 500,
                      'volume_6h_usd': None if second == 0 else 50, 'founder_net_cash_usd': -5000,
                      'checkpoint_sha256': 'f' * 64} for second in (0, 21600)]}
    output = tmp_path / 'report.pdf'
    module.write_pdf({'native': {'status': 'partial_budget_limited', 'budget': {}}, 'paths': [path]}, output)
    assert output.read_bytes().startswith(b'%PDF')


def test_large_mobile_exports_compress_inline_data_without_losing_states():
    data = {'actor': 'retail', 'roles': {}, 'paths': [], 'fixture': 'state-only ' * 250000}
    html = module.interactive_html(data)
    envelope = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html).group(1))
    assert envelope['encoding'] == 'gzip-base64'
    assert json.loads(gzip.decompress(base64.b64decode(envelope['payload']))) == data
    assert len(html) < 100000 and '<script src=' not in html


def test_six_hour_caption_describes_available_values_after_warmup():
    path = {'rows': [{'hours': 0, 'volume_6h_usd': None}, {'hours': 6, 'volume_6h_usd': 10},
                     {'hours': 12, 'volume_6h_usd': 20}], 'attempts': {}, 'mode': 'native', 'status': 'budget_exhausted'}
    text = module.interpretation(path, 'volume_6h_usd')
    assert '$10.00' in text and '$20.00' in text and '+6.00h' in text
    assert 'unavailable during six-hour warmup across' not in text
