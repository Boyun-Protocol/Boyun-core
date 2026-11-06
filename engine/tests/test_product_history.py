"""Recorded results survive mutable re-review and need no new inference."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import pytest
from test_product_api import FakeModel,ready
from test_web_server import request


def complete(manager,*,worlds=1):
    example=manager.bootstrap()['examples'][0]
    session=manager.create({'mode':'example','example_id':example['id'],'question':'PRIVATE_USER_PROMPT','public_input':False})
    session=manager.review(session['id'],{'world':session['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':worlds,'seed':42,'max_calls':96,'max_credits':0})
    manager.run(session['id'],{'review_sha256':session['review']['sha256'],'public_input':True})
    session=ready(manager,session['id']);assert session['status']=='completed'
    return session


def test_saved_runs_survive_review_clear_without_mutating_current_session_or_dispatch(tmp_path):
    from decision_lab.product_api import ProductManager
    client=FakeModel();manager=ProductManager(tmp_path,actor_clients={'gemini':client})
    try:
        completed=complete(manager,worlds=2);sid=completed['id'];run=completed['run_id']
        # A local re-review clears the live results as before. The run archive
        # still carries its exact old world, denominator and reviewed budgets.
        world=deepcopy(completed['proposal']['world']);world['title']='Another proposed world'
        current=manager.review(sid,{'world':world,'actor_route':'gemini','mode':'argmax','worlds':1,'seed':7,'max_calls':96,'max_credits':0})
        assert not current['results']
        count=len(client.calls);state_bytes=(tmp_path/sid/'state.json').read_bytes()
        index=manager.saved_results();assert index['model_requests']==0 and len(index['runs'])==1
        entry=index['runs'][0];assert entry['session_id']==sid and entry['run_id']==run
        assert entry['requested_worlds']==entry['completed_worlds']==2 and entry['replay_verified']is False
        assert 'PRIVATE_USER_PROMPT'not in json.dumps(index)
        assert completed['proposal']['world']['actors'][0]['information']not in json.dumps(index)
        saved=manager.saved_result(sid,run)
        assert saved['results']==completed['results']and saved['proposal']['world']==completed['proposal']['world']
        assert saved['archive']['replay_verified']and saved['summary']['requested_worlds']==2
        assert saved['cost']['recorded_model_calls']==count and saved['cost']['recorded_input_tokens']is None
        assert saved['cost']['cost_usd']is None and 'credits_charged'not in saved['cost']
        assert saved['review']['max_calls']==96 and saved['read_only']
        assert manager.snapshot(sid)==current and (tmp_path/sid/'state.json').read_bytes()==state_bytes
        assert len(client.calls)==count
        assert json.loads(manager.saved_result_bytes(sid,run))==completed['results']
        assert (tmp_path/sid/run/'review.json').stat().st_mode&0o777==0o600
    finally:manager.close()


def test_historical_denominator_unknown_is_not_invented_and_restart_listing_does_not_restore(tmp_path):
    from decision_lab.product_api import ProductManager
    manager=ProductManager(tmp_path,actor_clients={'gemini':FakeModel()})
    completed=complete(manager);manager.close();sid=completed['id'];run=completed['run_id']
    (tmp_path/sid/run/'review.json').unlink()
    path=tmp_path/sid/'state.json';state=json.loads(path.read_text());state['review']=None;path.write_text(json.dumps(state))
    restarted=ProductManager(tmp_path)
    try:
        before=path.read_bytes()
        entry=restarted.saved_results()['runs'][0]
        assert entry['requested_worlds']is None and entry['status']=='recorded'
        value=restarted.saved_result(sid,run)
        assert value['summary']['requested_worlds']is None and value['archive']['requested_worlds_known']is False
        assert not restarted._sessions and path.read_bytes()==before
    finally:restarted.close()


def test_corrupt_world_and_symlink_paths_never_bypass_replay_or_escape_root(tmp_path):
    from decision_lab.product_api import ProductManager
    manager=ProductManager(tmp_path,actor_clients={'gemini':FakeModel()})
    try:
        completed=complete(manager);sid=completed['id'];run=completed['run_id'];path=tmp_path/sid/run/'world-0.json'
        value=json.loads(path.read_text());value['result']['final_metrics']['trust']=999
        path.write_text(json.dumps(value))
        with pytest.raises(ValueError):manager.saved_result(sid,run)
        with pytest.raises(KeyError):manager.saved_result('../.env',run)
        alias='f'*32;(tmp_path/alias).symlink_to(tmp_path/sid,target_is_directory=True)
        assert all(e['session_id']!=alias for e in manager.saved_results()['runs'])
        with pytest.raises(KeyError):manager.saved_result(alias,run)
        path.unlink();path.symlink_to(tmp_path/sid/'state.json')
        assert not manager.saved_results()['runs']
        with pytest.raises((ValueError,OSError)):manager.saved_result(sid,run)
    finally:manager.close()


def test_index_bounds_and_partial_run_keep_requested_denominator(tmp_path,monkeypatch):
    from decision_lab.product_api import ProductManager
    from decision_lab import product_history
    manager=ProductManager(tmp_path,actor_clients={'gemini':FakeModel()})
    try:
        first=complete(manager,worlds=2);second=complete(manager)
        (tmp_path/first['id']/first['run_id']/'world-1.json').unlink()
        value=manager.saved_result(first['id'],first['run_id'])
        assert value['status']=='partial'and value['summary']['completed_worlds']==1 and value['summary']['requested_worlds']==2
        monkeypatch.setattr(product_history,'MAX_ITEMS',1)
        index=manager.saved_results();assert len(index['runs'])==1 and index['truncated']
    finally:manager.close()


def test_http_recorded_result_index_open_download_and_origin_boundary(tmp_path):
    from decision_lab.web_server import create_server
    client=FakeModel();server=create_server(port=0,output_dir=tmp_path,product_actor_clients={'gemini':client})
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        completed=complete(server.product);count=len(client.calls)
        status,headers,raw=request(server,'GET','/api/product/results')
        assert status==200 and headers['Cache-Control']=='no-store'
        assert json.loads(raw)['runs'][0]['session_id']==completed['id']
        path=f"/api/product/results/{completed['id']}/{completed['run_id']}"
        value=json.loads(request(server,'GET',path)[2]);assert value['archive']['replay_verified']
        assert json.loads(request(server,'GET',path+'/download')[2])==completed['results']
        assert request(server,'GET','/api/product/results',headers={'Origin':'https://evil.test'})[0]==403
        assert request(server,'GET',path,headers={'Origin':'null'})[0]==403
        assert request(server,'GET',path.replace(completed['id'],'../.env'))[0]==404
        assert len(client.calls)==count
    finally:server.shutdown();server.server_close();thread.join(3)


def test_saved_receipt_summary_distinguishes_native_evidence_from_historical_identity(tmp_path):
    from decision_lab.product_api import ProductManager
    client=FakeModel();manager=ProductManager(tmp_path,actor_clients={'gemini':client})
    try:
        completed=complete(manager);sid=completed['id'];run=completed['run_id']
        path=tmp_path/sid/run/'world-0.json';record=json.loads(path.read_text())
        for decision in record['decisions']:
            decision['receipt']={'model_reported':'historical-model-identity','transport':'historical-provider',
                'credits':{'charged':1},'usage':{'input_tokens':9999},'input_cost_estimate_usd':10}
        record['decisions'][0]['receipt']={'model_reported':'native-fixture-model','transport':'typesafe_systemone_curl',
            'usage':{'input_tokens':2500,'output_tokens':0},'input_cost_estimate_usd':0.000105}
        path.write_text(json.dumps(record));before=len(client.calls)
        summary=manager.saved_result(sid,run)['cost']
        assert summary['models']==['historical-model-identity','native-fixture-model']
        assert summary['native_typesafe_receipts']==summary['input_token_receipts']==1
        assert summary['recorded_input_tokens']==2500 and summary['input_cost_estimate_usd']==0.000105
        assert summary['cost_usd']is None and 'credits_charged'not in summary
        assert 'Completed-world'in summary['scope']and 'not independent attestation'in summary['identity_meaning']
        assert len(client.calls)==before
    finally:manager.close()
