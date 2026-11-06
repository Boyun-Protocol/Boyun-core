"""Content identity shared by run manifests and local checkpoints."""
from hashlib import sha256
from pathlib import Path


def engine_fingerprint():
    digest = sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        name, data = path.name.encode(), path.read_bytes()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()
