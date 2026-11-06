"""Versioned state checkpoints and actor market memory for timestamped worlds."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

from .agent_worlds import canonical, digest, _int, _shape, _text
from .timeline_worlds import TimelineWorld, TIMELINE_SHA256, validate_timeline


EVOLVING_SHA256 = sha256(Path(__file__).read_bytes() + TIMELINE_SHA256.encode()).hexdigest()


def validate_evolving(package):
    _shape(package, {'schema_version', 'world', 'start_time', 'decision_seconds', 'events', 'token'})
    if package['schema_version'] != 'timeline-world.v2':
        raise ValueError('unsupported evolving world')
    token = package['token']
    _shape(token, {'symbol', 'decimals', 'total_supply_units', 'circulating_supply_units',
                   'volume_windows_seconds', 'provenance'})
    _text(token['symbol'], 24)
    _text(token['provenance'], 1600)
    _int(token['decimals'], 0, 12)
    _int(token['total_supply_units'], 1, 10**18)
    _int(token['circulating_supply_units'], 1, token['total_supply_units'])
    windows = token['volume_windows_seconds']
    if type(windows) is not list or not 1 <= len(windows) <= 4:
        raise ValueError('one to four volume windows required')
    for window in windows:
        _int(window, 1, 7 * 86400)
    if windows != sorted(set(windows)):
        raise ValueError('sorted unique volume windows required')
    base = {key: deepcopy(value) for key, value in package.items() if key != 'token'}
    base['schema_version'] = 'timeline-world.v1'
    validate_timeline(base)
    if token['total_supply_units'] != package['world']['market']['project_token_units']:
        raise ValueError('declared token supply must match the conserved initial ledger supply')
    return deepcopy(package), base


class EvolvingWorld(TimelineWorld):
    def __init__(self, package, seed=42):
        self.evolving_package, base = validate_evolving(package)
        self.checkpoints = []
        super().__init__(base, seed)

    def market_state(self, second):
        pool = self.ledger.accounts['pool']
        token = self.evolving_package['token']
        turnover = []
        for index, phase in enumerate(self.history):
            for receipt in phase['settlements']:
                if receipt['status'] == 'executed' and receipt['fill'] is not None:
                    turnover.append((self.steps[index], receipt['fill']['cash_cents']))
        return {
            'elapsed_seconds': second,
            'price_usd_per_token_exact': str(Fraction(pool.cash_cents * 10**token['decimals'],
                                                       pool.token_units * 100)),
            'market_cap_usd_exact': str(Fraction(pool.cash_cents * token['circulating_supply_units'],
                                                pool.token_units * 100)),
            'fdv_usd_exact': str(Fraction(pool.cash_cents * token['total_supply_units'],
                                         pool.token_units * 100)),
            'pool_cash_cents': pool.cash_cents, 'pool_token_units': pool.token_units,
            'volume_windows_cents': {str(window): sum(amount for timestamp, amount in turnover
                                                     if second - window < timestamp <= second)
                                     for window in token['volume_windows_seconds']},
            'cumulative_volume_cents': sum(amount for _, amount in turnover),
            'executed_trade_count': len(turnover),
            'supply_provenance': token['provenance'],
            'limitations': 'Point-in-time synthetic venue. Reserves are not executable liquidity at every trade size. '
                          'Volume is simulated executed turnover; exact window is (end-window, end]. '
                          'Market cap uses declared circulating supply, not independently verified supply.'}

    def snapshot(self):
        base = super().snapshot()
        second = self.steps[min(self.round - 1, len(self.steps) - 1)]
        return {**base, 'token_state': self.market_state(second)}

    def observations(self):
        observations = super().observations()
        if not observations:
            return observations
        for actor_id, observation in observations.items():
            observation['messages'] = [message for message in observation['messages']
                                       if not message['id'].startswith('state-memory:')]
            memory = [{'elapsed_seconds': checkpoint['elapsed_seconds'],
                       'market_before': checkpoint['market_before'],
                       'market_after': checkpoint['market_after'],
                       'own_balance_before': checkpoint['balances_before'][actor_id],
                       'own_balance_after': checkpoint['balances_after'][actor_id]}
                      for checkpoint in self.checkpoints]
            message = {'id': f'state-memory:{self.round}', 'source': 'news',
                       'published_round': self.round,
                       'text': canonical({'completed_barriers': memory,
                                          'meaning': 'Recorded public market history and only your own balances. '
                                                     'Your own choices/settlements are in own_history. '
                                                     'No future event, other actor balance or private plan is included.'}).decode(),
                       'stance': 'external', 'citations': [],
                       'provenance': 'engine-derived state memory'}
            observation['messages'] = (observation['messages'] + [message])[-64:]
            visible_ids = {item['id'] for item in observation['messages']}
            observation['new_message_ids'] = [identifier for identifier in observation['new_message_ids']
                                               if identifier in visible_ids]
            observation['new_message_ids'].append(message['id'])
            observation.pop('observation_sha256')
            observation['observation_sha256'] = digest(observation)
        return observations

    def advance(self, proposals):
        if self.round > len(self.steps):
            raise ValueError('world completed')
        second = self.steps[self.round - 1]
        before = self.market_state(second)
        balances_before = {owner: {'cash_cents': balance.cash_cents, 'token_units': balance.token_units}
                           for owner, balance in self.ledger.accounts.items()}
        super().advance(proposals)
        phase = self.history[-1]
        self.checkpoints.append({
            'barrier': len(self.history), 'elapsed_seconds': second,
            'market_before': before, 'market_after': self.market_state(second),
            'balances_before': balances_before,
            'balances_after': {owner: {'cash_cents': balance.cash_cents, 'token_units': balance.token_units}
                               for owner, balance in self.ledger.accounts.items()},
            'own_choices_by_actor': {turn['actor_id']: deepcopy(turn) for turn in phase['proposals']},
            'settlements': deepcopy(phase['settlements']),
            'observation_hashes': {actor: observation['observation_sha256']
                                   for actor, observation in phase['observations'].items()},
            'pending_commitments_status': 'not implemented; no delayed campaign or order queue claimed'})
        return self.report()

    def timeline_report(self):
        report = super().timeline_report()
        report.update(schema_version='timeline-world-results.v2', package=deepcopy(self.evolving_package),
                      package_sha256=digest(self.evolving_package), timeline_engine_sha256=EVOLVING_SHA256,
                      checkpoints=deepcopy(self.checkpoints))
        return report


def make_timeline(package, seed=42):
    if type(package) is not dict:
        raise ValueError('timeline package object required')
    if package.get('schema_version') == 'timeline-world.v2':
        return EvolvingWorld(package, seed)
    return TimelineWorld(package, seed)


def replay_evolving(report):
    from .timeline_worlds import replay_timeline
    if type(report) is not dict:
        raise ValueError('timeline report object required')
    if report.get('schema_version') == 'timeline-world-results.v1':
        return replay_timeline(report)
    _shape(report, {'schema_version', 'package', 'package_sha256', 'timeline_engine_sha256',
                    'financial_report', 'realized_event_ids', 'final_market', 'checkpoints'})
    if report['schema_version'] != 'timeline-world-results.v2' or len(canonical(report)) > 8 * 1024 * 1024:
        raise ValueError('invalid bounded evolving report')
    engine = EvolvingWorld(report['package'], report['financial_report']['seed'])
    for phase in report['financial_report']['history']:
        engine.advance(phase['proposals'])
    if engine.timeline_report() != report:
        raise ValueError('evolving state replay mismatch')
    return engine.timeline_report()


def evolving_actor_trajectory(report, actor_id):
    from .timeline_worlds import actor_trajectory
    if type(report) is not dict:
        raise ValueError('timeline report object required')
    if report.get('schema_version') == 'timeline-world-results.v1':
        return actor_trajectory(report, actor_id)
    replay_evolving(report)
    if actor_id not in {actor['id'] for actor in report['package']['world']['agents']}:
        raise ValueError('unknown actor')
    nodes = []
    for phase, checkpoint in zip(report['financial_report']['history'], report['checkpoints']):
        nodes.append({'id': f'barrier-{phase["round"]}', 'elapsed_seconds': checkpoint['elapsed_seconds'],
                      'observation': deepcopy(phase['observations'][actor_id]),
                      'own_action': deepcopy(checkpoint['own_choices_by_actor'][actor_id]),
                      'own_settlement': deepcopy(next(item for item in phase['settlements'] if item['actor_id'] == actor_id)),
                      'market_before': deepcopy(checkpoint['market_before']),
                      'market_after': deepcopy(checkpoint['market_after']),
                      'own_balance_after': deepcopy(checkpoint['balances_after'][actor_id])})
    return {'schema_version': 'actor-timeline.v2', 'actor_id': actor_id,
            'start_time': report['package']['start_time'], 'nodes': nodes,
            'edges': [{'from': nodes[index]['id'], 'to': nodes[index + 1]['id'],
                       'duration_seconds': nodes[index + 1]['elapsed_seconds'] - nodes[index]['elapsed_seconds'],
                       'meaning': 'Own action then later observation; no causal claim.'}
                      for index in range(len(nodes) - 1)],
            'probability_status': 'One recorded path; threshold odds not estimated.'}
