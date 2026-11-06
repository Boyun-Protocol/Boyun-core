import json
from unittest.mock import patch

import pytest

from test_public_capture import POOL
from test_wallet_evidence import snapshot


def main(args):
    from decision_lab.cli import main
    return main(['public-data', *args])


def test_ingest_status_export_round_trip_without_network(tmp_path, capsys):
    source, database, output = (tmp_path / name for name in ('source.json', 'archive.sqlite', 'export.json'))
    source.write_text(json.dumps(snapshot()))
    assert main(['ingest', '--input', str(source), '--archive', str(database)]) == 0
    assert main(['ingest', '--input', str(source), '--archive', str(database)]) == 0
    assert main(['status', '--archive', str(database)]) == 0
    lines = capsys.readouterr().out
    assert '"total_trades": 1' in lines
    assert main(['export', '--archive', str(database), '--network', 'near', '--output', str(output)]) == 0
    assert json.loads(output.read_text())['network'] == 'near'
    assert main(['export', '--archive', str(database), '--network', 'near', '--output', str(output)]) == 2


def test_collect_opt_in_and_preflight_precede_dispatch(tmp_path):
    config = tmp_path / 'pools.json'
    config.write_text(json.dumps({'near': [POOL]}))
    with patch('decision_lab.public_commands.collect_public') as collect:
        assert main(['collect', '--pools', str(config), '--archive', str(tmp_path / 'archive.sqlite')]) == 2
        collect.assert_not_called()


def test_serve_corrupt_archive_reports_safe_configuration_error(tmp_path, capsys):
    from decision_lab.cli import main as cli_main
    path = tmp_path / 'PRIVATE-file.sqlite'
    path.write_bytes(b'not sqlite')
    assert cli_main(['serve', '--port', '0', '--output-dir', str(tmp_path/'out'), '--public-archive', str(path)]) == 2
    output = capsys.readouterr()
    assert 'Cannot start workbench' in output.err
    assert 'PRIVATE' not in output.err


def test_bounded_watch_cycles_rate_limit_cooldown_and_duplicate_lock(tmp_path):
    from decision_lab.public_commands import watch_public
    config = {'near': [POOL]}
    sleeps = []
    calls = []
    def collect(**kwargs):
        calls.append(kwargs)
        return {'rate_limited': True, 'pools': [{'retry_after_seconds': 600}], 'request_count': 1,
                'success_count': 0, 'failure_count': 1}
    path = tmp_path / 'archive.sqlite'
    assert watch_public(config=config, archive_path=path, allow_network=True, interval=60,
                        max_cycles=2, collect_fn=collect, sleep_fn=sleeps.append) == 0
    assert len(calls) == 2
    assert sleeps == [600]
    import fcntl
    with open(str(path) + '.watch.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='already'):
            watch_public(config=config, archive_path=path, allow_network=True, max_cycles=1)


@pytest.mark.parametrize('interval', [0, 59, True, 86401])
def test_watch_invalid_interval_never_dispatches(tmp_path, interval):
    from decision_lab.public_commands import watch_public
    with pytest.raises(ValueError):
        watch_public(config={'near': [POOL]}, archive_path=tmp_path/'db', allow_network=True,
                     interval=interval, max_cycles=1, collect_fn=lambda **kwargs: pytest.fail('dispatch'))
