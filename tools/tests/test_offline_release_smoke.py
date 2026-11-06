"""Release smoke must execute real rules/replay, never just import successfully."""
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / 'offline_release_smoke.py'


def invoke(tmp_path, *extra):
    return subprocess.run(
        [sys.executable, '-I', str(SCRIPT), '--output-dir', str(tmp_path / 'run'),
         '--format', 'md', *extra],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )


def test_public_smoke_executes_and_reopens_two_worlds_without_network(tmp_path):
    result = invoke(tmp_path)
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence['completed_worlds'] == 2
    assert evidence['local_decision_turns'] == 8
    assert evidence['provider_calls'] == 0
    assert evidence['replay_exact'] is True
    assert evidence['reopened_markdown_identical'] is True
    assert evidence['network_blocked'] is True
    assert (tmp_path / 'run' / 'scenario-report.md').is_file()
    assert not (tmp_path / 'run' / 'scenario-report.pdf').exists()


def test_smoke_refuses_checkout_import_when_installed_root_is_required(tmp_path):
    result = invoke(tmp_path, '--installed-root', str(tmp_path / 'fake-venv'))
    assert result.returncode != 0
    assert not (tmp_path / 'run').exists()


def test_smoke_never_overwrites_previous_artifacts(tmp_path):
    (tmp_path / 'run').mkdir()
    sentinel = tmp_path / 'run' / 'scenario-report.md'
    sentinel.write_text('keep my report')
    result = invoke(tmp_path)
    assert result.returncode != 0
    assert sentinel.read_text() == 'keep my report'
