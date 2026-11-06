"""Append-only local public-swap observations; coverage is always unverified.

SQLite transactions preserve event identity across overlapping provider slices.
An archive retains raw observations, including rows the cohort analyzer excludes.
Neither deduplication nor repeated overlapping polls proves complete history.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from threading import RLock
from urllib.parse import quote

from .wallet_evidence import _bounded_json, _canonical, _date, _iso, _text, analyze_wallets

_MAX_BYTES = 2 * 1024 * 1024


def _stamp(value):
    return _date(value, 'timestamp').isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _display(value):
    return _iso(_date(value, 'timestamp')) if value is not None else None


def _identity(network, address):
    if network not in {'near', 'solana'} or type(network) is not str:
        raise ValueError('network must be near or solana')
    _text(address, 'pool_address')


def _public_url(network, address):
    return f'https://api.geckoterminal.com/api/v2/networks/{network}/pools/{quote(address, safe="")}/trades'


def _cost(value):
    nodes = chars = 0
    stack = [value]
    while stack:
        item = stack.pop()
        nodes += 1
        if isinstance(item, dict):
            chars += sum(map(len, item))
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, str):
            chars += len(item)
    return nodes, chars


class PublicArchive:
    """Operator-selected private SQLite file; no HTTP endpoint chooses its path."""

    def __init__(self, path, read_only=False):
        self.path = Path(path)
        self.read_only = read_only
        self._lock = RLock()
        if self.path.is_symlink() or self.path.exists() and not self.path.is_file():
            raise ValueError('archive must be a regular nonsymlink file')
        if read_only and not self.path.exists():
            raise ValueError('read-only archive must already exist')
        if not read_only:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not self.path.exists():
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
        self._db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro' if read_only else str(self.path),
                                   uri=read_only, timeout=10, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA busy_timeout=10000')
        self._db.execute('PRAGMA foreign_keys=ON')
        try:
            if read_only:
                if self._db.execute('PRAGMA user_version').fetchone()[0] != 1:
                    raise ValueError('unsupported public archive schema')
                self._db.execute('SELECT network FROM pools LIMIT 1')
            else:
                version = self._db.execute('PRAGMA user_version').fetchone()[0]
                if version not in {0, 1}:
                    raise ValueError('unsupported public archive schema')
                self._db.executescript('''
                    CREATE TABLE IF NOT EXISTS pools (
                        network TEXT NOT NULL, address TEXT NOT NULL, name TEXT,
                        base_token TEXT, quote_token TEXT, source_url TEXT,
                        PRIMARY KEY(network,address));
                    CREATE TABLE IF NOT EXISTS events (
                        network TEXT NOT NULL, pool TEXT NOT NULL, event_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL, canonical TEXT NOT NULL, sha256 TEXT NOT NULL,
                        PRIMARY KEY(network,pool,event_id),
                        FOREIGN KEY(network,pool) REFERENCES pools(network,address));
                    CREATE INDEX IF NOT EXISTS events_time ON events(network,timestamp DESC);
                    CREATE TABLE IF NOT EXISTS captures (
                        id INTEGER PRIMARY KEY, network TEXT NOT NULL, pool TEXT NOT NULL,
                        captured_at TEXT NOT NULL, retrieved_at TEXT NOT NULL, source_url TEXT NOT NULL,
                        raw_rows INTEGER NOT NULL, new_rows INTEGER NOT NULL, duplicate_rows INTEGER NOT NULL,
                        earliest_at TEXT, latest_at TEXT, possible_gap INTEGER NOT NULL,
                        poll_interval_seconds REAL,
                        FOREIGN KEY(network,pool) REFERENCES pools(network,address));
                    CREATE TABLE IF NOT EXISTS failures (
                        id INTEGER PRIMARY KEY, network TEXT NOT NULL, pool TEXT NOT NULL,
                        at TEXT NOT NULL, error_code TEXT NOT NULL,
                        FOREIGN KEY(network,pool) REFERENCES pools(network,address));
                    PRAGMA user_version=1;
                ''')
        except Exception:
            self._db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        with self._lock:
            self._db.close()

    @contextmanager
    def _write(self):
        if self.read_only:
            raise ValueError('archive is read-only')
        with self._lock:
            self._db.execute('BEGIN IMMEDIATE')
            try:
                yield
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise

    @contextmanager
    def _read(self):
        """Keep metadata and event queries in one SQLite snapshot during polling."""
        with self._lock:
            self._db.execute('BEGIN')
            try:
                yield
            finally:
                self._db.rollback()

    def _pool(self, network, address, metadata=None):
        row = self._db.execute('SELECT * FROM pools WHERE network=? AND address=?', (network, address)).fetchone()
        if row is None:
            total = self._db.execute('SELECT count(*) FROM pools').fetchone()[0]
            count = self._db.execute('SELECT count(*) FROM pools WHERE network=?', (network,)).fetchone()[0]
            if total >= 8 or count >= 4:
                raise ValueError('archive pool limit: four per network, eight total')
            self._db.execute('INSERT INTO pools(network,address) VALUES (?,?)', (network, address))
        if metadata is not None:
            expected = (metadata['name'], metadata['base_token_address'], metadata['quote_token_address'], metadata['source_url'])
            if row is not None and row['source_url'] is not None:
                current = tuple(row[key] for key in ('name', 'base_token', 'quote_token', 'source_url'))
                if current != expected:
                    raise ValueError('conflicting immutable pool metadata')
            else:
                self._db.execute('UPDATE pools SET name=?,base_token=?,quote_token=?,source_url=? WHERE network=? AND address=?',
                                 (*expected, network, address))

    def record_snapshot(self, snapshot):
        """Validate fully before BEGIN; conflicting event IDs roll back the batch."""
        _bounded_json(snapshot)
        encoded = _canonical(snapshot).encode('utf-8')
        if len(encoded) > _MAX_BYTES:
            raise ValueError('snapshot exceeds 2 MiB')
        analyze_wallets(snapshot)
        network = snapshot['network']
        for pool in snapshot['pools']:
            if pool['source_url'] != _public_url(network, pool['address']):
                raise ValueError('archive only accepts public GeckoTerminal source endpoints')
        captured = _stamp(snapshot['captured_at'])
        prepared = []
        for pool in snapshot['pools']:
            rows = [(event['id'], _stamp(event['attributes']['block_timestamp']), _canonical(event))
                    for event in pool['trades']['data']]
            prepared.append((pool, rows))
        receipt = {'schema_version': 'public-history-capture.v1', 'network': network,
                   'captured_at': _display(captured), 'raw_rows': 0, 'new_trades': 0,
                   'duplicate_trades': 0, 'complete_history': False, 'pools': []}
        with self._write():
            for pool, rows in prepared:
                address = pool['address']
                self._pool(network, address, pool)
                previous = self._db.execute('SELECT max(timestamp) FROM events WHERE network=? AND pool=?', (network, address)).fetchone()[0]
                last_success = self._db.execute('SELECT max(retrieved_at) FROM captures WHERE network=? AND pool=?', (network, address)).fetchone()[0]
                new = duplicates = overlap = 0
                for event_id, timestamp, canonical in rows:
                    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
                    old = self._db.execute('SELECT sha256,canonical FROM events WHERE network=? AND pool=? AND event_id=?', (network, address, event_id)).fetchone()
                    if old is not None:
                        if old['sha256'] != digest or old['canonical'] != canonical:
                            raise ValueError('conflicting duplicate event ID in archive')
                        duplicates += 1
                        overlap += 1
                    else:
                        self._db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)', (network, address, event_id, timestamp, canonical, digest))
                        new += 1
                times = [row[1] for row in rows]
                earliest, latest = (min(times), max(times)) if times else (None, None)
                retrieved = _stamp(pool['retrieved_at'])
                gap = bool(previous and earliest and earliest > previous and len(rows) >= 300 and not overlap)
                interval = max(0.0, (_date(retrieved, 'retrieved_at') - _date(last_success, 'last_success_at')).total_seconds()) if last_success else None
                self._db.execute('''INSERT INTO captures(network,pool,captured_at,retrieved_at,source_url,raw_rows,new_rows,
                    duplicate_rows,earliest_at,latest_at,possible_gap,poll_interval_seconds) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (network, address, captured, retrieved, pool['source_url'], len(rows), new, duplicates, earliest, latest, int(gap), interval))
                receipt['raw_rows'] += len(rows)
                receipt['new_trades'] += new
                receipt['duplicate_trades'] += duplicates
                receipt['pools'].append({'address': address, 'raw_rows': len(rows), 'new_trades': new,
                                         'duplicate_trades': duplicates, 'possible_gap': gap})
        return receipt

    def record_failure(self, network, pool_address, at, error_code, pool_metadata=None):
        """Store a bounded machine code, never exception text, URLs or credentials."""
        _identity(network, pool_address)
        timestamp = _stamp(at)
        code = error_code if type(error_code) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', error_code) else 'collection_failed'
        with self._write():
            self._pool(network, pool_address)
            self._db.execute('INSERT INTO failures(network,pool,at,error_code) VALUES (?,?,?,?)', (network, pool_address, timestamp, code))
        return {'network': network, 'address': pool_address, 'at': _display(timestamp), 'error_code': code}

    def status(self):
        with self._read():
            pools = []
            for row in self._db.execute('SELECT * FROM pools ORDER BY network,address').fetchall():
                key = (row['network'], row['address'])
                events = self._db.execute('SELECT count(*),min(timestamp),max(timestamp) FROM events WHERE network=? AND pool=?', key).fetchone()
                captures = self._db.execute('SELECT count(*),max(retrieved_at),coalesce(sum(possible_gap),0),max(poll_interval_seconds) FROM captures WHERE network=? AND pool=?', key).fetchone()
                latest = self._db.execute('SELECT raw_rows FROM captures WHERE network=? AND pool=? ORDER BY id DESC LIMIT 1', key).fetchone()
                failures = self._db.execute('SELECT count(*),max(at) FROM failures WHERE network=? AND pool=?', key).fetchone()
                error = self._db.execute('SELECT error_code FROM failures WHERE network=? AND pool=? ORDER BY at DESC,id DESC LIMIT 1', key).fetchone()
                pools.append({'network': row['network'], 'address': row['address'], 'name': row['name'],
                              'source_url': row['source_url'], 'capture_count': captures[0], 'failed_capture_count': failures[0],
                              'trade_count': events[0], 'first_trade_at': _display(events[1]), 'last_trade_at': _display(events[2]),
                              'last_success_at': _display(captures[1]), 'latest_capture_rows': latest[0] if latest else 0,
                              'possible_gap_count': captures[2], 'max_poll_interval_seconds': captures[3],
                              'last_failure_at': _display(failures[1]), 'latest_error_code': error[0] if error else None,
                              'complete_history': False, 'continuity': 'unverified'})
            return {'schema_version': 'public-history-status.v1', 'pools': pools,
                    'total_trades': sum(pool['trade_count'] for pool in pools),
                    'capture_count': sum(pool['capture_count'] for pool in pools),
                    'failed_capture_count': sum(pool['failed_capture_count'] for pool in pools),
                    'complete_history': False, 'continuity': 'unverified',
                    'collection_mode': 'public_forward_observation', 'target_days': 30}

    def export_snapshot(self, network, limit=1000, as_of=None):
        """Newest bounded observed rows in the requested 30 days, never a backfill."""
        if type(network) is not str or network not in {'near', 'solana'}:
            raise ValueError('network must be near or solana')
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('export limit must be 1 to 1000')
        captured = _stamp(as_of or _iso(datetime.now(timezone.utc)))
        try:
            start = (_date(captured, 'as_of') - timedelta(days=30)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
        except OverflowError:
            raise ValueError('target window starts before supported dates') from None
        with self._read():
            rows = self._db.execute('SELECT * FROM pools WHERE network=? AND source_url IS NOT NULL ORDER BY address', (network,)).fetchall()
            if not rows:
                raise ValueError('no successful public pool observations for network')
            pools = {}
            for row in rows:
                retrieved = self._db.execute('SELECT max(retrieved_at) FROM captures WHERE network=? AND pool=?', (network, row['address'])).fetchone()[0]
                pools[row['address']] = {'address': row['address'], 'name': row['name'],
                    'base_token_address': row['base_token'], 'quote_token_address': row['quote_token'],
                    'source_url': row['source_url'], 'retrieved_at': _display(retrieved), 'trades': {'data': []}}
            used_bytes = nodes = chars = 0
            query = self._db.execute('SELECT pool,canonical FROM events WHERE network=? AND timestamp>=? AND timestamp<=? ORDER BY timestamp DESC,pool,event_id LIMIT ?', (network, start, captured, limit))
            for row in query:
                event = json.loads(row['canonical'])
                more_nodes, more_chars = _cost(event)
                used_bytes += len(row['canonical'].encode('utf-8'))
                nodes += more_nodes
                chars += more_chars
                if used_bytes > 1400000 or nodes > 95000 or chars > 1400000:
                    break
                pools[row['pool']]['trades']['data'].append(event)
        value = {'schema_version': 'wallet-observations.v1', 'network': network, 'target_days': 30,
                 'captured_at': _display(captured), 'pools': list(pools.values())}
        analyze_wallets(value)
        return value
