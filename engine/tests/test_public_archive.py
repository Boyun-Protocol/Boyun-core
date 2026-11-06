"""The forward archive preserves observations without inventing continuity."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from test_wallet_evidence import snapshot, trade


def archive(path):
    from decision_lab.public_archive import PublicArchive
    return PublicArchive(path)


def test_atomic_dedup_keeps_multifill_and_ledger(tmp_path):
    value = snapshot([trade(), trade('other-fill')])
    value['pools'][0]['trades']['data'].append(deepcopy(value['pools'][0]['trades']['data'][0]))
    with archive(tmp_path / 'private' / 'history.sqlite') as store:
        first = store.record_snapshot(value)
        second = store.record_snapshot(value)
        assert first['new_trades'] == 2 and first['duplicate_trades'] == 1
        assert second['new_trades'] == 0 and second['duplicate_trades'] == 3
        state = store.status()
        assert state['total_trades'] == 2
        pool = state['pools'][0]
        assert pool['capture_count'] == 2 and pool['latest_capture_rows'] == 3
        assert state['complete_history'] is False and pool['complete_history'] is False
    assert os.stat(tmp_path / 'private' / 'history.sqlite').st_mode & 0o777 == 0o600
    assert os.stat(tmp_path / 'private').st_mode & 0o777 == 0o700
    with archive(tmp_path / 'private' / 'history.sqlite') as store:
        assert store.status()['total_trades'] == 2


def test_conflicting_duplicate_rolls_back_all_changes(tmp_path):
    with archive(tmp_path / 'history.sqlite') as store:
        store.record_snapshot(snapshot())
        conflict = snapshot([trade('new'), trade(usd='101')])
        with pytest.raises(ValueError, match='conflicting'):
            store.record_snapshot(conflict)
        assert store.status()['total_trades'] == 1
        assert store.status()['pools'][0]['capture_count'] == 1


def test_source_metadata_and_public_endpoint_enforced(tmp_path):
    with archive(tmp_path / 'history.sqlite') as store:
        store.record_snapshot(snapshot())
        modified = snapshot()
        modified['pools'][0]['base_token_address'] = 'different.near'
        with pytest.raises(ValueError, match='metadata'):
            store.record_snapshot(modified)
        modified = snapshot()
        modified['pools'][0]['source_url'] = 'https://pro-api.coingecko.com/api/v3/onchain/networks/near/pools/pool%2F123/trades/range'
        with pytest.raises(ValueError, match='public'):
            store.record_snapshot(modified)
        assert store.status()['pools'][0]['capture_count'] == 1


def test_failure_records_never_retain_raw_error_or_create_fake_success(tmp_path):
    with archive(tmp_path / 'history.sqlite') as store:
        store.record_failure('near', 'pool/123', '2026-10-24T01:00:00Z', 'token SECRET https://host/?key=abc')
        status = store.status()
        pool = status['pools'][0]
        assert pool['failed_capture_count'] == 1 and pool['capture_count'] == 0
        assert pool['last_success_at'] is None and pool['latest_error_code'] == 'collection_failed'
        assert 'SECRET' not in json.dumps(status)
        assert 'SECRET' not in (tmp_path / 'history.sqlite').read_bytes().decode('latin1')
        store.record_snapshot(snapshot())
        assert store.status()['total_trades'] == 1


def test_fractional_dates_order_numerically_and_empty_capture_recorded(tmp_path):
    value = snapshot([trade('fraction', block_timestamp='2026-10-23T12:00:00.5Z'), trade('whole')])
    with archive(tmp_path / 'history.sqlite') as store:
        store.record_snapshot(value)
        store.record_snapshot(snapshot([]))
        pool = store.status()['pools'][0]
        assert pool['first_trade_at'] == '2026-10-23T12:00:00Z'
        assert pool['last_trade_at'] == '2026-10-23T12:00:00.500000Z'
        assert pool['latest_capture_rows'] == 0 and pool['capture_count'] == 2


def test_export_is_valid_bounded_and_excludes_older_than_thirty_days(tmp_path):
    from decision_lab.wallet_evidence import analyze_wallets
    value = snapshot([trade('old', block_timestamp='2026-09-01T00:00:00Z'), trade('recent'),
                      trade('latest', block_timestamp='2026-10-23T15:00:00Z')])
    with archive(tmp_path / 'history.sqlite') as store:
        store.record_snapshot(value)
        exported = store.export_snapshot('near', limit=1, as_of='2026-10-24T00:00:00Z')
        assert len(exported['pools'][0]['trades']['data']) == 1
        assert exported['pools'][0]['trades']['data'][0]['id'] == 'latest'
        assert analyze_wallets(exported)['summary']['accepted_trades'] == 1
        assert store.status()['total_trades'] == 3  # Raw archive is not pruned.
        assert store.status()['complete_history'] is False


def test_networks_never_mix_and_empty_export_is_valid(tmp_path):
    from decision_lab.wallet_evidence import analyze_wallets
    with archive(tmp_path / 'history.sqlite') as store:
        store.record_snapshot(snapshot())
        store.record_snapshot(snapshot(network='solana'))
        near = store.export_snapshot('near', as_of='2026-10-24T00:00:00Z')
        assert near['network'] == 'near'
        assert analyze_wallets(near)['summary']['accepted_trades'] == 1
        empty = store.export_snapshot('near', as_of='2026-12-24T00:00:00Z')
        assert analyze_wallets(empty)['summary']['raw_records'] == 0


def test_possible_gap_is_conservative_and_never_proves_continuity(tmp_path):
    with archive(tmp_path / 'history.sqlite') as store:
        store.record_snapshot(snapshot())
        newer = snapshot([trade(f'new-{n}', block_timestamp='2026-10-23T16:00:00Z') for n in range(300)])
        store.record_snapshot(newer)
        pool = store.status()['pools'][0]
        assert pool['possible_gap_count'] == 1
        store.record_snapshot(newer)
        assert store.status()['pools'][0]['possible_gap_count'] == 1
        assert pool['continuity'] == 'unverified'


def test_invalid_or_oversized_input_is_rejected_before_transaction(tmp_path):
    with archive(tmp_path / 'history.sqlite') as store:
        value = snapshot()
        value['pools'][0]['trades']['data'][0]['extra'] = 'x' * 2100000
        with pytest.raises(ValueError):
            store.record_snapshot(value)
        assert store.status()['pools'] == []


@pytest.mark.parametrize('value', [0, 1001, True, '1'])
def test_export_limit_is_strict(tmp_path, value):
    with archive(tmp_path / 'history.sqlite') as store:
        with pytest.raises(ValueError):
            store.export_snapshot('near', limit=value)


def test_symlink_rejected_without_touching_target(tmp_path):
    target = tmp_path / 'target'
    target.write_text('not a database')
    link = tmp_path / 'link'
    link.symlink_to(target)
    with pytest.raises(ValueError, match='symlink|regular'):
        archive(link)
    assert target.read_text() == 'not a database'


def test_eight_pool_total_and_four_per_network_cap_is_atomic(tmp_path):
    with archive(tmp_path / 'history.sqlite') as store:
        for n in range(4):
            store.record_failure('near', f'pool-{n}', '2026-10-24T00:00:00Z', 'http_error')
        with pytest.raises(ValueError, match='four|pool limit'):
            store.record_failure('near', 'fifth', '2026-10-24T00:00:00Z', 'http_error')
        assert len(store.status()['pools']) == 4


def test_export_keeps_one_read_snapshot_when_collector_commits_between_queries(tmp_path):
    from decision_lab.public_archive import PublicArchive
    path = tmp_path / 'archive.sqlite'
    with PublicArchive(path) as writer:
        writer.record_snapshot(snapshot())
        writer._db.execute('PRAGMA journal_mode=WAL')
        newer = snapshot([trade('new', block_timestamp='2026-10-24T01:00:00Z')])
        newer['captured_at'] = '2026-10-24T03:00:00Z'
        newer['pools'][0]['retrieved_at'] = '2026-10-24T02:00:00Z'
        with PublicArchive(path, read_only=True) as reader:
            committed = []
            def interleave(sql):
                if 'SELECT max(retrieved_at)' in sql and not committed:
                    committed.append(True)
                    writer.record_snapshot(newer)
            reader._db.set_trace_callback(interleave)
            exported = reader.export_snapshot('near', as_of='2026-10-24T03:00:00Z')
            assert committed
            assert len(exported['pools'][0]['trades']['data']) == 1
            reader._db.set_trace_callback(None)
            assert reader.status()['total_trades'] == 2
