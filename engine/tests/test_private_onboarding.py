import json
import threading
import pytest
from decision_lab.product_api import ProductManager
from test_product_api import ready


def offline(manager):
    return manager.configure_access({'mode':'offline','api_key':'','accept_host_access':False})


def test_import_is_process_only_no_request_and_reset_invalidates_review(tmp_path):
    secret='private-test-key-not-a-real-credential'
    manager=ProductManager(tmp_path)
    try:
        assert not manager.access_status()['completed']
        status=manager.configure_access({'mode':'typesafe','api_key':secret,'accept_host_access':False})
        assert status['mode']=='typesafe'and status['completed']
        assert secret not in json.dumps(manager.bootstrap())
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        r=manager.review(s['id'],{'world':s['proposal']['world'],'actor_route':'typesafe','mode':'argmax','worlds':1,'seed':42,'max_calls':96,'max_credits':0})
        offline(manager)
        assert manager.snapshot(s['id'])['review']is None
        with pytest.raises(ValueError):manager.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':False})
        assert 'typesafe'not in manager.actors
        assert all(secret not in p.read_text()for p in tmp_path.rglob('*.json'))
    finally:manager.close()
    other=ProductManager(tmp_path)
    try:assert 'typesafe'not in other.actors and not other.access_status()['completed']
    finally:other.close()


def test_host_consent_busy_and_bad_key_do_not_replace_client(tmp_path):
    manager=ProductManager(tmp_path,hosted=True)
    try:
        with pytest.raises(ValueError):manager.configure_access({'mode':'typesafe','api_key':'key','accept_host_access':False})
        assert not manager.actors
        for key in ('bad\nheader','',123):
            with pytest.raises(ValueError):manager.configure_access({'mode':'typesafe','api_key':key,'accept_host_access':True})
        manager._busy=True
        with pytest.raises(ValueError):offline(manager)
        manager._busy=False
        assert not manager.access_status()['completed']
    finally:manager.close()


def test_offline_entire_journey_no_network_replay_and_truthful_receipts(tmp_path,monkeypatch):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('network forbidden')))
    manager=ProductManager(tmp_path)
    try:
        offline(manager);assert manager.bootstrap()['access']['mode']=='offline'
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        r=manager.review(s['id'],{'world':s['proposal']['world'],'actor_route':'offline','mode':'argmax','worlds':1,'seed':42,'max_calls':96,'max_credits':0})
        manager.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':False});s=ready(manager,s['id'])
        assert s['status']=='completed'
        deck=manager.presentation(s['id']);provider=deck['slides'][2]['provider']
        assert provider['recorded_model_calls']==0 and provider['local_decision_turns']>0
        assert provider['models']==[]
        assert not manager.author
        with pytest.raises(ValueError):manager.check_typesafe_access()
    finally:manager.close()


def test_http_key_import_csrf_and_near_blocked_offline(tmp_path):
    from decision_lab.web_server import create_server
    from test_web_server import request
    server=create_server(port=0,output_dir=tmp_path)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        boot=json.loads(request(server,'GET','/api/product')[2]);path='/api/product/access'
        body=json.dumps({'mode':'typesafe','api_key':'test-secret-no-leak','accept_host_access':False})
        assert request(server,'POST',path,body,{'Content-Type':'application/json'})[0]==403
        headers={'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        assert request(server,'POST',path,body,{**headers,'Origin':'https://evil.test'})[0]==403
        status,_,raw=request(server,'POST',path,body,headers)
        assert status==200 and b'test-secret-no-leak'not in raw
        assert request(server,'GET',path)[0]==404
        assert request(server,'POST',path,json.dumps({'mode':'offline','api_key':'','accept_host_access':False}),headers)[0]==200
        ex=server.product.bootstrap()['examples'][0];s=server.product.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        assert request(server,'POST',f"/api/product/sessions/{s['id']}/near/prepare",'{}',headers)[0]==400
    finally:server.shutdown();server.server_close();thread.join(3)


def test_revocation_stops_after_inflight_turn_without_fallback(tmp_path):
    from decision_lab.offline_decisions import OfflineDecisions
    started=threading.Event();finish=threading.Event();calls=[]
    class Blocking(OfflineDecisions):
        def evaluate(self,**kw):
            calls.append(kw);started.set();assert finish.wait(3)
            return super().evaluate(**kw)
    m=ProductManager(tmp_path)
    try:
        m.configure_access({'mode':'typesafe','api_key':'test-key','accept_host_access':False})
        m.actors['typesafe']=Blocking()
        ex=m.bootstrap()['examples'][0];s=m.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        # Use a non-Station fixture route so no invented Station billing is needed.
        m.actors['gemini']=m.actors.pop('typesafe')
        r=m.review(s['id'],{'world':s['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':1,'seed':42,'max_calls':96,'max_credits':0})
        m.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':True})
        assert started.wait(3);m.release_imported_access();finish.set();s=ready(m,s['id'])
        assert s['status']=='failed'and len(calls)==1
        assert not m.actors and not m.access_status()['completed']
    finally:finish.set();m.close()


def test_free_check_revocation_does_not_cache_old_client_catalog(tmp_path):
    started=threading.Event();finish=threading.Event();result=[]
    class Client:
        def get_models(self):started.set();assert finish.wait(3);return {'models':['jev-latest']}
    m=ProductManager(tmp_path)
    try:
        m.configure_access({'mode':'typesafe','api_key':'test-key','accept_host_access':False});m.actors['typesafe']=Client()
        thread=threading.Thread(target=lambda:result.append(m.check_typesafe_access()));thread.start();assert started.wait(3)
        m.release_imported_access();finish.set();thread.join(3)
        assert result[0]['status']=='revoked'and m.bootstrap()['typesafe_health']is None
    finally:finish.set();m.close()


def test_revocation_during_question_preparation_blocks_dispatch(tmp_path,monkeypatch):
    import decision_lab.product_api as module
    started=threading.Event();finish=threading.Event();calls=[]
    from test_product_api import FakeModel
    client=FakeModel();m=ProductManager(tmp_path,actor_clients={'gemini':client})
    ex=m.bootstrap()['examples'][0];s=m.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
    r=m.review(s['id'],{'world':s['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':1,'seed':42,'max_calls':96,'max_credits':0})
    original=module.decision_request
    def pause(obs):started.set();assert finish.wait(3);return original(obs)
    monkeypatch.setattr(module,'decision_request',pause)
    try:
        m.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':True});assert started.wait(3)
        m._access['mode']='typesafe';m.release_imported_access();finish.set();s=ready(m,s['id'])
        assert not client.calls and s['status']=='failed'
    finally:finish.set();m.close()


def test_shutdown_stops_future_actor_calls_after_active_response(tmp_path):
    from test_product_api import FakeModel
    started=threading.Event();finish=threading.Event()
    class Blocking(FakeModel):
        def generate(self,messages):started.set();assert finish.wait(3);return super().generate(messages)
    client=Blocking();m=ProductManager(tmp_path,actor_clients={'gemini':client})
    ex=m.bootstrap()['examples'][0];s=m.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
    r=m.review(s['id'],{'world':s['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':1,'seed':42,'max_calls':96,'max_credits':0})
    m.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':True});assert started.wait(3)
    closer=threading.Thread(target=m.close);closer.start();assert m._closing.wait(3);finish.set();closer.join(3)
    assert not closer.is_alive()and len(client.calls)==1
    assert m.snapshot(s['id'])['status']=='failed'
