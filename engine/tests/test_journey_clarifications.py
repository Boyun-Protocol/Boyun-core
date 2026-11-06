"""Author clarification is paid work, separate from local answers and RUN."""
from argparse import Namespace
import json

import pytest

from decision_lab.journey_commands import journey
from decision_lab.product_api import ProductManager, examples
from decision_lab.jev import TypeSafeClient


@pytest.fixture
def author_route(monkeypatch):
    import decision_lab.near_ai as cloud
    calls = {'author': [], 'actor': []}
    settings = {'always_ask': False, 'failure': None}

    class Author:
        provider = 'near_ai'
        public_only = False
        model = 'fixture/author'

        def __init__(self, **kwargs):
            pass

        def generate(self, messages):
            calls['author'].append(messages)
            if settings['failure']:
                raise cloud.NearAIError(settings['failure'])
            context = json.loads(messages[1]['content'])
            pending = settings['always_ask'] or len(calls['author']) == 1
            return {'value': {
                'schema_version': 'strategic-proposal.v1',
                'context_sha256': context['context_sha256'],
                'summary': 'Clarify the objective' if pending else 'Reviewed proposal',
                'questions': [{'id': 'objective', 'prompt': 'What is the primary objective?',
                               'choices': ['Preserve runway', 'Maximize attention'], 'required': True}] if pending else [],
                'world': None if pending else examples()[0]['world'],
                'limitations': ['Hypothetical fixture, no empirical calibration.'],
            }, 'receipt': {'provider': 'near_ai'}}

    def wire(**request):
        calls['actor'].append(request)
        payload = json.loads(request['body'])
        options = list(payload['questions']['action']['criteria'])
        return json.dumps({
            'model': 'jev-1.14.0', 'answers': {'action': {
                'type': 'choice', 'choice': options[0], 'confidence': .8,
                'probabilities': {k: float(k == options[0]) for k in options},
            }}, 'usage': {'input_tokens': 100, 'output_tokens': 0},
        }).encode()

    class Manager(ProductManager):
        def configure_access(self, data):
            result = super().configure_access(data)
            self.actors['typesafe'] = TypeSafeClient(api_key='synthetic-actor', transport=wire)
            return result

    monkeypatch.setattr(cloud, 'NearAITextModel', Author)
    monkeypatch.setenv('TEST_AUTHOR_KEY', 'synthetic-author-key-never-persist')
    return Manager, calls, settings


def run(tmp_path, author_route, answers, max_calls=3):
    manager, calls, settings = author_route
    args = Namespace(output_dir=str(tmp_path / 'journey'), offline=False,
                     api_key_env=None, format='md', world=None, author_near_ai=True,
                     author_api_key_env='TEST_AUTHOR_KEY', author_model='fixture/author',
                     author_max_calls=max_calls)
    inputs = iter(answers)
    messages = []
    status = journey(args, read=lambda _: next(inputs), write=messages.append,
                     secret_read=lambda _: 'synthetic-actor', manager_factory=manager)
    assert 'synthetic-author-key-never-persist' not in '\n'.join(messages)
    for path in (tmp_path / 'journey').rglob('*.json'):
        assert 'synthetic-author-key-never-persist' not in path.read_text()
    return status, messages, calls


def test_clarification_reaches_review_and_actual_injected_actor_run(tmp_path, author_route):
    status, messages, calls = run(tmp_path, author_route,
        ['2', 'Compare a small pilot with waiting.', 'AUTHOR', '1', 'AUTHOR',
         '1', '1', '1', 'n', 'RUN'])
    assert status == 0
    assert len(calls['author']) == 2 and len(calls['actor']) == 2
    assert 'Preserve runway' in json.dumps(calls['author'][1])
    report = (tmp_path / 'journey/scenario-report.md').read_text()
    assert '1 / 1' in report
    assert any('Author requests: 2 / 3' in line for line in messages)


def test_declining_clarification_dispatch_keeps_one_initial_call_only(tmp_path, author_route):
    status, messages, calls = run(tmp_path, author_route,
        ['2', 'My decision', 'AUTHOR', '2', ''])
    assert status == 0 and len(calls['author']) == 1 and not calls['actor']
    assert any('Stopped before clarification' in line for line in messages)
    assert not (tmp_path / 'journey/scenario-report.md').exists()


@pytest.mark.parametrize('max_calls', [1, 3])
def test_repeated_questions_stop_at_declared_author_budget(tmp_path, author_route, max_calls):
    author_route[2]['always_ask'] = True
    status, messages, calls = run(tmp_path, author_route,
        ['2', 'My decision', 'AUTHOR'] + ['1', 'AUTHOR'] * (max_calls - 1), max_calls)
    assert status == 2 and len(calls['author']) == max_calls and not calls['actor']
    assert any('Author request limit reached' in line for line in messages)


@pytest.mark.parametrize('http_status', [402, 429, 502])
def test_failed_author_is_not_a_clarification_retry(tmp_path, author_route, http_status):
    author_route[2]['failure'] = http_status
    status, messages, calls = run(tmp_path, author_route, ['2', 'My decision', 'AUTHOR'])
    assert status == 2 and len(calls['author']) == 1 and not calls['actor']


@pytest.mark.parametrize('cap', [0, 7, True])
def test_invalid_author_budget_rejected_before_credentials_or_output(tmp_path, cap):
    args = Namespace(output_dir=str(tmp_path / 'journey'), offline=False, world=None,
                     api_key_env=None, format='md', author_near_ai=True, author_max_calls=cap)
    with pytest.raises(ValueError):
        journey(args, read=lambda _: pytest.fail('must reject before prompts'), write=lambda _: None)
    assert not (tmp_path / 'journey').exists()
