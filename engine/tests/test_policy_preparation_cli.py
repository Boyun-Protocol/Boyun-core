import json
from pathlib import Path

import pytest

from decision_lab.cli import main


def prepare(tmp_path):
    request = tmp_path / "request.json"
    assert main(["policy", "prepare", "--model", "declared/model", "--template", "retail-01",
                 "--output", str(request)]) == 0
    return request


def reply_for(request, path):
    req = json.loads(request.read_text())
    raw = {"policies": [{"template_id": "retail-01", "entry_signal": "none", "entry_fraction_bps": 0,
                         "exit_on_contradiction": True, "rationale": "Offline synthetic fixture.",
                         "assumptions": ["No model called to write this fixture."]}]}
    path.write_text(json.dumps({"schema_version": "policy-response.v1", "request_sha256": req["request_sha256"],
                                "output_text": json.dumps(raw), "usage": None}))
    return path


def import_args(request, reply, output):
    return ["policy", "import", "--request", str(request), "--response", str(reply),
            "--bundle-id", "offline-fixture", "--output", str(output)]


def test_cli_prepares_imports_then_runs_with_source_and_unknown_cost(tmp_path):
    request = prepare(tmp_path)
    reply = reply_for(request, tmp_path / "response.json")
    output = tmp_path / "bundle.json"
    assert main(import_args(request, reply, output)) == 0
    receipt = json.loads(output.with_suffix(".preparation.json").read_text())
    assert receipt["cost_usd"] is None
    assert receipt["inference_calls_performed"] == 0
    result = tmp_path / "result.json"
    assert main(["run", "--policy-bundle", str(output), "--worlds", "1", "--output", str(result)]) == 0
    manifest = json.loads(result.with_suffix(".manifest.json").read_text())
    assert manifest["policy_bundle_sha256"] == receipt["bundle_sha256"]
    assert manifest["policy_bundle"]["source"]["model"] == "declared/model"
    assert manifest["model_rollout_calls"] == 0


@pytest.mark.parametrize("collision", ["bundle.json", "bundle.preparation.json"])
def test_import_never_overwrites_bundle_or_preparation_receipt(tmp_path, collision):
    request = prepare(tmp_path)
    reply = reply_for(request, tmp_path / "response.json")
    (tmp_path / collision).write_text("keep")
    output = tmp_path / "bundle.json"
    assert main(import_args(request, reply, output)) == 2
    assert (tmp_path / collision).read_text() == "keep"
    absent = "bundle.preparation.json" if collision == "bundle.json" else "bundle.json"
    assert not (tmp_path / absent).exists()


def test_failed_receipt_write_rolls_back_only_new_bundle(tmp_path, monkeypatch):
    request = prepare(tmp_path)
    reply = reply_for(request, tmp_path / "response.json")
    original = Path.open

    def fail_receipt(path, *args, **kwargs):
        if path.name == "bundle.preparation.json":
            raise OSError("simulated disk error")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_receipt)
    output = tmp_path / "bundle.json"
    assert main(import_args(request, reply, output)) == 2
    assert not output.exists()
    assert request.exists() and reply.exists()


def test_prepare_collision_and_invalid_input_create_no_new_artifacts(tmp_path):
    request = prepare(tmp_path)
    before = request.read_bytes()
    assert main(["policy", "prepare", "--model", "other", "--template", "retail-01",
                 "--output", str(request)]) == 2
    assert request.read_bytes() == before
    output = tmp_path / "invalid.json"
    assert main(["policy", "prepare", "--model", "declared/model", "--template", "launch_teams-01",
                 "--output", str(output)]) == 2
    assert not output.exists()


def test_duplicate_response_envelope_and_wrong_request_identity_rejected(tmp_path):
    request = prepare(tmp_path)
    reply = reply_for(request, tmp_path / "response.json")
    reply.write_text(reply.read_text().replace('"usage": null', '"usage": null, "usage": null'))
    output = tmp_path / "bundle.json"
    assert main(import_args(request, reply, output)) == 2
    assert not output.exists()
    reply_for(request, reply)
    envelope = json.loads(reply.read_text())
    envelope["request_sha256"] = "0" * 64
    reply.write_text(json.dumps(envelope))
    assert main(import_args(request, reply, output)) == 2
    assert not output.exists()
    assert not output.with_suffix(".preparation.json").exists()
