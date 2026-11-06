"""Offline, domain-neutral provenance checks; not source authentication or calibration."""
from datetime import datetime
import json
import math
import re

from .agent_worlds import digest


KINDS = {'input', 'mechanism', 'outcome', 'probability'}
STATUSES = {'observed', 'derived', 'assumed', 'model_judged', 'unknown', 'disputed'}
PROBABILITY_SOURCES = {
    'event_probability': {'measurement', 'forecast'},
    'poll_share': {'poll'},
    'market_implied': {'prediction_market'},
    'model_score': {'model_receipt'},
    'simulation_frequency': {'engine_receipt'},
    'assumed_probability': set(),
}
SOURCE_KINDS = {'measurement', 'forecast', 'poll', 'prediction_market', 'model_receipt',
                'engine_receipt', 'official_schedule', 'official_result', 'user_input'}


def _text(value):
    return type(value) is str and bool(value.strip()) and len(value) <= 12000


def _time(value):
    if not _text(value):
        raise ValueError('explicit evidence timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('evidence timestamp needs a timezone')
    return result


def _indexed(rows, limit, label):
    if type(rows) is not list or len(rows) > limit:
        raise ValueError(f'bounded {label} list required')
    indexed = {}
    for row in rows:
        if type(row) is not dict or not _text(row.get('id')) or row['id'] in indexed:
            raise ValueError(f'unique {label} IDs required')
        indexed[row['id']] = row
    return indexed


def numeric_targets(value, prefix=''):
    """Inventory every numeric/boolean leaf; domain callers add semantic output targets."""
    result = {}
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError('JSON object keys required')
            escaped = key.replace('~', '~0').replace('/', '~1')
            result.update(numeric_targets(item, prefix + '/' + escaped))
    elif type(value) is list:
        for index, item in enumerate(value):
            result.update(numeric_targets(item, prefix + '/' + str(index)))
    elif type(value) in {int, float, bool}:
        if type(value) is float and not math.isfinite(value):
            raise ValueError('finite input required')
        result[prefix] = 'input'
    return result


def audit_evidence(register, *, required_targets, target_sha256=None):
    """Check a reviewed inventory and dependency graph without reading URLs or making model calls.

    A passing result permits conditional assumptions, never certifies real-world forecasts.
    Source review, completeness of semantic inventories and causal validity need human review.
    """
    try:
        encoded = json.dumps(register, allow_nan=False).encode()
    except (TypeError, RecursionError) as error:
        raise ValueError('bounded JSON evidence required') from error
    if len(encoded) > 1048576 or type(register) is not dict or register.get('schema_version') != 'simulation-evidence.v1':
        raise ValueError('bounded simulation-evidence.v1 register required')
    if (type(required_targets) is not dict or not 1 <= len(required_targets) <= 16384
            or any(not _text(key) or kind not in KINDS for key, kind in required_targets.items())):
        raise ValueError('nonempty reviewed target inventory required')
    cutoff = _time(register.get('as_of'))
    if type(register.get('target_sha256')) is not str or not re.fullmatch('[0-9a-f]{64}', register['target_sha256']):
        raise ValueError('target content checksum required')
    sources = _indexed(register.get('sources'), 256, 'source')
    claims = _indexed(register.get('claims'), 512, 'claim')
    bindings = register.get('bindings')
    if type(bindings) is not dict or any(not _text(key) or type(value) is not str or value not in claims
                                         for key, value in bindings.items()):
        raise ValueError('bindings must name existing claims')
    for source in sources.values():
        if (source.get('kind') not in SOURCE_KINDS or source.get('review') not in {'reviewed', 'unreviewed', 'disputed'}
                or any(not _text(source.get(key)) for key in ('publisher', 'locator', 'scope', 'method', 'limitations'))):
            raise ValueError('source identity, scope, method, limitations and review required')
        for field in ('available_at', 'retrieved_at'):
            if source.get(field) is not None:
                _time(source[field])
    for claim in claims.values():
        dependencies = claim.get('depends_on')
        source_ids = claim.get('source_ids', [])
        if (claim.get('kind') not in KINDS or claim.get('status') not in STATUSES
                or not _text(claim.get('statement'))):
            raise ValueError('typed claim and statement required')
        if (type(dependencies) is not list or any(type(item) is not str or item not in claims for item in dependencies)
                or len(dependencies) != len(set(dependencies))):
            raise ValueError('unique existing claim dependency required')
        if type(source_ids) is not list or any(type(item) is not str or item not in sources for item in source_ids):
            raise ValueError('existing source IDs required')
    ancestors = {}
    visiting = set()

    def visit(identifier):
        if identifier in visiting:
            raise ValueError('claim dependency cycle')
        if identifier not in ancestors:
            visiting.add(identifier)
            dependencies = claims[identifier]['depends_on']
            inherited = set(dependencies)
            for dependency in dependencies:
                inherited.update(visit(dependency))
            ancestors[identifier] = inherited
            visiting.remove(identifier)
        return ancestors[identifier]

    for identifier in claims:
        visit(identifier)
    issues = []
    labels = {}

    def issue(identifier, code, detail):
        issues.append({'claim_id': identifier, 'code': code, 'detail': detail})

    if target_sha256 is not None and register['target_sha256'] != target_sha256:
        issue(None, 'target_mismatch', 'Evidence belongs to different inputs; review and bind the changed package.')
    for target, kind in required_targets.items():
        if target not in bindings:
            issue(None, 'missing_binding', f'No supporting claim for {target}.')
        elif claims[bindings[target]]['kind'] != kind:
            issue(bindings[target], 'binding_kind_mismatch', f'{target} requires a {kind} claim.')
    for identifier, claim in claims.items():
        status = claim['status']
        source_ids = claim.get('source_ids', [])
        if status in {'unknown', 'disputed'}:
            issue(identifier, 'unresolved_claim', 'Resolve the evidence or compare an explicitly justified assumption.')
        if status == 'assumed':
            for field in ('rationale', 'sensitivity', 'falsification'):
                if not _text(claim.get(field)):
                    issue(identifier, 'unsupported_assumption', f'A reasonable cause, sensitivity and falsification are required: {field}.')
        if status in {'observed', 'model_judged'} and not source_ids:
            issue(identifier, 'missing_source', 'A specific reviewed measurement or model receipt is required.')
        if status in {'observed', 'derived', 'model_judged'} and not _text(claim.get('method')):
            issue(identifier, 'missing_method', 'State the measurement, transfer, formula or decision method.')
        if status == 'derived' and not claim['depends_on']:
            issue(identifier, 'missing_inputs', 'A calculation needs named input claims.')
        for source_id in source_ids:
            source = sources[source_id]
            if source['review'] != 'reviewed':
                issue(identifier, 'source_not_reviewed', f'{source_id} has not passed a specific claim/source review.')
            if any(source.get(field) is None for field in ('available_at', 'retrieved_at')):
                issue(identifier, 'unknown_source_time', f'{source_id} has no established availability/capture time.')
            if any(source.get(field) is not None and _time(source[field]) > cutoff
                   for field in ('available_at', 'retrieved_at')):
                issue(identifier, 'source_after_cutoff', f'{source_id} cannot be used as launch-as-of evidence.')
            if (source.get('available_at') is not None and source.get('retrieved_at') is not None
                    and _time(source['available_at']) > _time(source['retrieved_at'])):
                issue(identifier, 'source_time_order', f'{source_id} was captured before its declared publication/availability time.')
        if claim['kind'] == 'probability':
            probability_kind = claim.get('probability_kind')
            if probability_kind not in PROBABILITY_SOURCES or not _text(claim.get('uncertainty')):
                issue(identifier, 'probability_definition_missing', 'Name the probability type, denominator, window and uncertainty.')
            if probability_kind in PROBABILITY_SOURCES and status not in {'assumed', 'unknown', 'disputed'}:
                allowed = PROBABILITY_SOURCES[probability_kind]
                if source_ids and any(sources[source_id]['kind'] not in allowed for source_id in source_ids):
                    issue(identifier, 'invalid_probability_transfer', 'A poll, vote, calendar, market quote or model score cannot silently become event odds.')
                inherited = [claims[parent].get('probability_kind') for parent in ancestors[identifier]
                             if claims[parent]['kind'] == 'probability']
                if (any(kind != probability_kind for kind in inherited)
                        or (status == 'derived' and not source_ids and not inherited)):
                    issue(identifier, 'invalid_probability_transfer', 'A new probability meaning needs a separately justified assumed or externally validated model.')
        if claim['kind'] == 'outcome':
            if not any(claims[parent]['kind'] == 'mechanism' for parent in ancestors[identifier]):
                issue(identifier, 'outcome_without_mechanism', 'Link the modeled outcome to its executable causal mechanism and inputs.')
            if status != 'derived':
                issue(identifier, 'outcome_not_derived', 'A modeled result must be derived from recorded inputs and mechanics, not a copied forecast.')
        lineage = [claim] + [claims[parent] for parent in ancestors[identifier]]
        labels[identifier] = ('unresolved_dependency' if any(item['status'] in {'unknown', 'disputed'} for item in lineage)
                              else 'assumption_dependent' if any(item['status'] == 'assumed' for item in lineage)
                              else 'model_dependent' if any(item['status'] == 'model_judged' for item in lineage)
                              else 'source_or_calculation_dependent')
    blocked = {row['claim_id'] for row in issues if row['claim_id'] is not None}
    for identifier in sorted(claims, key=lambda key: len(ancestors[key])):
        if identifier not in blocked and ancestors[identifier] & blocked:
            blocked.add(identifier)
            issue(identifier, 'dependency_blocked', 'A required upstream claim is unresolved or unsupported.')
    return {
        'schema_version': 'simulation-evidence-audit.v1',
        'status': 'blocked' if issues else 'ready_for_conditional_simulation',
        'forecast_validated': False, 'as_of': register['as_of'],
        'register_sha256': digest(register), 'target_sha256': register['target_sha256'],
        'required_targets_sha256': digest(required_targets),
        'required_targets': len(required_targets), 'bound_targets': sum(key in bindings for key in required_targets),
        'assumed_claims': sorted(key for key, claim in claims.items() if claim['status'] == 'assumed'),
        'blocked_claims': sorted(blocked), 'claim_labels': labels, 'issues': issues, 'model_calls': 0,
        'limitations': [
            'Structural provenance checks do not authenticate sources or judge the truth of a causal rationale.',
            'The caller must review nonnumeric assumptions, source quality and completeness of the target inventory.',
            'Passing permits conditional simulation only; external probabilities and outcomes are not forced to match.',
        ],
    }
