"""Strict local JSON and exclusive mode0600 artifact reservations."""
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object keys are not supported")
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite JSON")
    return number


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                      parse_float=_finite_float,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def open_private(path):
    """Create a new writable private file, never following an existing symlink."""
    return os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600), "w+b")


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_directory(path):
    """Create ancestors and persist their links before acknowledging side effects."""
    path = Path(path)
    missing, cursor = [], path
    while not cursor.exists():
        missing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    path.mkdir(parents=True, exist_ok=True)
    for directory in reversed(missing):
        sync_directory(directory.parent)
        sync_directory(directory)


class _Reservation:
    def __init__(self):
        self.handles = {}
        self.preserve = False

    def write(self, path, data):
        handle = self.handles[Path(path)]
        handle.seek(0)
        handle.write(data)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())

    def sync_directories(self):
        """Flush created directory entries before an external side effect."""
        for parent in {path.parent for path in self.handles}:
            sync_directory(parent)


@contextmanager
def reserve_outputs(paths):
    """Reserve every output before side effects; rollback only our own inodes.

    Setting preserve retains evidence even when later work fails. This is used
    immediately before dispatching an opt-in provider request.
    """
    reservation = _Reservation()
    try:
        for path in map(Path, paths):
            ensure_directory(path.parent)
            handle = open_private(path)
            reservation.handles[path] = handle
        yield reservation
    except BaseException:
        if not reservation.preserve:
            for path, handle in reservation.handles.items():
                try:
                    local = path.lstat()
                    owned = os.fstat(handle.fileno())
                    if (local.st_dev, local.st_ino) == (owned.st_dev, owned.st_ino):
                        path.unlink()
                except FileNotFoundError:
                    pass
        raise
    finally:
        for handle in reservation.handles.values():
            handle.close()


def write_artifacts(artifacts):
    with reserve_outputs(path for path, _ in artifacts) as reserved:
        for path, data in artifacts:
            reserved.write(path, data)
