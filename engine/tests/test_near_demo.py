"""NEAR demonstrations freeze evidence without converting addresses into actors."""
from copy import deepcopy
import hashlib
import json

import pytest

from test_wallet_evidence import snapshot, trade


def test_evidence_survives_world_validation_report_and_replay_without_auto_funding():
    from decision_lab.near_demo import build_near_demo, rehearse_near_demo
    from decision_lab.strategic_worlds import replay_strategic_world, validate_strategic_world

    source = snapshot([trade(usd="10.005"), trade("second", usd="20", direction="sell")])
    before = deepcopy(source)
    result = build_near_demo(source)
    evidence = result['evidence']
    assert source == before
    assert evidence['network'] == 'near'
    assert evidence['summary']['accepted_trades'] == 2
    assert evidence['summary']['observed_notional_cents'] == 3001
    assert evidence['captured_at'] == '2026-10-24T00:00:00Z'
    assert evidence['units']['observed_notional_cents'] == 'USD cents; provider-declared swap notional, not capital or profit'
    expected_hash = hashlib.sha256(json.dumps(source, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    assert evidence['snapshot_sha256'] == expected_hash
    world = validate_strategic_world(result['world'])
    assert [a['initial_cash_cents'] for a in world['actors']] == [1000000, 50000]
    assert all(a['id'] != 'alice.near' for a in world['actors'])
    assert expected_hash in str(world['assumptions'])
    assert evidence['sources'][0]['source_url'] in str(world['assumptions'])
    assert '2026-10-23T23:59:00Z' in str(world['assumptions'])
    assert all('urn:sha256:' + expected_hash in a['provenance']['source_refs'] for a in world['actors'])
    rehearsal = rehearse_near_demo(result)
    assert rehearsal['model_requests'] == 0
    assert len(rehearsal['branches']) == 4
    for branch in rehearsal['branches']:
        report = branch['result']
        assert replay_strategic_world(report) == report
        assert report['world'] == world
    pilot = rehearsal['branches'][1]['result']['actor_results']['creator']
    assert pilot['cash_cents'] == 950000
    assert pilot['cost_cents'] == 50000


@pytest.mark.parametrize('source', [snapshot(network='solana'), snapshot([])])
def test_rejects_cross_network_or_no_accepted_observations(source):
    from decision_lab.near_demo import build_near_demo
    with pytest.raises(ValueError):
        build_near_demo(source)


def test_sources_never_change_authored_costs_preferences_or_effects():
    from decision_lab.near_demo import build_near_demo
    first = build_near_demo(snapshot())['world']
    second = build_near_demo(snapshot([trade(usd='999999999')]))['world']
    for one, two in zip(first['actors'], second['actors']):
        assert one['initial_cash_cents'] == two['initial_cash_cents']
        assert one['utility_weights'] == two['utility_weights']
        assert [(a['cost_cents'], a['effects']) for a in one['actions']] == [(a['cost_cents'], a['effects']) for a in two['actions']]


def test_supplied_world_retains_authored_budget_and_is_not_mutated():
    from decision_lab.near_demo import build_near_demo
    from test_strategic_worlds import world
    base = world()
    before = deepcopy(base)
    result = build_near_demo(snapshot(), base_world=base)
    assert base == before
    assert result['world']['id'] == 'small-coordination'
    assert [a['initial_cash_cents'] for a in result['world']['actors']] == [100, 100]
    assert result['world']['actors'][0]['actions'][1]['cost_cents'] == 60
    assert result['world']['actors'][0]['actions'][1]['effects'] == {'readiness': 6}


def test_cli_reads_archive_without_mutation_and_refuses_existing_output(tmp_path):
    from decision_lab.near_demo import main
    from decision_lab.public_archive import PublicArchive
    archive = tmp_path / 'history.sqlite'
    with PublicArchive(archive) as store:
        store.record_snapshot(snapshot())
    before = archive.read_bytes()
    output = tmp_path / 'demo'
    args = ['--archive', str(archive), '--as-of', '2026-10-24T00:00:00Z', '--output', str(output), '--rehearse']
    assert main(args) == 0
    assert archive.read_bytes() == before
    built = json.loads((output / 'demo.json').read_text())
    assert json.loads((output / 'world.json').read_text()) == built['world']
    assert json.loads((output / 'evidence.json').read_text()) == built['evidence']
    assert json.loads((output / 'rehearsal.json').read_text())['model_requests'] == 0
    assert output.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in output.iterdir())
    with pytest.raises(FileExistsError):
        main(args)
    assert json.loads((output / 'demo.json').read_text()) == built


def test_cli_refuses_symlink_ancestors_before_archive_access(tmp_path):
    from decision_lab.near_demo import main
    actual = tmp_path / 'actual'
    actual.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        main(['--archive', str(tmp_path / 'missing.sqlite'), '--output', str(alias / 'demo')])
    assert not (actual / 'demo').exists()


def test_product_http_imports_frozen_near_evidence_without_inference(tmp_path):
    import threading
    from decision_lab.public_archive import PublicArchive
    from decision_lab.web_server import create_server
    from test_web_server import request
    archive_path=tmp_path/'history.sqlite'
    with PublicArchive(archive_path)as store:store.record_snapshot(snapshot())
    server=create_server(port=0,output_dir=tmp_path/'product',public_archive_path=archive_path)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        boot=json.loads(request(server,'GET','/api/product')[2]);assert boot['near_demo']['available']
        assert request(server,'POST','/api/product/near-demo','{}',{'Content-Type':'application/json'})[0]==403
        status,_,raw=request(server,'POST','/api/product/near-demo','{}',{'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']})
        assert status==202
        state=json.loads(raw);assert state['status']=='ready'and state['authoring_attempts']==0
        assert state['evidence_summary']['network']=='near'
        assert (server.product.root/state['id']/'near-evidence.json').is_file()
        # The sidecar carries evidence; redundant response metadata must not
        # break strict persisted-session restoration after a process restart.
        from decision_lab.product_api import ProductManager
        restored=ProductManager(server.product.root)
        try:assert restored.snapshot(state['id'])['status']=='ready'
        finally:restored.close()
    finally:server.shutdown();server.server_close();thread.join(3)


def test_persona_observation_contains_public_source_summary_not_raw_addresses():
    from decision_lab.near_demo import build_near_demo
    from decision_lab.strategic_worlds import StrategicWorld
    demo=build_near_demo(snapshot())
    for observation in StrategicWorld(demo['world']).observations().values():
        text=json.dumps(observation)
        assert demo['evidence']['snapshot_sha256']in text
        assert 'sampled swaps' in text and 'not calibrated' in text
        assert 'alice.near' not in text
