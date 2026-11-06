"""The paper's ablation must execute communication and joint rules independently."""
import importlib.util
import json
from pathlib import Path


def test_paper_ablation_separates_delivery_from_declared_complementarity():
    path = Path(__file__).resolve().parents[1] / 'build_whitepaper_evidence.py'
    spec = importlib.util.spec_from_file_location('whitepaper_builder', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = json.loads(module.render()['evidence/mechanisms.json'])
    rows = {row['id']: row for row in results['conditions']}
    expected = {
        'delivery-and-joint-rule': (6, 50, 1),
        'delivery-only': (3, 50, 1),
        'joint-rule-only': (1, 20, 0),
        'neither': (1, 20, 0),
    }
    for name, (readiness, cost, received) in expected.items():
        row = rows[name]
        assert row['final_readiness'] == readiness
        assert row['action_cost_cents'] == cost
        assert row['reviewer_messages_before_round_two'] == received
        assert row['remaining_cash_cents'] + cost == 200
        assert row['exact_replay'] is True
    assert results['model_calls'] == 0
    assert results['policy_source'] == 'Explicit deterministic test policy, not Jev or human behavior.'
