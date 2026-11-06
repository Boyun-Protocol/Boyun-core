import json

import pytest

from decision_lab.campaign_evidence import campaign_evidence_context, campaign_evidence_targets
from decision_lab.campaign_orchestration import run_campaign_experiment, replay_campaign_experiment
from test_campaign_worlds import package, evidence
from test_jev import Transport, client


def test_campaign_inventory_covers_numbers_behaviors_probabilities_and_outcomes():
    value = campaign_evidence_targets(campaign_evidence_context(package()))
    assert value['/package/campaigns/0/delivery_bps'] == 'probability'
    assert value['/package/actors/0/goal'] == 'input'
    assert value['/package/market/cash_cents'] == 'input'
    assert value['outcome:controlled_cash'] == 'outcome'
    assert value['probability:actor_choices'] == 'probability'
    assert value['/package/signals/0/recipients/0'] == 'input'


def test_missing_or_invalid_evidence_blocks_before_calls_or_output_creation(tmp_path):
    transport = Transport()
    for index, register in enumerate((None, {**evidence(package()), 'target_sha256': '0' * 64})):
        destination = tmp_path / str(index)
        with pytest.raises(ValueError, match='evidence'):
            run_campaign_experiment(package=package(), client=client(transport), worlds=1,
                                    max_calls=12, output_dir=destination, evidence_register=register)
        assert not destination.exists() and not transport.calls


def test_saved_audit_is_rechecked_and_evidence_tampering_breaks_replay(tmp_path):
    root = tmp_path / 'run'
    result = run_campaign_experiment(package=package(), client=client(Transport()), worlds=1,
                                    max_calls=12, output_dir=root, evidence_register=evidence(package()))
    assert result['evidence_audit']['status'] == 'ready_for_conditional_simulation'
    assert replay_campaign_experiment(root)['verified_worlds'] == 1
    saved = json.loads((root / 'evidence-register.json').read_text())
    saved['claims'][0]['rationale'] += ' Changed after dispatch.'
    (root / 'evidence-register.json').write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='evidence'):
        replay_campaign_experiment(root)


def test_offline_plan_discloses_missing_review_and_run_never_reads_a_key(tmp_path, capsys, monkeypatch):
    from decision_lab.cli import main
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(package()))
    base = ['campaign', 'plan', '--input', str(source), '--worlds', '1', '--max-calls', '12']
    assert main(base) == 0
    assert json.loads(capsys.readouterr().out)['execution_ready'] is False
    calls = []
    monkeypatch.setattr('decision_lab.jev_commands.typesafe_actor_client', lambda args: calls.append(args))
    base[1] = 'run'
    assert main(base + ['--output-dir', str(tmp_path / 'run'), '--env-file', '/missing']) == 2
    assert not calls
    assert 'evidence' in capsys.readouterr().out.lower()


def test_legacy_manifests_can_still_be_replayed_without_claiming_an_audit(tmp_path):
    root = tmp_path / 'old'
    run_campaign_experiment(package=package(), client=client(Transport()), worlds=1,
                            max_calls=12, output_dir=root, evidence_register=evidence(package()))
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.pop('evidence_audit')
    manifest_path.write_text(json.dumps(manifest))
    assert replay_campaign_experiment(root)['verified_worlds'] == 1


@pytest.mark.parametrize('sample_actions', [False, True])
def test_stress_and_legacy_policy_flags_remain_bound_on_replay(tmp_path, sample_actions):
    from decision_lab.campaign_stress import stress_config
    root = tmp_path / 'policy'
    stress = stress_config()
    run_campaign_experiment(package=package(), client=client(Transport()), worlds=1,
                            max_calls=12, output_dir=root, stress=stress, sample_actions=sample_actions,
                            evidence_register=evidence(package(), stress=stress, sample_actions=sample_actions))
    assert replay_campaign_experiment(root)['verified_worlds'] == 1


def test_campaign_cutoff_cannot_be_moved_after_launch(tmp_path):
    value = evidence(package())
    value['as_of'] = '2026-11-02T09:00:00Z'
    transport = Transport()
    with pytest.raises(ValueError, match='cutoff'):
        run_campaign_experiment(package=package(), client=client(transport), worlds=1, max_calls=12,
                                output_dir=tmp_path / 'late', evidence_register=value)
    assert not transport.calls and not (tmp_path / 'late').exists()
