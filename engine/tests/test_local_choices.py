import json

import pytest

from decision_lab.agent_models import ModelFailure
from decision_lab.local_choices import LocalChoiceClient


QUESTIONS = {'action': {'type': 'choice', 'instructions': 'Choose.', 'criteria': {'hold': 'Hold', 'buy': 'Buy'}}}


def test_local_choice_validates_and_records_provider():
    answer = {'answers': {'action': {'type': 'choice', 'choice': 'hold', 'confidence': 0.7,
                                     'probabilities': {'hold': 0.7, 'buy': 0.3}}}}
    raw = json.dumps({'message': {'content': json.dumps(answer)}, 'prompt_eval_count': 3, 'eval_count': 4}).encode()
    result = LocalChoiceClient(model='fixture', transport=lambda payload: raw).evaluate(state={'cash': 1}, questions=QUESTIONS)
    assert result['answers']['action']['choice'] == 'hold'
    assert result['receipt']['transport'] == 'ollama-local-structured-choice'
    assert result['receipt']['cost_usd'] == 0


def test_local_choice_rejects_malformed_probabilities():
    raw = json.dumps({'message': {'content': json.dumps({'answers': {'action': {'type': 'choice',
        'choice': 'buy', 'confidence': 0.5, 'probabilities': {'hold': 0.8, 'buy': 0.2}}}})}}).encode()
    with pytest.raises(ModelFailure):
        LocalChoiceClient(model='fixture', transport=lambda payload: raw).evaluate(state={}, questions=QUESTIONS)
