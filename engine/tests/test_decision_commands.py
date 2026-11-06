import json
from decision_lab.cli import main
from test_decision_sessions import Planner


def test_cli_guided_workflow_without_manual_engine_json(tmp_path,monkeypatch,capsys):
    from decision_lab import decision_commands
    client=Planner(missing=True)
    monkeypatch.setattr(decision_commands,'_client',lambda args: client)
    path=tmp_path/'case'
    route=['--transport','agy','--model','fixture-model','--allow-model','--public-input']
    assert main(['decision','start','--question','Should I launch on NEAR with $10k?', '--session-dir',str(path)]+route)==0
    assert 'expenses' in capsys.readouterr().out
    assert main(['decision','run','--session-dir',str(path),'--review-hash','0'*64]+route)==2
    client.missing=False
    assert main(['decision','say','--session-dir',str(path),'--message','Use explicitly illustrative numbers.']+route)==0
    assert main(['decision','review','--session-dir',str(path),'--max-calls','7']+route)==0
    review=json.loads((path/'review.json').read_text())
    assert main(['decision','run','--session-dir',str(path),'--review-hash',review['review_sha256']]+route)==0
    assert main(['decision','report','--session-dir',str(path)])==0
    assert 'break' in capsys.readouterr().out.lower()
    assert main(['decision','status','--session-dir',str(path)])==0
    assert main(['decision','recover','--session-dir',str(path)])==0


def test_cli_explicit_access_and_file_input_before_side_effect(tmp_path):
    path=tmp_path/'case'
    assert main(['decision','start','--question','A case','--session-dir',str(path), '--transport','agy','--model','fixture-model'])==2
    assert not path.exists()


def test_cli_branches_a_completed_decision_then_compares_offline(tmp_path,monkeypatch):
    from decision_lab import decision_commands
    from test_decision_sessions import completed_parent
    parent,client,_=completed_parent(tmp_path)
    monkeypatch.setattr(decision_commands,'_client',lambda args: client)
    child=tmp_path/'alternative';out=tmp_path/'comparison'
    route=['--transport','agy','--model','fixture-model','--allow-model','--public-input']
    assert main(['decision','branch','--source-dir',str(parent),'--session-dir',str(child),'--message','Compare smaller LP.']+route)==0
    assert main(['decision','review','--session-dir',str(child),'--max-calls','6']+route)==0
    review=json.loads((child/'review.json').read_text())
    assert review['seed']==73
    assert main(['decision','run','--session-dir',str(child),'--review-hash',review['review_sha256']]+route)==0
    count=len(client.calls)
    assert main(['decision','compare','--session-dir',str(parent),'--against',str(child),'--output-dir',str(out)])==0
    assert (out/'comparison-report.md').is_file()
    comparison=json.loads((out/'comparison.json').read_text())
    assert comparison['rows'][1]['deltas']['actual_cash_profit_cents']==200000
    assert len(client.calls)==count
    assert all(f.stat().st_mode&0o777==0o600 for f in out.iterdir())
    assert main(['decision','compare','--session-dir',str(parent),'--against',str(child),'--output-dir',str(out)])==2
    assert main(['decision','compare','--session-dir',str(parent),'--against',str(parent),'--output-dir',str(tmp_path/'duplicate')])==2
