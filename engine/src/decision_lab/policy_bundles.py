"""Strict, inert strategy proposals; source metadata is declared, not attested."""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from types import MappingProxyType
from typing import Mapping

from .actors import CATEGORIES, TRADING_CATEGORIES, _integer, _text


RULE_KEYS = frozenset({
    "template_id", "entry_signal", "entry_fraction_bps", "exit_on_contradiction", "rationale", "assumptions",
})


def _keys(value, expected, name):
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{name} has missing or unknown fields")


def _choice(value, allowed, name):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} is not an allowed value")


@dataclass(frozen=True, slots=True)
class PolicyRule:
    template_id: str
    entry_signal: str
    entry_fraction_bps: int
    exit_on_contradiction: bool
    rationale: str
    assumptions: tuple[str, ...]

    def __post_init__(self):
        _text(self.template_id, "template_id")
        _choice(self.entry_signal, {"confirmed", "rumor_or_confirmed", "none"}, "entry_signal")
        _integer(self.entry_fraction_bps, "entry_fraction_bps", maximum=10000)
        if type(self.exit_on_contradiction) is not bool:
            raise ValueError("exit_on_contradiction must be a boolean")
        _text(self.rationale, "rationale")
        if type(self.assumptions) is not tuple or not self.assumptions:
            raise ValueError("assumptions must be a nonempty tuple of strings")
        for assumption in self.assumptions:
            _text(assumption, "assumption")

    def as_dict(self):
        return {
            "template_id": self.template_id, "entry_signal": self.entry_signal,
            "entry_fraction_bps": self.entry_fraction_bps, "exit_on_contradiction": self.exit_on_contradiction,
            "rationale": self.rationale, "assumptions": list(self.assumptions),
        }


@dataclass(frozen=True, slots=True)
class PolicyBundle:
    """Compiled snapshot. Only compile_bundle validates pool eligibility.

    Rules and nested values are immutable. The canonical serialization also
    avoids retaining mutable references to the caller's source declarations.
    """
    bundle_id: str
    fallback: str
    rules: Mapping[str, PolicyRule]
    _canonical: str

    def __post_init__(self):
        object.__setattr__(self, "rules", MappingProxyType(dict(self.rules)))

    @property
    def sha256(self):
        return sha256(self._canonical.encode("utf-8")).hexdigest()

    def as_dict(self):
        return json.loads(self._canonical)


def compile_bundle(value: dict, pool: dict) -> PolicyBundle:
    """Compile JSON data with no expressions, inference, or network access.

    Provenance fields identify what the author declares; this does not verify
    that a model was called, that a human reviewed it, or that it is calibrated.
    """
    _keys(value, {"schema_version", "bundle_id", "source", "fallback", "policies"}, "bundle")
    _choice(value["schema_version"], {"policy-bundle.v1"}, "schema_version")
    _text(value["bundle_id"], "bundle_id")
    _choice(value["fallback"], {"baseline", "abstain"}, "fallback")
    source = value["source"]
    _keys(source, {"kind", "model", "prompt_sha256"}, "source")
    _choice(source["kind"], {"manual", "model_proposal"}, "source.kind")
    if source["kind"] == "manual":
        if source["model"] is not None or source["prompt_sha256"] is not None:
            raise ValueError("manual source requires null model and prompt_sha256")
    else:
        _text(source["model"], "source.model")
        digest = source["prompt_sha256"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("source.prompt_sha256 must be 64 lowercase hexadecimal characters")

    if type(pool) is not dict or type(pool.get("profiles")) is not list or not pool["profiles"]:
        raise ValueError("pool must contain profiles")
    categories = {}
    for profile in pool["profiles"]:
        if type(profile) is not dict:
            raise ValueError("pool profiles must be mappings")
        template_id = profile.get("id")
        category = profile.get("category")
        _text(template_id, "profile.id")
        _choice(category, CATEGORIES, "profile.category")
        if template_id in categories:
            raise ValueError("pool template IDs must be unique")
        categories[template_id] = category

    if type(value["policies"]) is not list:
        raise ValueError("policies must be a list")
    rules = {}
    for raw in value["policies"]:
        _keys(raw, RULE_KEYS, "policy")
        _text(raw["template_id"], "template_id")
        if categories.get(raw["template_id"]) not in TRADING_CATEGORIES:
            raise ValueError("policy target must be a known outside trading template")
        if raw["template_id"] in rules:
            raise ValueError("policy template IDs must be unique")
        if type(raw["assumptions"]) is not list or not raw["assumptions"]:
            raise ValueError("assumptions must be a nonempty list of strings")
        rule = PolicyRule(**{**raw, "assumptions": tuple(raw["assumptions"])})
        rules[rule.template_id] = rule
    canonical = {
        "schema_version": "policy-bundle.v1", "bundle_id": value["bundle_id"],
        "source": dict(source), "fallback": value["fallback"],
        "policies": [rules[template_id].as_dict() for template_id in sorted(rules)],
    }
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return PolicyBundle(value["bundle_id"], value["fallback"], rules, serialized)
