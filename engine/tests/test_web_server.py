"""HTTP integration: loopback origin boundary and actual local engine jobs."""
import http.client
import json
import threading
import time

import pytest


@pytest.fixture
def running(tmp_path):
    from decision_lab.web_server import create_server
    server = create_server(port=0, output_dir=tmp_path)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(3)
    assert not thread.is_alive()


def request(server, method, path, body=None, headers=None):
    client = http.client.HTTPConnection(*server.server_address, timeout=5)
    client.request(method, path, body=body, headers=headers or {})
    response = client.getresponse()
    value = response.read()
    result = (response.status, dict(response.getheaders()), value)
    client.close()
    return result


def test_bootstrap_origin_csrf_strict_json_and_private_paths(running):
    status, headers, body = request(running, 'GET', '/api/bootstrap')
    assert status == 200
    boot = json.loads(body)
    assert boot['csrf_token']
    assert boot['capabilities']['live_model_calls'] is False
    assert boot['capabilities']['onchain_submission'] is False
    assert 'Access-Control-Allow-Origin' not in headers
    for headers in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'Host': 'localhost.evil:8769'}):
        assert request(running, 'GET', '/api/bootstrap', headers=headers)[0] == 403
    for path in ('/../pyproject.toml', '/%2e%2e/secret', '/api/jobs/../../secret', '/favicon.ico'):
        assert request(running, 'GET', path)[0] == 404
    assert request(running, 'POST', '/api/jobs', '{}', {'Content-Type': 'application/json'})[0] == 403
    valid = {'Content-Type': 'application/json', 'X-CSRF-Token': boot['csrf_token']}
    for raw in ('{"kind":"run","kind":"cast"}', '{"kind":"run","seed":NaN}', '{"kind":"run","seed":Infinity}', '[]', '{'):
        assert request(running, 'POST', '/api/jobs', raw, valid)[0] == 400
    assert request(running, 'POST', '/api/jobs', '{}', {**valid, 'Content-Type': 'text/plain'})[0] == 415
    assert request(running, 'POST', '/api/jobs', '{}', {**valid, 'Content-Length': str(2 * 1024 * 1024 + 1)})[0] == 413


def test_http_run_download_commitment_opening_and_unsigned_action(running):
    boot = json.loads(request(running, 'GET', '/api/bootstrap')[2])
    headers = {'Content-Type': 'application/json', 'X-CSRF-Token': boot['csrf_token']}
    status, _, body = request(running, 'POST', '/api/jobs', json.dumps({'kind': 'run', 'worlds': 1, 'seed': 7}), headers)
    assert status == 202
    job_id = json.loads(body)['job_id']
    for _ in range(300):
        job = json.loads(request(running, 'GET', '/api/jobs/' + job_id)[2])
        if job['status'] == 'completed':
            break
        assert job['status'] != 'failed'
        time.sleep(.01)
    assert job['result']['usage']['model_calls'] == 0
    data = request(running, 'GET', '/api/jobs/' + job_id + '/download')[2]
    assert json.loads(data) == job['result']
    status, _, body = request(running, 'POST', '/api/jobs/' + job_id + '/commitment', '{}', headers)
    assert status == 200
    commitment = json.loads(body)
    assert commitment['verified'] is True
    opening = json.loads(request(running, 'GET', '/api/jobs/' + job_id + '/opening')[2])
    from decision_lab.integrity import verify_commitment
    assert verify_commitment(data, commitment['public'], opening)
    status, _, action = request(running, 'POST', '/api/jobs/' + job_id + '/near-action', json.dumps({'network': 'testnet', 'signer_id': 'a.testnet', 'contract_id': 'r.testnet'}), headers)
    assert status == 200 and json.loads(action)['status'] == 'unsigned_unverified'
    assert request(running, 'POST', '/api/jobs/' + job_id + '/near-action', json.dumps({'network': 'mainnet', 'signer_id': 'a.near', 'contract_id': 'r.near'}), headers)[0] == 400
    assert request(running, 'GET', '/api/jobs/' + '0' * 32)[0] == 404


def test_binding_rejects_nonloopback(tmp_path):
    from decision_lab.web_server import create_server
    with pytest.raises(ValueError):
        create_server(host='0.0.0.0', port=0, output_dir=tmp_path)


def test_fonts_are_exact_allowlist_and_opening_is_origin_guarded(running):
    assert request(running, 'GET', '/fonts/manrope.ttf')[0] == 200
    assert request(running, 'GET', '/fonts/OFL-Manrope.txt')[0] == 200
    assert request(running, 'GET', '/fonts/../../data/personas.json')[0] == 404
    for path in ('/api/jobs/' + '0' * 32, '/api/jobs/' + '0' * 32 + '/opening', '/api/jobs/' + '0' * 32 + '/download', '/'):
        assert request(running, 'GET', path, headers={'Origin': 'null'})[0] == 403
    origin = f'http://127.0.0.1:{running.server_address[1]}'
    assert request(running, 'GET', '/api/bootstrap', headers={'Origin': origin})[0] == 200


def test_non_ascii_csrf_rejected_with_json_error(running):
    assert request(running, 'POST', '/api/jobs', '{}', {'Content-Type': 'application/json', 'X-CSRF-Token': '\u00e9'})[0] == 403


@pytest.mark.parametrize('recipe', [[], None, 'bad', 1])
def test_malformed_recipe_returns_safe_json_error(running, recipe):
    boot = json.loads(request(running, 'GET', '/api/bootstrap')[2])
    headers = {'Content-Type': 'application/json', 'X-CSRF-Token': boot['csrf_token']}
    scenario = boot['scenario']
    scenario['cast_recipe'] = recipe
    status, _, body = request(running, 'POST', '/api/jobs', json.dumps({'kind': 'cast', 'scenario': scenario}), headers)
    assert status == 400 and set(json.loads(body)) == {'error'}
    request_body = {'kind': 'import', 'request': {'context': {'scenario': scenario}}, 'response': {}, 'bundle_id': 'bad'}
    status, _, body = request(running, 'POST', '/api/jobs', json.dumps(request_body), headers)
    assert status == 400 and set(json.loads(body)) == {'error'}


def test_huge_decimal_content_length_returns_json_error(running):
    boot = json.loads(request(running, 'GET', '/api/bootstrap')[2])
    headers = {'Content-Type': 'application/json', 'X-CSRF-Token': boot['csrf_token'], 'Content-Length': '9' * 5000}
    status, _, body = request(running, 'POST', '/api/jobs', '{}', headers)
    assert status == 413 and set(json.loads(body)) == {'error'}


def test_container_bind_serves_published_port_without_loosening_origin_checks(tmp_path):
    """A published container port is unreachable on the container's own loopback.

    Widening the socket must not widen the trust boundary, so a foreign Host still
    gets 403 and only a loopback Host is served.
    """
    from decision_lab.web_server import create_server

    server = create_server(port=0, output_dir=tmp_path, container_bind=True)
    assert server.server_address[0] == '0.0.0.0'
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        port = server.server_address[1]
        def get(headers=None):
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            client.request('GET', '/api/bootstrap', headers=headers or {})
            response = client.getresponse()
            response.read()
            client.close()
            return response.status
        assert get() == 200
        assert get({'Host': f'localhost:{port}'}) == 200
        assert get({'Host': f'evil.example:{port}'}) == 403
        assert get({'Host': 'evil.example'}) == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()


def test_bind_arguments_stay_restricted(tmp_path):
    from decision_lab.web_server import create_server

    for host in ('0.0.0.0', 'evil.example'):
        with pytest.raises(ValueError):
            create_server(host=host, port=0, output_dir=tmp_path)
    # The container bind is a decision, not an address the caller can steer.
    for container_bind in ('0.0.0.0', 'evil.example'):
        with pytest.raises(ValueError):
            create_server(port=0, output_dir=tmp_path, container_bind=container_bind)
