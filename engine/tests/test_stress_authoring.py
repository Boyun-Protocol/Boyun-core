"""Offline contract routing: stress awareness reaches authors, not executable inputs.

These tests verify prompt delivery and scope boundaries, not model compliance or
financial execution of the requested stress policies.
"""
from copy import deepcopy
import json

from test_scenario_authoring import draft
from test_strategic_worlds import world


def test_evidence_guidance_reaches_persona_batches_and_external_agent_clients():
    from decision_lab.batch_authoring import batch_messages
    from decision_lab.mcp_adapter import guidelines
    from decision_lab.evidence_planning import EVIDENCE_PLANNING_GUIDELINES
    from test_batch_authoring import scaffold
    value = scaffold(20, '0' * 64)
    original = deepcopy(value)
    messages, _ = batch_messages('Compare hypothetical protocol-adoption plans.', value, value['roster'][:20])
    for content in (messages[0]['content'], guidelines()):
        assert EVIDENCE_PLANNING_GUIDELINES in content
        assert 'assumption-outcome-evidence.v1' in content
        assert 'every simulation domain' in content
        assert 'input -> mechanism -> outcome' in content
        assert 'poll shares are not event probabilities' in content
        assert 'documented reasonable cause' in content
    assert value == original


def test_stress_guidance_reaches_all_world_authoring_routes_without_mutating_inputs():
    from decision_lab.stress_planning import STRESS_PLANNING_GUIDELINES
    from decision_lab.evidence_planning import EVIDENCE_PLANNING_GUIDELINES
    from decision_lab.strategic_models import authoring_messages
    from decision_lab.batch_authoring import scaffold_messages
    from decision_lab.scenario_authoring import prepare_authoring_request
    example = world()
    original = deepcopy(example)
    question = 'Compare a token migration and a DEX LP-withdrawal contingency.'
    history = [{'role': 'user', 'content': 'Keep disputed event odds unknown.'}]
    messages, identity = authoring_messages(question, history, example)
    staged, staged_identity = scaffold_messages(question, {
        'mode': 'batched', 'actor_count': 20, 'batch_size': 20, 'max_calls': 2}, example)
    value = draft(None)
    before = deepcopy(value)
    exported = prepare_authoring_request(value, 'offline-author')
    for routed in (messages, staged, exported['messages']):
        assert STRESS_PLANNING_GUIDELINES in routed[0]['content']
        assert EVIDENCE_PLANNING_GUIDELINES in routed[0]['content']
        assert routed[0]['role'] == 'system'
        assert 'dynamic-event-planning.v1' in routed[0]['content']
        assert 'repeated state-conditioned decisions' in routed[0]['content']
        assert 'six- or twelve-month historical cohort' in routed[0]['content']
        assert 'current permitted observations' in routed[0]['content']
        assert 'Preflight actor-time-world call counts' in routed[0]['content']
        assert 'assumption-outcome-evidence.v1' in routed[0]['content']
        assert 'every simulation domain' in routed[0]['content']
        assert 'input -> mechanism -> outcome' in routed[0]['content']
        assert 'poll shares are not event probabilities' in routed[0]['content']
    assert example == original and value == before
    assert json.loads(messages[1]['content'])['context_sha256'] == identity
    assert json.loads(staged[1]['content'])['context_sha256'] == staged_identity
    assert exported['usage']['model_calls'] == 0
    assert set(value) == set(before)  # No planning fields inserted into strict engine schemas.


def test_material_stress_questions_can_block_a_world_using_existing_contract():
    from decision_lab.strategic_models import authoring_messages, validate_proposal
    question = 'What if the position loses 20 percent within five minutes?'
    _, identity = authoring_messages(question, [], world())
    proposal = {'schema_version': 'strategic-proposal.v1', 'context_sha256': identity,
        'summary': 'A rolling-time cash-exit policy needs a supported execution adapter.',
        'questions': [{'id': 'response-authority',
            'prompt': 'Which response policy should be compared in simulation?',
            'choices': ['Require user decision', 'Use a reviewed conditional policy'],
            'required': True}],
        'world': None,
        'limitations': ['Rolling five-minute detection and actual venue exits are unsupported here; odds remain unknown.']}
    result = validate_proposal(proposal, identity)
    assert result['world'] is None
    assert result['questions'][0]['required'] is True
    assert result['context_sha256'] == identity
