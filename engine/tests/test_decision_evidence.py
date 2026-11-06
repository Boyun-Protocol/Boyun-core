"""Decision context contains measured cohorts, never invented agent resources."""
from copy import deepcopy
import hashlib
import json

import pytest

from test_wallet_evidence import snapshot, trade


def build(**kwargs):
    from decision_lab.decision_evidence import build_evidence_context
    return build_evidence_context(**kwargs)


def test_context_separates_primary_and_comparison_without_population_or_capital_claims():
    near = snapshot([trade('near-a', usd='25'), trade('near-b', usd='12500')])
    sol = snapshot([trade('solana-a', usd='100000')], network='solana')
    result = build(wallet_snapshots=[near, sol])
    assert result['schema_version'] == 'decision-evidence-context.v1'
    assert result['primary_network'] == 'near'
    assert result['primary'][0]['summary']['accepted_trades'] == 2
    assert result['comparisons'][0]['summary']['accepted_trades'] == 1
    assert result['comparisons'][0]['network'] == 'solana'
    assert result['primary'][0]['cohorts'][0]['wallet_count'] == 1
    assert result['resource_assignment'] == 'none'
    assert result['population_calibration'] is False
    assert {'available_capital', 'kol_or_market_maker_role', 'future_behavior'} <= set(result['unknown_traits'])
    assert 'alice.near' not in json.dumps(result)
    assert near == snapshot([trade('near-a', usd='25'), trade('near-b', usd='12500')])


def test_exact_duplicate_sources_removed_but_overlapping_snapshots_are_not_summed():
    first = snapshot()
    second = snapshot([trade(), trade('second')])
    result = build(wallet_snapshots=[first, deepcopy(first), second])
    assert result['duplicate_input_sources'] == 1
    assert len(result['primary']) == 2
    assert 'combined_summary' not in result
    source = result['primary'][0]
    expected = hashlib.sha256(json.dumps(first, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    assert source['sha256'] == expected
    assert expected in source['source_ref']
    assert 'overlap' in ' '.join(result['limitations']).lower()


def test_empty_context_and_empty_valid_capture_do_not_claim_observed_population():
    result = build()
    assert result['primary'] == result['comparisons'] == []
    assert result['status'] == 'no_primary_observations'
    from decision_lab.decision_evidence import brief_evidence
    evidence = brief_evidence(result)
    assert len(evidence) == 1
    assert 'No observed' in evidence[0]['summary']
    zero = build(wallet_snapshots=[snapshot([])])['primary'][0]
    assert zero['summary']['observed_wallets'] == 0
    assert zero['observed_window'] == {'start': None, 'end': None}
    assert zero['coverage']['complete_target_window'] is False


def test_coverage_exclusions_cutoff_and_source_references_are_retained():
    source = snapshot([trade(), trade('bad', wallet=None), trade('anomaly', is_anomalous=True)])
    result = build(wallet_snapshots=[source], as_of='2026-10-24T01:00:00Z')
    row = result['primary'][0]
    assert result['as_of'] == '2026-10-24T01:00:00Z'
    assert row['captured_at'] == source['captured_at']
    assert row['summary']['excluded']['missing_wallet'] == 1
    assert row['summary']['excluded']['anomalous'] == 1
    assert row['provider_endpoints'] == [source['pools'][0]['source_url']]
    assert row['coverage']['thresholds_usd'] == {'small_max_inclusive': 100, 'large_min_inclusive': 10000}
    with pytest.raises(ValueError, match='cutoff'):
        build(wallet_snapshots=[source], as_of='2026-10-23T00:00:00Z')


@pytest.mark.parametrize('bad', [None, {}, {'schema_version': 'other'}])
def test_invalid_snapshot_is_rejected(bad):
    with pytest.raises(ValueError):
        build(wallet_snapshots=[bad])


@pytest.mark.parametrize('kwargs', [dict(network='ethereum'), dict(network=True), dict(wallet_snapshots={}),
                                    dict(wallet_snapshots=[snapshot()] * 9), dict(as_of='yesterday')])
def test_boundaries_are_validated_before_processing(kwargs):
    with pytest.raises(ValueError):
        build(**kwargs)


def test_unicode_and_many_sources_fit_ascii_prompt_budget_with_exact_cohort_omissions():
    values = []
    for n in range(8):
        source = snapshot([trade(f'{n}-small', wallet='x', usd='1'), trade(f'{n}-large', wallet='y', usd='10000')], network='near' if n < 4 else 'solana')
        source['pools'][0]['name'] = '🧪' * 160
        source['pools'][0]['address'] = '🧪' * 256
        from urllib.parse import quote
        source['pools'][0]['source_url'] = f"https://api.geckoterminal.com/api/v2/networks/{source['network']}/pools/{quote(source['pools'][0]['address'], safe='')}/trades"
        # Analyzer intentionally limits any single provider field to 2048 chars.
        source['pools'][0]['address'] = '🧪' * 100
        source['pools'][0]['source_url'] = f"https://api.geckoterminal.com/api/v2/networks/{source['network']}/pools/{quote(source['pools'][0]['address'], safe='')}/trades"
        values.append(source)
    result = build(wallet_snapshots=values)
    assert len(json.dumps(result, ensure_ascii=True).encode()) <= 24000
    assert len(result['primary']) + len(result['comparisons']) == 8
    for source in result['primary'] + result['comparisons']:
        assert sum(row['trade_count'] for row in source['cohorts']) + source['omitted_cohorts']['trade_count'] == source['summary']['accepted_trades']
        assert sum(row['notional_cents'] for row in source['cohorts']) + source['omitted_cohorts']['notional_cents'] == source['summary']['observed_notional_cents']


def test_brief_evidence_contains_actual_summary_and_bounded_limitations():
    from decision_lab.decision_evidence import brief_evidence
    context = build(wallet_snapshots=[snapshot([trade(usd='123.45')])])
    rows = brief_evidence(context)
    assert rows[0]['source_ref'] == context['primary'][0]['source_ref']
    assert '12345' in rows[0]['summary']
    assert 'capital' in rows[0]['limitations'].lower()
    assert all(set(row) == {'source_ref', 'summary', 'limitations'} for row in rows)
    assert all(len(value) <= 4000 for row in rows for value in row.values())
    mutated = deepcopy(context)
    mutated['primary'][0]['summary']['accepted_trades'] = 999
    with pytest.raises(ValueError):
        brief_evidence(mutated)


def test_archive_reads_are_read_only_and_network_specific(tmp_path):
    from decision_lab.public_archive import PublicArchive
    path = tmp_path / 'history.sqlite'
    with PublicArchive(path) as archive:
        archive.record_snapshot(snapshot())
        archive.record_snapshot(snapshot([trade('solana-1')], network='solana'))
        archive.record_failure('near', 'pool/123', '2026-10-24T00:00:01Z', 'rate_limited')
    before = path.read_bytes()
    context = build(archive_path=path, as_of='2026-10-24T01:00:00Z')
    assert path.read_bytes() == before
    assert context['primary'][0]['summary']['accepted_trades'] == 1
    assert context['comparisons'][0]['network'] == 'solana'
    assert context['primary'][0]['archive_inventory']['failed_capture_count'] == 1
    assert context['primary'][0]['archive_inventory']['continuity'] == 'unverified'
    assert context['primary'][0]['origin'] == 'public_archive_export'
    assert context['primary'][0]['archive_inventory']['scope'] == 'current_inventory_not_historical_cutoff'


def test_missing_archive_never_creates_file_and_symlink_rejected(tmp_path):
    path = tmp_path / 'missing.sqlite'
    with pytest.raises(ValueError):
        build(archive_path=path)
    assert not path.exists()
    from decision_lab.public_archive import PublicArchive
    with PublicArchive(path):
        pass
    link = tmp_path / 'link.sqlite'
    link.symlink_to(path)
    with pytest.raises(ValueError):
        build(archive_path=link)


def test_failure_only_archive_keeps_failed_capture_counts_even_without_a_snapshot(tmp_path):
    from decision_lab.public_archive import PublicArchive
    path = tmp_path / 'history.sqlite'
    with PublicArchive(path) as archive:
        archive.record_failure('near', 'no-data', '2026-10-24T00:00:00Z', 'rate_limited')
    context = build(archive_path=path, as_of='2026-10-24T01:00:00Z')
    assert context['primary'] == []
    assert context['archive_inventory'][0]['network'] == 'near'
    assert context['archive_inventory'][0]['failed_capture_count'] == 1
    assert context['archive_inventory'][0]['latest_error_codes'] == ['rate_limited']
    from decision_lab.decision_evidence import brief_evidence
    assert 'failed_capture_count' in brief_evidence(context)[0]['summary']


def test_archive_export_records_actual_retrieval_time_and_not_a_knowledge_backtest(tmp_path):
    from decision_lab.public_archive import PublicArchive
    path = tmp_path / 'history.sqlite'
    source = snapshot()
    with PublicArchive(path) as archive:
        archive.record_snapshot(source)
    context = build(archive_path=path, as_of='2026-10-23T13:00:00Z')
    assert context['primary'][0]['latest_provider_retrieved_at'] == source['pools'][0]['retrieved_at']
    assert context['primary'][0]['cutoff_semantics'] == 'event_time_filter_not_historical_knowledge'
    assert 'knowledge' in ' '.join(context['limitations'])


def test_context_hash_is_stable_for_ordered_same_inputs_and_no_hidden_clock():
    source = snapshot()
    assert build(wallet_snapshots=[source]) == build(wallet_snapshots=[deepcopy(source)])
    assert build() == build()


def test_duplicate_trade_exclusions_are_not_reintroduced_in_context():
    event = trade()
    result = build(wallet_snapshots=[snapshot([event, deepcopy(event)])])['primary'][0]
    assert result['summary']['duplicate_records'] == 1
    assert result['summary']['accepted_trades'] == 1
    assert sum(row['trade_count'] for row in result['cohorts']) == 1


def test_invalid_comparison_is_rejected_instead_of_ignored():
    comparison = snapshot(network='solana')
    comparison['pools'][0]['trades']['data'][0]['attributes']['volume_in_usd'] = 'NaN'
    with pytest.raises(ValueError):
        build(wallet_snapshots=[snapshot(), comparison])


def test_comparison_only_context_also_reports_absent_primary_data_to_builder():
    from decision_lab.decision_evidence import brief_evidence
    context = build(wallet_snapshots=[snapshot(network='solana')])
    rows = brief_evidence(context)
    assert len(rows) == 2
    assert any('No observed' in row['summary'] and 'near' in row['summary'] for row in rows)
    assert any('separate comparison only' in row['summary'] for row in rows)


def test_archive_export_never_claims_complete_matching_history(tmp_path):
    from decision_lab.public_archive import PublicArchive
    path = tmp_path / 'history.sqlite'
    with PublicArchive(path) as archive:
        archive.record_snapshot(snapshot())
    result = build(archive_path=path, as_of='2026-10-24T01:00:00Z')
    assert result['primary'][0]['coverage']['export_row_limit'] == 1000
    assert result['primary'][0]['coverage']['matching_history_complete'] is False


def test_maximum_sources_and_unicode_endpoints_preserve_all_receipts_under_budget():
    from urllib.parse import quote
    from decision_lab.decision_evidence import brief_evidence
    values = []
    for n in range(8):
        rows = []
        for size, usd in [('small', '1'), ('medium', '200'), ('large', '15000')]:
            rows.extend([trade(f'{n}-{size}-one', wallet=f'{size}-one', usd=usd),
                         trade(f'{n}-{size}-both1', wallet=f'{size}-both', usd=usd),
                         trade(f'{n}-{size}-both2', wallet=f'{size}-both', usd=usd, direction='sell')])
        source = snapshot(rows, network='near' if n < 4 else 'solana')
        pools = []
        for pool_n in range(4):
            pool = deepcopy(source['pools'][0])
            pool['address'] = '🧪' * 100 + str(pool_n)
            pool['source_url'] = f"https://api.geckoterminal.com/api/v2/networks/{source['network']}/pools/{quote(pool['address'], safe='')}/trades"
            pools.append(pool)
        source['pools'] = pools
        values.append(source)
    result = build(wallet_snapshots=values)
    assert len(json.dumps(result, ensure_ascii=True).encode('ascii')) <= 24000
    sources = result['primary'] + result['comparisons']
    assert len(sources) == 8
    assert sum(row['omitted_provider_endpoints'] for row in sources) > 0
    for source in sources:
        assert len(source['provider_endpoints']) + source['omitted_provider_endpoints'] == 4
        assert source['omitted_cohorts']['cohort_count'] + len(source['cohorts']) == 6
        for cohort_key, summary_key in [('trade_count', 'accepted_trades'), ('wallet_count', 'observed_wallets'), ('notional_cents', 'observed_notional_cents')]:
            assert sum(row[cohort_key] for row in source['cohorts']) + source['omitted_cohorts'][cohort_key] == source['summary'][summary_key]
    assert len(brief_evidence(result)) == 8


def test_real_existing_agent_brief_accepts_generated_evidence_without_changes():
    from pathlib import Path
    from decision_lab.agent_orchestration import validate_brief, construction_messages
    from decision_lab.decision_evidence import brief_evidence
    brief = json.loads((Path(__file__).parents[1] / 'examples' / 'agent-world-brief.public.json').read_text())
    context = build(wallet_snapshots=[snapshot([trade(usd='123.45')]), snapshot(network='solana')])
    brief['evidence'] = brief_evidence(context)
    assert validate_brief(brief) == brief
    supplied = json.loads(construction_messages(brief)[1]['content'])['brief']['evidence']
    assert supplied == brief['evidence']
    assert context['primary'][0]['source_ref'] in json.dumps(supplied)
    assert '12345' in json.dumps(supplied)
