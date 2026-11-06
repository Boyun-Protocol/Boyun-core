from copy import deepcopy
import json
import os
import stat

import pytest

from decision_lab import checkpoints
from decision_lab.simulation import default_scenario, load_pool, simulate


def scenario():
    value = default_scenario()
    value["horizon_hours"] = 6
    return value


def test_completed_world_resume_matches_uninterrupted_report(tmp_path):
    path = tmp_path / "run.checkpoint.json"
    assert checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path,
                                        worlds=4, seed=17, max_new_worlds=2) is None
    saved = json.loads(path.read_text())
    assert [world["world_id"] for world in saved["completed_worlds"]] == [0, 1]
    report = checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path,
                                          worlds=4, seed=17, resume=True)
    assert report == simulate(scenario(), load_pool(), worlds=4, seed=17)
    assert checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path,
                                         worlds=4, seed=17, resume=True) == report


@pytest.mark.parametrize("change", ["scenario", "pool", "seed", "worlds", "plan", "policy"])
def test_changed_run_identity_preserves_existing_checkpoint(tmp_path, change):
    path = tmp_path / "checkpoint.json"
    checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2, max_new_worlds=1)
    before = path.read_bytes()
    value, pool, kwargs = scenario(), load_pool(), {"worlds": 2}
    if change == "scenario":
        value["catalyst_probability_bps"] = 1
    elif change == "pool":
        pool["profiles"][0]["description"] = "changed"
    elif change == "seed":
        kwargs["seed"] = 13
    elif change == "worlds":
        kwargs["worlds"] = 3
    elif change == "plan":
        kwargs["plan"] = "do_not_launch"
    else:
        kwargs["policy_bundle"] = {"schema_version": "policy-bundle.v1", "bundle_id": "new",
                                   "source": {"kind": "manual", "model": None, "prompt_sha256": None},
                                   "fallback": "abstain", "policies": []}
    with pytest.raises(ValueError):
        checkpoints.run_checkpointed(value, pool, checkpoint_path=path, resume=True, **kwargs)
    assert path.read_bytes() == before


def test_world_failure_keeps_only_completed_prefix(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    real_world = checkpoints._world

    def interrupt(value, cast, seed, world_id, *args):
        if world_id == 1:
            raise KeyboardInterrupt()
        return real_world(value, cast, seed, world_id, *args)

    monkeypatch.setattr(checkpoints, "_world", interrupt)
    with pytest.raises(KeyboardInterrupt):
        checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=3)
    assert len(json.loads(path.read_text())["completed_worlds"]) == 1
    monkeypatch.setattr(checkpoints, "_world", real_world)
    assert checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path,
                                         worlds=3, resume=True) == simulate(scenario(), load_pool(), worlds=3)


def test_bad_checksum_duplicate_keys_and_collision_are_rejected(tmp_path):
    path = tmp_path / "checkpoint.json"
    checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2, max_new_worlds=1)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2)
    assert path.read_bytes() == before
    value = json.loads(before)
    value["completed_worlds"][0]["net_profit_cents"] = 1
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2, resume=True)
    path.write_text('{"schema_version":"run-checkpoint.v1","schema_version":"bad"}')
    with pytest.raises(ValueError):
        checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2, resume=True)


def test_failed_atomic_replace_preserves_previous_checkpoint(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2, max_new_worlds=1)
    before = path.read_bytes()

    def fail_replace(*args):
        raise OSError("simulated disk error")

    monkeypatch.setattr(checkpoints.os, "replace", fail_replace)
    with pytest.raises(OSError):
        checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2, resume=True)
    assert path.read_bytes() == before
    assert set(tmp_path.iterdir()) == {path, path.with_name(path.name + ".lock")}


@pytest.mark.parametrize("limit", [0, True, 1.5])
def test_invalid_partial_limit_rejected_before_creating_file(tmp_path, limit):
    path = tmp_path / "checkpoint.json"
    with pytest.raises(ValueError):
        checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path,
                                     worlds=2, max_new_worlds=limit)
    assert not path.exists()


def test_concurrent_writer_and_changed_engine_are_rejected(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    with checkpoints._locked(path):
        with pytest.raises(ValueError, match="in use"):
            checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2)
    assert not path.exists()
    checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2, max_new_worlds=1)
    before = path.read_bytes()
    monkeypatch.setattr(checkpoints, "engine_fingerprint", lambda: "0" * 64)
    with pytest.raises(ValueError, match="changed"):
        checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=2, resume=True)
    assert path.read_bytes() == before


def test_checkpoint_publication_syncs_directory_metadata(tmp_path, monkeypatch):
    real_sync = os.fsync
    directories = []

    def sync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            directories.append(True)
        real_sync(fd)

    monkeypatch.setattr(checkpoints.os, "fsync", sync)
    checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=tmp_path / "checkpoint.json",
                                 worlds=2, max_new_worlds=1)
    # Initial empty publication and the first completed world's atomic rename.
    assert len(directories) == 2


def test_checkpoint_syncs_new_directory_ancestors(tmp_path, monkeypatch):
    seen = set()
    real_sync = os.fsync

    def sync(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            seen.add((info.st_dev, info.st_ino))
        real_sync(fd)

    monkeypatch.setattr(checkpoints.os, "fsync", sync)
    path = tmp_path / "new" / "nested" / "checkpoint.json"
    checkpoints.run_checkpointed(scenario(), load_pool(), checkpoint_path=path, worlds=1)
    for parent in (tmp_path, tmp_path / "new", path.parent):
        info = parent.stat()
        assert (info.st_dev, info.st_ino) in seen
