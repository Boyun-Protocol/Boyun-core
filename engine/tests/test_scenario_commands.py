"""CLI consumes reviewed data and exports requests without contacting models."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import stat

from decision_lab.cli import main


def invoke(arguments):
    stdout, stderr = StringIO(), StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


def make_draft():
    package = json.loads((Path(__file__).parents[1] / 'examples/ticker-evaluation.v1.json').read_text())
    return {'schema_version': 'scenario-draft.v1', 'id': package['id'], 'revision': 0,
            'event_description': package['event_description'], 'fields': [], 'engine_input': package}


def test_scenario_validate_and_run_real_module_with_private_outputs(tmp_path):
    source = tmp_path/'draft.json'
    source.write_text(json.dumps(make_draft()))
    compiled, result = tmp_path/'compiled.json', tmp_path/'result.json'
    assert invoke(['scenario','validate','--input',str(source),'--output',str(compiled)])[0] == 0
    assert json.loads(compiled.read_text())['ready']
    assert invoke(['scenario','run','--input',str(source),'--worlds','3','--seed','4','--output',str(result)])[0] == 0
    report = json.loads(result.read_text())
    assert report['worlds'] == 3 and len(report['world_results']) == 3
    assert report['usage']['model_calls'] == 0
    assert len(report['input_sha256']) == 64
    assert stat.S_IMODE(result.stat().st_mode) == 0o600
    original = result.read_bytes()
    assert invoke(['scenario','run','--input',str(source),'--worlds','1','--output',str(result)])[0] == 2
    assert result.read_bytes() == original


def test_capabilities_guidelines_and_provider_neutral_prepare(tmp_path):
    source = tmp_path/'draft.json'
    source.write_text(json.dumps(make_draft()))
    for command in ['capabilities','guidelines']:
        target = tmp_path/(command+'.json')
        assert invoke(['scenario',command,'--output',str(target)])[0] == 0
        assert target.read_text()
    output = tmp_path/'request.json'
    assert invoke(['scenario','prepare','--input',str(source),'--model','my-own-agent','--output',str(output)])[0] == 0
    request = json.loads(output.read_text())
    assert request['model'] == 'my-own-agent' and request['usage']['model_calls'] == 0


def test_invalid_input_keeps_secret_out_of_errors_and_no_partial_output(tmp_path):
    source, output = tmp_path/'private-input.json',tmp_path/'result.json'
    source.write_text('{"PRIVATE-SCENARIO-SECRET":')
    code, stdout, stderr = invoke(['scenario','run','--input',str(source),'--output',str(output)])
    assert code == 2 and not output.exists()
    assert 'PRIVATE-SCENARIO' not in stdout+stderr


def test_missing_fields_emit_diagnostics_without_running(tmp_path):
    value = make_draft()
    value['engine_input'] = None
    source, output = tmp_path/'draft.json',tmp_path/'validation.json'
    source.write_text(json.dumps(value))
    assert invoke(['scenario','validate','--input',str(source),'--output',str(output)])[0] == 0
    validation = json.loads(output.read_text())
    assert not validation['ready'] and validation['package'] is None
    failed = tmp_path/'failed.json'
    assert invoke(['scenario','run','--input',str(source),'--output',str(failed)])[0] == 2
    assert not failed.exists()


def test_raw_package_can_execute_without_any_chat_process(tmp_path):
    package = make_draft()['engine_input']
    source, output = tmp_path/'package.json',tmp_path/'result.json'
    source.write_text(json.dumps(package))
    assert invoke(['scenario','run','--package',str(source),'--worlds','2','--output',str(output)])[0] == 0
    assert json.loads(output.read_text())['worlds'] == 2


def test_response_application_and_stale_protection(tmp_path):
    from decision_lab.scenario_authoring import draft_digest
    current = make_draft()
    revised = {**current,'revision':1}
    response = {'schema_version':'scenario-authoring-response.v1','base_revision':0,
                'base_sha256':draft_digest(current),'draft':revised}
    source, response_path, output = tmp_path/'draft.json', tmp_path/'response.json', tmp_path/'new.json'
    source.write_text(json.dumps(current)); response_path.write_text(json.dumps(response))
    assert invoke(['scenario','apply','--input',str(source),'--response',str(response_path),'--output',str(output)])[0] == 0
    assert json.loads(output.read_text())['revision'] == 1
    failed = tmp_path/'stale.json'
    assert invoke(['scenario','apply','--input',str(output),'--response',str(response_path),'--output',str(failed)])[0] == 2
    assert not failed.exists()
