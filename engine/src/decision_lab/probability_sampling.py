"""Unbuffed sampling of validated Jev action scores; no confidence abstention gate."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

from .randomness import keyed_rng


POLICY_SHA256 = sha256(Path(__file__).read_bytes()).hexdigest()


def sample_answer(answer, *, seed, actor_id, elapsed_seconds, question):
    from .jev import validate_answers
    criteria = {key: key for key in answer['probabilities']}
    validate_answers({'selection': answer}, {'selection': {'type': 'choice', 'instructions': 'Validate existing answer', 'criteria': criteria}})
    scores = {key: Fraction(str(value)) for key, value in answer['probabilities'].items()}
    draw = keyed_rng(seed, 'unbuffed-jev-sampling', actor_id, elapsed_seconds, question).getrandbits(53)
    target = sum(scores.values()) * Fraction(draw, 2**53)
    running = Fraction(0)
    for key, value in sorted(scores.items()):
        running += value
        if target < running:
            return key, {'policy': 'sample_provider_scores.v1', 'policy_sha256': POLICY_SHA256,
                         'draw_uint53': draw, 'provider_choice': answer['choice'],
                         'sampled_choice': key, 'confidence_gate': 'not_applied',
                         'interpretation': 'Model-conditioned action sampling, not calibrated event odds.'}
    raise ValueError('no positive probability mass')


def decide_sampled(engine, actor_id, client):
    from .campaign_worlds import campaign_request
    from .agent_worlds import digest
    request = campaign_request(engine, actor_id, client.model)
    response = client.evaluate(state=request['state'], questions=request['questions'])
    choices, metadata = {}, {}
    for question in ('action', 'coordination'):
        if question in response['answers']:
            choices[question], metadata[question] = sample_answer(response['answers'][question], seed=engine.seed,
                actor_id=actor_id, elapsed_seconds=engine.second, question=question)
    return {'decision': {'actor_id': actor_id, 'observation_sha256': request['state']['observation_sha256'],
                          'action_id': choices.get('action', 'wait'), 'signal_id': choices.get('coordination', 'silent')},
            'receipt': response['receipt'], 'answers': deepcopy(response['answers']),
            'request_sha256': digest(request), 'sampling_policy': metadata}
