"""Private CLI artifacts and opt-in transport; no model service is contacted."""
import json
import os
import stat

import pytest

from decision_lab.cli import main
from decision_lab import providers
from decision_lab.policy_preparation import prepare_request
from decision_lab.simulation import default_scenario, load_pool, simulate


def invoke(*args):
    try:
        return main(list(map(str, args)))
    except SystemExit as error:
        return error.code


def save(path, value):
    path.write_text(json.dumps(value))
    return path


def read(path):
    return json.loads(path.read_text())


def bundle():
    return {"schema_version": "policy-bundle.v1", "bundle_id": "cli-core",
            "source": {"kind": "manual", "model": None, "prompt_sha256": None},
            "fallback": "abstain", "policies": []}


def dataset():
    return {"schema_version": "binary-evaluation.v1", "source_mode": "synthetic",
        "split_at": "2025-02-01T00:00:00Z", "sources": [
            {"id": "e", "url": "https://example.invalid/evidence", "observed_at": "2024-12-01T00:00:00Z"},
            {"id": "t", "url": "https://example.invalid/train", "observed_at": "2025-01-15T00:00:00Z"},
            {"id": "h", "url": "https://example.invalid/holdout", "observed_at": "2025-02-15T00:00:00Z"}],
        "forecasts": [
            {"id": "t", "question": "Fictional training outcome?", "issued_at": "2025-01-01T00:00:00Z",
             "resolves_at": "2025-01-15T00:00:00Z", "resolved_at": "2025-01-16T00:00:00Z",
             "probability": .5, "outcome": 0, "source_ids": ["e"], "outcome_source_ids": ["t"]},
            {"id": "h", "question": "Fictional holdout outcome?", "issued_at": "2025-02-01T00:00:00Z",
             "resolves_at": "2025-02-15T00:00:00Z", "resolved_at": "2025-02-16T00:00:00Z",
             "probability": .25, "outcome": 1, "source_ids": ["e"], "outcome_source_ids": ["h"]}]}


def test_experiment_commands_execute_real_matched_modules(tmp_path):
    policy = save(tmp_path / "policy.json", bundle())
    output = tmp_path / "policies.json"
    assert invoke("experiment", "policies", "--policy-bundle", policy, "--worlds", 1, "--seed", 9, "--output", output) == 0
    result = read(output)
    assert result["schema_version"] == "synthetic-policy-comparison.v1"
    assert result["paired"]["worlds"][0]["world_id"] == 0
    sweep = tmp_path / "sweep.json"
    assert invoke("experiment", "sensitivity", "--parameter", "fee_bps", "--value", 10,
                  "--value", 20, "--policy-bundle", policy, "--worlds", 1, "--output", sweep) == 0
    assert [row["value"] for row in read(sweep)["variants"]] == [10, 20]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_evaluation_scores_strict_synthetic_input(tmp_path):
    data = save(tmp_path / "data.json", dataset())
    output = tmp_path / "evaluation.json"
    assert invoke("evaluate", "--input", data, "--output", output) == 0
    result = read(output)
    assert result["holdout"]["brier_score"] == .5625
    assert result["source_metadata"]["status"] == "synthetic_fixture_only"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert invoke("evaluate", "--input", data, "--output", output) == 2
    data.write_text('{"schema_version": "a", "schema_version": "b"}')
    assert invoke("evaluate", "--input", data, "--output", tmp_path / "bad.json") == 2


def test_legacy_preparation_and_import_artifacts_are_private(tmp_path):
    request_path = tmp_path / "request.json"
    assert invoke("policy", "prepare", "--model", "test-model", "--template", "retail-01", "--output", request_path) == 0
    assert stat.S_IMODE(request_path.stat().st_mode) == 0o600
    request = read(request_path)
    response = {"schema_version": "policy-response.v1", "request_sha256": request["request_sha256"], "usage": None,
        "output_text": json.dumps({"policies": [{"template_id": "retail-01", "entry_signal": "none",
            "entry_fraction_bps": 0, "exit_on_contradiction": True, "rationale": "Synthetic.", "assumptions": ["Unmeasured."]}]})}
    response_path = save(tmp_path / "response.json", response)
    output = tmp_path / "bundle.json"
    assert invoke("policy", "import", "--request", request_path, "--response", response_path,
                  "--bundle-id", "test-private", "--output", output) == 0
    for path in (output, output.with_suffix(".preparation.json")):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_receipt_create_verify_tampering_and_unsigned_action(tmp_path):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"private exact bytes\x00\xff")
    public, opening = tmp_path / "public.json", tmp_path / "opening.json"
    assert invoke("receipt", "create", "--input", artifact, "--output", public, "--opening-output", opening) == 0
    assert set(read(public)) == {"schema_version", "commitment"}
    for path in (public, opening):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert invoke("receipt", "verify", "--input", artifact, "--public", public, "--opening", opening) == 0
    artifact.write_bytes(b"changed")
    assert invoke("receipt", "verify", "--input", artifact, "--public", public, "--opening", opening) == 2
    action = tmp_path / "near.json"
    assert invoke("receipt", "near-action", "--public", public, "--network", "testnet", "--signer", "alice.testnet",
                  "--contract", "receipts.testnet", "--output", action) == 0
    assert read(action)["status"] == "unsigned_unverified"


@pytest.mark.parametrize("collision", ["public", "opening", "same", "dangling"])
def test_receipt_pair_collision_preserves_existing_paths(tmp_path, collision):
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"test")
    public, opening = tmp_path / "public.json", tmp_path / "opening.json"
    existing = None
    if collision == "same":
        opening = public
    else:
        existing = public if collision in {"public", "dangling"} else opening
        if collision == "dangling":
            existing.symlink_to(tmp_path / "missing")
        else:
            existing.write_text("keep")
    assert invoke("receipt", "create", "--input", artifact, "--output", public, "--opening-output", opening) == 2
    if existing is not None:
        assert existing.is_symlink() if collision == "dangling" else existing.read_text() == "keep"
    if collision == "opening":
        assert not public.exists()


def generation(tmp_path):
    request = save(tmp_path / "request.json", prepare_request(default_scenario(), load_pool(),
                   model="test-model", template_ids=["retail-01"], max_output_tokens=1000))
    output = tmp_path / "response.json"
    return ["policy", "generate", "--request", request, "--protocol", "openai", "--endpoint",
            "https://example.invalid/v1/chat/completions", "--api-key-env", "LAB_TEST_KEY", "--output", output], output


@pytest.mark.parametrize("protocol", ["openai", "gemini"])
def test_provider_generation_uses_real_envelope_and_private_transport_receipt(tmp_path, monkeypatch, protocol):
    args, output = generation(tmp_path)
    args[args.index("--protocol") + 1] = protocol
    if protocol == "gemini":
        args[args.index("--endpoint") + 1] = "https://example.invalid/v1beta/models/test-model:generateContent"
    monkeypatch.setenv("LAB_TEST_KEY", "secret-do-not-save")
    actual = providers.generate_response
    calls = []
    synced_directories = []
    actual_fsync = os.fsync
    def record_fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            synced_directories.append(fd)
        actual_fsync(fd)
    monkeypatch.setattr(os, "fsync", record_fsync)
    def fake_generate(request, pool, **kwargs):
        assert output.exists() and output.with_suffix(".transport.json").exists()
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
        pending = read(output.with_suffix(".transport.json"))
        assert pending["status"] == "dispatch_pending"
        assert pending["transport_attempts"] is None
        assert synced_directories
        calls.append(kwargs)
        proposal = {"policies": [{"template_id": "retail-01", "entry_signal": "none", "entry_fraction_bps": 0,
            "exit_on_contradiction": True, "rationale": "Synthetic proposal.", "assumptions": ["Unmeasured."]}]}
        raw = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(proposal)}}]}
        if protocol == "gemini":
            raw = {"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [{"text": json.dumps(proposal)}]}}]}
        return actual(request, pool, **kwargs, transport=lambda **_: json.dumps(raw).encode())
    monkeypatch.setattr(providers, "generate_response", fake_generate)
    assert invoke(*args, "--allow-network") == 0
    assert len(calls) == 1 and calls[0]["api_key"] == "secret-do-not-save"
    assert read(output)["schema_version"] == "policy-response.v1"
    receipt = read(output.with_suffix(".transport.json"))
    assert receipt["schema_version"] == "provider-transport.v1"
    assert receipt["protocol"] == protocol
    assert receipt["usage"] is None and receipt["cost_usd"] is None
    assert "secret-do-not-save" not in output.read_text() + output.with_suffix(".transport.json").read_text()


@pytest.mark.parametrize("reason", ["optin", "key", "output", "receipt", "unwritable", "dangling"])
def test_provider_preflight_prevents_dispatch(tmp_path, monkeypatch, reason):
    args, output = generation(tmp_path)
    calls = []
    monkeypatch.setattr(providers, "generate_response", lambda *a, **k: calls.append(1))
    monkeypatch.setenv("LAB_TEST_KEY", "secret")
    if reason != "optin":
        args.append("--allow-network")
    if reason == "key":
        monkeypatch.delenv("LAB_TEST_KEY")
    if reason == "output":
        output.write_text("keep")
    if reason == "receipt":
        output.with_suffix(".transport.json").write_text("keep")
    if reason == "dangling":
        output.with_suffix(".transport.json").symlink_to(tmp_path / "missing")
    if reason == "unwritable":
        parent = tmp_path / "file"
        parent.write_text("not a directory")
        args[args.index("--output") + 1] = parent / "response.json"
    assert invoke(*args) == 2
    assert not calls
    if reason == "receipt":
        assert output.with_suffix(".transport.json").read_text() == "keep"
        assert not output.exists()
    if reason in {"optin", "key", "unwritable"}:
        assert not output.exists() and not output.with_suffix(".transport.json").exists()


@pytest.mark.parametrize("kind", ["timeout", "unexpected"])
def test_provider_failure_keeps_safe_evidence_and_never_retries(tmp_path, monkeypatch, capsys, kind):
    args, output = generation(tmp_path)
    monkeypatch.setenv("LAB_TEST_KEY", "secret-do-not-save")
    calls = []
    def fail(*a, **k):
        calls.append(1)
        if kind == "timeout":
            raise providers.ProviderError("timeout", request_count=1, remote_outcome="unknown")
        raise RuntimeError("secret-do-not-save private provider body")
    monkeypatch.setattr(providers, "generate_response", fail)
    assert invoke(*args, "--allow-network") == 2
    receipt = read(output.with_suffix(".transport.json"))
    assert receipt["transport_attempts"] == 1
    assert receipt["remote_outcome"] == "unknown"
    assert receipt["usage"] is None and receipt["cost_usd"] is None
    assert read(output)["status"] == "failed"
    combined = output.read_text() + output.with_suffix(".transport.json").read_text() + str(capsys.readouterr())
    assert "secret-do-not-save" not in combined and "private provider body" not in combined
    assert invoke(*args, "--allow-network") == 2
    assert calls == [1]


def test_checkpoint_pause_resume_matches_direct_report(tmp_path, capsys):
    checkpoint, output = tmp_path / "checkpoint.json", tmp_path / "result.json"
    args = ["run", "--worlds", 2, "--seed", 9, "--checkpoint", checkpoint, "--output", output]
    assert invoke(*args, "--max-new-worlds", 1) == 0
    assert checkpoint.exists() and not output.exists() and not output.with_suffix(".manifest.json").exists()
    assert "checkpoint" in capsys.readouterr().out.lower()
    assert invoke(*args, "--resume") == 0
    assert read(output) == simulate(default_scenario(), load_pool(), worlds=2, seed=9)
    assert read(output.with_suffix(".manifest.json"))["result_sha256"]


@pytest.mark.parametrize("extra", [["--resume"], ["--max-new-worlds", 1], ["--checkpoint", "CHECKPOINT", "--compare"]])
def test_invalid_checkpoint_options_have_no_outputs(tmp_path, extra):
    extra = [tmp_path / "checkpoint.json" if x == "CHECKPOINT" else x for x in extra]
    output = tmp_path / "result.json"
    assert invoke("run", "--worlds", 1, "--output", output, *extra) == 2
    assert not output.exists() and not (tmp_path / "checkpoint.json").exists()


@pytest.mark.parametrize("name", ["result.json", "result.manifest.json", "result.json.lock", "result.manifest.json.lock"])
def test_checkpoint_cannot_conflict_with_result_or_manifest(tmp_path, name):
    checkpoint = tmp_path / name
    if name.endswith(".lock"):
        checkpoint = tmp_path / name.removesuffix(".lock")
        output = tmp_path / name
    else:
        output = tmp_path / "result.json"
    assert invoke("run", "--worlds", 1, "--checkpoint", checkpoint, "--output", output) == 2
    assert not checkpoint.exists() and not output.exists()


def test_post_dispatch_disk_failure_retains_pending_evidence(tmp_path, monkeypatch):
    from decision_lab import io_helpers
    args, output = generation(tmp_path)
    monkeypatch.setenv("LAB_TEST_KEY", "secret")
    calls = []
    def generate(*a, **k):
        calls.append(1)
        raise providers.ProviderError("timeout", request_count=1, remote_outcome="unknown")
    monkeypatch.setattr(providers, "generate_response", generate)
    actual = io_helpers._Reservation.write
    def disk_full(reserved, path, data):
        if calls:
            raise OSError("sensitive simulated storage failure")
        return actual(reserved, path, data)
    monkeypatch.setattr(io_helpers._Reservation, "write", disk_full)
    assert invoke(*args, "--allow-network") == 2
    assert calls == [1]
    assert read(output)["status"] == "dispatch_pending"
    assert read(output.with_suffix(".transport.json"))["remote_outcome"] == "unknown"
    assert invoke(*args, "--allow-network") == 2
    assert calls == [1]


def test_directory_sync_failure_prevents_dispatch_and_rolls_back(tmp_path, monkeypatch):
    args, output = generation(tmp_path)
    monkeypatch.setenv("LAB_TEST_KEY", "secret")
    calls = []
    monkeypatch.setattr(providers, "generate_response", lambda *a, **k: calls.append(1))
    actual_fsync = os.fsync
    def directory_error(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("simulated directory sync failure")
        actual_fsync(fd)
    monkeypatch.setattr(os, "fsync", directory_error)
    assert invoke(*args, "--allow-network") == 2
    assert not calls
    assert not output.exists() and not output.with_suffix(".transport.json").exists()


def test_run_rollback_preserves_a_replacement_created_by_another_writer(tmp_path, monkeypatch):
    from decision_lab import cli
    output = tmp_path / "result.json"
    manifest = output.with_suffix(".manifest.json")
    replacement = tmp_path / "replacement.json"
    replacement.write_text("other writer")
    real_open = cli.open_private

    def race(path):
        if path == manifest:
            os.replace(replacement, output)
            raise OSError("manifest could not be created")
        return real_open(path)

    monkeypatch.setattr(cli, "open_private", race)
    assert invoke("run", "--worlds", 1, "--output", output) == 2
    assert output.read_text() == "other writer"


def test_new_ancestor_links_are_synced_before_provider_dispatch(tmp_path, monkeypatch):
    args, _ = generation(tmp_path)
    output = tmp_path / "new" / "nested" / "response.json"
    args[args.index("--output") + 1] = output
    monkeypatch.setenv("LAB_TEST_KEY", "secret")
    synced = set()
    at_dispatch = []
    real_sync = os.fsync

    def sync(fd):
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode):
            synced.add((info.st_dev, info.st_ino))
        real_sync(fd)

    def generate(*a, **k):
        at_dispatch.append(set(synced))
        raise providers.ProviderError("timeout", request_count=1, remote_outcome="unknown")

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(providers, "generate_response", generate)
    assert invoke(*args, "--allow-network") == 2
    assert len(at_dispatch) == 1
    ancestors = set()  # Inodes, not path names, identify fsync targets.
    for parent in (tmp_path, tmp_path / "new", output.parent):
        info = parent.stat()
        ancestors.add((info.st_dev, info.st_ino))
    assert ancestors <= at_dispatch[0]
