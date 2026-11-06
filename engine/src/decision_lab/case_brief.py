"""Case brief: the single input a report run needs, plus the interview record it came from.

A brief names the case, the artefacts the report reads, and the declared estimate parameters.
The interview extraction turns recorded answer files into an auditable Q&A table, so every
assumption in a document can be traced back to the answer that set it.
"""
from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from pathlib import Path

SCHEMA = 'case-brief.v1'
REQUIRED_ARTEFACTS = ('probabilities', 'cast', 'launch_cases', 'bootstrap', 'events')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')


def _error(path, reason):
    raise ValueError(f'{path}: {reason}')


def validate_brief(brief):
    """Return a complete validated brief; unknown fields are rejected rather than ignored."""
    if type(brief) is not dict:
        _error('$', 'brief object required')
    allowed = {'schema_version', 'id', 'question', 'labels', 'labels_public', 'artefacts',
               'estimate', 'sensitivity', 'interview_files'}
    unknown = set(brief) - allowed
    if unknown:
        _error('$', f'unknown fields: {", ".join(sorted(unknown))}')
    if brief.get('schema_version') != SCHEMA:
        _error('$.schema_version', f'{SCHEMA} required')
    case_id = brief.get('id')
    if type(case_id) is not str or not _ID.fullmatch(case_id):
        _error('$.id', 'bounded identifier required')
    question = brief.get('question')
    if type(question) is not str or not question.strip() or len(question) > 500:
        _error('$.question', 'bounded question text required')
    labels = brief.get('labels', {})
    if type(labels) is not dict:
        _error('$.labels', 'object required')
    for key in ('title', 'decision', 'currency_unit', 'venue'):
        if key in labels and (type(labels[key]) is not str or len(labels[key]) > 200):
            _error(f'$.labels.{key}', 'bounded text required')
    public = brief.get('labels_public', {})
    if type(public) is not dict:
        _error('$.labels_public', 'object required')
    for key in ('title', 'question', 'venue'):
        if key in public and (type(public[key]) is not str or not public[key].strip()
                              or len(public[key]) > 300):
            _error(f'$.labels_public.{key}', 'bounded text required')
    artefacts = brief.get('artefacts')
    if type(artefacts) is not dict:
        _error('$.artefacts', 'object required')
    for name in REQUIRED_ARTEFACTS:
        value = artefacts.get(name)
        if type(value) is not str or not value or value.startswith('/'):
            _error(f'$.artefacts.{name}', 'relative path required')
    estimate = brief.get('estimate', {})
    if type(estimate) is not dict:
        _error('$.estimate', 'object required')
    sensitivity = brief.get('sensitivity', {})
    if type(sensitivity) is not dict:
        _error('$.sensitivity', 'object required')
    files = brief.get('interview_files', [])
    if type(files) is not list or any(type(item) is not str for item in files):
        _error('$.interview_files', 'list of relative paths required')
    return deepcopy(brief)


def load_brief(case_dir):
    """Read and validate ``<case>/brief.json``."""
    path = Path(case_dir) / 'brief.json'
    if not path.exists():
        _error('$', f'{path} not found; every case needs a brief')
    return validate_brief(json.loads(path.read_text()))


def read_artefacts(case_dir, brief):
    """Load every artefact the brief names, keeping the paths in the returned map."""
    case = Path(case_dir)
    loaded = {}
    for name, relative in brief['artefacts'].items():
        path = case / relative
        if not path.exists():
            _error(f'$.artefacts.{name}', f'{relative} not found')
        loaded[name] = json.loads(path.read_text())
    return loaded


_ANSWER_KEYS = ('question_id', 'item', 'question')


def _answer_row(record, source):
    """Normalise one recorded answer across the shapes the interview files use."""
    if type(record) is not dict:
        return None
    answer = record.get('answer_as_received', record.get('answer'))
    if type(answer) is not str or not answer.strip():
        return None
    question = next((record[key] for key in _ANSWER_KEYS if type(record.get(key)) is str), None)
    meaning = record.get('meaning') or record.get('note') or ''
    return {'source': source, 'question': question or '', 'answer': answer.strip(),
            'status': record.get('status', ''), 'meaning': meaning}


def extract_interview(case_dir, files):
    """Turn recorded answer files into rows; files without answers contribute nothing."""
    rows = []
    for relative in files:
        path = Path(case_dir) / relative
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        records = payload.get('answers') if isinstance(payload, dict) else None
        if type(records) is not list:
            continue
        for record in records:
            row = _answer_row(record, relative)
            if row:
                rows.append(row)
    return rows


def write_interview(case_dir, files, destination):
    """Write the interview table as CSV next to the other data files."""
    rows = extract_interview(case_dir, files)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['question', 'answer', 'status', 'interpretation', 'source'])
        for row in rows:
            writer.writerow([row['question'], row['answer'], row['status'], row['meaning'],
                             row['source']])
    return rows


def describe_estimate(estimate):
    """Human-readable label for the parameters that shape the distribution."""
    parts = []
    if 'sol_usd' in estimate:
        parts.append(f"${estimate['sol_usd']}/SOL")
    if 'half_life_hours' in estimate:
        parts.append(f"{estimate['half_life_hours']}h decay")
    if 'worlds' in estimate:
        parts.append(f"{estimate['worlds']:,} worlds")
    return ', '.join(parts)
