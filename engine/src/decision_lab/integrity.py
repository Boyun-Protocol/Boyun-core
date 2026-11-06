"""Private artifact openings and unsigned, unverified NEAR testnet actions.

This module performs no I/O. A commitment binds bytes when opened; it neither
encrypts the artifact nor attests its author, truth, creation time or accuracy.
"""
from hashlib import sha256
from hmac import compare_digest
import re
import secrets


_PUBLIC_SCHEMA = "artifact-commitment.v1"
_PRIVATE_SCHEMA = "artifact-opening.v1"
_DOMAIN = b"decision-lab/artifact-commitment.v1\x00"
_HEX32 = re.compile(r"[0-9a-f]{64}")
_NAMED_ACCOUNT = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")


def _hex32(value):
    return type(value) is str and _HEX32.fullmatch(value) is not None


def _valid_public(public):
    return (type(public) is dict and set(public) == {"schema_version", "commitment"}
            and type(public["schema_version"]) is str
            and public["schema_version"] == _PUBLIC_SCHEMA and _hex32(public["commitment"]))


def _valid_private(private):
    return (type(private) is dict and set(private) == {"schema_version", "salt", "artifact_sha256"}
            and type(private["schema_version"]) is str
            and private["schema_version"] == _PRIVATE_SCHEMA
            and _hex32(private["salt"]) and _hex32(private["artifact_sha256"]))


def _commitment(salt, artifact_digest):
    # Lengths are unsigned 64-bit big-endian byte counts. Both fields currently
    # have length 32; framing plus a domain keeps this format unambiguous.
    framed = (_DOMAIN + len(salt).to_bytes(8, "big") + salt
              + len(artifact_digest).to_bytes(8, "big") + artifact_digest)
    return sha256(framed).hexdigest()


def create_commitment(data: bytes) -> tuple[dict, dict]:
    """Commit exact bytes using a fresh private 32-byte cryptographic salt.

    Keep the private opening and original bytes separate from any public
    projection. Do not publish the raw artifact hash from the private opening.
    """
    if type(data) is not bytes:
        raise ValueError("artifact must be bytes")
    salt = secrets.token_bytes(32)
    digest = sha256(data).digest()
    return (
        {"schema_version": _PUBLIC_SCHEMA, "commitment": _commitment(salt, digest)},
        {"schema_version": _PRIVATE_SCHEMA, "salt": salt.hex(), "artifact_sha256": digest.hex()},
    )


def verify_commitment(data: bytes, public: dict, private: dict) -> bool:
    """Return False for malformed records, changed bytes or an incorrect opening."""
    if type(data) is not bytes or not _valid_public(public) or not _valid_private(private):
        return False
    digest = sha256(data).digest()
    if not compare_digest(digest.hex(), private["artifact_sha256"]):
        return False
    expected = _commitment(bytes.fromhex(private["salt"]), digest)
    return compare_digest(expected, public["commitment"])


def _testnet_account(account):
    # Named accounts are deliberately limited to descendants of testnet. A
    # 64-hex implicit account is network-neutral; network must still be explicit.
    return (type(account) is str and 2 <= len(account) <= 64
            and (_hex32(account) or (account.endswith(".testnet")
                                    and _NAMED_ACCOUNT.fullmatch(account) is not None)))


def near_anchor_action(public: dict, *, network: str, signer_id: str, contract_id: str) -> dict:
    """Prepare an unsigned call to the project's proposed receipt-contract ABI.

    Account syntax validation does not establish account existence, deployed
    code, contract compatibility or transaction success. The selected signer
    will be visible if a future client signs and submits this action.
    """
    if not _valid_public(public):
        raise ValueError("public commitment must match artifact-commitment.v1 exactly")
    if type(network) is not str or network != "testnet":
        raise ValueError("network must explicitly be testnet")
    if not _testnet_account(signer_id) or not _testnet_account(contract_id):
        raise ValueError("signer and contract must be valid testnet account identifiers")
    return {
        "schema_version": "near-anchor-action.v1", "network": network,
        "signer_id": signer_id, "receiver_id": contract_id, "status": "unsigned_unverified",
        "actions": [{"type": "FunctionCall", "params": {
            "methodName": "register_commitment", "args": {"commitment": public["commitment"]},
            "gas": "30000000000000", "deposit": "0"}}],
    }
