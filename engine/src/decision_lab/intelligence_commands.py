"""Private intelligence artifacts and explicit opt-in read-only history requests."""
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys

from .io_helpers import json_bytes, read_json, reserve_outputs, write_artifacts
from .market_sources import CollectionError, collect_pool_trades


def register_intelligence_commands(commands):
    root = commands.add_parser("intelligence", help="Observed wallet/topic evidence; not identity or calibrated odds")
    subcommands = root.add_subparsers(dest="intelligence_command", required=True)
    for name in ("wallets", "topics"):
        command = subcommands.add_parser(name)
        command.add_argument("--input", required=True)
        command.add_argument("--output", required=True)
    collect = subcommands.add_parser("collect", help="Opt-in CoinGecko Pro 30-day pool history; account required")
    collect.add_argument("--network", required=True, choices=("near", "solana"))
    collect.add_argument("--pools", required=True, help="Explicit list of pool/token metadata")
    collect.add_argument("--api-key-env", required=True)
    collect.add_argument("--allow-network", action="store_true")
    collect.add_argument("--captured-at", help="UTC ending Z; defaults to current whole-second UTC")
    collect.add_argument("--max-pages", type=int, default=5)
    collect.add_argument("--max-records", type=int, default=1000)
    collect.add_argument("--output", required=True)


def _read(path):
    if Path(path).stat().st_size > 2 * 1024 * 1024:
        raise ValueError("input exceeds limit")
    return read_json(path)


def _attempt(status, *, code=None, request_count=None, remote_outcome="unknown"):
    return {"schema_version": "history-collection-status.v1", "status": status,
            "error_code": code, "request_count": request_count,
            "remote_outcome": remote_outcome, "automatic_retry": False,
            "provider": "coingecko-pro", "cost_usd": None,
            "limitations": "Read-only GET attempts may consume provider credits; a transport attempt does not prove remote success. No automatic retry."}


def _collect(args):
    if not args.allow_network:
        raise ValueError("explicit network opt-in required")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", args.api_key_env):
        raise ValueError("invalid environment variable name")
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise ValueError("selected key absent")
    pools = _read(args.pools)
    captured_at = args.captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    output = Path(args.output)
    receipt_path = output.with_suffix(".collection.json")
    if output == receipt_path:
        raise ValueError("output conflicts with receipt")
    with reserve_outputs((output, receipt_path)) as reserved:
        marker = {"schema_version": "history-collection-status.v1", "status": "dispatch_pending",
                  "remote_outcome": "unknown", "automatic_retry": False}
        reserved.write(output, json_bytes(marker))
        reserved.write(receipt_path, json_bytes(_attempt("dispatch_pending")))
        reserved.sync_directories()
        reserved.preserve = True
        try:
            snapshot, receipt = collect_pool_trades(network=args.network, pools=pools, captured_at=captured_at,
                api_key=api_key, max_pages=args.max_pages, max_records=args.max_records)
        except BaseException as error:
            attempts, code, remote = None, "unexpected_failure", "unknown"
            if isinstance(error, CollectionError):
                attempts = error.request_count
                code = error.code if error.code in {"invalid_request", "invalid_response", "transport_failed"} else "collection_failure"
                remote = error.remote_outcome
            marker.update(status="failed", remote_outcome=remote)
            reserved.write(receipt_path, json_bytes(_attempt("failed", code=code, request_count=attempts, remote_outcome=remote)))
            reserved.write(output, json_bytes(marker))
            if not isinstance(error, Exception):
                raise
            print("History collection failed; sanitized private status retained. No automatic retry; inspect provider usage before resubmitting.", file=sys.stderr)
            return 2
        reserved.write(receipt_path, json_bytes(receipt))
        reserved.write(output, json_bytes(snapshot))
    print("Saved private pool-trade snapshot and collection receipt. Inspect pagination limits; full chain coverage is unverified.")
    return 0


def run_intelligence_command(args):
    """Return None for unrelated commands, otherwise an exit status."""
    if args.command != "intelligence":
        return None
    try:
        if args.intelligence_command == "collect":
            return _collect(args)
        if args.intelligence_command == "wallets":
            from .wallet_evidence import analyze_wallets
            result = analyze_wallets(_read(args.input))
        elif args.intelligence_command == "topics":
            from .topic_evidence import analyze_topics
            result = analyze_topics(_read(args.input))
        else:
            raise ValueError("unknown intelligence command")
        write_artifacts([(Path(args.output), json_bytes(result))])
    except (ValueError, OSError, KeyError, TypeError, OverflowError):
        print("Cannot complete intelligence command: check opt-in/key, bounded input and new output paths. No credentials or raw provider errors are printed.", file=sys.stderr)
        return 2
    print("Saved private evidence analysis. Wallet identity, source claims and future outcomes are not verified.")
    return 0
