"""Bounded, data-only decision insights from replayed strategic results.

This bridge never calls a model or changes a world. Cash reconciliation uses
recorded spending; static incentives use the existing exact finite-game engine.
"""
from copy import deepcopy

from .agent_worlds import canonical, digest
from .strategic_worlds import replay_strategic_world, strategic_game, validate_strategic_world

MAX_INSIGHTS_BYTES = 2 * 1024 * 1024

DECISION_RECORD_SCOPE = (
    'The record shows supplied observations, action scores, selected actions and numeric consequences. '
    'Jev returns no reasoning trace. Declared goals and utility comparisons do not establish why the '
    'model chose an action. Replay checks settlement with saved choices, not the hidden inference.'
)

RESOURCE_MEANING = (
    'Initial cash minus action costs equals remaining cash. Costs accumulate in a '
    'modeled expense sink. No revenue, transfers, AMM, trades, asset valuation or '
    'financial profit is modeled. Aggregates sum completed simulated worlds; '
    'they are accounting totals across alternative runs, not a pooled portfolio.'
)
STRATEGIC_SCOPE = (
    'Exact author-omniscient complete-information one-round normal-form game '
    'under declared cash and metric utility weights, with simultaneous actions.'
)
OPENING_SCOPE = (
    'FIRST ROUND ONLY: exact author-omniscient complete-information static '
    'counterfactual under declared utility weights and simultaneous opening '
    'actions. Excludes future messages, events and commitments, later decisions '
    'and reactions; not a full-world equilibrium or repeated-game solution.'
)
STRATEGIC_LIMITATIONS = [
    'Utility points are declared preferences, not cash profit or a monetary valuation of shared metrics.',
    'Pure Nash means no strictly profitable unilateral deviation in this supplied static game; it is not a forecast of actor choices.',
    'Strict dominance compares other pure actions over all affordable opponent profiles; no iterated elimination or mixed-strategy equilibrium is computed.',
    'No strategy beliefs are supplied or invented. Expected utility under beliefs and probabilistic recommendations are not computed.',
    'Observed unilateral improvements hold recorded opponents fixed; they do not model reactions, information constraints or future rounds.',
]


def _validated(snapshot):
    if (type(snapshot) is not dict or type(snapshot.get('results')) is not list
            or len(snapshot['results']) > 4):
        raise ValueError('zero to four completed recorded worlds required')
    results = snapshot['results']
    world = None
    seen = set()
    verified = []
    for entry in results:
        if type(entry) is not dict or not {'world_index', 'result'} <= set(entry):
            raise ValueError('recorded world entry required')
        index = entry['world_index']
        if type(index) is not int or not 0 <= index <= 3 or index in seen:
            raise ValueError('unique bounded world indexes required')
        seen.add(index)
        report = replay_strategic_world(entry['result'])
        if report['status'] != 'completed':
            raise ValueError('decision insights use completed worlds only')
        if world is None:
            world = report['world']
        elif world != report['world']:
            raise ValueError('one reviewed world definition required')
        verified.append({'world_index': index, 'result': report})
    proposal = snapshot.get('proposal')
    if type(proposal) is dict and proposal.get('world') is not None:
        if world is not None and proposal['world'] != world:
            raise ValueError('snapshot world differs from recorded results')
        if world is None:
            world = validate_strategic_world(proposal['world'])
    return world, sorted(verified, key=lambda entry: entry['world_index'])


def _cash_row(initial, costs, remaining):
    if initial - costs != remaining:
        raise ValueError('strategic cash reconciliation failed')
    return {'initial_cash_cents': str(initial), 'action_cost_cents': str(costs),
            'remaining_cash_cents': str(remaining), 'reconciled': True}


def _resources(world, results):
    base = {'status': 'not_computed', 'reason': 'No completed recorded worlds.',
            'actors': [], 'worlds': [], 'aggregate': None, 'meaning': RESOURCE_MEANING}
    if not results:
        return base
    actors = []
    for actor in world['actors']:
        identifier = actor['id']
        rows = []
        initial = actor['initial_cash_cents']
        total_cost = total_remaining = 0
        for entry in results:
            report = entry['result']
            settled = report['actor_results'][identifier]
            cost = sum(step['receipts'][identifier]['cost_cents'] for step in report['rounds'])
            if cost != settled['cost_cents'] or settled['initial_cash_cents'] != initial:
                raise ValueError('strategic expense receipts differ from actor totals')
            rows.append({'world_index': entry['world_index'],
                         **_cash_row(initial, cost, settled['cash_cents'])})
            total_cost += cost
            total_remaining += settled['cash_cents']
        actors.append({'id': identifier, 'name': actor['name'], 'role': actor['role'],
                       'initial_cash_cents': str(initial), 'worlds': rows,
                       'aggregate': _cash_row(initial * len(results), total_cost, total_remaining)})
    worlds = []
    initial = sum(actor['initial_cash_cents'] for actor in world['actors'])
    total_cost = total_remaining = 0
    for entry in results:
        report = entry['result']
        cost = sum(actor['cost_cents'] for actor in report['actor_results'].values())
        remaining = sum(actor['cash_cents'] for actor in report['actor_results'].values())
        if cost != report['total_cost_cents']:
            raise ValueError('strategic total expenses differ from actor totals')
        worlds.append({'world_index': entry['world_index'], **_cash_row(initial, cost, remaining)})
        total_cost += cost
        total_remaining += remaining
    return {**base, 'status': 'computed', 'reason': None, 'actors': actors, 'worlds': worlds,
            'aggregate': _cash_row(initial * len(results), total_cost, total_remaining)}


def _observed_profiles(world, results, game, analysis):
    identifiers = [actor['id'] for actor in world['actors']]
    table = {tuple(row['actions'][identifier] for identifier in identifiers): row['payoffs']
             for row in game['profiles']}
    observed = []
    for entry in results:
        selected = {identifier: entry['result']['rounds'][0]['decisions'][identifier]['action_id']
                    for identifier in identifiers}
        profile = tuple(selected[identifier] for identifier in identifiers)
        actors = []
        for position, actor in enumerate(world['actors']):
            identifier = actor['id']
            affordable = game['players'][position]['actions']
            utilities = {action['id']: table[profile[:position] + (action['id'],) + profile[position + 1:]][identifier]
                         for action in affordable}
            best = max(utilities.values())
            best_actions = [action for action, utility in utilities.items() if utility == best]
            costs = {action['id']: action['cost_cents'] for action in actor['actions']}
            actors.append({'id': identifier, 'selected_action_id': selected[identifier],
                'selected_utility': str(table[profile][identifier]),
                'best_response_action_ids': best_actions, 'best_response_utility': str(best),
                'unilateral_improvement_utility': str(best - table[profile][identifier]),
                'selected_cost_cents': str(costs[selected[identifier]]),
                'best_responses': [{'action_id': action, 'cost_cents': str(costs[action])}
                                   for action in best_actions]})
        observed.append({'world_index': entry['world_index'], 'actions': selected,
                         'is_pure_nash': selected in analysis['pure_nash_profiles'], 'actors': actors})
    return observed


def _strategic(world, results, *, opening=False):
    base = {'status': 'not_computed', 'reason': 'No completed recorded worlds.',
            'scope': OPENING_SCOPE if opening else STRATEGIC_SCOPE, 'profile_count': None, 'players': [],
            'strategy_beliefs': None, 'pure_nash_profiles': [],
            'strictly_dominated_actions': [], 'observed_profiles': [],
            'utility_unit': 'declared utility points', 'limitations': list(STRATEGIC_LIMITATIONS)}
    if not results:
        return base
    if world['rounds'] != 1 and not opening:
        return {**base, 'reason': 'Only one-round worlds qualify for this static analysis. Multi-round strategies, future events and reactions require a different game model.'}
    computed = strategic_game(world, strategy_beliefs=None)
    if computed['status'] != 'computed':
        return {**base, 'reason': computed['reason']}
    game, analysis = computed['game'], computed['analysis']
    return {**base, 'status': 'computed', 'reason': None,
            'game_sha256': analysis['game_sha256'], 'engine_sha256': analysis['engine_sha256'],
            'profile_count': analysis['profile_count'], 'players': deepcopy(game['players']),
            'utility_unit': analysis['utility_unit'],
            'pure_nash_profiles': deepcopy(analysis['pure_nash_profiles']),
            'strictly_dominated_actions': deepcopy(analysis['strictly_dominated_actions']),
            'observed_profiles': _observed_profiles(world, results, game, analysis)}


def build_insights(snapshot):
    """Return JSON-compatible, replay-verified resources and bounded incentives.

    Results may contain zero to four completed worlds sharing one definition.
    Empty results produce explicit unavailable sections rather than fake zeros.
    Money and utility are decimal integer strings, never floating point values.
    Invalid or tampered records raise ValueError instead of partial insights.
    """
    try:
        world, results = _validated(snapshot)
        strategic = _strategic(world, results)
        opening = (_strategic(world, results, opening=True)
                   if world is not None and world['rounds'] != 1 else deepcopy(strategic))
        value = {'schema_version': 'decision-insights.v1',
                 'source': {'world_sha256': digest(world) if world is not None else None,
                            'completed_worlds': len(results), 'replay_verified': bool(results),
                            'model_requests': 0},
                 'resources': _resources(world, results), 'strategic': strategic,
                 'opening_game': opening,
                 'caveats': [
                     DECISION_RECORD_SCOPE,
                     'All insights are conditional on supplied hypothetical rules and preferences. Replay verifies arithmetic, not empirical truth or predictive accuracy.',
                     'Only completed recorded worlds contribute; failed, interrupted and unattempted worlds are not zero-valued outcomes.',
                     'Action spending is simulated scenario cash. Provider calls, credits and USD billing belong to separate run accounting.',
                     'Author-private output may include persona identities and complete private utility assumptions. Review before sharing.',
                 ],
                 'numeric_format': 'Cash cents and utility are exact decimal integer strings. Counts and bounded indexes are JSON integers.'}
        if len(canonical(value)) > MAX_INSIGHTS_BYTES:
            raise ValueError('decision insights exceed bounded payload')
        return value
    except (KeyError, TypeError, OverflowError, RecursionError) as error:
        raise ValueError('invalid decision insight input') from error
