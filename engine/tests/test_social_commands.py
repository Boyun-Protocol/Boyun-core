"""Offline social planning and explicit model access CLI boundaries."""
import argparse
import json

from test_social_experiments import protocol,Role


def parser():
    from decision_lab.social_commands import register_social_commands
    p=argparse.ArgumentParser();register_social_commands(p.add_subparsers(dest='command',required=True));return p


def test_prepare_and_inspect_require_no_model_route_and_save_private_artifact(tmp_path,capsys):
    from decision_lab.social_commands import run_social_command
    source=tmp_path/'protocol.json';source.write_text(json.dumps(protocol()))
    output=tmp_path/'plan.json'
    assert run_social_command(parser().parse_args(['social','prepare','--input',str(source),'--output',str(output)]))==0
    assert json.loads(output.read_text())['required_calls']==16
    assert output.stat().st_mode&0o777==0o600
    assert run_social_command(parser().parse_args(['social','inspect','--input',str(source)]))==0
    assert '16'in capsys.readouterr().out
    assert run_social_command(parser().parse_args(['social','prepare','--input',str(source),'--output',str(output)]))==2


def test_run_requires_allow_model_before_provider_or_output(tmp_path):
    from decision_lab.social_commands import run_social_command
    source=tmp_path/'protocol.json';source.write_text(json.dumps(protocol()))
    out=tmp_path/'run'
    args=parser().parse_args(['social','run','--input',str(source),'--output-dir',str(out),
                             '--transport','agy','--model','unselected','--max-calls','16'])
    assert run_social_command(args)==2
    assert not out.exists()


def test_run_dispatches_fresh_roles_through_shared_explicit_client(tmp_path,monkeypatch):
    from decision_lab.social_commands import run_social_command
    from decision_lab import decision_commands
    source=tmp_path/'protocol.json';source.write_text(json.dumps(protocol()))
    out=tmp_path/'run';client=Role()
    monkeypatch.setattr(decision_commands,'_client',lambda args:client)
    args=parser().parse_args(['social','run','--input',str(source),'--output-dir',str(out),
                             '--transport','agy','--model','test-fixture','--allow-model','--public-input','--max-calls','16'])
    assert run_social_command(args)==0
    assert len(client.calls)==16
    assert json.loads((out/'analysis.json').read_text())['completed_pairs']==2
