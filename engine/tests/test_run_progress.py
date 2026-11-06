"""Worker progress counts only completed numerical worlds."""
from threading import Event
import time

from decision_lab.simulation import default_scenario, load_pool, simulate


def finish(manager, job_id):
    for _ in range(500):
        snapshot = manager.snapshot(job_id)
        if snapshot['status'] in {'completed', 'failed'}:
            return snapshot
        time.sleep(.01)
    raise AssertionError('job did not finish')


def test_run_progress_is_actual_world_completion_and_preserves_engine_output(tmp_path, monkeypatch):
    import decision_lab.web_jobs as jobs
    import decision_lab.simulation as simulation
    original = simulation._world
    first_started, second_started, first_release, second_release = (Event() for _ in range(4))

    def gated(value, cast, seed, world_id, plan, keep_trace, bundle=None):
        if world_id == 0:
            first_started.set()
            assert first_release.wait(5)
        elif world_id == 1:
            second_started.set()
            assert second_release.wait(5)
        return original(value, cast, seed, world_id, plan, keep_trace, bundle)

    monkeypatch.setattr(jobs, '_world', gated, raising=False)
    scenario = default_scenario()
    scenario.update(horizon_hours=1, campaigns=[], founder_sales=[], competitor_messages=[])
    manager = jobs.JobManager(tmp_path)
    try:
        job_id = manager.submit({'kind': 'run', 'scenario': scenario, 'worlds': 2})['job_id']
        assert first_started.wait(2), 'run must expose numerical-world execution'
        snapshot = manager.snapshot(job_id)
        assert snapshot['phase'] == 'simulating'
        assert snapshot['completed_worlds'] == 0
        assert snapshot['target_worlds'] == 2
        assert snapshot['actor_count'] > snapshot['active_traders'] > 0
        first_release.set()
        assert second_started.wait(2)
        assert manager.snapshot(job_id)['completed_worlds'] == 1
        second_release.set()
        result = finish(manager, job_id)
        assert result['status'] == 'completed'
        assert result['phase'] == 'completed'
        assert result['completed_worlds'] == 2
        assert result['result'] == simulate(scenario, load_pool(), worlds=2)
    finally:
        first_release.set()
        second_release.set()
        manager.close()


def test_failed_world_does_not_advance_completion_counter(tmp_path, monkeypatch):
    import decision_lab.web_jobs as jobs
    def broken(*_args, **_kwargs):
        raise ValueError('private failure detail')
    monkeypatch.setattr(jobs, '_world', broken, raising=False)
    with jobs.JobManager(tmp_path) as manager:
        result = finish(manager, manager.submit({'kind': 'run', 'worlds': 2})['job_id'])
        assert result['status'] == 'failed'
        assert result['completed_worlds'] == 0
        assert result['phase'] == 'failed'
        assert 'private failure detail' not in result['error']
