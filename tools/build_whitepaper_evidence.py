"""Reproduce the whitepaper's synthetic arithmetic and resolve its code anchors.

No credentials, inference, chain calls or observed personal data are read. Outbound
socket creation is rejected during experiments. --check compares deterministic
artifacts; it does not certify the manuscript's scientific claims.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine/src'))
sys.path.insert(0, str(ROOT / 'tools'))
from build_evidence_docs import symbols


def communication_ablation(template, engine_type, replay):
    """A deterministic mechanism test, not an estimated behavioral experiment."""
    base = deepcopy(template)
    base.update(id='paper-mechanism-fixture', title='Synthetic communication ablation',
                events=[], interactions=[])
    base['metrics'][0]['initial'] = 0
    alice, bob = base['actors']
    alice['subscriptions'] = []
    bob['subscriptions'] = ['alice']
    alice['actions'][1].update(cost_cents=20, effects={'readiness': 1})
    bob['actions'][1].update(id='join', label='Join', cost_cents=30,
                             effects={'readiness': 2}, message='')
    base['interactions'] = [{'id': 'coordination', 'when': {'alice': 'wait', 'bob': 'join'},
                             'effects': {'readiness': 3},
                             'description': 'Assumed complementarity after an early build.',
                             'provenance': deepcopy(alice['provenance'])}]
    rows = []
    for identifier, delivery, joint in (
        ('delivery-and-joint-rule', True, True), ('delivery-only', True, False),
        ('joint-rule-only', False, True), ('neither', False, False),
    ):
        world = deepcopy(base)
        if not delivery:
            world['actors'][1]['subscriptions'] = []
        if not joint:
            world['interactions'] = []
        engine = engine_type(world, seed=42)
        received = 0
        for round_number in (1, 2):
            observations = engine.observations()
            messages = observations['bob']['messages']
            if round_number == 2:
                received = len(messages)
            actions = {'alice': 'build' if round_number == 1 else 'wait',
                       'bob': 'join' if any(m['source'] == 'alice' for m in messages) else 'wait'}
            engine.advance({actor: {'action_id': action,
                                    'observation_sha256': observations[actor]['observation_sha256']}
                            for actor, action in actions.items()})
        report = engine.report()
        assert replay(report) == report
        rows.append({'id': identifier, 'delivery': delivery, 'joint_rule': joint,
                     'reviewer_messages_before_round_two': received,
                     'final_readiness': report['final_metrics']['readiness'],
                     'action_cost_cents': report['total_cost_cents'],
                     'remaining_cash_cents': sum(a['cash_cents'] for a in report['actor_results'].values()),
                     'exact_replay': True, 'report': report})
    return {'base_world': base,
            'policy_source': 'Explicit deterministic test policy, not Jev or human behavior.',
            'policy': 'Alice builds only in round one. Bob joins only after receiving Alice\'s message; otherwise waits.',
            'model_calls': 0, 'conditions': rows}


def persona_preference_check(world, engine_type, replay):
    from decision_lab.game_construction import game_construction_audit
    from decision_lab.offline_decisions import OfflineDecisions
    from decision_lab.strategic_models import decide
    conditions = []
    baseline = None
    for label in ('declared-preferences', 'stronger-risk-penalty', 'narrative-only'):
        value = deepcopy(world)
        if label == 'stronger-risk-penalty':
            next(a for a in value['actors'] if a['id'] == 'momentum')['utility_weights']['risk'] = -5000
        elif label == 'narrative-only':
            for actor in value['actors']:
                actor['motivation'] = 'Become exceptionally cautious.'
                actor['goal'] = 'Preserve cash above everything else.'
        engine = engine_type(value)
        while engine.observations():
            decisions = {key: decide(OfflineDecisions(), obs) for key, obs in engine.observations().items()}
            engine.advance({key: {field: choice[field] for field in ('action_id', 'observation_sha256')}
                for key, choice in decisions.items()})
        result = engine.report()
        assert replay(result) == result
        assert sum(a['cash_cents'] for a in result['actor_results'].values()) + result['total_cost_cents'] == 1000000
        if baseline is None: baseline = result
        if label == 'narrative-only':
            assert result['final_metrics'] == baseline['final_metrics']
            assert result['actor_results'] == baseline['actor_results']
        conditions.append({'id': label, 'model_calls': 0, 'exact_replay': True,
            'first_round_actions': {key: item['action_id'] for key, item in result['rounds'][0]['receipts'].items()},
            'final_metrics': result['final_metrics'], 'cost_cents': result['total_cost_cents'], 'report': result})
    return {'audit': game_construction_audit(world), 'conditions': conditions,
        'interpretation': 'Synthetic execution and preference sensitivity under a deterministic myopic rule, not Jev behavior or evidence about people.'}


def render():
    from decision_lab.strategic_games import analyze_game
    from decision_lab.probability_updates import update_beliefs
    from decision_lab.evaluation import evaluate_forecasts
    # Load the typed adapter before replacing socket.socket: ssl subclasses it
    # at import time. No client is created and no request is made.
    from decision_lab.strategic_models import decide
    from decision_lab.strategic_worlds import StrategicWorld, replay_strategic_world

    def no_network(*args, **kwargs):
        raise RuntimeError('Whitepaper synthetic experiments prohibit network access')

    previous_socket = socket.socket
    socket.socket = no_network
    try:
        examples = ROOT / 'engine/examples'
        loaded = {name: json.loads((examples / filename).read_text()) for name, filename in (
            ('game', 'launch-coordination.game.json'),
            ('bayes', 'event-belief-update.json'),
            ('scoring', 'evaluation.synthetic.json'))}
        outputs = {'game': analyze_game(loaded['game']),
                   'bayes': update_beliefs(loaded['bayes']),
                   'scoring': evaluate_forecasts(loaded['scoring'])}
        # Deliberately synthetic scheduling fixture, not a population/market model.
        p = {'status': 'assumed', 'rationale': 'Synthetic whitepaper scheduling fixture.', 'source_refs': []}
        actor = {'id': 'alice', 'name': 'Alice', 'role': 'Builder',
                 'motivation': 'Explore a shared prototype.', 'goal': 'Compare spending and readiness.',
                 'information': 'Fictional own information.', 'initial_cash_cents': 100,
                 'utility_weights': {'readiness': 10, 'cash_cents': 1},
                 'actions': [{'id': 'wait', 'label': 'Wait', 'description': 'Keep resources.',
                              'cost_cents': 0, 'effects': {}, 'message': '', 'provenance': p},
                             {'id': 'build', 'label': 'Build', 'description': 'Fund a prototype step.',
                              'cost_cents': 60, 'effects': {'readiness': 6},
                              'message': 'I supported the prototype.', 'provenance': p}],
                 'subscriptions': ['bob'], 'provenance': p}
        bob = deepcopy(actor); bob.update(id='bob', name='Bob', subscriptions=['alice'])
        world = {'schema_version': 'strategic-world.v1', 'id': 'paper-scheduling-fixture',
                 'title': 'Synthetic scheduling fixture', 'description': 'Not empirical personas or a forecast.',
                 'rounds': 2, 'metrics': [{'id': 'readiness', 'label': 'Readiness', 'unit': 'points',
                 'initial': 1, 'min': 0, 'max': 10, 'provenance': p}], 'actors': [actor, bob],
                 'events': [{'id': 'first', 'round': 1, 'text': 'Fictional early signal.',
                            'effects': {'readiness': 1}, 'visible_to': ['alice'], 'provenance': p},
                            {'id': 'next', 'round': 2, 'text': 'Fictional later signal.',
                            'effects': {'readiness': -1}, 'visible_to': ['bob'], 'provenance': p}],
                 'interactions': [], 'assumptions': ['All values are teaching assumptions.'],
                 'limitations': ['No market forecast, inference or cash profit.']}
        engine = StrategicWorld(world, seed=42)
        states = []
        for action in ('build', 'wait'):
            obs = engine.observations()
            states.append({'round': engine.round, 'metrics': deepcopy(engine.metrics),
                           'alice_actions': [a['id'] for a in obs['alice']['actions']],
                           'alice_messages': [m['source'] for m in obs['alice']['messages']]})
            engine.advance({key: {'action_id': action, 'observation_sha256': value['observation_sha256']}
                            for key, value in obs.items()})
        report = engine.report()
        assert replay_strategic_world(report) == report
        outputs['rounds'] = {'world': world, 'observed_before_round': states,
                             'report': report, 'exact_replay': True}
        outputs['mechanisms'] = communication_ablation(world, StrategicWorld, replay_strategic_world)
        pilot = next(item['world'] for item in json.loads((ROOT/'engine/src/decision_lab/data/strategic_examples.json').read_text()) if item['id'] == 'near-pilot-eight-roles')
        loaded['personas'] = pilot
        outputs['personas'] = persona_preference_check(pilot, StrategicWorld, replay_strategic_world)
        loaded['mechanisms'] = {'world': outputs['mechanisms']['base_world'],
                                'policy': outputs['mechanisms']['policy']}
    finally:
        socket.socket = previous_socket
    refs = symbols()
    selected = ['world_validate', 'world_observe', 'world_advance', 'world_utility', 'world_replay',
                'world_game', 'construction_audit', 'construction_summary', 'actor_support', 'decision_request', 'decide', 'author_prompt', 'persona', 'batch',
                'review', 'execute', 'jev', 'cloud', 'game', 'bayes', 'evaluation', 'amm', 'social_run',
                'wallet_data', 'presentation', 'commitment', 'verify', 'wallet', 'allowance', 'contract']
    source_rows = []
    for key in selected:
        path, line, symbol, layer = refs[key]
        source_rows.append({'id': key, 'file': str(path.relative_to(ROOT)), 'line': line,
                            'symbol': symbol, 'layer': layer,
                            'sha256': sha256(path.read_bytes()).hexdigest()})
    manifest = {'schema': 'whitepaper-evidence.v1',
                'implementation_baseline': '8318244515bf4b85ef831060e6f3a2878055bbb8',
                'evidence_revision': 'v0.8: economic decision scope and explicit record limits; six synthetic fixtures unchanged',
                'evidence_builder_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
                'scope': 'Synthetic arithmetic and engine scheduling; no empirical forecast validation.',
                'network_allowed': False, 'model_calls': 0, 'chain_transactions': 0,
                'inputs': {name: sha256(json.dumps(v, sort_keys=True).encode()).hexdigest()
                           for name, v in loaded.items()}, 'sources': source_rows}
    outputs['manifest'] = manifest
    files = {f'evidence/{name}.json': json.dumps(value, indent=2, ensure_ascii=False) + '\n'
             for name, value in outputs.items()}
    # Clickable relative links work locally, and paths remain meaningful in GitHub source.
    lines = ['% Generated by tools/build_whitepaper_evidence.py. Do not edit.',
             r'\begin{longtable}{p{0.24\linewidth}p{0.69\linewidth}}',
             r'\toprule Responsibility & Implementation location \\ \midrule\endhead']
    for row in source_rows:
        path = row['file']; line = row['line']
        label = row['id'].replace('_', r'\_')
        lines.append(label + ' & ' + r'\href{../../' + path + '#L' + str(line) + r'}{\nolinkurl{' + path + ':' + str(line) + r'}} \\')
    lines += [r'\bottomrule\end{longtable}', '']
    files['source-map.tex'] = '\n'.join(lines)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    folder = ROOT / 'docs/whitepaper'
    rendered = render()
    anchors = len(json.loads(rendered['evidence/manifest.json'])['sources'])
    changes = []
    for name, value in rendered.items():
        target = folder / name
        if not target.exists() or target.read_text() != value:
            changes.append((target, value))
    if args.check and changes:
        raise SystemExit('Stale whitepaper evidence: ' + ', '.join(str(p.relative_to(ROOT)) for p, _ in changes))
    for target, value in changes:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)
    print(f'Whitepaper: 6 synthetic experiments, {anchors} source anchors; no network/model/chain calls. ' +
          ('Current.' if not changes else 'Artifacts refreshed.'))


if __name__ == '__main__':
    main()
