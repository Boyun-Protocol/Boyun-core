"""Use the official MCP client against the actual decision-lab stdio process."""
import asyncio
import json
import sys
import tempfile

import pytest

mcp = pytest.importorskip('mcp', reason='install the optional mcp extra for protocol integration tests')
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_official_stdio_client_discovers_and_executes_supplied_world(tmp_path, record_property):
    async def workflow():
        params = StdioServerParameters(command=sys.executable,
            args=['-m', 'decision_lab.cli', 'mcp', '--workspace', str(tmp_path/'private')])
        with tempfile.TemporaryFile(mode='w+') as errors:
            async with stdio_client(params, errlog=errors) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    record_property('mcp_protocol_version', initialized.protocolVersion)
                    print('Negotiated MCP protocol:', initialized.protocolVersion)
                    tools = {t.name: t for t in (await session.list_tools()).tools}
                    assert {'inspect_game', 'inspect_actor', 'validate_world', 'run_offline', 'get_run', 'export_markdown', 'read_artifact'} <= set(tools)
                    assert len(tools) == 11
                    assert tools['run_offline'].inputSchema['properties']['world']['type'] == 'object'
                    assert 'api_key' not in json.dumps([t.inputSchema for t in tools.values()])
                    resources = {str(r.uri) for r in (await session.list_resources()).resources}
                    assert {'decision-lab://guidelines', 'decision-lab://capabilities'} <= resources
                    prompts = {p.name for p in (await session.list_prompts()).prompts}
                    assert 'construct_world' in prompts
                    guideline = await session.read_resource('decision-lab://guidelines')
                    assert 'strategic-world.v2' in guideline.contents[0].text
                    assert 'assumption-outcome-evidence.v1' in guideline.contents[0].text
                    prompt = await session.get_prompt('construct_world', {'question': 'A hypothetical coordination problem'})
                    assert 'A hypothetical coordination problem' in prompt.messages[0].content.text
                    assert 'assumption-outcome-evidence.v1' in prompt.messages[0].content.text

                    async def call(name, args=None):
                        result = await session.call_tool(name, args or {})
                        assert not result.isError, result
                        return result.structuredContent

                    examples = (await call('list_examples'))['examples']
                    supplied = (await call('get_example', {'example_id': examples[0]['id']}))['world']
                    # This is caller data, not selection of a hardcoded execution fixture.
                    supplied.update(id='caller-supplied-mcp', title='Caller-supplied hypothetical world')
                    construction = await call('inspect_game', {'world': supplied})
                    assert construction['actor_count'] == len(supplied['actors'])
                    own = await call('inspect_actor', {'world': supplied, 'actor_id': supplied['actors'][0]['id']})
                    assert own['actor']['goal'] == supplied['actors'][0]['goal']
                    assert supplied['actors'][1]['information'] not in json.dumps(own)
                    assert supplied['actors'][1]['goal'] not in json.dumps(own)
                    validated = await call('validate_world', {'world': supplied})
                    assert validated['valid'] is True
                    bad = await session.call_tool('run_offline', {'world': supplied, 'question': 'x', 'worlds': 5})
                    assert bad.isError
                    bad = await session.call_tool('run_offline', {'world': supplied, 'question': 'x', 'worlds': True})
                    assert bad.isError, 'MCP must not coerce boolean world counts into one run'
                    started = await call('run_offline', {'world': supplied, 'question': 'Caller agent constructed world', 'worlds': 1, 'seed': 42})
                    run_id = started['run_id']
                    for _ in range(200):
                        state = await call('get_run', {'run_id': run_id})
                        if state['status'] != 'running':break
                        await asyncio.sleep(.01)
                    assert state['status'] == 'completed', state
                    assert state['replay_verified'] is True
                    assert state['accounting']['provider_calls'] == 0
                    parts = [];offset = 0
                    while True:
                        chunk = await call('read_artifact', {'run_id': run_id, 'artifact': 'results_json', 'offset': offset})
                        parts.append(chunk['text'])
                        if chunk['next_offset'] is None:break
                        offset = chunk['next_offset']
                    result = json.loads(''.join(parts))[0]
                    assert result['result']['world']['id'] == 'caller-supplied-mcp'
                    from decision_lab.strategic_worlds import replay_strategic_world
                    replay_strategic_world(result['result'])
                    audit_parts = []; offset = 0
                    while True:
                        chunk = await call('read_artifact', {'run_id': run_id, 'artifact': 'game_audit_json', 'offset': offset})
                        audit_parts.append(chunk['text'])
                        if chunk['next_offset'] is None: break
                        offset = chunk['next_offset']
                    audit = json.loads(''.join(audit_parts))
                    assert audit['schema_version'] == 'game-construction-audit.v1'
                    assert audit['representation']['actor_count'] == len(supplied['actors'])
                    export = await call('export_markdown', {'run_id': run_id})
                    assert export['bytes'] > 100
                    report = await call('read_artifact', {'run_id': run_id, 'artifact': 'report_markdown'})
                    assert '# Boyun report' in report['text']
                    for name, arguments in [('get_run', {'run_id': '../outside'}),
                        ('read_artifact', {'run_id': run_id, 'artifact': '../../outside'})]:
                        assert (await session.call_tool(name, arguments)).isError
            errors.seek(0)
            # Invalid tools may log errors on stderr. Stdout contamination would
            # make the actual protocol workflow above fail before this point.
            assert 'Traceback' not in errors.read()
        return run_id

    run_id = asyncio.run(asyncio.wait_for(workflow(), timeout=30))
    # No MCP process remains; persisted opaque IDs are usable by a new adapter.
    from decision_lab.mcp_adapter import MCPWorkspace
    with MCPWorkspace(tmp_path/'private') as restored:
        assert restored.get_run(run_id)['status'] == 'completed'
