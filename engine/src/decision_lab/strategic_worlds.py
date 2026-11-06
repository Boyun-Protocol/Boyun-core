"""Data-only discrete strategic worlds with explicit resources and information.

Shared metrics are hypothetical state variables. Utility is declared arithmetic,
not money, empirical preference, calibrated odds or an equilibrium forecast.
"""
from copy import deepcopy
from hashlib import sha256
from itertools import product
from pathlib import Path
import re

from .agent_worlds import canonical, digest
from .strategic_games import analyze_game

MAX_BYTES = 131072
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_ACTORS = 100
MAX_NEIGHBORS = 12
SCALE_MAX_BYTES = 512 * 1024
SCALE_MAX_REPORT_BYTES = 6 * 1024 * 1024
# Exact previous implementation, with unchanged v1 settlement/observations.
# Unknown hashes are never accepted; v2 cannot claim a legacy implementation.
LEGACY_ENGINE_SHA256 = frozenset({'6da87ea970d9a2cb60fb235cc30e4f5c23481cf78d62ce65844cc9dc4c479a41'})
ENGINE_SHA256 = sha256(Path(__file__).read_bytes()).hexdigest()
_LIMITATIONS = [
    'Metrics, utilities, motivations, costs and behaviors are supplied hypothetical assumptions; no real-world event odds are inferred.',
    'Utility equals remaining own cash times its declared cash weight plus shared metric values times declared weights. Utility points are not cash profit.',
    'Action costs leave actor cash and accumulate in a cost sink; no transfers, AMM, borrowing, execution venue or asset valuation is modeled.',
    'Actions are simultaneous. Effects sum before metric bounds clamp; next-round scheduled effects form a separate aggregate stage.',
    'Actors receive own private information, public metrics and personally visible event/peer text. Author reports contain the complete private scenario and must stay private.',
    'Replay checks recorded rules and arithmetic, not evidence truth, actor realism, authenticated provider identity or predictive validity.',
]


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('invalid strategic object shape')


def _text(value, limit=1600, empty=False):
    if type(value) is not str or len(value) > limit or (not empty and not value.strip()):
        raise ValueError('invalid bounded strategic text')


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', value):
        raise ValueError('invalid strategic identifier')
    return value


def _integer(value, minimum=0, maximum=10**12):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('strategic integer outside bounds')


def _list(value, minimum, maximum):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError('invalid bounded strategic list')
    return value


def _strings(value, maximum=16):
    for item in _list(value, 0, maximum):
        _text(item)
    if len(set(value)) != len(value):
        raise ValueError('duplicate strategic text')


def _provenance(value):
    _shape(value, {'status', 'rationale', 'source_refs'})
    if value['status'] not in ('assumed', 'estimated', 'model_proposal'):
        raise ValueError('explicit hypothetical provenance required')
    _text(value['rationale'])
    for source in _list(value['source_refs'], 0, 8):
        _text(source, 400)


def _effects(value, metric_ids):
    if type(value) is not dict or not set(value) <= metric_ids:
        raise ValueError('unknown strategic metric effect')
    for effect in value.values():
        _integer(effect, -10**9, 10**9)


def validate_strategic_world(value):
    """Validate all shapes/references and bounded arithmetic before execution."""
    try:
        scaled = type(value)is dict and value.get('schema_version')=='strategic-world.v2'
        if len(canonical(value)) > (SCALE_MAX_BYTES if scaled else MAX_BYTES):
            raise ValueError('strategic world exceeds size budget')
        _shape(value, {'schema_version', 'id', 'title', 'description', 'rounds', 'metrics',
                       'actors', 'events', 'interactions', 'assumptions', 'limitations'})
        if value['schema_version'] not in ('strategic-world.v1','strategic-world.v2'):
            raise ValueError('unsupported strategic world')
        _id(value['id']);_text(value['title'], 200);_text(value['description'], 8000)
        _integer(value['rounds'], 1, 8)
        metric_ids = set()
        for metric in _list(value['metrics'], 1, 8):
            _shape(metric, {'id', 'label', 'unit', 'initial', 'min', 'max', 'provenance'})
            identifier = _id(metric['id'])
            if identifier == 'cash_cents' or identifier in metric_ids:
                raise ValueError('reserved or duplicate strategic metric')
            metric_ids.add(identifier);_text(metric['label'], 200);_text(metric['unit'], 100)
            for key in ('initial', 'min', 'max'):
                _integer(metric[key], -10**9, 10**9)
            if not metric['min'] <= metric['initial'] <= metric['max']:
                raise ValueError('invalid metric bounds')
            _provenance(metric['provenance'])
        actors = _list(value['actors'], 2, MAX_ACTORS if scaled else 12)
        actor_ids = set()
        for actor in actors:
            _shape(actor, {'id', 'name', 'role', 'motivation', 'goal', 'information', 'initial_cash_cents',
                           'utility_weights', 'actions', 'subscriptions', 'provenance'})
            identifier = _id(actor['id'])
            if identifier in actor_ids:
                raise ValueError('duplicate strategic actor')
            actor_ids.add(identifier)
            _text(actor['name'], 160)
            for key in ('role', 'motivation', 'goal'):
                _text(actor[key])
            _text(actor['information'], 1600, empty=True);_integer(actor['initial_cash_cents'])
            weights = actor['utility_weights']
            if type(weights) is not dict or not set(weights) <= metric_ids | {'cash_cents'} or not weights:
                raise ValueError('explicit known utility weights required')
            for weight in weights.values():
                _integer(weight, -10**6, 10**6)
            action_ids = set()
            for action in _list(actor['actions'], 2, 8):
                _shape(action, {'id', 'label', 'description', 'cost_cents', 'effects', 'message', 'provenance'})
                identifier = _id(action['id'])
                if identifier in action_ids:
                    raise ValueError('duplicate strategic action')
                action_ids.add(identifier);_text(action['label'], 200);_text(action['description'])
                _integer(action['cost_cents']);_effects(action['effects'], metric_ids)
                _text(action['message'], 1200, empty=True);_provenance(action['provenance'])
                if identifier == 'wait' and (action['cost_cents'] or action['effects'] or action['message']):
                    raise ValueError('wait must be a zero-cost, silent no-op')
            if 'wait' not in action_ids:
                raise ValueError('strategic wait action required')
            _provenance(actor['provenance'])
        for actor in actors:
            subscriptions = _list(actor['subscriptions'], 0, MAX_NEIGHBORS if scaled else 11)
            if (any(type(identifier) is not str for identifier in subscriptions)
                or len(set(subscriptions)) != len(subscriptions)
                or not set(subscriptions) <= actor_ids - {actor['id']}):
                raise ValueError('invalid strategic subscriptions')
        interaction_ids = set()
        action_ids_by_actor = {a['id']: {action['id'] for action in a['actions']} for a in actors}
        for interaction in _list(value['interactions'], 0, 16):
            _shape(interaction, {'id', 'when', 'effects', 'description', 'provenance'})
            identifier = _id(interaction['id'])
            if identifier in interaction_ids:
                raise ValueError('duplicate strategic interaction')
            interaction_ids.add(identifier)
            when = interaction['when']
            if type(when) is not dict or not 2 <= len(when) <= len(actors) or not set(when) <= actor_ids:
                raise ValueError('interaction requires at least two known actors')
            for actor, action in when.items():
                if type(action) is not str or action not in action_ids_by_actor[actor]:
                    raise ValueError('interaction names an unknown actor action')
            _effects(interaction['effects'], metric_ids);_text(interaction['description']);_provenance(interaction['provenance'])
        event_ids = set()
        for event in _list(value['events'], 0, 32):
            _shape(event, {'id', 'round', 'text', 'effects', 'visible_to', 'provenance'})
            identifier = _id(event['id'])
            if identifier in event_ids:
                raise ValueError('duplicate strategic event')
            event_ids.add(identifier);_integer(event['round'], 1, value['rounds']);_text(event['text'])
            _effects(event['effects'], metric_ids);_provenance(event['provenance'])
            visible = _list(event['visible_to'], 0, MAX_ACTORS if scaled else 12)
            if (any(type(identifier) is not str for identifier in visible)
                or len(set(visible)) != len(visible) or not set(visible) <= actor_ids):
                raise ValueError('unknown or duplicate strategic event audience')
        _strings(value['assumptions']);_strings(value['limitations'])
        if not value['assumptions']:
            raise ValueError('explicit strategic assumptions required')
        if scaled:
            for actor in actors:
                if len(_neighbor_ids(value,actor))>MAX_NEIGHBORS:
                    raise ValueError('scaled public neighborhood exceeds twelve counterparties')
                if sum(actor['id']in other['subscriptions']for other in actors)>MAX_NEIGHBORS:
                    raise ValueError('scaled message fanout exceeds twelve subscribers')
        _report_preflight(value)
        return deepcopy(value)
    except (KeyError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError('invalid strategic world') from error


def _world_context(world):
    return {'title': world['title'], 'description': world['description'], 'rounds': world['rounds'],
            'metric_definitions': [{key: m[key] for key in ('id', 'label', 'unit', 'min', 'max')}
                                   for m in world['metrics']]}


def _neighbor_ids(world,actor):
    """v2's explicit public neighborhood, never arbitrary context truncation."""
    neighbors=set(actor['subscriptions'])
    for rule in world['interactions']:
        if actor['id']in rule['when']:neighbors.update(rule['when'])
    neighbors.discard(actor['id'])
    return neighbors


def _opponents(world,actor):
    visible=_neighbor_ids(world,actor)if world['schema_version']=='strategic-world.v2'else None
    return [{'id':other['id'],'name':other['name'],'role':other['role'],
             'publicactionlabels':[{'id':a['id'],'label':a['label']}for a in other['actions']]}
            for other in world['actors']if other['id']!=actor['id']and (visible is None or other['id']in visible)]


def _report_preflight(world):
    """Conservative exact-serialization expansion bound before any role calls."""
    rounds = world['rounds']
    actors = {a['id']: a for a in world['actors']}
    expansion = len(canonical(world)) + 16384
    for actor in world['actors']:
        opponents = _opponents(world,actor)
        events = [{'id': e['id'], 'text': e['text'], 'round': e['round']} for e in world['events']
                  if actor['id'] in e['visible_to']]
        base = sum(len(canonical(part)) for part in (actor, opponents, events, world['interactions'], _world_context(world))) + 8192
        messages_per_round = sum(max(len(canonical(c['message'])) for c in actors[source]['actions']) + 256
                                 for source in actor['subscriptions'])
        expansion += rounds * base + rounds * (rounds - 1) // 2 * messages_per_round
        # Decision/receipt/publication records also retain the chosen text.
        expansion += rounds * (max(len(canonical(c['message'])) for c in actor['actions']) + 2048)
    if expansion > (SCALE_MAX_REPORT_BYTES if world['schema_version']=='strategic-world.v2'else MAX_REPORT_BYTES):
        raise ValueError('conservative strategic report expansion exceeds budget')


class StrategicWorld:
    """Simultaneous bounded rules; supplied decisions are inert identifiers."""
    def __init__(self, world, seed=42):
        _integer(seed, 0, 10**9)
        self.world = validate_strategic_world(world)
        self.seed = seed
        self.round = 1
        self.metrics = {m['id']: m['initial'] for m in self.world['metrics']}
        self.cash = {a['id']: a['initial_cash_cents'] for a in self.world['actors']}
        self.history = []
        self.published = []
        self._apply_effects([e['effects'] for e in self.world['events'] if e['round'] == 1])

    def _apply_effects(self, effects):
        self.metrics = self._changed_metrics(self.metrics, effects)

    def _changed_metrics(self, metrics, effects):
        return {m['id']: max(m['min'], min(m['max'], metrics[m['id']] +
                    sum(effect.get(m['id'], 0) for effect in effects))) for m in self.world['metrics']}

    @staticmethod
    def _utility(actor, cash, metrics):
        return sum(weight * (cash if key == 'cash_cents' else metrics[key])
                   for key, weight in actor['utility_weights'].items())

    def observations(self):
        if self.round > self.world['rounds']:
            return {}
        result = {}
        for actor in self.world['actors']:
            identifier = actor['id']
            observation = {'schema_version': 'strategic-observation.v1', 'world_id': self.world['id'],
                'actor_id': identifier, 'round': self.round, 'world': _world_context(self.world),
                'own_history': [{'round': h['round'], 'action_id': h['receipts'][identifier]['action_id'],
                                 'cost_cents': h['receipts'][identifier]['cost_cents'], 'metrics_after': deepcopy(h['metrics_after'])}
                                for h in self.history],
                'actor': {key: deepcopy(actor[key]) for key in ('id', 'name', 'role', 'motivation', 'goal', 'information', 'utility_weights')},
                'cash_cents': self.cash[identifier], 'metrics': deepcopy(self.metrics),
                'actions': [deepcopy(a) for a in actor['actions'] if a['cost_cents'] <= self.cash[identifier]],
                'opponents': _opponents(self.world,actor),
                'interactions': deepcopy(self.world['interactions']),
                'events': [{'id': e['id'], 'text': e['text'], 'round': e['round']} for e in self.world['events']
                           if e['round'] <= self.round and identifier in e['visible_to']],
                'messages': [deepcopy(m) for m in self.published if m['source'] in actor['subscriptions'] and m['round'] < self.round],
                'limitations': list(_LIMITATIONS[:2])}
            if self.world['schema_version']=='strategic-world.v2':
                observation['population']={'actor_count':len(self.world['actors']),
                    'public_opponent_count':len(observation['opponents']),
                    'visibility':'Sparse public counterparties: own subscriptions and joint-rule counterparties only. Other actors still act and affect public metrics; their profiles and messages are not globally visible.'}
            observation['observation_sha256'] = digest(observation)
            result[identifier] = observation
        return result

    def _matched_interactions(self, selected):
        return [interaction for interaction in self.world['interactions']
                if all(selected[actor]['id'] == action for actor, action in interaction['when'].items())]

    def advance(self, decisions):
        if self.round > self.world['rounds']:
            raise ValueError('strategic world completed')
        observations = self.observations()
        _shape(decisions, observations)
        selected = {}
        for actor_id, decision in decisions.items():
            _shape(decision, {'action_id', 'observation_sha256'})
            if decision['observation_sha256'] != observations[actor_id]['observation_sha256']:
                raise ValueError('strategic decision has stale or wrong observation')
            choices = {a['id']: a for a in observations[actor_id]['actions']}
            if type(decision['action_id']) is not str or decision['action_id'] not in choices:
                raise ValueError('unknown or unaffordable strategic action')
            selected[actor_id] = choices[decision['action_id']]
        selected = {actor['id']: selected[actor['id']] for actor in self.world['actors']}
        matched = self._matched_interactions(selected)
        metrics = self._changed_metrics(self.metrics, [a['effects'] for a in selected.values()] + [i['effects'] for i in matched])
        cash = {actor: self.cash[actor] - selected[actor]['cost_cents'] for actor in self.cash}
        messages = [{'id': f"round-{self.round}-{actor}", 'source': actor, 'round': self.round, 'text': action['message']}
                    for actor, action in selected.items() if action['message']]
        receipts = {actor: {'action_id': action['id'], 'cost_cents': action['cost_cents'],
                            'cash_after_cents': cash[actor], 'effects': deepcopy(action['effects'])}
                    for actor, action in selected.items()}
        record = {'round': self.round, 'decisions': deepcopy(decisions), 'observations': observations,
                  'metrics_before': deepcopy(self.metrics), 'metrics_after': deepcopy(metrics), 'receipts': receipts,
                  'published_messages': deepcopy(messages), 'matched_interaction_ids': [i['id'] for i in matched]}
        # No state publication occurs until all input decisions pass validation.
        self.metrics, self.cash = metrics, cash
        self.history.append(record)
        self.published.extend(messages)
        self.round += 1
        if self.round <= self.world['rounds']:
            self._apply_effects([e['effects'] for e in self.world['events'] if e['round'] == self.round])
        return self.report()

    def report(self):
        initial_metrics = {m['id']: m['initial'] for m in self.world['metrics']}
        actors = {}
        for actor in self.world['actors']:
            initial = self._utility(actor, actor['initial_cash_cents'], initial_metrics)
            final = self._utility(actor, self.cash[actor['id']], self.metrics)
            actors[actor['id']] = {'initial_cash_cents': actor['initial_cash_cents'], 'cash_cents': self.cash[actor['id']],
                'cost_cents': actor['initial_cash_cents'] - self.cash[actor['id']],
                'utility': final, 'initial_utility': initial, 'utility_delta': final - initial}
        return deepcopy({'schema_version': 'strategic-world-result.v1', 'world': self.world,
            'world_sha256': digest(self.world), 'engine_sha256': ENGINE_SHA256, 'seed': self.seed,
            'status': 'completed' if self.round > self.world['rounds'] else 'active',
            'completed_rounds': self.round - 1, 'rounds': self.history, 'final_metrics': self.metrics,
            'actor_results': actors, 'total_cost_cents': sum(a['cost_cents'] for a in actors.values()),
            'limitations': list(_LIMITATIONS)})


def replay_strategic_world(report):
    try:
        scaled=type(report)is dict and type(report.get('world'))is dict and report['world'].get('schema_version')=='strategic-world.v2'
        if (type(report) is not dict or report.get('schema_version') != 'strategic-world-result.v1'
            or len(canonical(report)) > (SCALE_MAX_REPORT_BYTES if scaled else MAX_REPORT_BYTES)):
            raise ValueError('invalid bounded strategic report')
        identity=report.get('engine_sha256')
        legacy=identity in LEGACY_ENGINE_SHA256 and not scaled
        if identity!=ENGINE_SHA256 and not legacy:raise ValueError('unknown strategic engine identity')
        engine = StrategicWorld(report['world'], seed=report['seed'])
        for record in _list(report['rounds'], 0, engine.world['rounds']):
            engine.advance(record['decisions'])
        replayed=engine.report()
        if legacy:replayed['engine_sha256']=identity
        if replayed != report:
            raise ValueError('strategic report differs from replay')
        return replayed
    except (KeyError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError('invalid strategic replay report') from error


def strategic_game(world, strategy_beliefs=None):
    """First-round advisory normal form only; no future events or equilibrium play."""
    engine = StrategicWorld(world)
    actors = engine.world['actors']
    if len(actors) > 4:
        return {'status': 'not_computed', 'reason': 'Finite-game analyzer supports at most four players.'}
    choices = {actor: observation['actions'] for actor, observation in engine.observations().items()}
    count = 1
    for actions in choices.values():
        count *= len(actions)
    if any(len(a) < 2 for a in choices.values()) or count > 256:
        return {'status': 'not_computed', 'reason': 'Requires at least two affordable actions per actor and at most256 joint profiles.'}
    profiles = []
    for joint in product(*(choices[a['id']] for a in actors)):
        selected = {actor['id']: action for actor, action in zip(actors, joint)}
        matched = engine._matched_interactions(selected)
        metrics = engine._changed_metrics(engine.metrics, [a['effects'] for a in joint] + [i['effects'] for i in matched])
        profiles.append({'actions': {actor['id']: action['id'] for actor, action in zip(actors, joint)},
            'payoffs': {actor['id']: engine._utility(actor, actor['initial_cash_cents'] - action['cost_cents'], metrics)
                        for actor, action in zip(actors, joint)},
            'provenance': {'status': 'assumed', 'rationale': 'Derived from supplied hypothetical initial state, first-round events, action costs/effects and utility weights; no future rounds.', 'source_refs': []}})
    # finite-game.v1 utilities are bounded at1e9; never silently scale preferences.
    if any(abs(payoff) > 10**9 for profile in profiles for payoff in profile['payoffs'].values()):
        return {'status': 'not_computed', 'reason': 'Raw utility exceeds finite-game payoff bound; no silent rescaling applied.'}
    game = {'schema_version': 'finite-game.v1', 'id': engine.world['id'], 'description': 'First-round hypothetical strategic utility table; later rounds excluded.',
        'utility_unit': 'declared utility points (cash and metric units weighted explicitly)',
        'players': [{'id': a['id'], 'name': a['name'], 'actions': [{'id': c['id'], 'label': c['label']} for c in choices[a['id']]]} for a in actors],
        'profiles': profiles, 'strategy_beliefs': deepcopy(strategy_beliefs)}
    return {'status': 'computed', 'game': game, 'analysis': analyze_game(game),
            'limitations': ['Author-omniscient complete-information first-round counterfactual; uses all supplied private utility weights. This is not Bayesian Nash, a repeated-game equilibrium or a forecast.',
                            'Utility weights are hypothetical. A Nash profile does not determine actual actor decisions.']}
