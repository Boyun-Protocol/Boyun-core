import json

import pytest

from decision_lab.committed_campaigns import CommittedCampaignWorld
from decision_lab.campaign_orchestration import run_campaign_experiment, replay_campaign_experiment, summarize_campaign_experiment
from test_campaign_worlds import package, decisions, evidence
from test_jev import Transport, client


PLAN = [{'payer': 'founder', 'campaign_id': 'exposure', 'order_second': 0}]


def test_commitment_executes_even_when_all_actors_wait():
    engine = CommittedCampaignWorld(package(), 31, PLAN)
    engine.prepare_step()
    assert engine.ledger.accounts['founder'].cash_cents == 70100
    assert engine.ledger.accounts['services'].cash_cents == 29900
    engine.prepare_step()
    assert engine.ledger.accounts['services'].cash_cents == 29900
    assert not engine.observation('retail')['visible_campaigns']
    checkpoint = engine.advance(decisions(engine))
    assert checkpoint['committed_plan_execution'][0]['cost_cents'] == 29900
    assert checkpoint['market_before'] == checkpoint['market_after']
    engine.prepare_step()
    assert engine.observation('retail')['visible_campaigns'][0]['status'] == 'active'
    assert engine.observation('founder')['own_summary']['campaign_spend_cents'] == 29900
    assert engine.ledger.totals() == engine.initial_totals


def test_future_commitment_cannot_be_purchased_early_or_shown_before_delivery():
    plan = [{**PLAN[0], 'order_second': 3600}]
    engine = CommittedCampaignWorld(package(), 31, plan)
    engine.prepare_step()
    assert 'campaign_exposure' not in engine.menu('founder')[0]
    engine.advance(decisions(engine))
    engine.prepare_step()
    assert not engine.observation('retail')['visible_campaigns']
    engine.advance(decisions(engine))
    engine.prepare_step()
    assert len(engine.orders) == 1
    assert engine.orders[0]['ordered_second'] == 3600


def test_committed_native_fixture_replays_and_summary_counts_prepayments(tmp_path):
    root = tmp_path / 'committed'
    manifest = run_campaign_experiment(package=package(), client=client(Transport(choice='wait')),
                                       output_dir=root, worlds=2, max_calls=24, commitments=PLAN,
                                       evidence_register=evidence(package(), commitments=PLAN))
    assert manifest['status'] == 'completed', manifest
    assert replay_campaign_experiment(root)['verified_steps'] == 8
    summary = summarize_campaign_experiment(root)
    assert summary['campaign_spend_cents'] == 59800
    assert summary['executed_volume_cents'] == 0
    observed = json.loads((root / 'world-0000-step-00001.observations.json').read_text())
    assert observed['retail']['visible_campaigns']


def test_invalid_or_unfunded_plan_rejected_before_calls(tmp_path):
    transport = Transport()
    value = package()
    value['actors'][0]['cash_cents'] = 1
    with pytest.raises(ValueError, match='funding'):
        run_campaign_experiment(package=value, client=client(transport), output_dir=tmp_path / 'fail',
                                 worlds=1, max_calls=12, commitments=PLAN)
    assert not transport.calls and not (tmp_path / 'fail').exists()


def test_commitments_are_required_before_observing_decision_barrier():
    engine = CommittedCampaignWorld(package(), 31, PLAN)
    with pytest.raises(ValueError, match='before actor'):
        engine.advance(decisions(engine))


def test_cli_plan_names_committed_orders_without_inference(tmp_path, capsys):
    from decision_lab.cli import main
    source, plan = tmp_path / 'package.json', tmp_path / 'plan.json'
    source.write_text(json.dumps(package()))
    plan.write_text(json.dumps(PLAN))
    assert main(['campaign', 'plan', '--input', str(source), '--committed-plan', str(plan),
                 '--worlds', '2', '--max-calls', '24']) == 0
    assert json.loads(capsys.readouterr().out)['committed_plan'] == PLAN


def test_due_batch_fails_atomically_if_actor_spent_reserved_cash():
    value = package()
    value['campaigns'].append({**value['campaigns'][0], 'id': 'second', 'price_cents': 50000})
    value['actors'][0]['campaign_ids'].append('second')
    plan = [{**PLAN[0], 'order_second': 3600},
            {'payer': 'founder', 'campaign_id': 'second', 'order_second': 3600}]
    engine = CommittedCampaignWorld(value, 31, plan)
    engine.prepare_step()
    engine.advance(decisions(engine))
    engine.prepare_step()
    engine.advance(decisions(engine))
    engine.ledger.transfer('test-external-spend', 'founder', 'services', 30000)
    balances = dict(engine.ledger.accounts)
    with pytest.raises(ValueError):
        engine.prepare_step()
    assert dict(engine.ledger.accounts) == balances
    assert not engine.orders and engine.summary['founder']['campaign_spend_cents'] == 0
