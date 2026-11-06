from collections import Counter
import json

from decision_lab.probability_sampling import sample_answer, decide_sampled
from decision_lab.campaign_orchestration import run_campaign_experiment, replay_campaign_experiment
from decision_lab.campaign_worlds import CampaignWorld
from test_campaign_worlds import package, evidence
from test_jev import client, response


def test_unbuffed_sampling_is_not_argmax_or_confidence_abstention():
    answer = {'type': 'choice', 'choice': 'wait', 'confidence': .1, 'probabilities': {'wait': .7, 'buy': .3}}
    counts = Counter(sample_answer(answer, seed=seed, actor_id='retail', elapsed_seconds=3600, question='action')[0]
                     for seed in range(2000))
    assert 500 < counts['buy'] < 700
    assert 1300 < counts['wait'] < 1500


def test_decisions_use_native_probabilities_and_replay_without_provider(tmp_path):
    def transport(**kwargs):
        payload = json.loads(kwargs['body'])
        value = response(payload, 'wait', confidence=.1)
        if 'action' in value['answers']:
            criteria = payload['questions']['action']['criteria']
            distribution = {key: 0.0 for key in criteria}
            distribution['wait'] = .6
            distribution['buy_2500'] = .4
            value['answers']['action']['probabilities'] = distribution
        return json.dumps(value).encode()
    root = tmp_path/'sampled'
    result = run_campaign_experiment(package=package(), client=client(transport), worlds=10,
                                     max_calls=120, output_dir=root, evidence_register=evidence(package()))
    assert result['status'] == 'completed', result
    replies = [json.loads(path.read_text()) for path in root.glob('*.response.json')]
    assert any(reply['decision']['action_id'].startswith('buy_') for reply in replies)
    assert all(reply['answers']['action']['choice'] == 'wait' for reply in replies)
    assert replay_campaign_experiment(root)['verified_worlds'] == 10
