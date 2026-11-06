import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('resume_lifecycle', Path(__file__).parents[1] / 'resume_macron_lifecycle.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def receipt(root, index, tokens=None):
    directory = root / 'case' / 'pause-and-observe'
    directory.mkdir(parents=True, exist_ok=True)
    prefix = directory / f'call-{index:07d}'
    Path(str(prefix) + '.dispatch.json').write_text(json.dumps({'reservation_micro_usd': 120,
        'observation_sha256': 'own-view', 'actor': 'retail', 'second': 3600}))
    Path(str(prefix) + '.request.json').write_text(json.dumps({'state': {'actor': 'retail'}, 'questions': {}}))
    if tokens is not None:
        Path(str(prefix) + '.response.json').write_text(json.dumps({'answers': {'action': {}},
            'receipt': {'usage': {'input_tokens': tokens}}}))
    return directory


def test_restore_counts_cost_once_preserves_unknown_reservation_and_skips_it(tmp_path):
    directory = receipt(tmp_path, 1, 1000)
    receipt(tmp_path, 2)
    guard, caches, blocked, ledger = module.restore_receipts(tmp_path, 31)
    assert guard.spent_micro_usd == 42
    assert guard.reserved_micro_usd == 120
    assert guard.attempted_calls == 2 and guard.completed_calls == 1
    assert directory in blocked
    assert len(caches['case']) == 1
    assert ledger['unknown_dispatches'] == 1
    assert guard.reserve({})['call_index'] == 3


def test_duplicate_global_call_id_is_rejected_before_any_new_dispatch(tmp_path):
    receipt(tmp_path, 1, 1000)
    other = tmp_path / 'other' / 'staged-exit'
    other.mkdir(parents=True)
    (other / 'call-0000001.dispatch.json').write_text('{}')
    with pytest.raises(ValueError, match='duplicate'):
        module.restore_receipts(tmp_path, 31)


def test_receipts_already_over_authorization_block_resume(tmp_path):
    receipt(tmp_path, 1, 50000000)
    with pytest.raises(ValueError, match='budget'):
        module.restore_receipts(tmp_path, 31)


def test_existing_artifacts_preserve_prior_files_and_replace_manifest(tmp_path):
    (tmp_path / 'manifest.json').write_text('{"old":true}')
    store = module.ExistingArtifacts(tmp_path)
    store.replace('manifest.json', {'recovered': True})
    assert json.loads((tmp_path / 'manifest.json').read_text()) == {'recovered': True}
    with pytest.raises(FileExistsError):
        store.new('manifest.json', {})
