"""Bounded local authoring and replay-validated choice sessions, no inference."""
from copy import deepcopy
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import stat
from threading import RLock
from uuid import uuid4

from .scenario_authoring import (apply_authoring_response, authoring_guidelines, capabilities,
                                 compile_draft, prepare_authoring_request)
from .web_jobs import BusyError, MAX_BODY, MAX_RESULT_BYTES, _bounded_json, _integer, encode

MAX_WORLDS = 32
MAX_BROWSER_PACKAGE = 262_144
MAX_BROWSER_WORK = 200_000
_WORLD_ID = re.compile(r'[0-9a-f]{32}\Z')
_EXAMPLES = (
    ('ticker', 'Ticker evaluation', 'ticker-evaluation-draft.v1.json'),
    ('stress', 'DeFi stress', 'defi-stress-draft.v1.json'),
    ('launch', 'Explicit launch', 'launch-explicit.v1.json'),
    ('choice', 'Product release choices', 'choice-world-draft.v1.json'),
)


class RevisionConflict(ValueError):
    """A world advanced since the caller's last accepted revision."""


def _exact(data, keys):
    if type(data) is not dict or set(data) != set(keys):
        raise ValueError('invalid Studio request fields')


def _ascii_size(value):
    # Six ASCII characters bound each UTF-8 character and pretty JSON adds
    # whitespace. The separate structural estimates below cover indentation.
    return len(json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode())


def scenario_preflight(data):
    """Reject expansion before simulation; final byte guard still applies."""
    if type(data) is not dict or set(data) - {'kind', 'draft', 'worlds', 'seed'} or 'draft' not in data:
        raise ValueError('invalid scenario job')
    worlds = _integer(data.get('worlds', 10), 1, 100)
    seed = _integer(data.get('seed', 42), 0, 2**63 - 1)
    compiled = compile_draft(data['draft'])
    if not compiled['ready']:
        raise ValueError('draft is not ready')
    package = compiled['package']
    size = _ascii_size(package)
    if size > MAX_BROWSER_PACKAGE:
        raise ValueError('browser package size budget exceeded')
    mode = package['schema_version']
    estimate = size * 8 + 131_072
    if mode == 'event-chain.v1':
        rules = package['rules']
        effects = sum(max(len(o['effects']) for o in r['outcomes']) for r in rules)
        if worlds * (len(rules) + effects) > MAX_BROWSER_WORK:
            raise ValueError('browser rule work budget exceeded')
        # Each trace copies only the largest outcome and provenance, plus
        # identifiers and resolved integer effects; never all outcomes.
        trace = sum(max(_ascii_size(o) for o in r['outcomes']) +
                    _ascii_size(r['probability_provenance']) + 2048 for r in rules)
        estimate += worlds * (trace * 4 + len(package['metrics']) * 1024 + 4096)
    elif mode == 'choice-world.v1':
        _integer(seed, 0, 10**9)
        scenes = package['scenes']
        work = sum(len(package['metrics']) * (1 + len(c['outcomes'])) + len(c['requirements']) +
                   len(c['immediate_effects']) + sum(len(o['effects']) for o in c['outcomes'])
                   for scene in scenes for c in scene['choices'])
        if worlds * work > MAX_BROWSER_WORK:
            raise ValueError('browser choice work budget exceeded')
        # Histories contain metrics and IDs, not package copies per transition.
        estimate += worlds * (len(scenes) * (4096 + len(package['metrics']) * 1024) + size * 2 + 4096)
    elif mode == 'explicit-launch.v1':
        scenario, cast = package['scenario'], package['cast']
        actors = cast['actors']
        visits = len(actors) * (scenario['horizon_hours'] // scenario['visit_interval_hours'] + 1) * worlds
        publications = len(scenario['campaigns']) + len(scenario['competitor_messages']) + (2 if scenario['news_enabled'] else 0)
        if visits > MAX_BROWSER_WORK or visits * max(1, publications) > MAX_BROWSER_WORK * 10:
            raise ValueError('browser actor work budget exceeded')
        alternatives = {s['actor_id']: s['variants'] for s in cast.get('alternatives', [])}
        policy_size = sum(max([_ascii_size(a)] + [_ascii_size({**a, **v['overrides']}) + _ascii_size(v['id'])
                                               for v in alternatives.get(a['id'], [])]) for a in actors)
        max_id = max([len(a['id']) for a in actors] + [64])
        estimate += worlds * (policy_size * 4 + 8192) + min(worlds, 3) * 500 * (2048 + max_id * 6)
    else:
        raise ValueError('unsupported browser module')
    if estimate > MAX_RESULT_BYTES:
        raise ValueError('expanded browser result budget exceeded')
    return {'package': deepcopy(package), 'worlds': worlds, 'seed': seed}


def _example(filename):
    # Callers cannot supply filenames: only the fixed public catalog is read.
    resource = files('decision_lab').joinpath('data/scenario_examples', filename)
    try:
        raw = resource.read_text()
    except FileNotFoundError:
        raw = (Path(__file__).parents[2] / 'examples' / filename).read_text()
    value = json.loads(raw)
    if value['schema_version'] != 'scenario-draft.v1':
        value = {'schema_version': 'scenario-draft.v1', 'id': value['id'], 'revision': 0,
                 'event_description': value['event_description'], 'fields': [], 'engine_input': value}
    return value


class StudioAPI:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self._lock = RLock()
        self._worlds = {}

    def bootstrap(self):
        examples = []
        for example_id, label, filename in _EXAMPLES:
            examples.append({'id': example_id, 'label': label, 'draft': _example(filename)})
        return {'capabilities': capabilities(), 'guidelines': authoring_guidelines(), 'examples': examples,
                'limits': {'max_worlds': 100, 'max_choice_sessions': MAX_WORLDS,
                           'max_body_bytes': MAX_BODY, 'max_result_bytes': MAX_RESULT_BYTES,
                           'max_browser_package_bytes': MAX_BROWSER_PACKAGE,
                           'max_browser_work': MAX_BROWSER_WORK},
                'providers': {'mode': 'external', 'model_calls': 0, 'connected': False,
                              'description': 'Export a request and import a revision-bound response. No provider is called.'}}

    def author(self, action, data):
        _bounded_json(data)
        if action == 'validate':
            _exact(data, {'draft'})
            return compile_draft(data['draft'])
        if action == 'prepare':
            _exact(data, {'draft', 'model'})
            return prepare_authoring_request(data['draft'], data['model'])
        if action == 'apply':
            _exact(data, {'draft', 'response'})
            draft = apply_authoring_response(data['draft'], data['response'])
            return {'draft': draft, 'compilation': compile_draft(draft)}
        raise KeyError('unknown Studio operation')

    @staticmethod
    def _record(world_id, revision, snapshot):
        from .choice_worlds import choice_options
        return {'id': world_id, 'revision': revision, 'snapshot': deepcopy(snapshot), 'choices': choice_options(snapshot)}

    def _path(self, world_id):
        if type(world_id) is not str or not _WORLD_ID.fullmatch(world_id):
            raise KeyError('unknown local world')
        return self.output_dir / ('world-' + world_id + '.json')

    def _read(self, world_id):
        from .choice_worlds import validate_choice_snapshot
        fd = os.open(self._path(world_id), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BODY:
                raise ValueError('invalid saved local world')
            raw = handle.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError('saved world size limit exceeded')
        from .policy_preparation import _strict_json
        record = _strict_json(raw.decode('utf-8'))
        _exact(record, {'id', 'revision', 'snapshot'})
        if record['id'] != world_id:
            raise ValueError('saved world identity mismatch')
        _integer(record['revision'], 0, 10**9)
        record['snapshot'] = validate_choice_snapshot(record['snapshot'])
        return record

    def _get(self, world_id):
        # Disk is authoritative even after a failed write or later lazy reload.
        record = self._read(world_id)
        if world_id not in self._worlds and len(self._worlds) >= MAX_WORLDS:
            raise BusyError('choice session capacity reached')
        self._worlds[world_id] = record
        return record

    def _save(self, record):
        content = encode(record)
        if len(content) > MAX_BODY:
            raise ValueError('saved world size limit exceeded')
        path = self._path(record['id'])
        temporary = self.output_dir / ('.world-' + uuid4().hex + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        self._worlds[record['id']] = deepcopy(record)

    def _saved_capacity_reached(self):
        count = 0
        with os.scandir(self.output_dir) as entries:
            for entry in entries:
                if re.fullmatch(r'world-[0-9a-f]{32}\.json', entry.name):
                    count += 1
                    if count >= MAX_WORLDS:
                        return True
        return False

    def _new(self, snapshot):
        if len(self._worlds) >= MAX_WORLDS or self._saved_capacity_reached():
            raise BusyError('choice session capacity reached')
        record = {'id': uuid4().hex, 'revision': 0, 'snapshot': snapshot}
        result = self._record(record['id'], 0, snapshot)
        self._save(record)
        return result

    def get_world(self, world_id):
        with self._lock:
            record = self._get(world_id)
            return self._record(record['id'], record['revision'], record['snapshot'])

    def create_world(self, data):
        from .choice_worlds import start_choice_world
        _exact(data, {'package', 'seed', 'world_id'})
        with self._lock:
            return self._new(start_choice_world(data['package'], seed=data['seed'], world_id=data['world_id']))

    def restore_world(self, data):
        from .choice_worlds import validate_choice_snapshot
        _exact(data, {'snapshot'})
        with self._lock:
            return self._new(validate_choice_snapshot(data['snapshot']))

    def mutate_world(self, world_id, action, data):
        from .choice_worlds import step_choice_world, fork_choice_world
        _exact(data, {'choice_id', 'action_id', 'expected_revision'} if action == 'step' else {'branch_id', 'expected_revision'})
        expected = _integer(data['expected_revision'], 0, 10**9)
        with self._lock:
            record = self._get(world_id)
            if action == 'step':
                # Only an exact duplicate action may bypass CAS. Core verifies
                # both action identity and selected choice against full history.
                repeated = any(item['action_id'] == data['action_id'] for item in record['snapshot']['history'])
                if expected > record['revision'] or (expected != record['revision'] and not repeated):
                    raise RevisionConflict('stale choice revision')
                updated = step_choice_world(record['snapshot'], data['choice_id'], data['action_id'])
                if updated == record['snapshot']:
                    return self._record(world_id, record['revision'], updated)
                new_record = {'id': world_id, 'revision': record['revision'] + 1, 'snapshot': updated}
                result = self._record(world_id, new_record['revision'], updated)
                self._save(new_record)
                return result
            if action != 'fork':
                raise KeyError('unknown local operation')
            if expected != record['revision']:
                raise RevisionConflict('stale choice revision')
            return self._new(fork_choice_world(record['snapshot'], data['branch_id']))
