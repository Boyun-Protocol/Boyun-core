"""CLI snapshots are explicit data; restore verifies their realized history."""
import json
from pathlib import Path
import stat

from decision_lab.cli import main


def test_choice_cli_start_step_validate_fork_and_private_files(tmp_path):
    package = Path(__file__).parents[1]/'examples/choice-world.v1.json'
    start,step,replay,fork,options = [tmp_path/(name+'.json') for name in ['start','step','replay','fork','options']]
    assert main(['world','start','--input',str(package),'--seed','42','--output',str(start)]) == 0
    initial = json.loads(start.read_text())
    assert main(['world','options','--input',str(start),'--output',str(options)]) == 0
    eligible = next(row for row in json.loads(options.read_text()) if row['eligible'])
    assert main(['world','step','--input',str(start),'--choice-id',eligible['id'],'--action-id','demo-1','--output',str(step)]) == 0
    changed = json.loads(step.read_text())
    assert len(changed['history']) == 1 and len(initial['history']) == 0
    assert main(['world','validate','--input',str(step),'--output',str(replay)]) == 0
    assert json.loads(replay.read_text()) == changed
    assert main(['world','fork','--input',str(step),'--branch-id','comparison','--output',str(fork)]) == 0
    assert json.loads(fork.read_text())['branch_id'] == 'comparison'
    assert json.loads(fork.read_text())['metrics'] == changed['metrics']
    assert stat.S_IMODE(step.stat().st_mode) == 0o600
    before = start.read_bytes()
    assert main(['world','start','--input',str(package),'--output',str(start)]) == 2
    assert start.read_bytes() == before


def test_tampered_world_cannot_resume_and_leaves_no_output(tmp_path,capsys):
    from decision_lab.choice_worlds import start_choice_world
    package = json.loads((Path(__file__).parents[1]/'examples/choice-world.v1.json').read_text())
    value = start_choice_world(package)
    value['metrics'][next(iter(value['metrics']))] += 1
    source,target = tmp_path/'tampered.json',tmp_path/'output.json'
    source.write_text(json.dumps(value))
    assert main(['world','validate','--input',str(source),'--output',str(target)]) == 2
    assert not target.exists()
