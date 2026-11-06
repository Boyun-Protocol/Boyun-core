import json
import hashlib
import subprocess
import sys

import pytest

from decision_lab.cli import main
from decision_lab.simulation import _bin, default_scenario


def test_cli_creates_a_report_and_manifest_without_network_or_secrets(tmp_path):
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps(default_scenario()))
    output = tmp_path / "result.json"
    assert main(["run", "--scenario", str(scenario), "--worlds", "2", "--seed", "42", "--output", str(output)]) == 0
    result = json.loads(output.read_text())
    manifest = json.loads(output.with_suffix(".manifest.json").read_text())
    assert result["usage"]["model_calls"] == 0
    assert manifest["scenario_sha256"] == result["scenario_sha256"]
    assert manifest["source_mode"] == "synthetic"
    assert manifest["world_count"] == 2
    assert len(manifest["engine_source_sha256"]) == 64
    assert manifest["runtime"]["python"]
    assert manifest["scenario"] == default_scenario()
    assert manifest["result_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_cli_output_collision_never_overwrites_previous_work(tmp_path):
    output = tmp_path / "result.json"
    output.write_text("keep")
    assert main(["run", "--worlds", "1", "--output", str(output)]) == 2
    assert output.read_text() == "keep"


def test_cli_bad_json_and_invalid_world_count_have_nonzero_exit(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{notjson")
    assert main(["run", "--scenario", str(bad), "--output", str(tmp_path / "no.json")]) == 2
    assert main(["run", "--worlds", "0", "--output", str(tmp_path / "zero.json")]) == 2
    assert not (tmp_path / "zero.json").exists()


def test_cli_compares_matched_worlds(tmp_path):
    output = tmp_path / "comparison.json"
    assert main(["run", "--worlds", "1", "--compare", "--output", str(output)]) == 0
    result = json.loads(output.read_text())
    assert set(result["plans"]) == {"launch_now", "lower_marketing", "defer_launch", "do_not_launch"}


@pytest.mark.parametrize("profit,expected", [(-500001, "severe_loss"), (-500000, "loss"), (-1, "loss"),
                                           (0, "modest_profit"), (1999999, "modest_profit"), (2000000, "large_profit")])
def test_outcome_boundaries_are_disjoint(profit, expected):
    assert _bin(profit) == expected


def test_module_entrypoint_runs_in_a_subprocess(tmp_path):
    output = tmp_path / "subprocess.json"
    result = subprocess.run([sys.executable, "-m", "decision_lab.cli", "run", "--worlds", "1", "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert output.exists()


def policy_bundle():
    return {"schema_version": "policy-bundle.v1", "bundle_id": "cli-test",
            "source": {"kind": "manual", "model": None, "prompt_sha256": None},
            "fallback": "abstain", "policies": []}


def test_compile_policy_then_run_records_canonical_local_bundle(tmp_path):
    raw, compiled = tmp_path / "proposal.json", tmp_path / "compiled.json"
    raw.write_text(json.dumps(policy_bundle()))
    assert main(["policy", "compile", "--input", str(raw), "--output", str(compiled)]) == 0
    assert json.loads(compiled.read_text()) == policy_bundle()
    output = tmp_path / "policy-run.json"
    assert main(["run", "--policy-bundle", str(compiled), "--worlds", "1", "--output", str(output)]) == 0
    report = json.loads(output.read_text())
    manifest = json.loads(output.with_suffix(".manifest.json").read_text())
    assert report["worlds"][0]["participant_buys"] == 0
    assert manifest["policy_bundle"] == report["policy_bundle"]
    assert manifest["policy_bundle_sha256"] == report["policy_bundle_sha256"]
    assert manifest["model_rollout_calls"] == 0


def test_invalid_policy_has_no_artifact_and_compile_never_overwrites(tmp_path):
    raw, compiled = tmp_path / "proposal.json", tmp_path / "compiled.json"
    bad = policy_bundle()
    bad["execute"] = "not permitted"
    raw.write_text(json.dumps(bad))
    assert main(["policy", "compile", "--input", str(raw), "--output", str(compiled)]) == 2
    assert not compiled.exists()
    output = tmp_path / "run.json"
    assert main(["run", "--policy-bundle", str(raw), "--worlds", "1", "--output", str(output)]) == 2
    assert not output.exists()
    assert not output.with_suffix(".manifest.json").exists()
    compiled.write_text("keep")
    assert main(["policy", "compile", "--input", str(raw), "--output", str(compiled)]) == 2
    assert compiled.read_text() == "keep"


def test_duplicate_json_policy_fields_cannot_silently_replace_reviewed_values(tmp_path):
    raw, compiled = tmp_path / "duplicate.json", tmp_path / "compiled.json"
    raw.write_text(json.dumps(policy_bundle()).replace('"fallback": "abstain"',
                                                      '"fallback": "baseline", "fallback": "abstain"'))
    assert main(["policy", "compile", "--input", str(raw), "--output", str(compiled)]) == 2
    assert not compiled.exists()
