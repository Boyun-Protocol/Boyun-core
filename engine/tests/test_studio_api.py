"""Real HTTP and bounded offline Studio operations."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import stat
import threading
import time

import pytest


EXAMPLES = Path(__file__).parents[1] / 'examples'


def draft(name='ticker-evaluation-draft.v1.json'):
    return json.loads((EXAMPLES / name).read_text())


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


def request(server, method, path, value=None, *, authorized=True, headers=None):
    client = http.client.HTTPConnection(*server.server_address, timeout=10)
    supplied = {'Content-Type': 'application/json'}
    if authorized:
        supplied['X-CSRF-Token'] = server.manager.csrf_token
    supplied.update(headers or {})
    client.request(method, path, body=None if value is None else json.dumps(value), headers=supplied)
    response = client.getresponse()
    raw = response.read()
    result = response.status, json.loads(raw)
    client.close()
    return result


def test_bootstrap_pure_authoring_and_http_boundaries(running):
    status, boot = request(running, 'GET', '/api/studio')
    assert status == 200
    assert boot['providers']['mode'] == 'external' and boot['providers']['model_calls'] == 0
    assert {'ticker', 'stress', 'launch'} <= {row['id'] for row in boot['examples']}
    assert 'policies.synthetic' not in json.dumps(boot)
    current = draft()
    assert request(running, 'POST', '/api/studio/validate', {'draft': current}, authorized=False)[0] == 403
    assert request(running, 'POST', '/api/studio/validate', {'draft': current}, headers={'Origin': 'https://evil.example'})[0] == 403
    status, compilation = request(running, 'POST', '/api/studio/validate', {'draft': current})
    assert status == 200 and compilation['ready']
    status, prepared = request(running, 'POST', '/api/studio/prepare', {'draft': current, 'model': 'external-example'})
    assert status == 200 and prepared['usage']['model_calls'] == 0
    changed = deepcopy(current)
    changed['revision'] += 1
    response = {'schema_version': 'scenario-authoring-response.v1', 'base_revision': current['revision'],
                'base_sha256': prepared['draft_sha256'], 'draft': changed}
    status, applied = request(running, 'POST', '/api/studio/apply', {'draft': current, 'response': response})
    assert status == 200 and applied['draft'] == changed and applied['compilation']['ready']
    current['revision'] += 1
    status, error = request(running, 'POST', '/api/studio/apply', {'draft': current, 'response': response})
    assert status == 400 and set(error) == {'error'}
    for path in ('/api/studio/examples/../../policies.synthetic.json', '/api/studio/worlds/../../secret', '/world-any.json'):
        assert request(running, 'GET', path)[0] == 404
    assert request(running, 'POST', '/api/studio/validate', {'draft': current, 'path': '/private/SECRET'})[0] == 400


def test_scenario_queue_executes_actual_package_and_rejects_bounds(running):
    from decision_lab.scenario_authoring import compile_draft, run_package
    current = draft()
    status, submitted = request(running, 'POST', '/api/jobs', {'kind': 'scenario', 'draft': current, 'worlds': 3, 'seed': 7})
    assert status == 202
    for _ in range(500):
        _, job = request(running, 'GET', '/api/jobs/' + submitted['job_id'])
        if job['status'] in {'completed', 'failed'}:
            break
        time.sleep(.01)
    assert job['status'] == 'completed'
    assert job['result'] == run_package(compile_draft(current)['package'], worlds=3, seed=7)
    assert job['completed_worlds'] == job['target_worlds'] == 3
    for extra in ({'worlds': 101}, {'seed': True}, {'package': {}}, {'worlds': 0}):
        assert request(running, 'POST', '/api/jobs', {'kind': 'scenario', 'draft': current, **extra})[0] == 400
    current['fields'][0]['value'] = None
    assert request(running, 'POST', '/api/jobs', {'kind': 'scenario', 'draft': current})[0] == 400


def choice_package():
    provenance = {'status': 'assumed', 'rationale': 'Illustrative planning transition.', 'source_refs': []}
    def choice(key, next_scene):
        return {'id': key, 'label': key, 'explanation': 'Apply a declared planning point.', 'actor_id': 'lead',
                'requirements': [], 'immediate_effects': [{'action': 'adjust_metric', 'metric_id': 'points', 'delta': 1}],
                'outcomes': [{'id': 'done', 'label': 'Done', 'probability_bps': 10000, 'effects': [], 'next_scene_id': next_scene}],
                'probability_provenance': deepcopy(provenance)}
    return {'schema_version': 'choice-world.v1', 'id': 'planning', 'event_description': 'Declared planning choices.',
            'parameters': {}, 'personas': [{'id': 'lead', 'name': 'Lead', 'description': 'A supplied role.',
            'role': 'planner', 'allowed_actions': ['adjust_metric']}],
            'metrics': [{'id': 'points', 'unit': 'planning_points', 'initial': 0, 'minimum': 0, 'maximum': 3}],
            'scenes': [{'id': 'first', 'title': 'First', 'description': 'Choose.', 'choices': [choice('build', 'last')]},
                       {'id': 'last', 'title': 'Last', 'description': 'Finish.', 'choices': [choice('finish', None)]}],
            'initial_scene_id': 'first', 'policy': {'first': ['build'], 'last': ['finish']},
            'assumptions': ['Points are not money.']}


def test_choice_http_steps_cas_idempotency_restore_and_fork(running):
    status, original = request(running, 'POST', '/api/studio/worlds', {'package': choice_package(), 'seed': 42, 'world_id': 0})
    assert status == 201 and original['revision'] == 0 and original['choices'][0]['eligible']
    path = '/api/studio/worlds/' + original['id']
    step = {'choice_id': 'build', 'action_id': 'click-1', 'expected_revision': 0}
    status, advanced = request(running, 'POST', path + '/step', step)
    assert status == 200 and advanced['revision'] == 1 and advanced['snapshot']['metrics'] == {'points': 1}
    assert request(running, 'POST', path + '/step', step) == (200, advanced)
    assert request(running, 'POST', path + '/step', {**step, 'choice_id': 'finish'})[0] == 400
    assert request(running, 'POST', path + '/step', {**step, 'expected_revision': 99})[0] == 409
    assert request(running, 'POST', path + '/step', {'choice_id': 'finish', 'action_id': 'click-2', 'expected_revision': 0})[0] == 409
    assert request(running, 'POST', path + '/fork', {'branch_id': 'alternative', 'expected_revision': 0})[0] == 409
    status, forked = request(running, 'POST', path + '/fork', {'branch_id': 'alternative', 'expected_revision': 1})
    assert status == 201 and forked['id'] != original['id'] and forked['revision'] == 0
    assert forked['snapshot']['history'] == advanced['snapshot']['history']
    assert request(running, 'GET', path) == (200, advanced)
    status, restored = request(running, 'POST', '/api/studio/restore', {'snapshot': advanced['snapshot']})
    assert status == 201 and restored['id'] not in {original['id'], forked['id']}
    forged = deepcopy(advanced['snapshot'])
    forged['metrics']['points'] = 3
    assert request(running, 'POST', '/api/studio/restore', {'snapshot': forged})[0] == 400
    assert request(running, 'GET', '/api/studio/worlds/' + 'f' * 32)[0] == 404
    assert request(running, 'POST', path + '/step', step, authorized=False)[0] == 403
    for artifact in running.manager.output_dir.glob('world-*.json'):
        assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
        assert 'choices' not in json.loads(artifact.read_text())


def test_saved_session_lazy_reload_capacity_and_failed_persist(tmp_path, monkeypatch):
    import decision_lab.studio_api as studio
    api = studio.StudioAPI(tmp_path)
    original = api.create_world({'package': choice_package(), 'seed': 1, 'world_id': 0})
    reloaded = studio.StudioAPI(tmp_path)
    assert reloaded.get_world(original['id']) == original
    def failed(*args):
        raise OSError('/private/SECRET')
    with monkeypatch.context() as patch:
        patch.setattr(studio.os, 'replace', failed)
        with pytest.raises(OSError):
            api.mutate_world(original['id'], 'step', {'choice_id': 'build', 'action_id': 'a', 'expected_revision': 0})
    assert api.get_world(original['id']) == original
    assert not list(tmp_path.glob('.*.tmp'))
    monkeypatch.setattr(studio, 'MAX_WORLDS', 2)
    reloaded.create_world({'package': choice_package(), 'seed': 1, 'world_id': 1})
    fresh = studio.StudioAPI(tmp_path)
    with pytest.raises(studio.BusyError):
        fresh.restore_world({'snapshot': original['snapshot']})
    assert fresh.get_world(original['id']) == original


def test_saved_sessions_reject_symlink_tamper_oversize_and_keep_inputs_private(running, tmp_path):
    status, saved = request(running, 'POST', '/api/studio/worlds', {'package': choice_package(), 'seed': 1, 'world_id': 0})
    assert status == 201
    artifact = running.manager.output_dir / ('world-' + saved['id'] + '.json')
    raw = artifact.read_text()
    tampered = json.loads(raw)
    tampered['snapshot']['metrics']['points'] = 2
    artifact.write_text(json.dumps(tampered))
    assert request(running, 'GET', '/api/studio/worlds/' + saved['id'])[0] == 409
    artifact.unlink()
    private = tmp_path / 'operator-secret.txt'
    private.write_text('DO-NOT-EXPOSE-PRIVATE-TOKEN')
    artifact.symlink_to(private)
    status, body = request(running, 'GET', '/api/studio/worlds/' + saved['id'])
    assert status == 500 and 'PRIVATE' not in json.dumps(body)
    artifact.unlink()
    artifact.write_text('x' * (2 * 1024 * 1024 + 1))
    assert request(running, 'GET', '/api/studio/worlds/' + saved['id'])[0] == 409


def test_scenario_expansion_rejected_before_execution(tmp_path, monkeypatch):
    import decision_lab.web_jobs as jobs
    from decision_lab.studio_api import scenario_preflight
    huge = draft()
    # Valid bounded metadata can become huge when copied into every trace.
    for rule in huge['engine_input']['rules']:
        rule['probability_provenance']['source_refs'] = ['x' * 4000] * 8
    with pytest.raises(ValueError, match='budget'):
        scenario_preflight({'kind': 'scenario', 'draft': huge, 'worlds': 100})
    launch = json.loads((EXAMPLES / 'launch-explicit.v1.json').read_text())
    launch['scenario']['horizon_hours'] = 8760
    launch['scenario']['visit_interval_hours'] = 1
    current = {'schema_version': 'scenario-draft.v1', 'id': launch['id'], 'revision': 0,
               'event_description': launch['event_description'], 'fields': [], 'engine_input': launch}
    with jobs.JobManager(tmp_path) as manager:
        with pytest.raises(ValueError):
            manager.submit({'kind': 'scenario', 'draft': current, 'worlds': 100})
        assert not manager._jobs


@pytest.mark.parametrize('example_id', ['ticker', 'stress', 'launch', 'choice'])
def test_each_public_demo_runs_real_queue_result(running, example_id):
    from decision_lab.scenario_authoring import compile_draft, run_package
    _, boot = request(running, 'GET', '/api/studio')
    current = next(e['draft'] for e in boot['examples'] if e['id'] == example_id)
    status, submitted = request(running, 'POST', '/api/jobs', {'kind': 'scenario', 'draft': current, 'worlds': 2, 'seed': 42})
    assert status == 202
    running.manager._queue.join()
    job = running.manager.snapshot(submitted['job_id'])
    assert job['status'] == 'completed'
    assert job['result'] == run_package(compile_draft(current)['package'], worlds=2, seed=42)
    if example_id == 'choice':
        assert request(running, 'POST', '/api/jobs', {'kind': 'scenario', 'draft': current, 'seed': 10**9 + 1})[0] == 400


def test_concurrent_choices_commit_once_and_capacity_is_http_429(running, monkeypatch):
    import decision_lab.studio_api as studio
    status, world = request(running, 'POST', '/api/studio/worlds', {'package': choice_package(), 'seed': 1, 'world_id': 0})
    assert status == 201
    path = '/api/studio/worlds/' + world['id']
    barrier = threading.Barrier(3)
    results = []
    def choose(action):
        barrier.wait()
        results.append(request(running, 'POST', path + '/step', {'choice_id': 'build', 'action_id': action, 'expected_revision': 0}))
    threads = [threading.Thread(target=choose, args=(str(i),)) for i in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert sorted(status for status, _ in results) == [200, 409]
    _, saved = request(running, 'GET', path)
    assert saved['revision'] == 1 and len(saved['snapshot']['history']) == 1
    monkeypatch.setattr(studio, 'MAX_WORLDS', 1)
    assert request(running, 'POST', '/api/studio/restore', {'snapshot': world['snapshot']})[0] == 429
    assert request(running, 'GET', path)[0] == 200


def test_scenario_jobs_share_single_worker_and_queue_capacity(tmp_path, monkeypatch):
    from threading import Event
    import decision_lab.web_jobs as jobs
    started, release = Event(), Event()
    original = jobs.JobManager.execute_job
    def gated(self, job):
        started.set()
        assert release.wait(5)
        return original(self, job)
    monkeypatch.setattr(jobs.JobManager, 'execute_job', gated)
    manager = jobs.JobManager(tmp_path)
    try:
        manager.submit({'kind': 'scenario', 'draft': draft(), 'worlds': 1})
        assert started.wait(2)
        for _ in range(jobs.MAX_QUEUED):
            manager.submit({'kind': 'scenario', 'draft': draft(), 'worlds': 1})
        with pytest.raises(jobs.BusyError):
            manager.submit({'kind': 'scenario', 'draft': draft(), 'worlds': 1})
        assert sum(j['status'] == 'running' for j in manager._jobs.values()) == 1
    finally:
        release.set()
        manager.close()
    assert all(job['status'] == 'completed' for job in manager._jobs.values())
