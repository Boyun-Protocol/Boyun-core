"""Named random streams; no process-randomized hash() or shared draw cursor."""
import hashlib
import json
import random


def keyed_rng(seed: int, *identity: object) -> random.Random:
    payload = json.dumps([seed, *identity], ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return random.Random(int.from_bytes(hashlib.sha256(payload.encode()).digest(), "big"))
