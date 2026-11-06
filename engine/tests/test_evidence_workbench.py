import json
import threading

import pytest

from test_topic_evidence import sample
from test_wallet_evidence import snapshot


def test_explicit_local_datasets_registered_without_exposing_paths(tmp_path):
    from decision_lab.web_jobs import JobManager
    wallet = tmp_path / 'private-wallet-path.json'
    topic = tmp_path / 'private-news-path.json'
    wallet.write_text(json.dumps(snapshot()))
    topic.write_text(json.dumps(sample()))
    with JobManager(tmp_path / 'output', wallet_observation_paths=[wallet], topic_observation_paths=[topic]) as manager:
        bootstrap = manager.bootstrap()
        assert len(bootstrap['evidence_options']) == 2
        encoded = json.dumps(bootstrap)
        assert str(tmp_path) not in encoded
        for option in bootstrap['evidence_options']:
            result = manager.evidence(option['id'])
            assert result['schema_version'] in {'wallet-cohorts.v1', 'topic-evidence.v1'}
        with pytest.raises(KeyError):
            manager.evidence('../../private')


def test_evidence_import_is_independent_of_synthetic_scenario(tmp_path):
    from decision_lab.web_jobs import JobManager
    with JobManager(tmp_path / 'output') as manager:
        for kind, value in [('wallets', snapshot()), ('topics', sample())]:
            kind_value, context, original = manager._prepare({'kind': kind, 'snapshot': value})
            assert original is None
            assert context['worlds'] == 0
            assert manager.execute_job({'kind': kind_value, 'context': context})['simulation_effect'] == 'none'
            with pytest.raises(ValueError):
                manager._prepare({'kind': kind, 'snapshot': value, 'scenario': {}})


def test_evidence_http_route_is_origin_guarded(tmp_path):
    from decision_lab.web_server import create_server
    from test_web_server import request
    wallet = tmp_path / 'source.json'
    wallet.write_text(json.dumps(snapshot()))
    server = create_server(port=0, output_dir=tmp_path / 'output', wallet_observation_paths=[wallet])
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        bootstrap = json.loads(request(server, 'GET', '/api/bootstrap')[2])
        evidence_id = bootstrap['evidence_options'][0]['id']
        path = '/api/evidence/' + evidence_id
        assert request(server, 'GET', path)[0] == 200
        assert request(server, 'GET', path, headers={'Origin': 'https://evil.example'})[0] == 403
        assert request(server, 'GET', '/api/evidence/../../source.json')[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def test_public_archive_live_evidence_is_read_only_and_explicit(tmp_path):
    from decision_lab.public_archive import PublicArchive
    from decision_lab.web_jobs import JobManager
    path = tmp_path / 'public.sqlite'
    with PublicArchive(path) as archive:
        archive.record_snapshot(snapshot())
    with JobManager(tmp_path / 'output', public_archive_path=path) as manager:
        bootstrap = manager.bootstrap()
        options = [o for o in bootstrap['evidence_options'] if 'accumulating' in o['label']]
        assert len(options) == 1
        result = manager.evidence(options[0]['id'])
        assert result['summary']['observed_wallets'] == 1
        assert result['archive_status']['configured'] is True
        assert result['archive_status']['complete_history'] is False
        assert manager.public_history()['configured'] is True
        assert str(tmp_path) not in json.dumps(bootstrap)
    with JobManager(tmp_path / 'empty') as manager:
        assert manager.public_history() == {'configured': False}


def test_public_archive_status_route_enforces_origin(tmp_path):
    from decision_lab.public_archive import PublicArchive
    from decision_lab.web_server import create_server
    from test_web_server import request
    path = tmp_path / 'public.sqlite'
    with PublicArchive(path) as archive:
        archive.record_snapshot(snapshot())
    server = create_server(port=0, output_dir=tmp_path / 'output', public_archive_path=path)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        status, _, body = request(server, 'GET', '/api/public-history')
        assert status == 200 and json.loads(body)['configured'] is True
        assert request(server, 'GET', '/api/public-history', headers={'Origin': 'https://evil.example'})[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
