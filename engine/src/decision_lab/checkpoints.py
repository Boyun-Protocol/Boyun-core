"""Trusted local completed-world recovery; checksums are not authentication."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import tempfile

try:
    import fcntl
except ImportError:  # Other offline commands remain available on non-POSIX hosts.
    fcntl = None

from .actors import _integer
from .identity import engine_fingerprint
from .io_helpers import ensure_directory, sync_directory as _sync_directory
from .policy_bundles import _keys
from .policy_preparation import _canonical, _strict_json
from .randomness import keyed_rng
from .simulation import _prepare_simulation, _summarize_worlds, _world


def _digest(value):
    return sha256(_canonical(value).encode()).hexdigest()


@contextmanager
def _locked(path):
    if fcntl is None:
        raise ValueError("checkpoint locking requires a POSIX host")
    ensure_directory(path.parent)
    lock = path.with_name(path.name + ".lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock, flags, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("checkpoint is in use") from None
        yield
    finally:
        os.close(fd)
    # Keep this inode stable for later callers; an empty lock file is harmless.


def _save(path, identity, completed, *, first=False):
    body = {"schema_version": "run-checkpoint.v1", "identity": identity, "completed_worlds": completed}
    body["content_sha256"] = _digest(body)
    encoded = (_canonical(body) + "\n").encode()
    if first:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            _sync_directory(path.parent)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _validate_worlds(completed, value, cast, seed, worlds):
    if type(completed) is not list or len(completed) > worlds:
        raise ValueError("invalid completed world prefix")
    keys = {"world_id", "external_draws", "initial_totals", "ending_totals", "project_cash_cents",
            "net_profit_cents", "unsold_project_tokens", "locked_project_lp_shares", "campaign_paid_cents",
            "unpaid_obligations_cents", "delivered_campaigns", "participant_buys", "participant_sells",
            "observed_message_count", "proposal_rejections", "cash_bridge", "trace", "trace_limited_to_events"}
    outside = {a.owner_id: a.initial_cash_cents for a in cast.actors if a.owner_id != "project"}
    initial = [sum(outside.values()) + value["capital_cents"], value["founder_tokens"]]
    for i, world in enumerate(completed):
        _keys(world, keys, "checkpoint world")
        if type(world["world_id"]) is not int or world["world_id"] != i:
            raise ValueError("checkpoint worlds must be a contiguous prefix")
        for key in keys - {"external_draws", "initial_totals", "ending_totals", "net_profit_cents", "cash_bridge", "trace"}:
            _integer(world[key], key)
        if type(world["net_profit_cents"]) is not int:
            raise ValueError("invalid world profit")
        for key in ("initial_totals", "ending_totals"):
            if type(world[key]) is not list or len(world[key]) != 2:
                raise ValueError("invalid checkpoint totals")
            for amount in world[key]:
                _integer(amount, "checkpoint total")
            if world[key] != initial:
                raise ValueError("checkpoint conservation mismatch")
        expected_draws = {"catalyst_draw_bps": keyed_rng(seed, "external", i, "catalyst").randrange(10000),
                          "followup_draw_bps": keyed_rng(seed, "external", i, "followup").randrange(10000)}
        if _canonical(world["external_draws"]) != _canonical(expected_draws):
            raise ValueError("checkpoint external draws mismatch")
        if world["net_profit_cents"] != world["project_cash_cents"] - value["capital_cents"]:
            raise ValueError("checkpoint cash bridge mismatch")
        bridge_keys = {"contributed_capital_cents", "launch_paid_cents", "lp_cash_allocated_cents",
                       "campaign_paid_cents", "founder_sale_proceeds_cents", "ending_withdrawable_cash_cents"}
        _keys(world["cash_bridge"], bridge_keys, "cash bridge")
        bridge = world["cash_bridge"]
        for amount in bridge.values():
            _integer(amount, "cash bridge amount")
        ending = (bridge["contributed_capital_cents"] - bridge["launch_paid_cents"] -
                  bridge["lp_cash_allocated_cents"] - bridge["campaign_paid_cents"] + bridge["founder_sale_proceeds_cents"])
        if (bridge["contributed_capital_cents"] != value["capital_cents"] or
                bridge["ending_withdrawable_cash_cents"] != world["project_cash_cents"] or
                bridge["campaign_paid_cents"] != world["campaign_paid_cents"] or ending != world["project_cash_cents"]):
            raise ValueError("checkpoint cash bridge mismatch")
        limit = 500 if i < 3 else 0
        if world["trace_limited_to_events"] != limit or type(world["trace"]) is not list or len(world["trace"]) > limit:
            raise ValueError("invalid checkpoint trace")


def run_checkpointed(scenario, pool, *, checkpoint_path, worlds=100, seed=42, plan="launch_now",
                     policy_bundle=None, resume=False, max_new_worlds=None):
    """Return a complete report, or None after a requested completed-world pause.

    Only resume checkpoints written by a trusted local writer. An unkeyed
    checksum catches corruption; a person able to rewrite it can forge results.
    This does not persist an incomplete world's internal state.
    """
    if type(resume) is not bool:
        raise ValueError("resume must be boolean")
    if max_new_worlds is not None:
        _integer(max_new_worlds, "max_new_worlds", minimum=1)
    value, cast, bundle = _prepare_simulation(scenario, pool, worlds, seed, plan, policy_bundle)
    identity = {"scenario_sha256": _digest(value), "persona_pool_sha256": _digest(pool),
                "policy_bundle_sha256": bundle.sha256 if bundle else None,
                "world_count": worlds, "seed": seed, "plan": plan,
                "engine_source_sha256": engine_fingerprint(), "python": platform.python_version(),
                "implementation": platform.python_implementation()}
    path = Path(checkpoint_path)
    with _locked(path):
        if path.is_symlink():
            raise ValueError("checkpoint cannot be a symlink")
        completed = []
        if resume:
            saved = _strict_json(path.read_text())
            _keys(saved, {"schema_version", "identity", "completed_worlds", "content_sha256"}, "checkpoint")
            content = {key: item for key, item in saved.items() if key != "content_sha256"}
            if saved["schema_version"] != "run-checkpoint.v1" or saved["content_sha256"] != _digest(content):
                raise ValueError("checkpoint version or checksum mismatch")
            if _canonical(saved["identity"]) != _canonical(identity):
                raise ValueError("checkpoint inputs, code or runtime changed")
            completed = saved["completed_worlds"]
            _validate_worlds(completed, value, cast, seed, worlds)
        else:
            if path.exists():
                raise ValueError("checkpoint already exists; use explicit resume")
            _save(path, identity, completed, first=True)
        end = worlds if max_new_worlds is None else min(worlds, len(completed) + max_new_worlds)
        for world_id in range(len(completed), end):
            world = _world(value, cast, seed, world_id, plan, world_id < 3, bundle)
            completed.append(world)
            _save(path, identity, completed)
        if len(completed) < worlds:
            return None
        return _summarize_worlds(value, pool, cast, completed, seed, plan, bundle)
