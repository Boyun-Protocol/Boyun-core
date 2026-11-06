"""A private opening binds exact bytes; public commitments disclose no raw hash."""
from copy import deepcopy
import hashlib
import importlib
import json

import pytest


def integrity():
    # Keep the first red run a direct assertion about the missing boundary.
    assert importlib.util.find_spec("decision_lab.integrity") is not None, "integrity boundary missing"
    return importlib.import_module("decision_lab.integrity")


def test_exact_binary_bytes_open_and_public_payload_is_minimal():
    api = integrity()
    data = b"\x00private artifact\xff\r\n"
    public, private = api.create_commitment(data)
    assert set(public) == {"schema_version", "commitment"}
    assert public["schema_version"] == "artifact-commitment.v1"
    assert set(private) == {"schema_version", "salt", "artifact_sha256"}
    assert private["schema_version"] == "artifact-opening.v1"
    assert private["artifact_sha256"] == hashlib.sha256(data).hexdigest()
    assert len(bytes.fromhex(private["salt"])) == 32
    assert len(bytes.fromhex(public["commitment"])) == 32
    assert private["artifact_sha256"] not in json.dumps(public)
    assert private["salt"] not in json.dumps(public)
    assert api.verify_commitment(data, public, private) is True
    assert api.verify_commitment(data.replace(b"\r\n", b"\n"), public, private) is False
    assert api.verify_commitment(data + b"\x00", public, private) is False


def test_fresh_calls_hide_equality_but_the_same_opening_replays():
    api = integrity()
    first_public, first_private = api.create_commitment(b"same low entropy artifact")
    second_public, second_private = api.create_commitment(b"same low entropy artifact")
    assert first_public != second_public
    assert first_private["salt"] != second_private["salt"]
    assert api.verify_commitment(b"same low entropy artifact", first_public, first_private)
    assert api.verify_commitment(b"same low entropy artifact", first_public, first_private)
    assert not api.verify_commitment(b"same low entropy artifact", first_public, second_private)


def test_domain_separated_length_prefixed_encoding_has_a_stable_vector(monkeypatch):
    api = integrity()
    monkeypatch.setattr(api.secrets, "token_bytes", lambda size: bytes(range(size)))
    public, private = api.create_commitment(b"\x00private artifact\xff\r\n")
    assert private["salt"] == "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    assert private["artifact_sha256"] == "b36310339e3026317cbdb8612833a85b5f7adb5755aa4041175bdebb4eed65ca"
    assert public["commitment"] == "98a0bb2daa13db38460c7731f971a7c917844a6a268a95ba57e9dbf5445cae45"


@pytest.mark.parametrize("data", ["text", bytearray(b"text"), memoryview(b"text"), None, 1])
def test_only_exact_bytes_can_be_committed(data):
    with pytest.raises(ValueError):
        integrity().create_commitment(data)


def test_empty_artifact_is_valid_and_non_bytes_never_verify():
    api = integrity()
    public, private = api.create_commitment(b"")
    assert api.verify_commitment(b"", public, private)
    assert not api.verify_commitment("", public, private)
    assert not api.verify_commitment(bytearray(), public, private)


@pytest.mark.parametrize("target,key,value", [
    ("public", "schema_version", "artifact-commitment.v2"),
    ("private", "schema_version", "artifact-opening.v2"),
    ("public", "commitment", "0" * 64),
    ("public", "commitment", "A" * 64),
    ("public", "commitment", "0" * 63),
    ("public", "commitment", "g" * 64),
    ("public", "commitment", 0),
    ("private", "salt", "0" * 62),
    ("private", "salt", "0" * 66),
    ("private", "salt", "\n" + "0" * 63),
    ("private", "salt", "A" * 64),
    ("private", "salt", None),
    ("private", "artifact_sha256", "0" * 64),
    ("private", "artifact_sha256", "A" * 64),
    ("private", "artifact_sha256", True),
    ("public", "filename", "sensitive.json"),
    ("private", "extra", "unsupported"),
])
def test_malformed_or_changed_openings_fail_closed(target, key, value):
    api = integrity()
    public, private = api.create_commitment(b"private")
    (public if target == "public" else private)[key] = value
    assert api.verify_commitment(b"private", public, private) is False


@pytest.mark.parametrize("target", ["public", "private"])
def test_missing_and_non_object_receipts_fail_closed(target):
    api = integrity()
    public, private = api.create_commitment(b"private")
    value = public if target == "public" else private
    del value["schema_version"]
    assert not api.verify_commitment(b"private", public, private)
    assert not api.verify_commitment(b"private", None if target == "public" else public,
                                     [] if target == "private" else private)


def test_unsigned_testnet_action_contains_only_the_commitment_argument():
    api = integrity()
    public, private = api.create_commitment(b"sensitive scenario")
    before = deepcopy(public)
    action = api.near_anchor_action(public, network="testnet", signer_id="alice.testnet",
                                    contract_id="receipts.lab.testnet")
    assert action == {
        "schema_version": "near-anchor-action.v1", "network": "testnet",
        "signer_id": "alice.testnet", "receiver_id": "receipts.lab.testnet",
        "status": "unsigned_unverified",
        "actions": [{"type": "FunctionCall", "params": {
            "methodName": "register_commitment", "args": {"commitment": public["commitment"]},
            "gas": "30000000000000", "deposit": "0"}}],
    }
    assert public == before
    assert private["artifact_sha256"] not in json.dumps(action)
    assert private["salt"] not in json.dumps(action)


@pytest.mark.parametrize("account", [
    "a.testnet", "test-account_1.testnet", "sub.alice.testnet", "a" * 56 + ".testnet", "a" * 64,
])
def test_named_testnet_and_hex_implicit_accounts_are_accepted(account):
    api = integrity()
    public, _ = api.create_commitment(b"artifact")
    action = api.near_anchor_action(public, network="testnet", signer_id=account, contract_id=account)
    assert action["signer_id"] == account
    assert action["receiver_id"] == account


@pytest.mark.parametrize("account", [
    None, 1, "", "testnet", "alice.near", "alice", "Alice.testnet", "alice.testnet\n",
    " alice.testnet", "alice.testnet ", "alice..testnet", "alice.-testnet", "alice__one.testnet",
    "-alice.testnet", "alice-.testnet", ".alice.testnet", "alice.testnet.",
    "a" * 57 + ".testnet", "g" * 64, "alice.testnet.evil", "álîce.testnet",
])
@pytest.mark.parametrize("field", ["signer_id", "contract_id"])
def test_invalid_or_non_testnet_accounts_are_rejected(account, field):
    api = integrity()
    public, _ = api.create_commitment(b"artifact")
    kwargs = {"network": "testnet", "signer_id": "alice.testnet", "contract_id": "receipts.testnet"}
    kwargs[field] = account
    with pytest.raises(ValueError):
        api.near_anchor_action(public, **kwargs)


@pytest.mark.parametrize("network", [None, True, "", "mainnet", "betanet", "TESTNET"])
def test_network_must_explicitly_be_testnet(network):
    api = integrity()
    public, _ = api.create_commitment(b"artifact")
    with pytest.raises(ValueError):
        api.near_anchor_action(public, network=network, signer_id="alice.testnet", contract_id="receipt.testnet")


def test_action_rejects_malformed_or_overdisclosing_public_receipt():
    api = integrity()
    public, _ = api.create_commitment(b"artifact")
    for value in (None, {}, {**public, "creator": "alice"}, {**public, "commitment": "g" * 64},
                  {**public, "schema_version": 1}):
        with pytest.raises(ValueError):
            api.near_anchor_action(value, network="testnet", signer_id="alice.testnet", contract_id="receipt.testnet")
