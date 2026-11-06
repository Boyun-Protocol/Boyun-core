"""Independent process-only author credentials, consent and lifecycle."""
import json
import threading
import pytest
from decision_lab.product_api import ProductManager
from decision_lab.agent_models import ModelFailure
from test_product_api import ready


def configure(m,mode='near_ai',key='author-test-key',host=False):
    return m.configure_author({'mode':mode,'api_key':key,'model':'canonical/model','accept_host_access':host})


def test_author_import_independent_from_actor_and_not_persisted(tmp_path):
    m=ProductManager(tmp_path)
    try:
        m.configure_access({'mode':'typesafe','api_key':'actor-test-key','accept_host_access':False})
        actor=m.actors['typesafe']
        status=configure(m)
        assert status['provider']=='near_ai' and status['enabled'] and not status['public_only']
        assert m.actors['typesafe']is actor
        assert m.bootstrap()['routes']['author']['provider']=='near_ai'
        assert 'author-test-key'not in json.dumps(m.bootstrap())
        assert not list(tmp_path.rglob('*.json'))
        m.release_imported_access()
        assert m.author is None and not m.actors
    finally:m.close()


def test_host_consent_offline_and_author_clear(tmp_path):
    m=ProductManager(tmp_path,hosted=True)
    try:
        with pytest.raises(ValueError):configure(m)
        configure(m,host=True)
        assert m.author
        configure(m,'none','',True)
        assert not m.author
        m.configure_access({'mode':'offline','api_key':'','accept_host_access':False})
        with pytest.raises(ValueError):configure(m,host=True)
    finally:m.close()


def test_private_author_consent_and_exact_response_validation(tmp_path):
    from decision_lab.near_ai import NearAITextModel
    class Author:
        model='canonical/model';provider='near_ai';public_only=False
        def generate(self,messages):
            payload=json.loads(messages[1]['content'])
            return {'value':{'schema_version':'strategic-proposal.v1','context_sha256':payload['context_sha256'],
                'summary':'Need goal','questions':[{'id':'goal','prompt':'Goal?','choices':['Reach','Runway'],'required':True}],
                'world':None,'limitations':['Hypothetical']},'receipt':{'provider':'near_ai'}}
    m=ProductManager(tmp_path,author_client=Author())
    try:
        data={'mode':'author','example_id':None,'question':'Private unreleased project','public_input':False}
        with pytest.raises(ValueError):m.create(data)
        data['public_input']=True
        s=ready(m,m.create(data)['id'])
        assert s['status']=='draft'
        assert m.bootstrap()['routes']['author']['public_only']is False
    finally:m.close()


def test_revocation_during_author_request_preparation_blocks_dispatch(tmp_path,monkeypatch):
    import decision_lab.product_api as module
    started=threading.Event();finish=threading.Event();calls=[]
    m=ProductManager(tmp_path)
    m.configure_access({'mode':'typesafe','api_key':'actor-test-key','accept_host_access':False})
    configure(m)
    m.author.generate=lambda messages:calls.append(messages)
    original=module.authoring_messages
    def pause(*a,**kw):
        started.set();assert finish.wait(3)
        return original(*a,**kw)
    monkeypatch.setattr(module,'authoring_messages',pause)
    try:
        # create holds the RLock until its worker starts; pause occurs in worker.
        s=m.create({'mode':'author','example_id':None,'question':'Test private world','public_input':True})
        assert started.wait(3)
        # release_imported_access must not wait for author preparation under lock.
        thread=threading.Thread(target=m.release_imported_access);thread.start()
        finish.set();thread.join(3)
        s=ready(m,s['id'])
        assert not calls and s['status']=='failed'
    finally:finish.set();m.close()


def test_author_http_csrf_and_explicit_catalog_no_inference(tmp_path):
    from decision_lab.web_server import create_server
    from test_web_server import request
    server=create_server(port=0,output_dir=tmp_path)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        boot=json.loads(request(server,'GET','/api/product')[2]);headers={'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        body=json.dumps({'mode':'near_ai','api_key':'http-author-test-key','model':'canonical/model','accept_host_access':False})
        assert request(server,'POST','/api/product/author-access',body,{'Content-Type':'application/json'})[0]==403
        assert request(server,'POST','/api/product/author-access',body,headers)[0]==200
        assert b'http-author-test-key'not in request(server,'GET','/api/product')[2]
        server.product.author.get_models=lambda:{'models':[{'id':'canonical/model'}],'model_requests':0}
        assert request(server,'GET','/api/product/author-models')[0]==404
        status,_,raw=request(server,'POST','/api/product/author-models','{}',headers)
        assert status==200 and json.loads(raw)['models'][0]['id']=='canonical/model'
    finally:server.shutdown();server.server_close();thread.join(3)
