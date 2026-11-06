import pytest

from decision_lab.agent_models import ModelFailure
from decision_lab.laya_choices import LayaChoiceClient


class Agent:
    def __init__(self, truncated=False):
        self.truncated = truncated

    def system_one(self, state, questions):
        return {'answers': {'action': {'type': 'choice', 'choice': 'hold',
                 'confidence': 0.1, 'probabilities': {'hold': 0.6666, 'buy': 0.3333}}},
                'usage': {'truncated': self.truncated}}


QUESTIONS = {'action': {'type': 'choice', 'instructions': 'Choose.',
                        'criteria': {'hold': 'Wait', 'buy': 'Buy'}}}


def test_rounding_is_normalized_without_changing_choice(monkeypatch):
    client = LayaChoiceClient('convaiinnovations/laya-typed-decisions', agent=Agent())
    monkeypatch.setattr(client, '_check_input', lambda *args: None)
    response = client.evaluate(state='state', questions=QUESTIONS)
    assert response['answers']['action']['choice'] == 'hold'
    assert sum(response['answers']['action']['probabilities'].values()) == pytest.approx(1)
    assert response['receipt']['cost_usd'] == 0


def test_reported_truncation_is_rejected(monkeypatch):
    client = LayaChoiceClient('convaiinnovations/laya-typed-decisions', agent=Agent(True))
    monkeypatch.setattr(client, '_check_input', lambda *args: None)
    with pytest.raises(ModelFailure):
        client.evaluate(state='state', questions=QUESTIONS)
