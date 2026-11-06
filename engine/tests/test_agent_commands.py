import json
from pathlib import Path
from decision_lab.cli import main
from decision_lab.agent_worlds import AgentWorld
from test_agent_worlds import spec,proposal


def test_agents_replay_cli_is_private_and_offline(tmp_path):
    engine=AgentWorld(spec());engine.advance([proposal(o)for o in engine.observations().values()])
    source=tmp_path/'source.json';source.write_text(json.dumps(engine.report()))
    out=tmp_path/'replayed.json'
    assert main(['agents','replay','--input',str(source),'--output',str(out)])==0
    assert json.loads(out.read_text())==engine.report()and out.stat().st_mode&0o777==0o600
    assert main(['agents','replay','--input',str(source),'--output',str(out)])==2


def test_cli_live_requires_explicit_access_and_rejects_bad_budget(tmp_path):
    example=Path(__file__).parents[1]/'examples/agent-world-brief.public.json'
    out=tmp_path/'live'
    args=['agents','simulate','--brief',str(example),'--transport','agy','--model','gemini-3.8-flash-high','--public-input','--max-calls','6','--output-dir',str(out)]
    assert main(args)==2 and not out.exists()
    assert main(args+['--allow-model'])==2 and not out.exists()


def test_replay_reader_accepts_report_budget_above_scenario_input_cap(tmp_path):
    from decision_lab.agent_commands import _read_replay
    file=tmp_path/'large.json';file.write_text(json.dumps({'text':'x'*(2*1024*1024+1)}))
    assert len(_read_replay(file)['text'])>2*1024*1024
    file.write_text(' '* (8*1024*1024+1))
    import pytest
    with pytest.raises(ValueError):_read_replay(file)
