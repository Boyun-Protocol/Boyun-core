import json
from pathlib import Path
from test_agent_worlds import spec
from test_jev import Transport


def test_offline_jev_prepare_no_key_or_model_request(tmp_path):
    from decision_lab.cli import main
    source=tmp_path/'world.json';source.write_text(json.dumps(spec()));out=tmp_path/'prepared'
    assert main(['jev','prepare','--world',str(source),'--output-dir',str(out)])==0
    plan=json.loads((out/'plan.json').read_text())
    assert plan['actor_count']==3 and plan['required_calls']==6
    assert plan['model_requests']==0
    assert (out/'whale.request.json').stat().st_mode&0o777==0o600
    assert main(['jev','prepare','--world',str(source),'--output-dir',str(out)])==2


def test_jev_world_route_runs_real_engine_with_injected_http_only(tmp_path,monkeypatch):
    from decision_lab.cli import main
    import decision_lab.jev as jev
    transport=Transport(choice='buy_10000bps')
    monkeypatch.setattr(jev,'_urllib_transport',transport)
    monkeypatch.setenv('TYPESAFE_TEST_KEY','unit-test-key')
    source=tmp_path/'world.json';source.write_text(json.dumps(spec()));out=tmp_path/'run'
    args=['agents','simulate','--world',str(source),'--output-dir',str(out),'--transport','typesafe','--endpoint','https://api.typesafe.ai/v1/systemone','--api-key-env','TYPESAFE_TEST_KEY','--model','jev-1.14.0','--max-calls','6','--allow-model']
    assert main(args)==0
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['completed_calls']==6 and len(transport.calls)==6
    assert json.loads((out/'result.json').read_text())['status']=='completed'


def test_jev_refuses_builder_before_dispatch_and_missing_key_is_safe(tmp_path,monkeypatch,capsys):
    from decision_lab.cli import main
    import decision_lab.jev as jev
    transport=Transport();monkeypatch.setattr(jev,'_urllib_transport',transport)
    monkeypatch.setenv('TYPESAFE_TEST_KEY','unit-test-key')
    source=Path(__file__).parents[1]/'examples/agent-world-brief.public.json'
    args=['agents','simulate','--brief',str(source),'--output-dir',str(tmp_path/'bad'),'--transport','typesafe','--endpoint','https://api.typesafe.ai/v1/systemone','--api-key-env','TYPESAFE_TEST_KEY','--model','jev-1.14.0','--max-calls','7','--allow-model']
    assert main(args)==2 and not transport.calls and not (tmp_path/'bad').exists()
    monkeypatch.delenv('TYPESAFE_TEST_KEY')
    assert main(args)==2
    assert 'unit-test-key'not in capsys.readouterr().err


def test_jev_can_run_both_social_experiment_arms_with_injected_primitive_replies(tmp_path,monkeypatch):
    from decision_lab.cli import main
    import decision_lab.jev as jev
    transport=Transport();monkeypatch.setattr(jev,'_urllib_transport',transport)
    monkeypatch.setenv('TYPESAFE_TEST_KEY','fixture-key')
    protocol={'schema_version':'social-experiment.v1','id':'jev-peer-check','baseline_world':spec(),
        'treatment':{'remove_subscriptions':[{'listener':'retail','source':'analyst'}]},'seeds':[42]}
    source=tmp_path/'protocol.json';source.write_text(json.dumps(protocol));out=tmp_path/'run'
    args=['social','run','--input',str(source),'--output-dir',str(out),'--max-calls','12','--transport','typesafe',
        '--endpoint','https://api.typesafe.ai/v1/systemone','--api-key-env','TYPESAFE_TEST_KEY','--model','jev-1.14.0','--allow-model']
    assert main(args)==0 and len(transport.calls)==12
    analysis=json.loads((out/'analysis.json').read_text())
    assert analysis['completed_pairs']==1



def test_explicit_env_file_uses_typesafe_key_and_private_engine_artifacts(tmp_path,monkeypatch):
    from decision_lab.cli import main
    import decision_lab.jev as jev
    wire=Transport();monkeypatch.setattr(jev,'_urllib_transport',wire)
    env=tmp_path/'selected.env';env.write_text('UNRELATED=ignored\nTYPESAFE_API_KEY=fixture-only-key\n')
    source=tmp_path/'world.json';source.write_text(json.dumps(spec()));out=tmp_path/'run'
    args=['agents','simulate','--world',str(source),'--output-dir',str(out),'--transport','typesafe',
          '--env-file',str(env),'--model','jev-latest','--max-calls','6','--allow-model']
    assert main(args)==0
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['completed_calls']==6 and len(wire.calls)==6
    assert manifest['calls'][0]['receipt']['model_reported']=='jev-1.14.0'
    assert all('fixture-only-key' not in path.read_text() for path in out.glob('*.json'))
    assert all(path.stat().st_mode&0o777==0o600 for path in out.glob('*.json'))


def test_selected_file_missing_key_has_no_process_fallback(tmp_path,monkeypatch):
    import pytest
    from types import SimpleNamespace
    from decision_lab.jev_commands import typesafe_actor_client
    monkeypatch.setenv('TYPESAFE_API_KEY','process-key-must-not-be-used')
    env=tmp_path/'selected.env';env.write_text('UNRELATED=ignored\n')
    args=SimpleNamespace(allow_model=True,endpoint=None,api_key_env=None,env_file=env,
                         model='jev-latest',timeout=30,http_client='urllib')
    with pytest.raises(ValueError):typesafe_actor_client(args)


def test_process_key_requires_explicit_name_even_when_default_variable_exists(monkeypatch):
    import pytest
    from types import SimpleNamespace
    from decision_lab.jev_commands import typesafe_actor_client
    monkeypatch.setenv('TYPESAFE_API_KEY','process-key-must-be-selected')
    args=SimpleNamespace(allow_model=True,endpoint=None,api_key_env=None,env_file=None,
                         model='jev-latest',timeout=30,http_client='urllib')
    with pytest.raises(ValueError):typesafe_actor_client(args)
    args.api_key_env='TYPESAFE_API_KEY'
    assert typesafe_actor_client(args).protocol=='typesafe-systemone'


def test_selected_file_name_and_explicit_curl_are_honored(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from decision_lab.jev_commands import typesafe_actor_client
    from decision_lab import typesafe_curl
    wire=Transport();monkeypatch.setattr(typesafe_curl,'curl_transport',wire)
    env=tmp_path/'selected.env';env.write_text('CUSTOM_NATIVE_KEY=file-key\nTYPESAFE_API_KEY=wrong-key\n')
    monkeypatch.setenv('CUSTOM_NATIVE_KEY','wrong-process-key')
    args=SimpleNamespace(allow_model=True,endpoint=None,api_key_env='CUSTOM_NATIVE_KEY',env_file=env,
                         model='jev-latest',timeout=30,http_client='curl')
    client=typesafe_actor_client(args)
    client.client.evaluate(state='fixture',questions={'check':{'type':'noul','instructions':'Check?'}})
    assert wire.calls[0]['headers']['Authorization']=='Bearer file-key'
    assert wire.calls[0]['endpoint']=='https://api.typesafe.ai/v1/systemone'


def test_cli_http_failure_is_single_attempt_and_persists_no_raw_diagnostics(tmp_path,monkeypatch,capsys):
    from decision_lab.cli import main
    from urllib.error import HTTPError
    import decision_lab.jev as jev
    calls=[]
    def forbidden(**kwargs):
        calls.append(kwargs)
        raise HTTPError(jev.ENDPOINT,401,'PRIVATE raw diagnostics',{},None)
    monkeypatch.setattr(jev,'_urllib_transport',forbidden)
    monkeypatch.setenv('TYPESAFE_TEST_KEY','fixture-only-key')
    source=tmp_path/'world.json';source.write_text(json.dumps(spec()));out=tmp_path/'failed'
    args=['agents','simulate','--world',str(source),'--output-dir',str(out),'--transport','typesafe',
          '--api-key-env','TYPESAFE_TEST_KEY','--model','jev-latest','--max-calls','6','--allow-model']
    assert main(args)==2 and len(calls)==1
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['attempted_calls']==1 and manifest['error']['code']=='typesafe_http_401'
    for path in out.glob('*.json'):
        assert 'fixture-only-key' not in path.read_text() and 'PRIVATE' not in path.read_text()
    captured=capsys.readouterr()
    assert 'fixture-only-key' not in captured.out+captured.err and 'PRIVATE' not in captured.out+captured.err
