"""Timestamped actor decisions over the bounded synthetic financial engine."""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

from .agent_worlds import AgentWorld, ENGINE_SHA256, canonical, digest, _int, _shape, _text
from .randomness import keyed_rng


TIMELINE_SHA256 = sha256(Path(__file__).read_bytes() + ENGINE_SHA256.encode()).hexdigest()


def validate_timeline(package):
    _shape(package, {'schema_version', 'world', 'start_time', 'decision_seconds', 'events'})
    if package['schema_version'] != 'timeline-world.v1':
        raise ValueError('unsupported timeline package')
    if len(canonical(package)) > 262144:
        raise ValueError('timeline input exceeds budget')
    start = datetime.fromisoformat(package['start_time'])
    if start.utcoffset() is None:
        raise ValueError('timezone required')
    steps = package['decision_seconds']
    if type(steps) is not list or not 1 <= len(steps) <= 16:
        raise ValueError('bounded decision schedule required')
    for second in steps:
        _int(second, 0, 7 * 86400)
    if steps != sorted(set(steps)) or steps[0] != 0:
        raise ValueError('strictly increasing schedule starting at zero required')
    world = deepcopy(package['world'])
    if world['rounds'] != len(steps) or world['events']:
        raise ValueError('round count must match schedule; events belong to timeline')
    AgentWorld(world)
    actors = {actor['id'] for actor in world['agents']}
    events = package['events']
    if type(events) is not list or len(events) > 16:
        raise ValueError('bounded event list required')
    identifiers = set()
    for event in events:
        _shape(event, {'id', 'event_second', 'available_second', 'text', 'source_ref',
                       'evidence_status', 'occurrence_bps', 'audience'})
        _text(event['id'], 48)
        if event['id'] in identifiers or not event['id'].isascii() or not event['id'].replace('-', '').isalnum():
            raise ValueError('unique ASCII event identifiers required')
        identifiers.add(event['id'])
        _int(event['event_second'], 0, steps[-1])
        _int(event['available_second'], event['event_second'], steps[-1])
        _int(event['occurrence_bps'], 0, 10000)
        for key in ('text', 'source_ref'):
            _text(event[key], 1600)
        if event['evidence_status'] not in {'assumed_stress', 'sourced_calendar', 'estimated_historical'}:
            raise ValueError('event evidence status required')
        audience = event['audience']
        if (type(audience) is not list or not audience or len(audience) != len(set(audience))
                or not set(audience) <= actors | {'public'} or ('public' in audience and len(audience) != 1)):
            raise ValueError('explicit event audience required')
    return deepcopy(package)


class TimelineWorld(AgentWorld):
    def __init__(self, package, seed=42):
        self.package = validate_timeline(package)
        self.steps = self.package['decision_seconds']
        self.start_time = datetime.fromisoformat(self.package['start_time'])
        self.realized_events = [event for event in self.package['events']
                                if keyed_rng(seed, 'timeline-event', event['id']).randrange(10000)
                                < event['occurrence_bps']]
        super().__init__(self.package['world'], seed)

    def snapshot(self):
        pool = self.ledger.accounts['pool']
        last = self.history[-1]['settlements'] if self.history else []
        volume = sum(receipt['fill']['cash_cents'] for receipt in last
                     if receipt['status'] == 'executed' and receipt['fill'] is not None)
        previous = 0
        if len(self.history) > 1:
            previous = sum(receipt['fill']['cash_cents'] for receipt in self.history[-2]['settlements']
                           if receipt['status'] == 'executed' and receipt['fill'] is not None)
        return {
            'pool_cash_cents': pool.cash_cents, 'pool_token_units': pool.token_units,
            'price_cents_per_token_unit': {'numerator': pool.cash_cents, 'denominator': pool.token_units},
            'previous_barrier_volume_cents': volume,
            'previous_barrier_volume_meaning': 'Executed cash turnover at the previous decision barrier; not hourly volume.',
            'volume_increased_vs_prior_barrier': volume > previous if len(self.history) > 1 else None,
            'limitations': 'Synthetic constant-product pool; no calibrated demand, migration or live price.'}

    def observations(self):
        observations = super().observations()
        if not observations:
            return observations
        second = self.steps[self.round - 1]
        clock = {'elapsed_seconds': second,
                 'timestamp': (self.start_time + timedelta(seconds=second)).isoformat(),
                 'decision_barrier': self.round, 'market': self.snapshot()}
        for actor_id, observation in observations.items():
            observation['messages'] = [message for message in observation['messages']
                                       if not message['id'].startswith('clock:')]
            known = {message['id'] for message in observation['messages']}
            added = []
            for event in self.realized_events:
                message_id = 'timed:' + event['id']
                if (event['available_second'] <= second and message_id not in known
                        and ('public' in event['audience'] or actor_id in event['audience'])):
                    added.append({'id': message_id, 'source': 'news', 'published_round': self.round,
                                  'text': event['text'], 'stance': 'external', 'citations': [],
                                  'provenance': {'source_ref': event['source_ref'],
                                                 'evidence_status': event['evidence_status'],
                                                 'event_second': event['event_second'],
                                                 'available_second': event['available_second']}})
            state = {'id': f'clock:{self.round}', 'source': 'news', 'published_round': self.round,
                     'text': canonical(clock).decode(), 'stance': 'external', 'citations': [],
                     'provenance': 'engine-derived timestamp and market; no future or peer private state'}
            observation['messages'] = (observation['messages'] + added + [state])[-64:]
            observation['new_message_ids'] = [message_id for message_id in observation['new_message_ids']
                                               if message_id in {item['id'] for item in observation['messages']}]
            observation['new_message_ids'].extend(item['id'] for item in added + [state])
            observation.pop('observation_sha256')
            observation['observation_sha256'] = digest(observation)
        return observations

    def timeline_report(self):
        return {'schema_version': 'timeline-world-results.v1', 'package': deepcopy(self.package),
                'package_sha256': digest(self.package), 'timeline_engine_sha256': TIMELINE_SHA256,
                'financial_report': super().report(),
                'realized_event_ids': [event['id'] for event in self.realized_events],
                'final_market': self.snapshot()}


def replay_timeline(report):
    _shape(report, {'schema_version', 'package', 'package_sha256', 'timeline_engine_sha256',
                    'financial_report', 'realized_event_ids', 'final_market'})
    if report['schema_version'] != 'timeline-world-results.v1' or len(canonical(report)) > 8 * 1024 * 1024:
        raise ValueError('invalid bounded timeline report')
    engine = TimelineWorld(report['package'], report['financial_report']['seed'])
    for phase in report['financial_report']['history']:
        engine.advance(phase['proposals'])
    if engine.timeline_report() != report:
        raise ValueError('timeline replay mismatch')
    return engine.timeline_report()


def actor_trajectory(report, actor_id):
    """Project verified receipts without serializing another actor's private state."""
    replay_timeline(report)
    world = report['package']['world']
    if actor_id not in {actor['id'] for actor in world['agents']}:
        raise ValueError('unknown actor')
    steps = report['package']['decision_seconds']
    nodes = []
    for index, phase in enumerate(report['financial_report']['history']):
        nodes.append({'id': f'barrier-{index + 1}', 'elapsed_seconds': steps[index],
                      'observation': deepcopy(phase['observations'][actor_id]),
                      'own_action': deepcopy(next(item for item in phase['proposals'] if item['actor_id'] == actor_id)),
                      'own_settlement': deepcopy(next(item for item in phase['settlements'] if item['actor_id'] == actor_id))})
    return {'schema_version': 'actor-timeline.v1', 'actor_id': actor_id,
            'start_time': report['package']['start_time'], 'nodes': nodes,
            'edges': [{'from': nodes[index]['id'], 'to': nodes[index + 1]['id'],
                       'duration_seconds': nodes[index + 1]['elapsed_seconds'] - nodes[index]['elapsed_seconds'],
                       'meaning': 'Own action then later observation; no causal claim.'}
                      for index in range(len(nodes) - 1)],
            'probability_status': 'One recorded path; threshold odds not estimated.'}
