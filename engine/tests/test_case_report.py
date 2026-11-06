from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from decision_lab.case_brief import (extract_interview, load_brief, validate_brief,
                                    write_interview)
from decision_lab.case_report import _table, money, render_case


def fixture_case(tmp_path):
    case = tmp_path / 'case'
    (case / 'plf-pilot').mkdir(parents=True)
    (case / 'world-grounding-2026-10-30').mkdir(parents=True)
    answers = {
        'large_buyer': {'probabilities': {'hold': .6, 'buy_small': .4}},
        'kol_a': {'probabilities': {'hold': .5, 'sell_half': .2, 'sell_all': .3}},
    }
    (case / 'plf-pilot' / 'jev-probabilities.json').write_text(json.dumps({
        'model': 'jev-latest', 'cap_usd': 1.0, 'spend_estimate_usd': 0.001,
        'label': 'provider decision probabilities', 'answers': answers,
        'calls': [{'actor': 'large_buyer', 'outcome': 'ok'},
                  {'actor': 'kol_a', 'outcome': 'ok'}]}))
    (case / 'world-grounding-2026-10-30' / 'cast-16.json').write_text(json.dumps({
        'actor_count': 2, 'role_counts': {'large_holder': 1, 'kol': 1},
        'actors': [{'label': 'Large buyer', 'role': 'large_holder',
                    'capital': {'mode': 'liquidity_multiple', 'low': 0.2, 'high': 4.0}},
                   {'label': 'Creator', 'role': 'kol',
                    'capital': {'mode': 'fee_and_supply', 'supply_share': 0.015}}]}))
    (case / 'world-grounding-2026-10-30' / 'launch-cases.json').write_text(json.dumps({
        'revision': 2, 'tier_rule': {'dead': 'turnover < 0.05'}}))
    (case / 'world-grounding-2026-10-30' / 'bootstrap-buy.json').write_text(json.dumps({
        'parameters': {'initial_virtual_sol_reserves': 30.0, 'fee_bps_assumed': 100.0},
        'base_case': {'share_of_supply_pct': 69.43}}))
    (case / 'world-grounding-2026-10-30' / 'real-world-events.json').write_text(json.dumps({
        'events': [{'id': 'e1', 'window_start': '2026-10-27', 'window_end': '2026-11-02',
                    'what': 'Finance bill examination', 'status': 'observed_calendar'}]}))
    (case / 'inputs').mkdir()
    (case / 'inputs' / 'round-one.json').write_text(json.dumps({'answers': [
        {'question_id': 'bootstrap', 'answer_as_received': '$5,000 as early buys',
         'status': 'confirmed', 'meaning': 'curve demand, not liquidity provision'}]}))
    (case / 'brief.json').write_text(json.dumps({
        'schema_version': 'case-brief.v1', 'id': 'fixture-case',
        'question': 'Should the fixture launch?',
        'labels': {'title': 'Fixture', 'venue': 'test venue'},
        'artefacts': {'probabilities': 'plf-pilot/jev-probabilities.json',
                      'cast': 'world-grounding-2026-10-30/cast-16.json',
                      'launch_cases': 'world-grounding-2026-10-30/launch-cases.json',
                      'bootstrap': 'world-grounding-2026-10-30/bootstrap-buy.json',
                      'events': 'world-grounding-2026-10-30/real-world-events.json'},
        'estimate': {'worlds': 150},
        'sensitivity': {'grid': {'sol_usd': [90, 200]}, 'worlds': 60},
        'interview_files': ['inputs/round-one.json']}))
    return case


def test_money_puts_the_sign_before_the_symbol():
    assert money(1234) == '$1,234'
    assert money(-1234) == '-$1,234'
    assert money(0) == '$0'


def test_table_shape():
    rendered = _table([['a', 1], ['b', 2]], ['name', 'n'])
    assert rendered.splitlines()[0] == '| name | n |'
    assert rendered.splitlines()[1] == '|---|---|'
    assert rendered.splitlines()[2] == '| a | 1 |'


def test_render_writes_every_document_and_figure(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    result = render_case(case, out, worlds=150)
    assert result['worlds'] == 150
    for name in ('00-DECISION.md', '01-MODEL.md', '02-SCENARIOS.md', '03-EVIDENCE.md',
                 '04-FORECAST.md', 'INDEX.md'):
        assert (out / name).exists(), name
    for name in ('fig-outcomes.svg', 'fig-net-cash.svg', 'fig-pipeline.svg', 'fig-sensitivity.svg'):
        assert (out / 'FIGURES' / name).exists(), name
    for name in ('inputs.json', 'outputs.json', 'assumptions.csv', 'scenarios.csv',
                 'cast.json', 'probabilities.json', 'sources.json', 'worlds.csv'):
        assert (out / 'DATA' / name).exists(), name


def test_documents_never_print_a_negative_with_the_symbol_first(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=150)
    for path in out.glob('*.md'):
        text = path.read_text()
        assert '$-' not in text, path.name
        assert 'None' not in text, path.name


def test_index_marks_every_document_ready(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=150)
    index = (out / 'INDEX.md').read_text()
    assert index.count('**ready**') >= 5
    assert 'pending' not in index


def test_outcome_figure_draws_one_dot_per_percent(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=150)
    svg = (out / 'FIGURES' / 'fig-outcomes.svg').read_text()
    assert len(re.findall(r'r="8"', svg)) == 100
    assert 'outcome of 100' in svg.lower()


def test_figures_stay_inside_their_canvas(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=150)
    for path in (out / 'FIGURES').glob('*.svg'):
        svg = path.read_text()
        width, height = map(int, re.search(r'viewBox="0 0 (\d+) (\d+)"', svg).groups())
        for x, y, r in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', svg):
            assert float(x) - float(r) >= 0 and float(x) + float(r) <= width, path.name
            assert float(y) + float(r) <= height, path.name
        for x, y, w, h in re.findall(
                r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', svg):
            assert float(x) + float(w) <= width + 0.5, path.name
            assert float(y) + float(h) <= height + 0.5, path.name


def test_report_states_the_no_launch_baseline(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=150)
    decision = (out / '00-DECISION.md').read_text()
    assert 'Do nothing' in decision
    assert 'of every 100' in decision


def test_missing_outcome_class_does_not_crash(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=120)
    outputs = json.loads((out / 'DATA' / 'outputs.json').read_text())
    assert 'whale outside money' not in outputs['by_bucket']
    assert (out / '00-DECISION.md').exists()


def test_forecast_record_has_resolution_criteria(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=150)
    forecast = (out / '04-FORECAST.md').read_text()
    assert 'Resolution' in forecast
    assert 'pending' in forecast.lower()
    assert 'Brier' in forecast


def test_brief_is_required_and_validated(tmp_path):
    case = fixture_case(tmp_path)
    brief = load_brief(case)
    assert brief['id'] == 'fixture-case'
    with pytest.raises(ValueError, match='unknown fields'):
        validate_brief({**brief, 'extra': 1})
    with pytest.raises(ValueError, match='case-brief.v1 required'):
        validate_brief({**brief, 'schema_version': 'case-brief.v2'})
    with pytest.raises(ValueError, match='relative path required'):
        validate_brief({**brief, 'artefacts': {**brief['artefacts'],
                                               'cast': '/absolute/cast.json'}})
    missing = tmp_path / 'no-brief'
    missing.mkdir()
    with pytest.raises(ValueError, match='every case needs a brief'):
        load_brief(missing)


def test_interview_extraction_handles_both_shapes(tmp_path):
    case = fixture_case(tmp_path)
    (case / 'inputs' / 'round-two.json').write_text(json.dumps({'answers': [
        {'item': 'decay', 'answer_as_received': '12h half-life', 'status': 'confirmed'},
        {'item': 'no answer', 'answer_as_received': '   '}]}))
    (case / 'inputs' / 'questions-only.json').write_text(json.dumps({'questions': [
        {'id': 'q1', 'question': 'pending?'}]}))
    rows = extract_interview(case, ['inputs/round-one.json', 'inputs/round-two.json',
                                    'inputs/questions-only.json', 'inputs/missing.json'])
    assert [row['answer'] for row in rows] == ['$5,000 as early buys', '12h half-life']
    assert rows[1]['question'] == 'decay'
    destination = tmp_path / 'interview.csv'
    written = write_interview(case, ['inputs/round-one.json'], destination)
    assert len(written) == 1
    assert destination.read_text().splitlines()[0].startswith('question,answer,status')


def test_brief_labels_reach_the_documents(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=120)
    decision = (out / '00-DECISION.md').read_text()
    assert decision.splitlines()[0].startswith('# Fixture')
    assert 'Should the fixture launch?' in (out / '04-FORECAST.md').read_text()
    assert (out / 'DATA' / 'interview.csv').exists()
    assert '$5,000 as early buys' in (out / '03-EVIDENCE.md').read_text()


def test_public_export_removes_identity_interview_and_raw_data(tmp_path):
    case = fixture_case(tmp_path)
    brief = json.loads((case / 'brief.json').read_text())
    brief['labels_public'] = {'title': 'An anonymous case',
                              'question': 'Should anyone launch anonymously?'}
    (case / 'brief.json').write_text(json.dumps(brief))
    out = tmp_path / 'public'
    render_case(case, out, worlds=120, public=True)
    assert not (out / 'DATA').exists()
    decision = (out / '00-DECISION.md').read_text()
    evidence = (out / '03-EVIDENCE.md').read_text()
    assert decision.splitlines()[0].startswith('# An anonymous case')
    assert 'Should anyone launch anonymously?' in (out / '04-FORECAST.md').read_text()
    assert 'Interview record' not in evidence
    assert 'Sources' not in evidence
    assert 'Public version' in evidence
    assert (out / 'report.html').exists()
    assert 'An anonymous case' in (out / 'report.html').read_text()


def test_private_export_keeps_the_evidence_trail(tmp_path):
    case = fixture_case(tmp_path)
    out = tmp_path / 'report'
    render_case(case, out, worlds=120)
    evidence = (out / '03-EVIDENCE.md').read_text()
    assert 'Interview record' in evidence
    assert 'Sources' in evidence
    assert (out / 'DATA' / 'interview.csv').exists()
    assert (out / 'report.html').exists()
