"""Data-only launch adapter: supplied actors, bounded per-slot alternatives.

Descriptions/provenance are declared context, never instructions or calibration.
The legacy ``cast_recipe`` remains required for financial-config compatibility;
this module never samples it or loads a descriptive persona library.
"""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import math

from .actors import Actor, Cast, CATEGORIES, TRADING_CATEGORIES
from .randomness import keyed_rng
from . import simulation

SCHEMA_VERSION = 'explicit-cast.v1'
MAX_ACTORS = 256
MAX_WORLDS = 100
MAX_ACTOR_VISITS = 1_000_000
MAX_FEED_SCANS = 20_000_000
MAX_HORIZON_HOURS = 8760
_ACTOR_FIELDS = frozenset(Actor.__dataclass_fields__)
_OVERRIDES = {'strategy', 'entry_fraction_bps', 'position_limit_cents', 'attention_capacity', 'subscriptions'}
_SCENARIO_FIELDS = {
    'schema_version', 'mode', 'name', 'horizon_hours', 'capital_cents', 'launch_cost_cents',
    'lp_cash_cents', 'lp_tokens', 'founder_tokens', 'fee_bps', 'founder_vested_at_hour',
    'lp_unlock_at_hour', 'founder_sales', 'campaigns', 'campaign_budget_cents', 'news_enabled',
    'catalyst_probability_bps', 'followup_positive_probability_bps', 'competitor_messages',
    'observation_window_hours', 'visit_interval_hours', 'max_slippage_bps', 'cast_recipe', 'assumptions',
}


def _fail(path):
    # Only static paths are accepted by helpers; input values/keys never enter errors.
    raise ValueError('invalid explicit launch input at ' + path)


def _integer(value, path, minimum=0, maximum=10**18):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(path)


def _text(value, path, maximum=160):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        _fail(path)


def _shape(value, required, path, optional=()):
    if type(value) is not dict or not set(required) <= set(value) <= set(required) | set(optional):
        _fail(path)


def _json_copy(value, path):
    """Reject non-JSON objects, excessive nesting and oversized supplied metadata."""
    budget = [100_000]
    def check(item, depth):
        budget[0] -= 1
        if depth > 20 or budget[0] < 0:
            _fail(path)
        if item is None or type(item) in (str, bool, int):
            if type(item) is str and len(item) > 20_000:
                _fail(path)
            if type(item) is int and abs(item) > 10**18:
                _fail(path)
        elif type(item) is float:
            if not math.isfinite(item):
                _fail(path)
        elif type(item) is list:
            for child in item:
                check(child, depth + 1)
        elif type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or len(key) > 160:
                    _fail(path)
                check(child, depth + 1)
        else:
            _fail(path)
    check(value, 0)
    if len(json.dumps(value, ensure_ascii=False).encode()) > 2_000_000:
        _fail(path)
    return deepcopy(value)


def _scenario(value, worlds=1, seed=0, plan='launch_now'):
    value = _json_copy(value, 'scenario')
    _shape(value, _SCENARIO_FIELDS, 'scenario', {'user_brief'})
    if value['schema_version'] != 'synthetic-scenario.v1':
        _fail('scenario.schema_version')
    _text(value['name'], 'scenario.name', 2000)
    _integer(worlds, 'worlds', 1, MAX_WORLDS)
    _integer(seed, 'seed')
    _integer(value['horizon_hours'], 'scenario.horizon_hours', 1, MAX_HORIZON_HOURS)
    if type(value['cast_recipe']) is not dict:
        _fail('scenario.cast_recipe')
    for name, keys in (('campaigns', {'at_hour', 'fee_cents'}),
                       ('founder_sales', {'at_hour', 'token_units'}),
                       ('competitor_messages', {'at_hour'})):
        entries = value[name]
        if type(entries) is not list or len(entries) > 2048:
            _fail('scenario.scheduled_events')
        for entry in entries:
            _shape(entry, keys, 'scenario.scheduled_events')
    try:
        simulation._validate(value, worlds, seed, plan)
    except (ValueError, TypeError, AttributeError, KeyError):
        _fail('scenario.financial_configuration')
    return value


def _actor(raw):
    _shape(raw, _ACTOR_FIELDS, 'cast.actors')
    for key in ('id', 'template_id', 'owner_id', 'category', 'strategy'):
        _text(raw[key], 'cast.actors.identity')
    if raw['category'] not in CATEGORIES:
        _fail('cast.actors.category')
    for key in ('initial_cash_cents', 'position_limit_cents'):
        _integer(raw[key], 'cast.actors.resources')
    _integer(raw['entry_fraction_bps'], 'cast.actors.entry_fraction_bps', maximum=10_000)
    _integer(raw['attention_capacity'], 'cast.actors.attention_capacity', maximum=2048)
    for key in ('allowed_actions', 'subscriptions'):
        items = raw[key]
        if type(items) is not list or any(type(v) is not str for v in items) or len(set(items)) != len(items):
            _fail('cast.actors.capabilities')
    if not set(raw['subscriptions']) <= {'news', 'creator', 'competitor'}:
        _fail('cast.actors.subscriptions')
    if type(raw['provenance']) is not dict:
        _fail('cast.actors.provenance')
    actor_id, category = raw['id'], raw['category']
    if actor_id == 'project-founder':
        valid_role = category == 'launch_teams' and raw['owner_id'] == 'project'
        strategies, actions = {'scheduled_exit'}, {'sell', 'abstain'}
    elif actor_id == 'project-lp':
        valid_role = category == 'liquidity' and raw['owner_id'] == 'project' and raw['initial_cash_cents'] == 0
        strategies, actions = {'observe'}, {'add_liquidity', 'remove_liquidity', 'abstain'}
    elif category in TRADING_CATEGORIES:
        valid_role = raw['owner_id'] not in {'project', 'pool', 'services'}
        strategies, actions = {'cautious', 'momentum'}, {'buy', 'sell', 'abstain'}
    else:
        valid_role = raw['owner_id'] not in {'project', 'pool', 'services'}
        strategies, actions = {'observe'}, {'observe', 'abstain'}
    if not valid_role or raw['strategy'] not in strategies or set(raw['allowed_actions']) != actions:
        _fail('cast.actors.role_strategy_capabilities')
    return Actor(**{**raw, 'allowed_actions': frozenset(raw['allowed_actions']),
                    'subscriptions': tuple(raw['subscriptions'])})


def _validated(spec, scenario):
    value = _json_copy(spec, 'cast')
    _shape(value, {'schema_version', 'actors', 'excluded'}, 'cast', {'alternatives', 'mixture_assumption'})
    if value['schema_version'] != SCHEMA_VERSION:
        _fail('cast.schema_version')
    raw_actors = value['actors']
    if type(raw_actors) is not list or not 2 <= len(raw_actors) <= MAX_ACTORS:
        _fail('cast.actors')
    actors = [_actor(raw) for raw in raw_actors]
    by_id = {actor.id: actor for actor in actors}
    if len(by_id) != len(actors) or not {'project-founder', 'project-lp'} <= set(by_id):
        _fail('cast.actors.identities')
    owners = [actor.owner_id for actor in actors if actor.owner_id != 'project']
    if len(set(owners)) != len(owners):
        _fail('cast.actors.ownership')
    if by_id['project-founder'].initial_cash_cents != scenario['capital_cents']:
        _fail('cast.actors.founder_capital')
    if scenario['campaigns'] and not any(a.category == 'creators_marketing' for a in actors):
        _fail('cast.actors.campaign_counterparty')
    excluded = value['excluded']
    if type(excluded) is not list or len(excluded) > MAX_ACTORS:
        _fail('cast.excluded')
    excluded_ids = set()
    for entry in excluded:
        _shape(entry, {'id', 'category', 'reason'}, 'cast.excluded')
        for key in ('id', 'category', 'reason'):
            _text(entry[key], 'cast.excluded', 2000)
        if entry['category'] not in CATEGORIES or entry['id'] in by_id or entry['id'] in excluded_ids:
            _fail('cast.excluded.identities')
        excluded_ids.add(entry['id'])
    alternatives = value.get('alternatives', [])
    if type(alternatives) is not list or len(alternatives) > len(actors):
        _fail('cast.alternatives')
    if alternatives and value.get('mixture_assumption') != 'independent_per_actor_per_world':
        _fail('cast.mixture_assumption')
    if 'mixture_assumption' in value and value['mixture_assumption'] != 'independent_per_actor_per_world':
        _fail('cast.mixture_assumption')
    mixed = set()
    for slot in alternatives:
        _shape(slot, {'actor_id', 'variants'}, 'cast.alternatives')
        if type(slot['actor_id']) is not str or slot['actor_id'] not in by_id or slot['actor_id'] in mixed:
            _fail('cast.alternatives.actor_id')
        mixed.add(slot['actor_id'])
        variants = slot['variants']
        if type(variants) is not list or not 1 <= len(variants) <= 32:
            _fail('cast.alternatives.variants')
        variant_ids = set()
        for variant in variants:
            _shape(variant, {'id', 'weight_bps', 'overrides'}, 'cast.alternatives.variants')
            _text(variant['id'], 'cast.alternatives.variants.id')
            if variant['id'] in variant_ids:
                _fail('cast.alternatives.variants.id')
            variant_ids.add(variant['id'])
            _integer(variant['weight_bps'], 'cast.alternatives.variants.weight_bps', maximum=10_000)
            override = variant['overrides']
            if type(override) is not dict or not set(override) <= _OVERRIDES:
                _fail('cast.alternatives.variants.overrides')
            baseline = next(raw for raw in raw_actors if raw['id'] == slot['actor_id'])
            _actor({**baseline, **override})
        if sum(v['weight_bps'] for v in variants) != 10_000:
            _fail('cast.alternatives.variants.weight_bps')
    return value, Cast(actors, excluded)


def export_cast(cast: Cast) -> dict:
    """Export explicit fields and supplied descriptions without library lookup."""
    if not isinstance(cast, Cast):
        _fail('cast')
    result = {'schema_version': SCHEMA_VERSION, 'actors': [], 'excluded': deepcopy(cast.excluded)}
    for actor in cast.actors:
        raw = asdict(actor)
        raw['allowed_actions'] = sorted(actor.allowed_actions)
        raw['subscriptions'] = list(actor.subscriptions)
        result['actors'].append(raw)
    return _json_copy(result, 'cast')


def validate_explicit_cast(spec: dict, scenario: dict) -> Cast:
    """Validate supplied launch actors/alternatives; return a detached base cast."""
    return _validated(spec, _scenario(scenario))[1]


def _select(value, cast, seed, world_id):
    selections, changes = {}, {}
    for slot in value.get('alternatives', []):
        draw = keyed_rng(seed, SCHEMA_VERSION, 'alternative', world_id, slot['actor_id']).randrange(10_000)
        cumulative = 0
        for variant in sorted(slot['variants'], key=lambda v: v['id']):
            cumulative += variant['weight_bps']
            if draw < cumulative:
                override = deepcopy(variant['overrides'])
                if 'subscriptions' in override:
                    override['subscriptions'] = tuple(override['subscriptions'])
                changes[slot['actor_id']] = override
                selections[slot['actor_id']] = variant['id']
                break
    return Cast([replace(actor, **changes.get(actor.id, {})) for actor in cast.actors], deepcopy(cast.excluded)), selections


def cast_for_world(spec, scenario, seed, world_id):
    """Choose exactly one weighted alternative per declared slot, using stable IDs."""
    _integer(seed, 'seed')
    _integer(world_id, 'world_id')
    value, cast = _validated(spec, _scenario(scenario))
    return _select(value, cast, seed, world_id)


def simulate_explicit(scenario, spec, worlds=100, seed=42, plan='launch_now') -> dict:
    """Execute bounded supplied actors in the legacy financial kernel, no inference."""
    scenario = _scenario(scenario, worlds, seed, plan)
    value, cast = _validated(spec, scenario)
    visits = len(cast.actors) * (scenario['horizon_hours'] // scenario['visit_interval_hours'] + 1) * worlds
    if visits > MAX_ACTOR_VISITS:
        _fail('run.actor_visit_budget')
    # Every visit may scan all published messages, including actors that only
    # observe. Bound that multiplication before entering the financial kernel.
    # Count all scheduled publications conservatively, even beyond the horizon
    # or when a chosen plan suppresses some campaigns.
    publications = (len(scenario['campaigns']) + len(scenario['competitor_messages'])
                    + (2 if scenario['news_enabled'] else 0))
    feed_scans = visits * publications
    if feed_scans > MAX_FEED_SCANS:
        _fail('run.feed_scan_budget')
    results, selections = [], []
    for world_id in range(worlds):
        selected_cast, selected = _select(value, cast, seed, world_id)
        results.append(simulation._world(scenario, selected_cast, seed, world_id, plan, world_id < 3))
        effective_policies = {
            actor.id: {'variant_id': selected[actor.id], 'strategy': actor.strategy,
                       'entry_fraction_bps': actor.entry_fraction_bps,
                       'position_limit_cents': actor.position_limit_cents,
                       'attention_capacity': actor.attention_capacity,
                       'subscriptions': list(actor.subscriptions)}
            for actor in selected_cast.actors if actor.id in selected
        }
        selections.append({'world_id': world_id, 'selections': selected,
                           'effective_actor_policies': effective_policies})
    # Summary only consumes pool cardinality. IDs originate entirely in the cast;
    # descriptions remain verbatim provenance and are never invented here.
    pool = {'profiles': [{'id': template_id} for template_id in sorted({a.template_id for a in cast.actors})]}
    report = simulation._summarize_worlds(scenario, pool, cast, results, seed, plan, None)
    identity = {'schema_version': SCHEMA_VERSION, 'adapter_version': 'explicit-launch.v1',
                'scenario': scenario, 'cast': value, 'seed': seed, 'worlds': worlds, 'plan': plan}
    canonical = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    report.update(schema_version='explicit-launch-result.v1', input_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
                  explicit_cast=deepcopy(value), variant_selections=selections,
                  cast_source='explicit_supplied', cast_scope='base_before_variants',
                  provenance_status='declared_unverified',
                  execution_limits={'max_actors': MAX_ACTORS, 'max_worlds': MAX_WORLDS,
                                    'max_actor_visits': MAX_ACTOR_VISITS, 'actor_visits': visits,
                                    'max_feed_scans': MAX_FEED_SCANS,
                                    'feed_scan_upper_bound': feed_scans,
                                    'publication_count_upper_bound': publications,
                                    'max_horizon_hours': MAX_HORIZON_HOURS})
    report['cast']['scope'] = 'base_before_variants'
    report['usage']['mode'] = 'offline_explicit_cast'
    report['limitations'] = [line for line in report['limitations']
                             if not line.startswith(('One fixed sampled cast', 'Bundle source metadata'))]
    report['limitations'].extend([
        'Actors and descriptions are supplied declarations; validation does not establish realism or forecast accuracy.',
        'Per-slot alternatives use declared independent categorical draws; actor count, ownership and endowments remain fixed.',
        'cast.actors describes base policies before variants; variant_selections records the effective policies only for slots with alternatives in each world. Other slots retain their supplied base policies.',
        'cast_recipe is retained only for legacy financial-config compatibility and is never used to generate personas.',
        'Launch actions use fixed cautious/momentum, scheduled founder exit and delegated LP rules; no imported policy bundle.',
    ])
    return report


def explicit_launch_capabilities() -> dict:
    """Publish the complete data contract without supplying behavioral estimates."""
    def integer(minimum=0, maximum=10**18, unit='count'):
        return {'type': 'integer', 'minimum': minimum, 'maximum': maximum, 'unit': unit,
                'boolean_is_integer': False}

    text = {'type': 'string', 'nonempty': True, 'max_characters': 160}
    money = integer(unit='cents')
    bps = integer(maximum=10_000, unit='basis_points')
    fields = {
        'schema_version': {'type': 'string', 'const': 'synthetic-scenario.v1'},
        'mode': {'type': 'string', 'const': 'synthetic'},
        'name': {**text, 'max_characters': 2000},
        'news_enabled': {'type': 'boolean'},
        'cast_recipe': {'type': 'object', 'required': ['founder_initial_cash_cents'],
                        'fields': {'founder_initial_cash_cents': {**money, 'equals': 'capital_cents'}},
                        'additional_fields': 'Legacy recipe JSON may be retained; it is never used for generation.'},
        'assumptions': {'type': 'array', 'min_items': 1, 'items': 'Supplied bounded JSON; declared, unverified.'},
        'user_brief': {'type': 'object', 'required': ['question', 'event', 'ticker'],
                       'additional_fields': False,
                       'fields': {'question': {'type': 'string', 'nonempty': True, 'max_characters': 2000},
                                  'event': {'type': 'string', 'max_characters': 160},
                                  'ticker': {'type': 'string', 'max_characters': 24}}},
    }
    for name in ('capital_cents', 'lp_cash_cents'):
        fields[name] = integer(1, unit='cents')
    for name in ('launch_cost_cents', 'campaign_budget_cents'):
        fields[name] = deepcopy(money)
    for name in ('lp_tokens', 'founder_tokens'):
        fields[name] = integer(1, unit='token_units')
    for name in ('visit_interval_hours', 'observation_window_hours'):
        fields[name] = integer(1, unit='hours')
    fields['horizon_hours'] = integer(1, MAX_HORIZON_HOURS, 'hours')
    for name in ('founder_vested_at_hour', 'lp_unlock_at_hour'):
        fields[name] = integer(unit='hours')
    for name in ('catalyst_probability_bps', 'followup_positive_probability_bps', 'max_slippage_bps'):
        fields[name] = deepcopy(bps)
    fields['fee_bps'] = integer(maximum=9999, unit='basis_points')
    for name, entry_fields in (
        ('campaigns', {'at_hour': integer(unit='hours'), 'fee_cents': money}),
        ('founder_sales', {'at_hour': integer(unit='hours'), 'token_units': integer(1, unit='token_units')}),
        ('competitor_messages', {'at_hour': integer(unit='hours')}),
    ):
        fields[name] = {'type': 'array', 'max_items': 2048, 'items': {
            'type': 'object', 'required': sorted(entry_fields), 'additional_fields': False,
            'fields': deepcopy(entry_fields)}}
    actor_fields = {name: deepcopy(text) for name in ('id', 'template_id', 'category', 'owner_id', 'strategy')}
    actor_fields.update({
        'initial_cash_cents': deepcopy(money), 'position_limit_cents': deepcopy(money),
        'entry_fraction_bps': deepcopy(bps), 'attention_capacity': integer(maximum=2048),
        'allowed_actions': {'type': 'array', 'items': 'string', 'unique': True, 'exact_role_sets': True},
        'subscriptions': {'type': 'array', 'items': 'string', 'unique': True,
                          'allowed_values': ['news', 'creator', 'competitor']},
        'provenance': {'type': 'object', 'content': 'Supplied bounded JSON, including optional descriptions; no inference.'},
    })
    observe = {'strategies': ['observe'], 'allowed_actions': ['abstain', 'observe']}
    trading = {'strategies': ['cautious', 'momentum'], 'allowed_actions': ['abstain', 'buy', 'sell']}
    return {
        'schema_version': 'explicit-launch.v1', 'model_calls': 0, 'defaults_or_estimates': None,
        'wrapper': {'required': ['schema_version', 'id', 'event_description', 'scenario', 'cast'],
                    'additional_fields': False, 'fields': {
                        'schema_version': {'type': 'string', 'const': 'explicit-launch.v1'},
                        'id': {'type': 'string', 'pattern': '[a-zA-Z][a-zA-Z0-9_-]{0,63}'},
                        'event_description': {**text, 'max_characters': 8000},
                        'scenario': {'type': 'object', 'contract': 'scenario'},
                        'cast': {'type': 'object', 'contract': 'cast'}}},
        'scenario': {'required': sorted(_SCENARIO_FIELDS), 'optional': ['user_brief'],
                     'additional_fields': False, 'fields': fields, 'constraints': [
                         'founder_tokens >= lp_tokens; lp_unlock_at_hour > horizon_hours.',
                         'Sum of campaign fees <= campaign_budget_cents.',
                         'launch_cost_cents + lp_cash_cents + sum of campaign fees <= capital_cents.',
                         'cast_recipe.founder_initial_cash_cents equals capital_cents; no other recipe fields are needed.',
                     ]},
        'cast': {'schema_version': SCHEMA_VERSION, 'required': ['schema_version', 'actors', 'excluded'],
                 'optional': ['alternatives', 'mixture_assumption'], 'additional_fields': False,
                 'actor_fields': actor_fields, 'actor_required': sorted(_ACTOR_FIELDS),
                 'actor_additional_fields': False, 'actor_count': {'minimum': 2, 'maximum': MAX_ACTORS},
                 'categories': list(CATEGORIES),
                 'category_rules': {category: deepcopy(trading if category in TRADING_CATEGORIES else observe)
                                    for category in CATEGORIES},
                 'role_rules': {
                     'project-founder': {'category': 'launch_teams', 'owner_id': 'project',
                                         'initial_cash_cents': 'equals scenario.capital_cents',
                                         'strategies': ['scheduled_exit'], 'allowed_actions': ['abstain', 'sell']},
                     'project-lp': {'category': 'liquidity', 'owner_id': 'project', 'initial_cash_cents': 0,
                                    'strategies': ['observe'],
                                    'allowed_actions': ['abstain', 'add_liquidity', 'remove_liquidity']},
                 },
                 'ownership': {'unique_actor_ids': True, 'required_roles': ['project-founder', 'project-lp'],
                               'unique_outside_owner_ids': True, 'reserved_owner_ids': ['project', 'pool', 'services'],
                               'project_owner_exception': 'Only the two required project roles share project.'},
                 'campaign_counterparty': 'At least one creators_marketing actor is required when campaigns are nonempty.',
                 'excluded': {'type': 'array', 'max_items': MAX_ACTORS,
                              'required_entry_fields': ['id', 'category', 'reason'], 'additional_entry_fields': False,
                              'entry_fields': {key: {**text, 'max_characters': 2000} for key in ('id', 'category', 'reason')},
                              'constraints': 'Known category; IDs unique and disjoint from active actor IDs.'},
                 'alternatives': {'type': 'array', 'max_items': 'actor count',
                                  'slot_required': ['actor_id', 'variants'], 'slot_additional_fields': False,
                                  'actor_id': 'Existing unique actor ID; each slot may appear once.',
                                  'variants': {'minimum': 1, 'maximum': 32,
                                               'required': ['id', 'weight_bps', 'overrides'], 'additional_fields': False,
                                               'id': {**text, 'unique_within_slot': True}, 'weight_bps': deepcopy(bps),
                                               'overrides': 'Object with only the allowlisted actor fields; same field and role validation applies.'},
                                  'allowed_overrides': sorted(_OVERRIDES), 'weight_sum_bps_per_slot': 10_000,
                                  'mixture_assumption': 'independent_per_actor_per_world',
                                  'mixture_assumption_required_when_nonempty': True,
                                  'invariants': 'No ownership, endowment, capability or population changes.'}},
        'run': {'worlds': integer(1, MAX_WORLDS), 'seed': integer(), 'plan': list(simulation.PLANS)},
        'limits': {'max_actors': MAX_ACTORS, 'max_worlds': MAX_WORLDS, 'max_actor_visits': MAX_ACTOR_VISITS,
                   'max_feed_scans': MAX_FEED_SCANS, 'max_horizon_hours': MAX_HORIZON_HOURS,
                   'actor_visits': 'actors * (horizon_hours // visit_interval_hours + 1) * worlds',
                   'feed_scans': 'actor_visits * (campaign_count + competitor_count + (2 if news_enabled else 0))',
                   'input_bytes_per_cast_or_scenario': 2_000_000, 'json_nodes': 100_000, 'json_depth': 20,
                   'json_string_characters': 20_000, 'json_key_characters': 160, 'json_integer_magnitude': 10**18,
                   'json_floats': 'Finite only; executable integer fields do not accept floats.',
                   'trace_worlds': 3, 'trace_events_per_world': 500},
        'limitations': ['Single-market launch financial mechanics; no imported policy bundle, lending, liquidation or executable code.',
                        'Descriptions and provenance are declarations and do not create behavior or calibrated probabilities.',
                        'Role capabilities are exact sets; project-role rules override category rules; outside nontraders observe only.',
                        'Scheduled launch/LP actions are fixed engine behavior; listing an LP capability does not supply a withdrawal policy.',
                        'Wrapper is validated by the authoring boundary; direct adapter APIs receive scenario and cast separately.'],
    }
