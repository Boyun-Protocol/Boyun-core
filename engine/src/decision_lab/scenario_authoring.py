"""Provider-independent authoring contract, separate from data-only execution.

Dynamic fields are authored by the caller. Compilation patches declared values
into a copy of an explicit engine input; it never infers missing assumptions.
"""
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
import json
import math
import re

from .stress_planning import STRESS_PLANNING_GUIDELINES


MAX_BYTES = 2_000_000
MAX_FIELDS = 128
ID = re.compile(r'[a-zA-Z][a-zA-Z0-9_-]{0,63}\Z')
DRAFT_KEYS = {'schema_version', 'id', 'revision', 'event_description', 'fields', 'engine_input'}
FIELD_KEYS = {'id', 'label', 'type', 'unit', 'required', 'value', 'minimum', 'maximum', 'choices', 'target', 'why', 'provenance'}
STATUSES = {'assumed', 'observed', 'estimated', 'model_proposal', 'user_supplied', 'unknown'}


def _canonical(value):
    nodes = 0
    def check(item, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 32 or nodes > 100_000:
            raise ValueError('input nesting exceeds limit')
        if type(item) is dict:
            if len(item) > 100_000:
                raise ValueError('input exceeds limit')
            if any(type(key) is not str for key in item):
                raise ValueError('JSON keys must be strings')
            for child in item.values():
                check(child, depth + 1)
        elif type(item) is list:
            if len(item) > 100_000:
                raise ValueError('input exceeds limit')
            for child in item:
                check(child, depth + 1)
        elif type(item) is str and len(item) > MAX_BYTES:
            raise ValueError('text exceeds limit')
        elif item is not None and type(item) not in {str, int, bool, float}:
            raise ValueError('only bounded JSON primitives are accepted')
        elif type(item) in {int, float} and (not math.isfinite(item) or abs(item) > 10**15):
            raise ValueError('integer exceeds limit')
    try:
        check(value)
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError, OverflowError, UnicodeError):
        raise ValueError('invalid or oversized JSON input') from None
    if len(raw) > MAX_BYTES:
        raise ValueError('invalid or oversized JSON input')
    return raw


def draft_digest(value):
    return sha256(_canonical(value)).hexdigest()


def authoring_guidelines():
    return (files('decision_lab').joinpath('data/scenario-authoring-guidelines.md').read_text()
            + '\n\n' + STRESS_PLANNING_GUIDELINES)


def capabilities():
    from .event_chains import event_chain_capabilities
    from .explicit_cast import explicit_launch_capabilities
    from .choice_worlds import choice_world_capabilities
    return {
        'schema_version': 'scenario-capabilities.v1', 'model_calls': 0,
        'draft_schema': 'scenario-draft.v1', 'authoring_response_schema': 'scenario-authoring-response.v1',
        'modules': [
            {'schema_version': 'event-chain.v1', 'kind': 'declared_event_metric_evaluation',
             'details': event_chain_capabilities()},
            {'schema_version': 'explicit-launch.v1', 'kind': 'single_asset_launch',
             'details': explicit_launch_capabilities()},
            {'schema_version': 'choice-world.v1', 'kind': 'interactive_declared_metrics',
             'details': choice_world_capabilities()},
        ],
        'field_contract': {
            'keys': sorted(FIELD_KEYS), 'types': ['integer', 'text', 'boolean', 'choice'],
            'provenance_keys': ['status', 'rationale', 'source_refs'], 'statuses': sorted(STATUSES),
            'target': 'JSON pointer to an existing engine-input object leaf, or null for context only.',
            'null_value': 'Unfilled; a required null blocks execution.',
        },
        'limits': {'max_bytes': MAX_BYTES, 'max_fields': MAX_FIELDS, 'max_json_nodes': 100_000,
                   'max_json_depth': 32, 'max_authored_numeric_magnitude': 10**15},
        'limitations': ['Validation does not establish source truth, statistical calibration or strategic realism.',
                        'Authoring and model/provider transport are outside execution.'],
    }


def _text(value, limit=4000):
    return type(value) is str and bool(value.strip()) and len(value) <= limit


def _identifier(value):
    return type(value) is str and ID.fullmatch(value) is not None


def _provenance(value):
    return (type(value) is dict and set(value) == {'status', 'rationale', 'source_refs'}
            and type(value['status']) is str and value['status'] in STATUSES
            and _text(value['rationale']) and type(value['source_refs']) is list
            and len(value['source_refs']) <= 32
            and all(_text(item, 2000) for item in value['source_refs']))


def _pointer(value):
    if not _text(value, 512) or not value.startswith('/'):
        raise ValueError('invalid target')
    parts = value[1:].split('/')
    if any(not part or re.search(r'~(?![01])', part) for part in parts):
        raise ValueError('invalid target')
    return tuple(part.replace('~1', '/').replace('~0', '~') for part in parts)


def _target_parent(package, parts):
    parent = package
    for part in parts[:-1]:
        if type(parent) is not dict or part not in parent:
            raise ValueError('target must exist')
        parent = parent[part]
    if type(parent) is not dict or parts[-1] not in parent or type(parent[parts[-1]]) in {dict, list}:
        raise ValueError('target must be an existing object leaf')
    if parts[0] in {'schema_version', 'id', 'event_description'}:
        raise ValueError('target cannot change input identity')
    return parent


def validate_package(value):
    """Return a deep validated module input; no generation or execution."""
    _canonical(value)
    if type(value) is not dict:
        raise ValueError('invalid execution input')
    kind = value.get('schema_version')
    if kind == 'event-chain.v1':
        from .event_chains import validate_event_chain
        return validate_event_chain(value)
    if kind == 'choice-world.v1':
        from .choice_worlds import validate_choice_world
        return validate_choice_world(value)
    if kind == 'explicit-launch.v1':
        if set(value) != {'schema_version', 'id', 'event_description', 'scenario', 'cast'} or not _identifier(value['id']) or not _text(value['event_description'], 8000):
            raise ValueError('invalid explicit launch wrapper')
        from .explicit_cast import validate_explicit_cast
        validate_explicit_cast(value['cast'], value['scenario'])
        return deepcopy(value)
    raise ValueError('unsupported execution module')


def compile_draft(value):
    """Return safe missing/invalid field issues, never guess a runnable input."""
    result = {'schema_version': 'scenario-compilation.v1', 'ready': False, 'draft_valid': True, 'issues': [],
              'package': None, 'package_sha256': None}
    def issue(path, code, message):
        if code != 'missing':
            result['draft_valid'] = False
        if len(result['issues']) < 64:
            result['issues'].append({'path': path, 'code': code, 'message': message})
    try:
        _canonical(value)
    except ValueError:
        issue('/', 'invalid_json', 'Supply bounded JSON without unsupported types.')
        return result
    if (type(value) is not dict or set(value) != DRAFT_KEYS or value.get('schema_version') != 'scenario-draft.v1'
            or not _identifier(value.get('id')) or type(value.get('revision')) is not int or not 0 <= value['revision'] <= 10**9
            or not _text(value.get('event_description'), 8000) or type(value.get('fields')) is not list
            or len(value['fields']) > MAX_FIELDS):
        issue('/', 'invalid_draft', 'Supply the complete scenario-draft.v1 contract.')
        return result
    package = deepcopy(value['engine_input'])
    if package is None:
        issue('/engine_input', 'missing', 'An explicit engine input is required; the compiler does not generate it.')
    elif type(package) is not dict:
        issue('/engine_input', 'invalid_engine_input', 'Engine input must be a supported object or null while unfilled.')
    elif type(package.get('schema_version')) is not str or package['schema_version'] not in {'event-chain.v1', 'explicit-launch.v1', 'choice-world.v1'}:
        issue('/engine_input/schema_version', 'unsupported_module', 'Choose a published supported execution module.')
    elif package.get('id') != value['id'] or package.get('event_description') != value['event_description']:
        issue('/engine_input', 'context_mismatch', 'Draft and engine input must describe the same scenario and ID.')
    ids, targets = set(), []
    for index, field in enumerate(value['fields']):
        path = f'/fields/{index}'
        if (type(field) is not dict or set(field) != FIELD_KEYS or not _identifier(field.get('id'))
                or field.get('id') in ids or not _text(field.get('label'), 160) or not _text(field.get('why'), 2000)
                or type(field.get('required')) is not bool or type(field.get('type')) is not str
                or field['type'] not in {'integer', 'text', 'boolean', 'choice'}
                or (field['unit'] is not None and not _text(field['unit'], 80)) or not _provenance(field['provenance'])
                or type(field['choices']) is not list):
            issue(path, 'invalid_field', 'Supply a unique typed field, reason and provenance.')
            continue
        ids.add(field['id'])
        kind = field['type']
        if kind == 'integer':
            if (any(bound is not None and type(bound) is not int for bound in [field['minimum'], field['maximum']])
                    or (field['minimum'] is not None and field['maximum'] is not None and field['minimum'] > field['maximum'])
                    or field['choices']):
                issue(path, 'invalid_constraints', 'Integer bounds must be ordered integers; choices must be empty.')
                continue
        elif field['minimum'] is not None or field['maximum'] is not None:
            issue(path, 'invalid_constraints', 'Only integer fields accept numeric bounds.')
            continue
        elif kind == 'choice':
            choices = field['choices']
            if not choices or len(choices) > 64 or any(not _text(item, 512) for item in choices) or len(set(choices)) != len(choices):
                issue(path, 'invalid_constraints', 'Choice fields require distinct nonempty string choices.')
                continue
        elif field['choices']:
            issue(path, 'invalid_constraints', 'Only choice fields accept choices.')
            continue
        parent, parts = None, None
        if field['target'] is not None:
            try:
                parts = _pointer(field['target'])
                if any(parts[:len(other)] == other or other[:len(parts)] == parts for other in targets):
                    raise ValueError('overlapping targets')
                if type(package) is dict:
                    parent = _target_parent(package, parts)
                targets.append(parts)
            except (ValueError, TypeError):
                issue(path + '/target', 'invalid_target', 'Use a distinct existing object leaf; array, identity or overlapping targets are not allowed.')
                continue
        item = field['value']
        if item is None:
            if parent is not None:
                parent[parts[-1]] = None
            if field['required'] or parts is not None:
                issue(path + '/value', 'missing', 'This executable or required value is unfilled; ask the user or supply a labelled assumption.')
            continue
        valid = False
        if kind == 'integer':
            valid = type(item) is int and (field['minimum'] is None or item >= field['minimum']) and (field['maximum'] is None or item <= field['maximum'])
        elif kind == 'boolean':
            valid = type(item) is bool
        elif kind == 'text':
            valid = _text(item, 8000)
        elif kind == 'choice':
            valid = type(item) is str and item in field['choices']
        if not valid:
            issue(path + '/value', 'invalid_value', 'Value does not match this field type, bounds or choices.')
        elif parent is not None:
            parent[parts[-1]] = item
    if result['issues']:
        return result
    if type(package.get('schema_version')) is not str or package['schema_version'] not in {'event-chain.v1', 'explicit-launch.v1', 'choice-world.v1'}:
        issue('/engine_input/schema_version', 'unsupported_module', 'Choose a published supported execution module.')
    elif package.get('id') != value['id'] or package.get('event_description') != value['event_description']:
        issue('/engine_input', 'context_mismatch', 'Draft and engine input must describe the same scenario and ID.')
    else:
        try:
            package = validate_package(package)
        except (ValueError, TypeError, KeyError, OverflowError):
            issue('/engine_input', 'invalid_engine_input', 'Execution input violates its published module contract; inspect its required fields and capabilities.')
    if not result['issues']:
        result.update(ready=True, package=package, package_sha256=draft_digest(package))
    return result


def run_package(value, worlds=100, seed=42):
    package = validate_package(value)
    if package['schema_version'] == 'event-chain.v1':
        from .event_chains import run_event_chain
        report = run_event_chain(package, worlds=worlds, seed=seed)
    elif package['schema_version'] == 'choice-world.v1':
        from .choice_worlds import run_choice_policy
        report = run_choice_policy(package, worlds=worlds, seed=seed)
    else:
        from .explicit_cast import simulate_explicit
        report = simulate_explicit(package['scenario'], package['cast'], worlds=worlds, seed=seed)
    from .identity import engine_fingerprint
    import platform
    if 'input_sha256' in report:
        report['module_input_sha256'] = report['input_sha256']
    report['input_sha256'] = draft_digest(package)
    report['execution_input'] = deepcopy(package)
    report['run_identity'] = {'schema_version': 'scenario-run-identity.v1',
                              'input_sha256': report['input_sha256'], 'seed': seed, 'worlds': worlds,
                              'engine_sha256': engine_fingerprint(),
                              'python_version': platform.python_version()}
    # Constructed identity uses the module's validated seed range, which may be
    # wider than authored parameter magnitudes. Do not reapply draft bounds.
    report['run_sha256'] = sha256(json.dumps(report['run_identity'], sort_keys=True,
                                            ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    report['usage'] = {'model_calls': 0, 'model_cost_usd': '0.00', 'cost_scope': 'offline_execution_only'}
    return report


def prepare_authoring_request(draft, model):
    _canonical(draft)
    # Missing engine values are allowed in authoring, malformed draft identity is not.
    if (type(draft) is not dict or set(draft) != DRAFT_KEYS or draft.get('schema_version') != 'scenario-draft.v1'
            or not _identifier(draft.get('id')) or type(draft.get('revision')) is not int or draft['revision'] < 0
            or not _text(draft.get('event_description'), 8000) or type(draft.get('fields')) is not list
            or len(draft['fields']) > MAX_FIELDS or not _text(model, 160)):
        raise ValueError('invalid authoring request')
    contract = ('Return scenario-authoring-response.v1 with keys schema_version,base_revision,base_sha256,draft. '
                'Copy the supplied revision/hash into base_revision/base_sha256; increment draft.revision by one. '
                'Keep the scenario ID. Use the supplied contracts; unknown values remain null. No model transport is performed here.')
    return {'schema_version': 'scenario-authoring-request.v1', 'model': model,
            'draft_revision': draft['revision'], 'draft_sha256': draft_digest(draft),
            'messages': [{'role': 'system', 'content': authoring_guidelines() + '\n' + contract + '\nCapabilities:\n' + json.dumps(capabilities())},
                         {'role': 'user', 'content': json.dumps(draft, ensure_ascii=False)}],
            'usage': {'model_calls': 0, 'cost_scope': 'request_export_only'}}


def apply_authoring_response(current, response):
    _canonical(current)
    _canonical(response)
    if type(current) is not dict or type(current.get('revision')) is not int:
        raise ValueError('invalid current draft')
    if type(response) is not dict or set(response) != {'schema_version', 'base_revision', 'base_sha256', 'draft'} or response.get('schema_version') != 'scenario-authoring-response.v1':
        raise ValueError('invalid authoring response')
    if type(response['base_revision']) is not int or response['base_revision'] != current['revision'] or response['base_sha256'] != draft_digest(current):
        raise ValueError('stale authoring response')
    draft = response['draft']
    if (type(draft) is not dict or draft.get('id') != current.get('id') or type(draft.get('revision')) is not int
            or draft['revision'] != current['revision'] + 1):
        raise ValueError('invalid revised draft')
    compilation = compile_draft(draft)
    # A revised draft may be incomplete, but must not contain malformed fields.
    if not compilation['draft_valid']:
        raise ValueError('invalid revised draft')
    return deepcopy(draft)
