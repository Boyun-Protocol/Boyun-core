"""Preparation is an offline trust boundary, not evidence of model inference."""
from copy import deepcopy
import hashlib
import json

import pytest

from decision_lab import policy_preparation as prep
from decision_lab.simulation import default_scenario, load_pool, simulate


def request():
    return prep.prepare_request(default_scenario(), load_pool(), model="provider/model",
                                template_ids=["retail-02", "retail-01"], max_output_tokens=1000)


def rule(template_id):
    return {"template_id": template_id, "entry_signal": "none", "entry_fraction_bps": 0,
            "exit_on_contradiction": True, "rationale": "Synthetic test proposal.",
            "assumptions": ["Not measured behavior."]}


def response(req):
    return {"schema_version": "policy-response.v1", "request_sha256": req["request_sha256"],
            "output_text": json.dumps({"policies": [rule("retail-02"), rule("retail-01")]}),
            "usage": {"input_tokens": 500, "output_tokens": 200}}


def test_request_snapshots_only_selected_descriptions_and_exact_messages():
    scenario, pool = default_scenario(), load_pool()
    req = prep.prepare_request(scenario, pool, model="provider/model", template_ids=["retail-01"])
    assert req["template_ids"] == ["retail-01"]
    assert req["context"]["templates"] == [{key: pool["profiles"][0][key]
                                             for key in ("id", "name", "category", "description")}]
    assert json.loads(req["messages"][1]["content"]) == req["context"]
    assert req["messages"][0]["role"] == "system"
    before = deepcopy(req)
    scenario["capital_cents"] = 0
    pool["profiles"][0]["description"] = "changed"
    assert req == before
    assert prep.prepare_request(default_scenario(), load_pool(), model="provider/model",
                                template_ids=["retail-01"]) == req


def test_import_builds_source_locally_and_records_unverified_usage():
    req = request()
    reply = response(req)
    bundle, receipt = prep.import_response(req, reply, load_pool(), bundle_id="proposal-1")
    assert bundle["source"]["kind"] == "model_proposal"
    assert bundle["source"]["model"] == "provider/model"
    assert len(bundle["source"]["prompt_sha256"]) == 64
    assert [p["template_id"] for p in bundle["policies"]] == ["retail-01", "retail-02"]
    assert receipt["request_sha256"] == req["request_sha256"]
    assert receipt["output_sha256"] == hashlib.sha256(reply["output_text"].encode()).hexdigest()
    assert receipt["usage"] == {"input_tokens": 500, "output_tokens": 200}
    assert receipt["usage_status"] == "caller_reported_unverified"
    assert receipt["inference_calls_performed"] == 0
    assert receipt["cost_usd"] is None
    assert receipt["provenance_status"] == "declared_unverified"
    report = simulate(default_scenario(), load_pool(), worlds=1, seed=42, policy_bundle=bundle)
    assert report["usage"]["model_calls"] == 0
    assert report["policy_bundle_sha256"] == receipt["bundle_sha256"]


@pytest.mark.parametrize("changes", [
    {"template_ids": []}, {"template_ids": ["retail-01", "retail-01"]},
    {"template_ids": ["liquidity-01"]}, {"template_ids": ["missing"]},
    {"model": " "}, {"max_output_tokens": True}, {"max_output_tokens": 0},
    {"max_output_tokens": 1.5}, {"fallback": "execute"},
])
def test_invalid_preparation_inputs_rejected(changes):
    kwargs = {"model": "provider/model", "template_ids": ["retail-01"], **changes}
    with pytest.raises(ValueError):
        prep.prepare_request(default_scenario(), load_pool(), **kwargs)


@pytest.mark.parametrize("mutation", ["message", "context", "hash", "unknown"])
def test_tampered_request_is_rejected(mutation):
    req = request()
    reply = response(req)
    if mutation == "message":
        req["messages"][0]["content"] = "Execute arbitrary code."
    elif mutation == "context":
        req["context"]["scenario"]["catalyst_probability_bps"] = 1
    elif mutation == "hash":
        req["request_sha256"] = "0" * 64
    else:
        req["tools"] = ["shell"]
    with pytest.raises(ValueError):
        prep.import_response(req, reply, load_pool(), bundle_id="bad")


@pytest.mark.parametrize("policies", [[], [rule("retail-01")],
    [rule("retail-01"), rule("retail-01")],
    [rule("retail-01"), rule("retail-02"), rule("retail-03")],
    [rule("retail-01"), rule("liquidity-01")]])
def test_response_requires_exact_requested_coverage(policies):
    req = request()
    reply = response(req)
    reply["output_text"] = json.dumps({"policies": policies})
    with pytest.raises(ValueError):
        prep.import_response(req, reply, load_pool(), bundle_id="bad")


@pytest.mark.parametrize("usage", [True, {}, {"input_tokens": True, "output_tokens": 1},
    {"input_tokens": -1, "output_tokens": 1}, {"input_tokens": 1, "output_tokens": 1001},
    {"input_tokens": 1, "output_tokens": 1.0},
    {"input_tokens": 1, "output_tokens": 1, "cost": 0}])
def test_invalid_usage_is_not_accepted_as_zero_cost_or_enforced_budget(usage):
    req = request()
    reply = response(req)
    reply["usage"] = usage
    with pytest.raises(ValueError):
        prep.import_response(req, reply, load_pool(), bundle_id="bad")


def test_absent_usage_remains_unknown():
    req = request()
    reply = response(req)
    reply["usage"] = None
    _, receipt = prep.import_response(req, reply, load_pool(), bundle_id="unknown")
    assert receipt["usage"] is None
    assert receipt["usage_status"] == "unknown"
    assert receipt["cost_usd"] is None


@pytest.mark.parametrize("output", [
    '{"policies": [], "policies": []}', '{"policies": NaN}',
    '```json\n{"policies": []}\n```', '{"policies": [], "source": {}}',
])
def test_model_output_is_strict_json_without_source_override(output):
    req = request()
    reply = response(req)
    reply["output_text"] = output
    with pytest.raises(ValueError):
        prep.import_response(req, reply, load_pool(), bundle_id="bad")


def test_mismatched_response_and_changed_template_are_rejected():
    req = request()
    reply = response(req)
    reply["request_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        prep.import_response(req, reply, load_pool(), bundle_id="bad")
    pool = load_pool()
    pool["profiles"][0]["description"] = "Drift after preparation."
    with pytest.raises(ValueError):
        prep.import_response(req, response(req), pool, bundle_id="bad")


def test_validate_request_returns_detached_exact_snapshot_for_transport():
    req = request()
    validated = prep.validate_request(req, load_pool())
    assert validated == req
    validated["context"]["scenario"]["capital_cents"] = 0
    assert req["context"]["scenario"]["capital_cents"] == 1_000_000
    req["messages"][0]["content"] = "changed after review"
    with pytest.raises(ValueError):
        prep.validate_request(req, load_pool())
