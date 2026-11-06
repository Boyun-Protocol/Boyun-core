"""Deterministic construction review for declared, hypothetical strategic games.

The author audit is private. Actor support follows the engine's observation
boundary. Neither function interprets biographies, verifies sources, estimates
beliefs, solves an equilibrium, or validates human behavior.
"""
from collections import Counter
from copy import deepcopy

from .agent_worlds import canonical, digest
from .strategic_worlds import StrategicWorld, validate_strategic_world
from .stress_planning import STRESS_PLANNING_GUIDELINES


GAME_CONSTRUCTION_GUIDELINES = '''Boyun focuses on financial and economic decisions and game-theoretic interactions.
Construct the game before elaborating personas; include actors because their goals, resources, information
or incentives affect the research question, not to populate a general social story:
1. State the decision, focal actor, horizon and terminal objective. Jev is the main actor decision
mechanism when requested; it chooses from each actor's reviewed feasible menu using that actor's
own information. A main actor is an explicitly chosen actor ID, never inferred from a name.
2. Identify players and represented roles. Distinguish a player from a type: types differ in
preferences, cash/resources, private information, feasible actions or observation links. Narrative
adjectives alone do not create a game-theoretic type. Actor count is a modeled cast, not an inferred
population. Explain why each role is included and which strategic dependency it represents.
3. Give each actor a declared motivation and goal, then operationalize preferences in signed integer
utility weights with units. Explain how costs, retained cash and bounded metrics implement the goal.
Show a numerical tradeoff. A risk-averse biography is not a modeled risk preference: this engine has
linear weighted utility and no stochastic lotteries or nonlinear risk utility. Keep such language a
behavioral hypothesis unless the supported numeric mechanism actually represents it.
4. Specify feasible actions, opportunity costs and the silent zero-cost wait outside option. Wait
does not mean exiting the game or freezing shared metrics. Include materially different choices
where useful; a story about maximizing an outcome does not prove the numeric objective matches it.
5. Specify information sets: own private information, public metric values, visible event text and
explicit subscriptions. Distinguish epistemic uncertainty from stochastic event probabilities.
Do not invent numeric beliefs. Messages are unverified claims and arrive next round. Public metric
effects remain visible even when event text is private. Future event text is hidden until scheduled.
6. State simultaneous action timing, aggregation before metric clamping, per-stage cash costs,
scheduled events and final weighted-utility evaluation. More rounds do not solve a repeated game.
Represent coordination with explicit conditional joint-action rules and payoff consequences.
Promises, threats and commitments have no enforcement beyond implemented costs/effects/rules;
do not imply off-engine contracts, transfers, borrowing or on-chain enforcement.
7. Keep source-supported context separate from assumptions and model proposals. Every number,
motivation, type allocation and effect needs provenance and a rationale. References are context,
not proof of fitted coefficients or observed motives. State missing evidence and unsupported rules.
8. Preserve total capital, scenario resources and represented population when varying persona
detail. Refining a type or adding variants must explicitly reallocate a fixed budget, not duplicate
cash or silently claim additional people. Compare variants under stable economics and disclose any
intentional budget or cast change. Avoid identity-based motive inference.
9. Review own-action counterfactuals separately from peer responses, joint rules and future effects.
Use objective-sensitive cross-dependencies to explain why this is a strategic interaction. Numeric
diagnostics are construction checks, not evidence of realistic behavior or a solved Nash equilibrium.'''

GAME_CONSTRUCTION_GUIDELINES += '\n\n' + STRESS_PLANNING_GUIDELINES

_EXCLUDED = ['other_actor_actions', 'joint_interaction_effects', 'future_events', 'future_rounds']
MAX_AUDIT_BYTES = 1024 * 1024
_COUNTERFACTUAL_SCOPE = (
    'Initial first-round state after aggregate round-one event effects and metric bounds. '
    'Each own action is applied alone against wait, with own cash cost and bounded metric changes. '
    'Other actor actions, all joint interaction effects, future events and future rounds are excluded. '
    'This is an isolated marginal utility check, not an optimal strategy or forecast.')
_LIMITATIONS = [
    'Motivations, goals, utility weights, types, effects and events are supplied hypothetical declarations; semantic alignment and human behavior are not validated.',
    _COUNTERFACTUAL_SCOPE,
    'Cross-dependencies measure only initially affordable individual effects and separate joint-rule increments at the initial bounded state. Cancellation, bounds or later states can change them; absence is not proof of strategic independence.',
    'No beliefs, event probabilities, population estimates, best responses or Nash equilibrium are inferred.',
    'Source references are retained attribution only; evidence verification and coefficient fitting are not performed.',
    'The author audit contains private scenario details and must not be given to actors. Use actor_game_support for the engine observation boundary.',
]


def _specification(world):
    return {
        'players': 'Explicit actor IDs; supplied role labels describe represented types, not observed populations.',
        'timing': 'Simultaneous actions each round; subscriptions deliver chosen messages in the following round.',
        'rounds': world['rounds'],
        'stage_transition': 'Scheduled event effects aggregate and clamp before the round. Affordable action and matched joint-rule effects then aggregate and clamp; own cash costs enter a cost sink.',
        'terminal_objective': 'Declared weighted utility of remaining own cash and final shared metrics. Utility points are not cash profit; no separate intermediate reward is accumulated.',
        'outside_option': 'wait is silent and zero-cost with no own effect. Other actors and events can still change shared metrics; external exit is not modeled.',
        'commitments': 'Only implemented cash costs and conditional joint-action metric effects are enforced. Messages have no independent enforcement.',
        'beliefs': 'Not represented in strategic-world.v1/v2; no belief distribution is inferred.',
        'utility_formula': 'sum(weight[metric] * metric_value) + weight[cash_cents] * remaining_own_cash_cents; omitted weights are zero.',
    }


def _counterfactuals(engine, actor):
    cash = actor['initial_cash_cents']
    baseline = engine._utility(actor, cash, engine.metrics)
    choices = []
    for action in actor['actions']:
        affordable = action['cost_cents'] <= cash
        metrics = engine._changed_metrics(engine.metrics, [action['effects']]) if affordable else None
        remaining = cash - action['cost_cents'] if affordable else None
        utility = engine._utility(actor, remaining, metrics) if affordable else None
        choices.append({'action_id': action['id'], 'label': action['label'],
            'affordable': affordable, 'cost_cents': action['cost_cents'],
            'cash_after_cents': remaining, 'metrics_after': metrics,
            'utility': utility, 'utility_delta': utility - baseline if affordable else None})
    return {'scope': _COUNTERFACTUAL_SCOPE, 'excluded': list(_EXCLUDED),
        'baseline_metrics': deepcopy(engine.metrics), 'baseline_utility': baseline,
        'affordable_action_ids': [a['action_id'] for a in choices if a['affordable']], 'actions': choices}


def _utility_units(world, actor):
    units = {metric['id']: metric['unit'] for metric in world['metrics']}
    units['cash_cents'] = 'cash cent'
    return {key: f'utility points per {units[key]}' for key in actor['utility_weights']}


def actor_game_support(world, actor_id):
    """Return first-round own-information support; never include author audit data."""
    engine = StrategicWorld(world)
    if type(actor_id) is not str or actor_id not in {a['id'] for a in engine.world['actors']}:
        raise ValueError('known actor ID required')
    actor = next(a for a in engine.world['actors'] if a['id'] == actor_id)
    observation = engine.observations()[actor_id]
    return {'schema_version': 'actor-game-support.v1', 'world_id': engine.world['id'],
        'actor_id': actor_id, 'observation_sha256': observation['observation_sha256'],
        'actor': deepcopy(observation['actor']), 'cash_cents': observation['cash_cents'],
        'utility_units': _utility_units(engine.world, actor),
        'specification': _specification(engine.world),
        'information': {'public_metrics': deepcopy(observation['metrics']),
            'metric_definitions': deepcopy(observation['world']['metric_definitions']),
            'public_counterparties': deepcopy(observation['opponents']),
            'subscriptions': list(actor['subscriptions']),
            'visible_events': deepcopy(observation['events']),
            'messages': deepcopy(observation['messages']),
            'interactions': deepcopy(observation['interactions'])},
        'own_action_counterfactuals': _counterfactuals(engine, actor),
        'limitations': [_COUNTERFACTUAL_SCOPE,
            'Only own utility weights and the engine first-round information boundary are used. Peer preferences, cash and private information are unavailable.']}


def _dependencies(engine):
    actors = engine.world['actors']
    edges = []
    for source in actors:
        outcomes = [(action, engine._changed_metrics(engine.metrics, [action['effects']]))
                    for action in source['actions'] if action['cost_cents'] <= source['initial_cash_cents']]
        for target in actors:
            if source['id'] == target['id']:
                continue
            baseline = engine._utility(target, target['initial_cash_cents'], engine.metrics)
            deltas = [(action, metrics, engine._utility(target, target['initial_cash_cents'], metrics) - baseline)
                      for action, metrics in outcomes]
            relevant = [(action, metrics, delta) for action, metrics, delta in deltas if delta]
            if relevant:
                metric_ids = sorted({key for _, metrics, _ in relevant for key in metrics
                    if metrics[key] != engine.metrics[key] and target['utility_weights'].get(key, 0)})
                edges.append({'source_actor_id': source['id'], 'target_actor_id': target['id'],
                    'action_ids': [action['id'] for action, _, _ in relevant], 'metric_ids': metric_ids,
                    'utility_delta_min': min(delta for _, _, delta in deltas),
                    'utility_delta_max': max(delta for _, _, delta in deltas)})
    actors_by_id = {actor['id']: actor for actor in actors}
    rules = []
    for rule in engine.world['interactions']:
        after = engine._changed_metrics(engine.metrics, [rule['effects']])
        affected = []
        for actor in actors:
            delta = engine._utility(actor, actor['initial_cash_cents'], after) - engine._utility(actor, actor['initial_cash_cents'], engine.metrics)
            if delta:
                affected.append({'actor_id': actor['id'], 'utility_delta': delta})
        affordable = all(next(action for action in actors_by_id[key]['actions'] if action['id'] == action_id)['cost_cents']
            <= actors_by_id[key]['initial_cash_cents'] for key, action_id in rule['when'].items())
        rules.append({'id': rule['id'], 'when': deepcopy(rule['when']),
            'initially_feasible': affordable, 'effects': deepcopy(rule['effects']),
            'affected_objectives': affected})
    return {'scope': 'Private author view. Direct edges exclude own costs and joint rules; joint increments apply each rule alone. All are bounded first-round comparisons against no effect, not joint-profile payoffs.',
        'direct_edges': edges, 'joint_rules': rules}


def _provenance_summary(world):
    objects = [*world['metrics'], *world['actors'], *world['events'], *world['interactions']]
    objects.extend(action for actor in world['actors'] for action in actor['actions'])
    refs = sorted({ref for item in objects for ref in item['provenance']['source_refs']})
    return {'status_counts': dict(sorted(Counter(item['provenance']['status'] for item in objects).items())),
        'source_refs': refs, 'source_ref_count': len(refs), 'omitted_source_ref_count': 0,
        'evidence_verification': 'not_performed',
        'meaning': 'Declared provenance status and context references; no supplied value becomes an established fact through this audit.'}


def game_construction_audit(world, *, main_actor_id=None):
    """Validate and describe a bounded game, with exact isolated utility diagnostics.

    Returns author-only data. It does not call a provider or read environment/network
    state. Complexity is bounded by existing world actor/action/metric limits and
    uses no exhaustive joint-strategy enumeration.
    """
    validated = validate_strategic_world(world)
    if main_actor_id is not None and (type(main_actor_id) is not str or main_actor_id not in {a['id'] for a in validated['actors']}):
        raise ValueError('known main actor ID required')
    engine = StrategicWorld(validated)
    dependencies = _dependencies(engine)
    warnings = []
    actor_reports = []
    actor_lookup = {a['id']: a for a in validated['actors']}
    observations = engine.observations()
    for actor in validated['actors']:
        identifier = actor['id']
        own = _counterfactuals(engine, actor)
        incoming = [e['source_actor_id'] for e in dependencies['direct_edges'] if e['target_actor_id'] == identifier]
        outgoing = [e['target_actor_id'] for e in dependencies['direct_edges'] if e['source_actor_id'] == identifier]
        joint_ids = [rule['id'] for rule in dependencies['joint_rules'] if rule['initially_feasible'] and rule['affected_objectives']
            and (identifier in rule['when'] or any(effect['actor_id'] == identifier for effect in rule['affected_objectives']))]
        possible_messages = validated['rounds'] > 1 and any(action['message'] for source in actor['subscriptions']
            for action in actor_lookup[source]['actions'] if action['cost_cents'] <= actor_lookup[source]['initial_cash_cents'])
        checks = [
            ('zero_utility_weights', not any(actor['utility_weights'].values()), 'Every declared utility weight is zero.'),
            ('one_affordable_action', len(own['affordable_action_ids']) == 1, 'Only wait is initially affordable.'),
            ('no_distinct_own_action_utility', len({a['utility'] for a in own['actions'] if a['affordable']}) == 1,
                'All initially affordable own-action utilities tie in the isolated counterfactual; joint effects and later states are excluded.'),
            ('no_initial_objective_coupling', not incoming and not outgoing and not joint_ids,
                'No nonzero objective-sensitive direct edge or feasible joint-rule increment touches this actor at the initial bounded state.'),
            ('no_possible_peer_messages', not possible_messages,
                'No subscribed source can deliver an initially affordable nonempty message before this horizon ends. This checks message availability, not future model behavior.'),
        ]
        warnings.extend({'code': code, 'actor_id': identifier, 'message': message} for code, condition, message in checks if condition)
        obs = observations[identifier]
        actor_reports.append({key: deepcopy(actor[key]) for key in ('id', 'name', 'role', 'motivation', 'goal', 'initial_cash_cents', 'utility_weights', 'subscriptions', 'provenance')})
        actor_reports[-1].update({'utility_units': _utility_units(validated, actor),
            'actions': [{key: deepcopy(action[key]) for key in ('id', 'label', 'cost_cents', 'effects')}
                | {'has_message': bool(action['message'])} for action in actor['actions']],
            'outside_option': {'action_id': 'wait', 'external_exit_modeled': False},
            'information_visibility': {'public_counterparty_ids': [other['id'] for other in obs['opponents']],
                'visible_initial_event_ids': [event['id'] for event in obs['events']],
                'private_information_owner': identifier, 'has_private_information': bool(actor['information']), 'message_delay_rounds': 1},
            'own_action_counterfactuals': own,
            'objective_dependencies': {'incoming_actor_ids': incoming[:12], 'outgoing_actor_ids': outgoing[:12],
                'incoming_actor_count': len(incoming), 'outgoing_actor_count': len(outgoing),
                'omitted_incoming_actor_ids': max(0, len(incoming) - 12),
                'omitted_outgoing_actor_ids': max(0, len(outgoing) - 12), 'joint_rule_ids': joint_ids}})
    edge_count = len(dependencies['direct_edges'])
    dependencies['direct_edge_count'] = edge_count
    dependencies['omitted_direct_edge_count'] = 0
    result = {'schema_version': 'game-construction-audit.v1', 'world_id': validated['id'],
        'world_sha256': digest(validated), 'audience': 'private_author_review', 'main_actor_id': main_actor_id,
        'specification': _specification(validated), 'metrics': deepcopy(validated['metrics']),
        'representation': {'actor_count': len(validated['actors']),
            'role_counts': dict(sorted(Counter(actor['role'] for actor in validated['actors']).items())),
            'population_estimate': None,
            'meaning': 'Counts of explicit modeled actors and declared role labels; not people, market share or validated behavioral types.'},
        'economics': {'total_initial_cash_cents': sum(actor['initial_cash_cents'] for actor in validated['actors']),
            'capital_allocation_cents': {actor['id']: actor['initial_cash_cents'] for actor in validated['actors']},
            'cash_mechanics': 'Own nonnegative action costs reduce cash and enter a cost sink. No transfers, borrowing, asset valuation or external income are modeled.'},
        'actors': actor_reports, 'cross_dependencies': dependencies,
        'provenance': _provenance_summary(validated), 'assumptions': deepcopy(validated['assumptions']),
        'declared_limitations': deepcopy(validated['limitations']), 'warnings': warnings,
        'detail_omissions': ['Actor action descriptions, message text and private-information text are omitted; action effects and information visibility remain explicit.',
            'Dependency ID samples retain at most twelve IDs per direction; their total and omitted counts are explicit.',
            'If direct edge details are omitted, retained entries are an input-order prefix; direct_edge_count includes all evaluated edges.'],
        'limitations': list(_LIMITATIONS)}
    # Dense objective coupling is possible even with sparse communication. Keep
    # exact total counts, but omit a deterministic tail of edges to bound review.
    while len(canonical(result)) > MAX_AUDIT_BYTES and dependencies['direct_edges']:
        dependencies['direct_edges'] = dependencies['direct_edges'][:len(dependencies['direct_edges']) // 2]
        dependencies['omitted_direct_edge_count'] = edge_count - len(dependencies['direct_edges'])
    if len(canonical(result)) > MAX_AUDIT_BYTES:
        for actor in actor_reports:
            for action in actor['own_action_counterfactuals']['actions']:
                action.pop('metrics_after', None)
            for action in actor['actions']:
                action.pop('effects', None)
        result['detail_omissions'].append('Per-action metric snapshots and duplicate menu effects are omitted for the byte budget; exact utility and cash comparisons remain.')
    if len(canonical(result)) > MAX_AUDIT_BYTES:
        result['provenance']['source_refs'] = []
        result['provenance']['omitted_source_ref_count'] = result['provenance']['source_ref_count']
        result['detail_omissions'].append('The duplicate global source-reference list is omitted; its exact count and retained actor/metric provenance remain explicit.')
    if len(canonical(result)) > MAX_AUDIT_BYTES:
        for actor in actor_reports:
            actor.pop('provenance', None)
            for action in actor['actions']:
                action.pop('label', None)
        result['detail_omissions'].append('Per-actor provenance and duplicate action labels are omitted for the byte budget; global provenance counts and action counterfactual labels remain.')
    return result


def game_construction_summary(world, *, main_actor_id=None):
    """Compact review/hash metadata; no actor biographies, goals or private text."""
    report = game_construction_audit(world, main_actor_id=main_actor_id)
    return {'schema_version': 'game-construction-summary.v1', 'world_sha256': report['world_sha256'],
        'actor_count': report['representation']['actor_count'],
        'role_label_count': len(report['representation']['role_counts']),
        'population_estimate': None, 'main_actor_selected': main_actor_id is not None,
        'rounds': report['specification']['rounds'], 'metric_count': len(report['metrics']),
        'action_count': sum(len(actor['actions']) for actor in report['actors']),
        'initially_affordable_action_count': sum(len(actor['own_action_counterfactuals']['affordable_action_ids']) for actor in report['actors']),
        'total_initial_cash_cents': report['economics']['total_initial_cash_cents'],
        'direct_dependency_edge_count': report['cross_dependencies']['direct_edge_count'],
        'interaction_rule_count': len(report['cross_dependencies']['joint_rules']),
        'objective_sensitive_joint_rule_count': sum(bool(rule['affected_objectives']) and rule['initially_feasible'] for rule in report['cross_dependencies']['joint_rules']),
        'warning_count': len(report['warnings']),
        'warning_counts': dict(sorted(Counter(warning['code'] for warning in report['warnings']).items())),
        'provenance_status_counts': report['provenance']['status_counts'],
        'source_ref_count': report['provenance']['source_ref_count'],
        'interpretation': 'Declared hypothetical game construction diagnostics; no population, behavioral validation, source verification or equilibrium claim.'}
