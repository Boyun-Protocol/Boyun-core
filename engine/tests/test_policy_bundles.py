"""Policy proposals are data: unknown instructions and mutable state fail closed."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
import json

import pytest

from decision_lab.simulation import load_pool


def proposal():
    return {
        "schema_version": "policy-bundle.v1", "bundle_id": "synthetic-reviewed.v1",
        "source": {"kind": "manual", "model": None, "prompt_sha256": None},
        "fallback": "baseline", "policies": [
            {"template_id": "retail-01", "entry_signal": "confirmed", "entry_fraction_bps": 500,
             "exit_on_contradiction": True, "rationale": "Only act on visible confirmation.",
             "assumptions": ["Synthetic strategy; not calibrated."]},
        ],
    }


def compile_value(value):
    from decision_lab.policy_bundles import compile_bundle
    return compile_bundle(value, load_pool())


def test_bundle_is_canonical_and_isolated_from_both_input_and_output_mutation():
    value = proposal()
    value["policies"].append({**deepcopy(value["policies"][0]), "template_id": "event_traders-01"})
    bundle = compile_value(value)
    expected = deepcopy(value)
    expected["policies"].reverse()  # event_traders sorts before retail
    assert bundle.as_dict() == expected
    assert bundle.sha256 == sha256(json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                             allow_nan=False).encode()).hexdigest()
    reversed_value = deepcopy(value)
    reversed_value["policies"].reverse()
    assert compile_value(reversed_value).sha256 == bundle.sha256
    value["source"]["kind"] = "untrusted"
    value["policies"][0]["assumptions"].append("mutated")
    exported = bundle.as_dict()
    exported["policies"][0]["assumptions"].clear()
    assert bundle.as_dict() == expected
    assert bundle.bundle_id == "synthetic-reviewed.v1"
    assert bundle.fallback == "baseline"
    with pytest.raises(TypeError):
        bundle.rules["retail-01"] = bundle.rules["retail-01"]
    with pytest.raises(FrozenInstanceError):
        bundle.rules["retail-01"].entry_fraction_bps = 10000
    with pytest.raises(FrozenInstanceError):
        bundle.fallback = "abstain"
    assert bundle.rules["retail-01"].assumptions == ("Synthetic strategy; not calibrated.",)


@pytest.mark.parametrize("key,value", [
    ("schema_version", "v2"), ("bundle_id", " "), ("bundle_id", 1),
    ("fallback", "infer"), ("fallback", None), ("policies", {}), ("policies", None),
    ("code", "raise RuntimeError('do not execute')"),
])
def test_rejects_invalid_top_level_fields(key, value):
    raw = proposal()
    raw[key] = value
    with pytest.raises(ValueError):
        compile_value(raw)


@pytest.mark.parametrize("field", ["source", "fallback", "policies", "schema_version", "bundle_id"])
def test_missing_top_level_fields_fail_closed(field):
    raw = proposal()
    del raw[field]
    with pytest.raises(ValueError):
        compile_value(raw)


@pytest.mark.parametrize("change", [
    {"entry_fraction_bps": True}, {"entry_fraction_bps": 1.5}, {"entry_fraction_bps": -1},
    {"entry_fraction_bps": 10001}, {"entry_signal": "price_pump"}, {"entry_signal": []},
    {"exit_on_contradiction": 1}, {"exit_on_contradiction": "false"}, {"rationale": " "},
    {"assumptions": []}, {"assumptions": [""]}, {"assumptions": "unreviewed"},
    {"assumptions": [True]}, {"code": "eval('money')"}, {"allowed_actions": ["mint"]},
    {"template_id": "missing-01"}, {"template_id": "liquidity-01"}, {"template_id": "launch_teams-01"},
])
def test_rejects_invalid_rule_fields_and_nontrading_targets(change):
    raw = proposal()
    raw["policies"][0].update(change)
    with pytest.raises(ValueError):
        compile_value(raw)


@pytest.mark.parametrize("field", ["template_id", "entry_signal", "entry_fraction_bps", "exit_on_contradiction", "rationale", "assumptions"])
def test_missing_rule_fields_fail_closed(field):
    raw = proposal()
    del raw["policies"][0][field]
    with pytest.raises(ValueError):
        compile_value(raw)


def test_rejects_duplicate_target_ids():
    raw = proposal()
    raw["policies"] *= 2
    with pytest.raises(ValueError):
        compile_value(raw)


@pytest.mark.parametrize("source", [
    None, {}, {"kind": "manual", "model": "fake-model", "prompt_sha256": None},
    {"kind": "manual", "model": None, "prompt_sha256": "a" * 64},
    {"kind": "model_proposal", "model": None, "prompt_sha256": "a" * 64},
    {"kind": "model_proposal", "model": "g", "prompt_sha256": "A" * 64},
    {"kind": "model_proposal", "model": "g", "prompt_sha256": "x" * 64},
    {"kind": "model_proposal", "model": "g", "prompt_sha256": "a" * 63},
    {"kind": "model_proposal", "model": " ", "prompt_sha256": "a" * 64},
    {"kind": "manual", "model": None, "prompt_sha256": None, "verified": True},
])
def test_source_metadata_is_strict_declaration(source):
    raw = proposal()
    raw["source"] = source
    with pytest.raises(ValueError):
        compile_value(raw)


def test_model_proposal_metadata_preserved_as_declared_without_network_attestation():
    raw = proposal()
    raw["source"] = {"kind": "model_proposal", "model": "declared-not-attested", "prompt_sha256": "a" * 64}
    bundle = compile_value(raw)
    assert bundle.as_dict()["source"] == raw["source"]
    assert set(bundle.as_dict()) == {"schema_version", "bundle_id", "source", "fallback", "policies"}


@pytest.mark.parametrize("fallback", ["baseline", "abstain"])
def test_empty_policy_list_requires_and_preserves_explicit_fallback(fallback):
    raw = proposal()
    raw.update(policies=[], fallback=fallback)
    assert compile_value(raw).rules == {}
    assert compile_value(raw).fallback == fallback


def test_malformed_or_ambiguous_pool_cannot_authorize_rule():
    from decision_lab.policy_bundles import compile_bundle
    for pool in ({}, {"profiles": []}, {"profiles": [{"id": "retail-01", "category": "retail"},
                                                         {"id": "retail-01", "category": "launch_teams"}]}):
        with pytest.raises(ValueError):
            compile_bundle(proposal(), pool)
