"""Offline strategic mechanics uses private no-overwrite output artifacts."""
import argparse
import json
import stat

from decision_lab.strategic_commands import register_strategic_commands, run_strategic_command
from test_strategic_games import game


def parser():
    result = argparse.ArgumentParser()
    register_strategic_commands(result.add_subparsers(dest='command', required=True))
    return result


def test_actual_parse_run_private_output_and_no_overwrite(tmp_path):
    source, output = tmp_path/'game.json', tmp_path/'analysis.json'
    source.write_text(json.dumps(game()))
    args = parser().parse_args(['mechanics', 'game', '--input', str(source), '--output', str(output)])
    assert run_strategic_command(args) == 0
    analysis = json.loads(output.read_text())
    assert analysis['schema_version'] == 'finite-game-analysis.v1'
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    before = output.read_bytes()
    assert run_strategic_command(args) == 2
    assert output.read_bytes() == before


def test_invalid_json_or_game_removes_reserved_output(tmp_path, capsys):
    source, output = tmp_path/'game.json', tmp_path/'analysis.json'
    args = parser().parse_args(['mechanics', 'game', '--input', str(source), '--output', str(output)])
    for raw in ('{"schema_version":"finite-game.v1"}', '{', '{"x":1,"x":2}', '{"x":NaN}'):
        source.write_text(raw)
        assert run_strategic_command(args) == 2
        assert not output.exists()
    assert 'No provider' in capsys.readouterr().err


def test_other_command_not_handled():
    assert run_strategic_command(argparse.Namespace(command='other')) is None


def test_bayes_command_private_exact_posterior_and_no_overwrite(tmp_path):
    from test_probability_updates import belief
    source, output = tmp_path/'belief.json', tmp_path/'posterior.json'
    source.write_text(json.dumps(belief()))
    args = parser().parse_args(['mechanics', 'bayes', '--input', str(source), '--output', str(output)])
    assert run_strategic_command(args) == 0
    value = json.loads(output.read_text())
    assert value['posterior']['fair'] == {'numerator': 1, 'denominator': 5}
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    before = output.read_bytes()
    assert run_strategic_command(args) == 2
    assert output.read_bytes() == before


def test_impossible_bayes_evidence_has_no_partial_output(tmp_path):
    from test_probability_updates import belief
    value = belief();value['evidence'][0]['likelihood_bps'] = {'fair': 0, 'heads-biased': 0}
    source, output = tmp_path/'belief.json', tmp_path/'posterior.json'
    source.write_text(json.dumps(value))
    args = parser().parse_args(['mechanics', 'bayes', '--input', str(source), '--output', str(output)])
    assert run_strategic_command(args) == 2
    assert not output.exists()
