"""Real engine execution and bounded local job state."""
import json
import stat
import time
from copy import deepcopy

import pytest

from decision_lab.simulation import default_scenario, load_pool, simulate


def wait(manager, job_id):
    for _ in range(500):
        job = manager.snapshot(job_id)
        if job['status'] in {'completed', 'failed', 'paused'}:
            return job
        time.sleep(.01)
    raise AssertionError('local job did not finish')


def test_real_run_checkpoint_resume_and_private_exact_bytes(tmp_path):
    from decision_lab.web_jobs import JobManager
    with JobManager(tmp_path) as manager:
        scenario = default_scenario()
        request = {'kind': 'run', 'scenario': scenario, 'worlds': 2, 'seed': 13}
        job = wait(manager, manager.submit(request)['job_id'])
        assert job['result'] == simulate(scenario, load_pool(), worlds=2, seed=13)
        assert json.loads(manager.result_bytes(job['job_id'])) == job['result']
        created = manager.commitment(job['job_id'])
        assert created['verified'] is True
        assert set(created) == {'public', 'verified'}
        assert 'salt' not in json.dumps(manager.snapshot(job['job_id']))
        from decision_lab.integrity import verify_commitment
        assert verify_commitment(manager.result_bytes(job['job_id']), created['public'], json.loads(manager.opening_bytes(job['job_id'])))
        action = manager.near_action(job['job_id'], {'network': 'testnet', 'signer_id': 'alice.testnet', 'contract_id': 'receipt.testnet'})
        assert action['status'] == 'unsigned_unverified'
        paused = wait(manager, manager.submit({**request, 'kind': 'checkpoint', 'batch_worlds': 1})['job_id'])
        assert paused['status'] == 'paused' and paused['result'] is None
        assert paused['completed_worlds'] == 1 and paused['target_worlds'] == 2
        resumed = wait(manager, manager.submit({'kind': 'resume', 'resume_job_id': paused['job_id']})['job_id'])
        assert resumed['result'] == job['result']
        with pytest.raises(ValueError):
            manager.submit({'kind': 'resume', 'resume_job_id': paused['job_id']})
    for artifact in tmp_path.iterdir():
        if artifact.is_file():
            assert stat.S_IMODE(artifact.stat().st_mode) == 0o600


def test_cast_evaluation_and_preflight_budget(tmp_path):
    from decision_lab.web_jobs import JobManager
    with JobManager(tmp_path) as manager:
        cast = wait(manager, manager.submit({'kind': 'cast'})['job_id'])['result']
        assert cast['selected_count'] == len(cast['actors'])
        actor = cast['actors'][0]
        assert {'allowed_actions', 'subscriptions', 'position_limit_cents', 'entry_fraction_bps', 'attention_capacity'} <= actor.keys()
        assert actor['provenance']['template']['description']
        evaluation = wait(manager, manager.submit({'kind': 'evaluate', 'dataset': manager.bootstrap()['evaluation_fixture']})['job_id'])['result']
        assert evaluation['counts']['holdout'] == 2
        assert evaluation['source_metadata']['status'] == 'synthetic_fixture_only'
        for bad in ({'worlds': 101}, {'worlds': True}, {'kind': 'plans', 'worlds': 51}, {'policy_id': '../secret'}, {'seed': -1}):
            with pytest.raises(ValueError):
                manager.submit({'kind': 'run', **bad})
        scenario = deepcopy(default_scenario())
        scenario['cast_recipe']['groups']['retail']['count'] = 1001
        with pytest.raises(ValueError):
            manager.submit({'kind': 'cast', 'scenario': scenario})
        scenario = deepcopy(default_scenario())
        scenario['visit_interval_hours'] = 1
        with pytest.raises(ValueError):
            manager.submit({'kind': 'run', 'scenario': scenario})


def test_actual_prepare_import_policy_comparison_and_sensitivity(tmp_path):
    from decision_lab.web_jobs import JobManager
    with JobManager(tmp_path) as manager:
        prepared = wait(manager, manager.submit({'kind': 'prepare', 'model': 'caller-declared-model', 'template_ids': ['retail-01']})['job_id'])['result']
        response = {'schema_version': 'policy-response.v1', 'request_sha256': prepared['request_sha256'], 'usage': None,
                    'output_text': json.dumps({'policies': [{'template_id': 'retail-01', 'entry_signal': 'none', 'entry_fraction_bps': 0,
                    'exit_on_contradiction': True, 'rationale': 'Synthetic fixture', 'assumptions': ['Unmeasured fixture assumption']}]})}
        imported = wait(manager, manager.submit({'kind': 'import', 'request': prepared, 'response': response, 'bundle_id': 'local-test'})['job_id'])['result']
        assert imported['receipt']['inference_calls_performed'] == 0
        policy_id = imported['policy_id']
        assert any(row['id'] == policy_id for row in manager.bootstrap()['policy_options'])
        comparison = wait(manager, manager.submit({'kind': 'policies', 'policy_id': policy_id, 'worlds': 1})['job_id'])['result']
        assert comparison['usage']['model_calls'] == 0 and len(comparison['paired']['worlds']) == 1
        plans = wait(manager, manager.submit({'kind': 'plans', 'worlds': 1})['job_id'])['result']
        assert len(plans['plans']) == 4
        sweep = wait(manager, manager.submit({'kind': 'sensitivity', 'parameter': 'fee_bps', 'values': [0, 30], 'worlds': 1})['job_id'])['result']
        assert [row['value'] for row in sweep['variants']] == [0, 30]


def test_queue_and_job_caps_and_no_duplicate_resume(tmp_path, monkeypatch):
    from threading import Event
    import decision_lab.web_jobs as jobs
    started, release = Event(), Event()
    original = jobs.JobManager.execute_job
    def gated(self, job):
        started.set()
        assert release.wait(5)
        return original(self, job)
    monkeypatch.setattr(jobs.JobManager, 'execute_job', gated)
    manager = jobs.JobManager(tmp_path)
    try:
        manager.submit({'kind': 'cast'})
        assert started.wait(2)
        for _ in range(jobs.MAX_QUEUED):
            manager.submit({'kind': 'cast'})
        with pytest.raises(jobs.BusyError):
            manager.submit({'kind': 'cast'})
    finally:
        release.set()
        manager.close()
    with jobs.JobManager(tmp_path / 'capped') as manager:
        monkeypatch.setattr(jobs, 'MAX_JOBS', 1)
        wait(manager, manager.submit({'kind': 'cast'})['job_id'])
        with pytest.raises(jobs.BusyError):
            manager.submit({'kind': 'cast'})


def test_invalid_import_is_rejected_before_embedded_cast_allocation(tmp_path, monkeypatch):
    import decision_lab.web_jobs as jobs
    with jobs.JobManager(tmp_path) as manager:
        scenario = default_scenario()
        scenario['cast_recipe']['groups']['retail']['count'] = 10**12
        with pytest.raises(ValueError):
            manager.submit({'kind': 'import', 'request': {'context': {'scenario': scenario}}, 'response': {}, 'bundle_id': 'untrusted'})
        assert not manager._jobs
        for request in ({'kind': 'run', 'checkpoint_path': '/tmp/private'}, {'kind': 'resume', 'resume_job_id': '../secret'},
                        {'kind': 'resume', 'resume_job_id': '0' * 32}, {'kind': 'run', 'scenario': None}):
            with pytest.raises(ValueError):
                manager.submit(request)


def test_optional_bundle_metadata_and_evidence_logs_remain_private(tmp_path):
    from pathlib import Path
    from decision_lab.web_jobs import JobManager
    policy = json.loads(Path(__file__).parents[1].joinpath('examples/policies.synthetic.json').read_text())
    bundle_path = tmp_path / 'selected.json'
    bundle_path.write_text(json.dumps(policy))
    evidence_path = tmp_path / 'operator-evidence.json'
    evidence_path.write_text('{"raw_stdout":"PRIVATE RAW KEY MUST NEVER APPEAR"}')
    with JobManager(tmp_path / 'reports', policy_bundle_path=bundle_path, policy_evidence_path=evidence_path) as manager:
        boot = manager.bootstrap()
        assert boot['policy_options'][1]['id'] == 'loaded-policy'
        assert boot['policy_options'][1]['label'] == 'Loaded manual policies'
        assert 'unverified' in boot['provenance']['pilot']
        assert 'authenticated' not in boot['provenance']['pilot']
        assert 'Gemini' not in boot['provenance']['pilot']
        assert 'PRIVATE RAW KEY' not in json.dumps(boot)
        assert str(tmp_path) not in json.dumps(boot)
        job = wait(manager, manager.submit({'kind': 'run', 'policy_id': 'loaded-policy', 'worlds': 1})['job_id'])
        assert job['result']['policy_version'] == 'policy-bundle.v1'


def test_worker_error_is_sanitized_and_worker_survives(tmp_path, monkeypatch):
    from decision_lab.web_jobs import JobManager
    with JobManager(tmp_path) as manager:
        original = manager.execute_job
        monkeypatch.setattr(manager, 'execute_job', lambda job: (_ for _ in ()).throw(ValueError('/private/secret token-do-not-return')))
        failed = wait(manager, manager.submit({'kind': 'cast'})['job_id'])
        assert failed['status'] == 'failed' and failed['result'] is None
        assert 'secret' not in json.dumps(failed) and 'token-do-not-return' not in json.dumps(failed)
        monkeypatch.setattr(manager, 'execute_job', original)
        assert wait(manager, manager.submit({'kind': 'cast'})['job_id'])['status'] == 'completed'


def test_loaded_other_model_never_attests_gemini_cli_generation(tmp_path):
    from pathlib import Path
    from decision_lab.web_jobs import JobManager
    policy = json.loads(Path(__file__).parents[1].joinpath('examples/policies.synthetic.json').read_text())
    policy['source'] = {'kind': 'model_proposal', 'model': 'declared-other-model', 'prompt_sha256': 'a' * 64}
    bundle_path = tmp_path / 'selected.json'
    bundle_path.write_text(json.dumps(policy))
    with JobManager(tmp_path / 'reports', policy_bundle_path=bundle_path) as manager:
        boot = manager.bootstrap()
        assert boot['policy_options'][1]['label'] == 'Loaded policies · declared-other-model'
        assert 'declared-other-model' in boot['provenance']['pilot']
        assert 'unverified' in boot['provenance']['pilot']
        assert 'Gemini' not in json.dumps(boot['provenance'])
        assert 'authenticated' not in json.dumps(boot['provenance'])
    with JobManager(tmp_path / 'empty') as manager:
        assert manager.bootstrap()['provenance']['pilot'] == 'No imported policy loaded.'


@pytest.mark.parametrize('mutate', [
    lambda group: group.update(subscription_choices=[['x' * 250000]]),
    lambda group: group.update(subscription_choices=[['news'] * 9]),
    lambda group: group.update(subscription_choices=[['news']] * 17),
    lambda group: group.update(strategy_choices=['cautious'] * 9),
])
def test_recipe_expansion_limits_precede_actor_allocation(tmp_path, monkeypatch, mutate):
    import decision_lab.web_jobs as jobs
    with jobs.JobManager(tmp_path) as manager:
        scenario = default_scenario()
        scenario['horizon_hours'] = 1
        scenario['cast_recipe']['groups']['retail']['count'] = 900
        mutate(scenario['cast_recipe']['groups']['retail'])
        def forbidden(*args, **kwargs):
            raise AssertionError('unbounded recipe reached actor allocation')
        monkeypatch.setattr(jobs, 'build_cast', forbidden)
        with pytest.raises(ValueError):
            manager._prepare({'kind': 'cast', 'scenario': scenario})
        with pytest.raises(ValueError):
            manager._prepare({'kind': 'import', 'request': {'context': {'scenario': scenario}}, 'response': {}, 'bundle_id': 'bad'})


def test_policy_replication_budget_rejects_before_execution(tmp_path):
    from pathlib import Path
    from decision_lab.web_jobs import JobManager
    policy = json.loads(Path(__file__).parents[1].joinpath('examples/policies.synthetic.json').read_text())
    for rule in policy['policies']:
        rule['rationale'] = 'x' * 240000
        rule['assumptions'] = ['y' * 240000]
    selected = tmp_path / 'large.json'
    selected.write_text(json.dumps(policy))
    with JobManager(tmp_path / 'reports', policy_bundle_path=selected) as manager:
        with pytest.raises(ValueError):
            manager._prepare({'kind': 'plans', 'policy_id': 'loaded-policy', 'worlds': 1})
        scenario = default_scenario()
        scenario['horizon_hours'] = 1
        scenario['cast_recipe']['groups']['retail']['count'] = 900
        with pytest.raises(ValueError):
            manager._prepare({'kind': 'cast', 'scenario': scenario, 'policy_id': 'loaded-policy'})
        assert not manager._jobs


def test_cast_selected_effective_policy_and_funding_are_actual(tmp_path):
    from pathlib import Path
    from decision_lab.policy_bundles import compile_bundle
    from decision_lab.simulation import _policy_bindings
    from decision_lab.actors import build_cast
    from decision_lab.web_jobs import JobManager
    policy = json.loads(Path(__file__).parents[1].joinpath('examples/policies.synthetic.json').read_text())
    # Force a rule cap lower than the recipe so the effective amount is observable.
    policy['policies'][0]['entry_fraction_bps'] = 125
    selected = tmp_path / 'selected.json'
    selected.write_text(json.dumps(policy))
    with JobManager(tmp_path / 'reports', policy_bundle_path=selected) as manager:
        baseline = wait(manager, manager.submit({'kind': 'cast', 'seed': 42})['job_id'])['result']
        explicit = wait(manager, manager.submit({'kind': 'cast', 'seed': 42, 'policy_id': 'loaded-policy'})['job_id'])['result']
        assert explicit['policy_source'] == policy['source']
        assert explicit['policy_bindings'] == _policy_bindings(build_cast(load_pool(), default_scenario()['cast_recipe'], 42), compile_bundle(policy, load_pool()))
        assert [a['initial_cash_cents'] for a in baseline['actors']] == [a['initial_cash_cents'] for a in explicit['actors']]
        assert [a['strategy'] for a in baseline['actors']] == [a['strategy'] for a in explicit['actors']]
        seen = set()
        rules = {rule['template_id']: rule for rule in policy['policies']}
        for actor in explicit['actors']:
            binding = actor['policy_binding']
            seen.add(binding['mode'])
            if binding['mode'] == 'explicit_rule':
                assert binding['rule'] == rules[actor['template_id']]
                assert actor['effective_entry_fraction_bps'] == min(actor['entry_fraction_bps'], binding['rule']['entry_fraction_bps'])
            elif binding['mode'] == 'passive_role':
                assert binding['rule'] is None and actor['effective_entry_fraction_bps'] == 0
            else:
                assert binding['rule'] is None and actor['effective_entry_fraction_bps'] == actor['entry_fraction_bps']
        assert {'explicit_rule', 'baseline_fallback', 'passive_role'} <= seen
        assert all(a['policy_binding']['mode'] in {'baseline', 'passive_role'} for a in baseline['actors'])
    policy['fallback'] = 'abstain'
    selected.write_text(json.dumps(policy))
    with JobManager(tmp_path / 'abstain', policy_bundle_path=selected) as manager:
        cast = wait(manager, manager.submit({'kind': 'cast', 'policy_id': 'loaded-policy'})['job_id'])['result']
        assert any(a['policy_binding']['mode'] == 'abstain_fallback' for a in cast['actors'])
        assert all(a['effective_entry_fraction_bps'] == 0 for a in cast['actors'] if a['policy_binding']['mode'] == 'abstain_fallback')


def test_final_result_size_cap_fails_without_persisting_oversize_artifact(tmp_path, monkeypatch):
    import decision_lab.web_jobs as jobs
    with jobs.JobManager(tmp_path) as manager:
        def oversized(job):
            # Lower only after preflight so this exercises the final guard with
            # a tiny allocation rather than generating an enormous test report.
            monkeypatch.setattr(jobs, 'MAX_RESULT_BYTES', 128, raising=False)
            return {'value': 'x' * 256}
        monkeypatch.setattr(manager, 'execute_job', oversized)
        job = wait(manager, manager.submit({'kind': 'cast'})['job_id'])
        assert job['status'] == 'failed' and job['result'] is None
        assert not list(tmp_path.glob('*.result.json'))
