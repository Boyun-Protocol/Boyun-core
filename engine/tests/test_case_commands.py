from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from decision_lab.case_commands import run_case_command
from test_case_report import fixture_case


def test_validate_reports_the_brief_without_rendering(tmp_path, capsys):
    case = fixture_case(tmp_path)
    args = SimpleNamespace(command='case', case_command='validate', case=str(case),
                           out=None, worlds=None)
    assert run_case_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['case'] == 'fixture-case'
    assert payload['rendered'] is False
    assert payload['artefacts'] == ['bootstrap', 'cast', 'events', 'launch_cases', 'probabilities']
    assert not (case / 'report').exists()


def test_build_renders_the_document_set(tmp_path, capsys):
    case = fixture_case(tmp_path)
    out = tmp_path / 'out'
    args = SimpleNamespace(command='case', case_command='build', case=str(case),
                           out=str(out), worlds=120)
    assert run_case_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['worlds'] == 120
    assert len(payload['documents']) == 5
    for name in payload['documents']:
        assert (out / name).exists(), name


def test_missing_brief_fails_closed(tmp_path, capsys):
    empty = tmp_path / 'empty'
    empty.mkdir()
    args = SimpleNamespace(command='case', case_command='validate', case=str(empty),
                           out=None, worlds=None)
    assert run_case_command(args) == 2
    message = capsys.readouterr().err
    assert 'needs a brief' in message
    assert list(empty.iterdir()) == []


def test_other_commands_are_ignored():
    assert run_case_command(SimpleNamespace(command='run')) is None


def test_build_rejects_a_broken_artefact_path(tmp_path, capsys):
    case = fixture_case(tmp_path)
    brief = json.loads((case / 'brief.json').read_text())
    brief['artefacts']['cast'] = 'missing/cast.json'
    (case / 'brief.json').write_text(json.dumps(brief))
    args = SimpleNamespace(command='case', case_command='build', case=str(case),
                           out=str(tmp_path / 'out'), worlds=50)
    assert run_case_command(args) == 2
    assert 'not found' in capsys.readouterr().err
