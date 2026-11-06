"""Public-source collection and forward history, with no credentials or LLMs."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from .io_helpers import read_json, json_bytes, write_artifacts
from .public_archive import PublicArchive
from .public_capture import collect_public, validate_public_config


def register_public_commands(commands):
    root = commands.add_parser('public-data', help='Public-only forward capture; no keys or backfill')
    sub = root.add_subparsers(dest='public_command', required=True)
    for name in ('collect', 'watch', 'status', 'export', 'ingest'):
        parser = sub.add_parser(name)
        parser.add_argument('--archive', required=True)
        if name in ('collect', 'watch'):
            parser.add_argument('--pools', required=True)
            parser.add_argument('--allow-network', action='store_true')
        if name == 'watch':
            parser.add_argument('--interval', type=int, default=60)
            parser.add_argument('--max-cycles', type=int)
        if name == 'export':
            parser.add_argument('--network', choices=('near', 'solana'), required=True)
            parser.add_argument('--output', required=True)
        if name == 'ingest':
            parser.add_argument('--input', required=True)


def _read(path):
    if Path(path).stat().st_size > 2 * 1024 * 1024:
        raise ValueError('input limit')
    return read_json(path)


def watch_public(*, config, archive_path, allow_network=False, interval=60,
                 max_cycles=None, collect_fn=None, sleep_fn=None):
    try:
        import fcntl
    except ImportError:
        raise ValueError('watch requires a POSIX process lock on this platform') from None
    if allow_network is not True or type(interval) is not int or not 60 <= interval <= 86400:
        raise ValueError('explicit opt-in and interval of 60 to 86400 seconds required')
    if max_cycles is not None and (type(max_cycles) is not int or not 1 <= max_cycles <= 100000):
        raise ValueError('invalid cycle limit')
    validate_public_config(config)
    path = Path(archive_path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(str(path) + '.watch.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('public collector already running') from None
        with PublicArchive(path) as archive:
            cycle = 0
            while max_cycles is None or cycle < max_cycles:
                delay = interval
                try:
                    receipt = (collect_fn or collect_public)(config=config, archive=archive, allow_network=True, max_requests=8)
                    print(json.dumps({key: receipt.get(key) for key in ('finished_at', 'request_count', 'success_count', 'failure_count', 'rate_limited')}), flush=True)
                    if receipt.get('rate_limited'):
                        delay = max(interval, 300, *(min(3600, p.get('retry_after_seconds') or 0) for p in receipt.get('pools', [])))
                except (ValueError, OSError, sqlite3.Error):
                    print('Public collection cycle failed; existing archive retained. Next cycle waits.', file=sys.stderr, flush=True)
                    delay = max(interval, 300)
                cycle += 1
                if max_cycles is None or cycle < max_cycles:
                    (sleep_fn or time.sleep)(delay)
    finally:
        os.close(fd)
    return 0


def run_public_command(args):
    if args.command != 'public-data':
        return None
    try:
        if args.public_command in ('collect', 'watch'):
            if not args.allow_network:
                raise ValueError('explicit network opt-in required')
            config = _read(args.pools)
            validate_public_config(config)
            if args.public_command == 'watch':
                return watch_public(config=config, archive_path=args.archive, allow_network=True,
                                    interval=args.interval, max_cycles=args.max_cycles)
            with PublicArchive(args.archive) as archive:
                result = collect_public(config=config, archive=archive, allow_network=True, max_requests=8)
        elif args.public_command == 'ingest':
            with PublicArchive(args.archive) as archive:
                result = archive.record_snapshot(_read(args.input))
        else:
            with PublicArchive(args.archive, read_only=True) as archive:
                if args.public_command == 'status':
                    result = archive.status()
                else:
                    result = archive.export_snapshot(args.network)
                    write_artifacts([(Path(args.output), json_bytes(result))])
                    print('Exported bounded observed snapshot; full history remains unverified.')
                    return 0
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
        print('Public-data operation failed; check explicit inputs, archive access and collection status.', file=sys.stderr)
        return 2
