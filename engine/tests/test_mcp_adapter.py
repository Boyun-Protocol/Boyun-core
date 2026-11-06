"""MCP boundary preserves the existing offline product execution contract."""
import json
import socket
import stat
import time

import pytest

from decision_lab.product_api import examples


def adapter_type():
    from decision_lab.mcp_adapter import MCPWorkspace
    return MCPWorkspace


def completed(adapter, run_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = adapter.get_run(run_id)
        if result['status'] not in ('ready', 'running'):
            assert result['status'] == 'completed', result
            return result
        time.sleep(.01)
    pytest.fail('bounded offline run did not complete')


def read_all(adapter, run_id, artifact):
    parts = []
    offset = 0
    while True:
        chunk = adapter.read_artifact(run_id, artifact, offset, 4096)
        parts.append(chunk['text'])
        if chunk['next_offset'] is None:
            return ''.join(parts)
        offset = chunk['next_offset']


def test_supplied_world_runs_without_network_and_restores_private_results(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('offline MCP attempted network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    root = tmp_path/'private'
    world = examples()[0]['world']
    with adapter_type()(root) as adapter:
        assert adapter.validate_world(world)['valid'] is True
        start = adapter.run_offline(world, 'Caller agent supplied this hypothetical world', 1, 42)
        run_id = start['run_id']
        result = completed(adapter, run_id)
        assert result['replay_verified'] is True
        assert result['accounting']['provider_calls'] == 0
        assert result['completed_worlds'] == 1
        values = json.loads(read_all(adapter, run_id, 'results_json'))
        assert values[0]['result']['world'] == world
        assert values[0]['result']['schema_version'] == 'strategic-world-result.v1'
        assert any(d['receipt']['local_decision'] for d in values[0]['decisions'])
        export = adapter.export_markdown(run_id)
        assert export['artifact'] == 'report_markdown'
        md = read_all(adapter, run_id, 'report_markdown')
        assert '# Boyun report' in md
        assert 'deterministic immediate own' in md.lower()
        assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in root.rglob('*') if p.is_file())
    with adapter_type()(root) as restored:
        assert restored.list_runs()['runs'][0]['run_id'] == run_id
        assert restored.get_run(run_id)['replay_verified'] is True
        assert read_all(restored, run_id, 'report_markdown') == md


@pytest.mark.parametrize('identifier', ['../outside', '/etc/passwd', 'run-abc', 'a'*31, 'A'*32, 'f'*32])
def test_opaque_ids_reject_paths_before_reading(tmp_path, identifier):
    with adapter_type()(tmp_path/'private') as adapter:
        with pytest.raises(ValueError, match='run'):
            adapter.get_run(identifier)


def test_workspace_rejects_public_directories_symlinks_and_concurrent_servers(tmp_path):
    public = tmp_path/'public';public.mkdir(mode=0o755)
    with pytest.raises(ValueError, match='private'):
        adapter_type()(public)
    link = tmp_path/'link';link.symlink_to(public, target_is_directory=True)
    with pytest.raises(ValueError, match='directory'):
        adapter_type()(link)
    with adapter_type()(tmp_path/'private'):
        with pytest.raises(ValueError, match='use'):
            adapter_type()(tmp_path/'private')


def test_invalid_world_and_bounds_create_no_run(tmp_path):
    with adapter_type()(tmp_path/'private') as adapter:
        world = examples()[0]['world']
        with pytest.raises(ValueError):adapter.run_offline(world, 'x', 5, 42)
        with pytest.raises(ValueError):adapter.run_offline(world, 'x', True, 42)
        with pytest.raises(ValueError):adapter.run_offline(world, 'x', 1, -1)
        with pytest.raises(ValueError):adapter.validate_world({'x': float('nan')})
        deep = {};value = deep
        for _ in range(40):value['x'] = {};value = value['x']
        with pytest.raises(ValueError):adapter.validate_world(deep)
        with pytest.raises(ValueError):adapter.validate_world({'x': 'x'*(513*1024)})
        assert adapter.list_runs() == {'runs': []}


def test_saved_run_symlink_and_tampered_replay_rejected_on_restore(tmp_path):
    root = tmp_path/'private'
    with adapter_type()(root) as adapter:
        run_id = adapter.run_offline(examples()[0]['world'], 'x', 1, 42)['run_id']
        completed(adapter, run_id)
    state_path = root/'runs'/run_id/'state.json'
    original = state_path.read_bytes()
    saved = json.loads(original)
    saved['results'][0]['result']['final_metrics'][next(iter(saved['results'][0]['result']['final_metrics']))] += 1
    state_path.write_text(json.dumps(saved))
    with adapter_type()(root) as restored:
        with pytest.raises(ValueError):restored.get_run(run_id)
    state_path.write_bytes(original)
    (root/'runs'/run_id/'outside').symlink_to(tmp_path)
    with adapter_type()(root) as restored:
        with pytest.raises(ValueError, match='artifact'):restored.get_run(run_id)


def test_close_stops_local_worker_and_releases_workspace(tmp_path):
    root = tmp_path/'private'
    with adapter_type()(root) as adapter:
        start = adapter.run_offline(examples()[0]['world'], 'x', 4, 42)
    with adapter_type()(root) as restored:
        assert restored.get_run(start['run_id'])['status'] in ('completed', 'failed')


def test_hundred_actor_world_stays_bounded_and_run_turn_cap_is_enforced(tmp_path):
    from test_strategic_scale import cast
    with adapter_type()(tmp_path/'private') as adapter:
        world = cast(100)
        start = adapter.run_offline(world, 'Explicit hypothetical sparse cast', 1, 42)
        state = completed(adapter, start['run_id'])
        assert state['accounting']['local_rule_turns'] == 200
        assert len(json.dumps(state)) < 16384
        chunk = adapter.read_artifact(start['run_id'], 'results_json', 0, 4096)
        assert len(chunk['text']) == 4096 and chunk['next_offset'] == 4096
        world = cast(100, rounds=3)
        with pytest.raises(ValueError):adapter.run_offline(world, 'x', 3, 42)
        assert len(adapter.list_runs()['runs']) == 1


def test_product_request_preflight_rejection_leaves_no_orphan_run(tmp_path):
    from decision_lab.strategic_worlds import validate_strategic_world
    world = examples()[0]['world']
    world['schema_version'] = 'strategic-world.v2'
    from copy import deepcopy
    world['rounds'] = 8
    world['description'] = 'd'*8000
    world['interactions'] = [{**deepcopy(world['interactions'][0]), 'id': 'rule-'+str(i),
        'description': 'r'*1600} for i in range(16)]
    for actor in world['actors']:
        actor['information'] = 'x'*1600
        for action in actor['actions'][1:]:
            action['message'] = 'm'*1200
    validate_strategic_world(world)  # Valid rules can exceed product request limits.
    with adapter_type()(tmp_path/'private') as adapter:
        with pytest.raises(ValueError):adapter.validate_world(world)
        with pytest.raises(ValueError):adapter.run_offline(world, 'x', 1, 42)
        assert adapter.list_runs() == {'runs': []}


def test_unmarked_or_foreign_runs_cannot_be_reported_as_offline(tmp_path):
    root = tmp_path/'private'
    with adapter_type()(root) as adapter:
        run_id = adapter.run_offline(examples()[0]['world'], 'x', 1, 42)['run_id']
        completed(adapter, run_id)
    (root/'runs'/run_id/'mcp-run.json').unlink()
    with adapter_type()(root) as restored:
        with pytest.raises(ValueError, match='MCP-owned'):
            restored.get_run(run_id)


def test_restored_summary_and_progress_are_derived_from_verified_results(tmp_path):
    root = tmp_path/'private'
    with adapter_type()(root) as adapter:
        run_id = adapter.run_offline(examples()[0]['world'], 'x', 1, 42)['run_id']
        original = completed(adapter, run_id)
    path = root/'runs'/run_id/'state.json'
    state = json.loads(path.read_bytes())
    state['summary'] = {'forged_summary': 'x'*(1024*1024)}
    state['progress'] = {'phase': 'forged', 'completed_calls': 'x'*(1024*1024)}
    path.write_text(json.dumps(state))
    with adapter_type()(root) as restored:
        result = restored.get_run(run_id)
        assert result['summary'] == original['summary']
        assert result['progress'] == original['progress']
        assert len(json.dumps(result)) < 32768


def test_restored_accounting_rejects_duplicate_decision_receipts(tmp_path):
    root = tmp_path/'private'
    with adapter_type()(root) as adapter:
        run_id = adapter.run_offline(examples()[0]['world'], 'x', 1, 42)['run_id']
        completed(adapter, run_id)
    path = root/'runs'/run_id/'state.json'
    state = json.loads(path.read_bytes())
    state['results'][0]['decisions'].append(state['results'][0]['decisions'][0])
    path.write_text(json.dumps(state))
    with adapter_type()(root) as restored:
        with pytest.raises(ValueError, match='decision'):
            restored.get_run(run_id)


def test_artifact_bounds_unknown_names_and_tampered_markdown(tmp_path):
    root = tmp_path/'private'
    with adapter_type()(root) as adapter:
        run_id = adapter.run_offline(examples()[0]['world'], 'x', 1, 42)['run_id']
        completed(adapter, run_id)
        for artifact, offset, limit in [('../x', 0, 1), ('results_json', -1, 1), ('results_json', 0, 4097)]:
            with pytest.raises(ValueError):adapter.read_artifact(run_id, artifact, offset, limit)
        adapter.export_markdown(run_id)
        report = next(root.rglob('mcp-report.md'))
        report.write_text('tampered')
        with pytest.raises(ValueError, match='artifact'):
            adapter.read_artifact(run_id, 'report_markdown', 0, 4096)


def test_base_cli_help_needs_no_optional_sdk(tmp_path):
    import subprocess
    import sys
    script = """import sys
class NoMCP:
 def find_spec(self, fullname, path=None, target=None):
  if fullname == 'mcp' or fullname.startswith('mcp.'):
   raise ImportError('optional SDK unavailable')
sys.meta_path.insert(0, NoMCP())
from decision_lab.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    help_result = subprocess.run([sys.executable, '-c', script, '--help'], capture_output=True, text=True)
    assert help_result.returncode == 0
    assert 'mcp' in help_result.stdout
    result = subprocess.run([sys.executable, '-c', script, 'mcp', '--workspace', str(tmp_path/'private')], capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'extra' in result.stderr.lower()
