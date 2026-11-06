from copy import deepcopy
import json
import time
import pytest


def ready(manager, session_id):
    for _ in range(200):
        value=manager.snapshot(session_id)
        if value['status'] not in ('authoring','running'):return value
        time.sleep(.01)
    raise AssertionError('worker did not finish')


class FakeModel:
    model='fixture'
    def __init__(self):self.calls=[]
    def generate(self,messages):
        self.calls.append(messages)
        data=json.loads(messages[1]['content']); obs=data['observation']
        probs={a['id']:0.0 for a in obs['actions']};probs['wait']=1.0
        return {'value':{'choice':'wait','confidence':.8,'probabilities':probs,'reason':'Keep resources.'},
                'receipt':{'request_attempts':1,'transport':'test_fixture','cost_usd':None}}


def test_examples_are_valid_private_worlds_no_inference(tmp_path):
    from decision_lab.product_api import ProductManager
    manager=ProductManager(tmp_path)
    try:
        boot=manager.bootstrap(); assert len(boot['examples'])>=2
        for example in boot['examples']:
            value=manager.create({'mode':'example','example_id':example['id'],'question':example['question'],'public_input':False})
            assert value['status']=='ready' and value['proposal']['world']
            assert value['progress']['attempted_calls']==0
        assert not boot['routes']['author']['enabled']
        assert not any(r['enabled']for r in boot['routes']['actors'])
    finally: manager.close()


def test_real_worker_calls_isolated_models_and_replays_aggregate(tmp_path):
    from decision_lab.product_api import ProductManager
    from decision_lab.strategic_worlds import replay_strategic_world
    client=FakeModel();manager=ProductManager(tmp_path,actor_clients={'gemini':client})
    try:
        example=manager.bootstrap()['examples'][0]
        value=manager.create({'mode':'example','example_id':example['id'],'question':example['question'],'public_input':False})
        sid=value['id'];world=value['proposal']['world']
        review=manager.review(sid,{'world':world,'actor_route':'gemini','mode':'argmax','worlds':2,'seed':42,'max_calls':96,'max_credits':0})
        request={'review_sha256':review['review']['sha256'],'public_input':True}
        manager.run(sid,request)
        value=ready(manager,sid)
        assert value['status']=='completed',value
        assert len(value['results'])==2
        expected=len(world['actors'])*world['rounds']*2
        assert len(client.calls)==expected
        assert value['progress']['completed_calls']==expected
        for result in value['results']: assert replay_strategic_world(result['result'])==result['result']
        assert len(value['summary']['metrics'])==len(world['metrics'])
        for messages in client.calls:
            obs=json.loads(messages[1]['content'])['observation']
            for other in world['actors']:
                if other['id']!=obs['actor_id']:assert other['information']not in json.dumps(obs)
        with pytest.raises(ValueError):manager.run(sid,request)
    finally:manager.close()


def test_caps_and_public_only_before_any_model_request(tmp_path):
    from decision_lab.product_api import ProductManager
    client=FakeModel();manager=ProductManager(tmp_path,actor_clients={'gemini':client})
    try:
        example=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':example['id'],'question':example['question'],'public_input':False})
        data={'world':s['proposal']['world'],'actor_route':'gemini','mode':'sample','worlds':1,'seed':42,'max_calls':1,'max_credits':0}
        with pytest.raises(ValueError):manager.review(s['id'],data)
        assert not client.calls
        data['max_calls']=96;r=manager.review(s['id'],data)
        with pytest.raises(ValueError):manager.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':False})
        assert not client.calls
        with pytest.raises(ValueError):manager.run(s['id'],{'review_sha256':'0'*64,'public_input':True})
    finally:manager.close()


def test_provider_failure_preserves_denominator_and_stops_no_fallback(tmp_path):
    from decision_lab.product_api import ProductManager
    from decision_lab.agent_models import ModelFailure
    class Failing(FakeModel):
        def generate(self,messages):self.calls.append(messages);raise ModelFailure('fixture_failed')
    model=Failing();manager=ProductManager(tmp_path,actor_clients={'gemini':model})
    try:
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        r=manager.review(s['id'],{'world':s['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':2,'seed':1,'max_calls':96,'max_credits':0})
        manager.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':True})
        s=ready(manager,s['id']);assert s['status']=='failed' and s['error']=='fixture_failed'
        assert len(model.calls)==1 and s['progress']['attempted_calls']==1 and not s['results']
        assert s['summary']['completed_worlds']==0 and s['summary']['requested_worlds']==2
        assert (tmp_path/s['id']/'state.json').exists()
        assert (tmp_path/s['id']).stat().st_mode & 0o777 == 0o700
    finally:manager.close()


def test_author_requires_explicit_public_inputs_and_current_hash(tmp_path):
    from decision_lab.product_api import ProductManager
    from decision_lab.agent_worlds import digest
    class Author:
        model='author-fixture'
        def __init__(self):self.calls=[]
        def generate(self,messages):
            self.calls.append(messages);data=json.loads(messages[1]['content'])
            return {'value':{'schema_version':'strategic-proposal.v1','context_sha256':data['context_sha256'],
                'summary':'Need objective','questions':[{'id':'goal','prompt':'Goal?','choices':['Reach','Runway'],'required':True}],
                'world':None,'limitations':['Insufficient detail']},'receipt':{'transport':'test_fixture'}}
    author=Author();manager=ProductManager(tmp_path,author_client=author)
    try:
        data={'mode':'author','example_id':None,'question':'Choose a ticker','public_input':False}
        with pytest.raises(ValueError):manager.create(data)
        assert not author.calls
        data['public_input']=True;s=manager.create(data);s=ready(manager,s['id'])
        assert s['status']=='draft' and s['proposal']['questions']
        assert s['progress']['attempted_calls']==s['progress']['completed_calls']==1
        assert len(author.calls)==1
        with pytest.raises(ValueError):manager.review(s['id'],{'world':{},'actor_route':'gemini','mode':'sample','worlds':1,'seed':1,'max_calls':2,'max_credits':0})
    finally:manager.close()


def test_route_change_cannot_use_an_old_review(tmp_path):
    from decision_lab.product_api import ProductManager
    model=FakeModel();manager=ProductManager(tmp_path,actor_clients={'gemini':model})
    try:
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        s=manager.review(s['id'],{'world':s['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':1,'seed':1,'max_calls':96,'max_credits':0})
        model.model='changed-model'
        with pytest.raises(ValueError):manager.run(s['id'],{'review_sha256':s['review']['sha256'],'public_input':True})
        assert not model.calls
    finally:manager.close()


def test_explicit_rereview_creates_new_attempt_artifacts(tmp_path):
    from decision_lab.product_api import ProductManager
    model=FakeModel();manager=ProductManager(tmp_path,actor_clients={'gemini':model})
    try:
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        ids=[]
        for _ in range(2):
            s=manager.review(s['id'],{'world':s['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':1,'seed':1,'max_calls':96,'max_credits':0})
            manager.run(s['id'],{'review_sha256':s['review']['sha256'],'public_input':True})
            s=ready(manager,s['id']);assert s['status']=='completed'
            ids.append(s['run_id'])
        assert ids[0]!=ids[1]
        for identifier in ids:assert (tmp_path/s['id']/identifier/'world-0.json').exists()
    finally:manager.close()


def test_author_artifact_failure_never_leaves_fake_running_status(tmp_path,monkeypatch):
    import decision_lab.product_api as module
    author=FakeModel();manager=module.ProductManager(tmp_path,author_client=author)
    write=module._write
    def fail(root,name,value,**kwargs):
        if name.endswith('.request.json'):raise OSError('disk not available')
        return write(root,name,value,**kwargs)
    monkeypatch.setattr(module,'_write',fail)
    try:
        s=manager.create({'mode':'author','example_id':None,'question':'A public test','public_input':True})
        s=ready(manager,s['id']);assert s['status']=='failed'
        assert not author.calls
    finally:manager.close()


def test_restart_restores_completed_results_without_model_or_reexecution(tmp_path):
    from decision_lab.product_api import ProductManager
    client=FakeModel();manager=ProductManager(tmp_path,actor_clients={'gemini':client})
    ex=manager.bootstrap()['examples'][0]
    s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
    s=manager.review(s['id'],{'world':s['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':1,'seed':1,'max_calls':96,'max_credits':0})
    manager.run(s['id'],{'review_sha256':s['review']['sha256'],'public_input':True})
    before=ready(manager,s['id']);manager.close();count=len(client.calls)
    restarted=ProductManager(tmp_path,actor_clients={'gemini':client})
    try:
        restored=restarted.snapshot(s['id'])
        assert restored['results']==before['results'] and restored['status']=='completed'
        assert restored['review'] is None
        assert len(client.calls)==count
        with pytest.raises(KeyError):restarted.snapshot('../../.env')
    finally:restarted.close()


def test_interrupted_session_restores_as_failed_without_dispatch(tmp_path):
    from decision_lab.product_api import ProductManager
    manager=ProductManager(tmp_path)
    ex=manager.bootstrap()['examples'][0]
    s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
    manager.close()
    path=tmp_path/s['id']/'state.json';saved=json.loads(path.read_text());saved['status']='running';path.write_text(json.dumps(saved))
    restarted=ProductManager(tmp_path)
    try:
        restored=restarted.snapshot(s['id'])
        assert restored['status']=='failed' and restored['error']=='interrupted_no_automatic_retry'
    finally:restarted.close()


def test_compact_native_criteria_avoid_duplicate_text_and_growing_prompts_still_reject_before_model_attempt(tmp_path):
    from decision_lab.product_api import ProductManager
    client=FakeModel();manager=ProductManager(tmp_path,actor_clients={'typesafe':client,'gemini':client})
    try:
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        world=deepcopy(s['proposal']['world']);world['actors'][0]['actions'][1]['description']='x'*1500;world['actors'][0]['actions'][1]['message']='y'*1100
        reviewed=manager.review(s['id'],{'world':world,'actor_route':'typesafe','mode':'argmax','worlds':1,'seed':1,'max_calls':96,'max_credits':0})
        assert reviewed['review']['construction_summary']['actor_count']==len(world['actors'])
        from decision_lab.strategic_models import decision_request
        from decision_lab.strategic_worlds import StrategicWorld
        request=decision_request(StrategicWorld(world).observations()[world['actors'][0]['id']])
        assert 'x'*1500 in json.dumps(request['state'])
        assert 'x'*1500 not in json.dumps(request['questions'])
        assert not client.calls
        world=deepcopy(s['proposal']['world']);world['rounds']=8
        for actor in world['actors']:
            actor['information']='z'*1600
            for action in actor['actions'][1:]:action['message']='m'*1200
        # Size-only guard must include all previous peer messages and own history.
        from decision_lab.product_api import _preflight_world
        from decision_lab.strategic_worlds import StrategicWorld
        _preflight_world(world,'gemini')
        world['description']='d'*8000
        world['interactions']=[{**deepcopy(world['interactions'][0]),'id':'rule-'+str(i),'description':'r'*1600}for i in range(16)]
        with pytest.raises(ValueError):_preflight_world(world,'gemini')
    finally:manager.close()


def test_result_download_preserves_integers_beyond_browser_number_precision(tmp_path):
    from decision_lab.product_api import ProductManager
    manager=ProductManager(tmp_path,actor_clients={'gemini':FakeModel()})
    try:
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        world=s['proposal']['world'];world['rounds']=1;world['actors'][0]['initial_cash_cents']=10**12
        world['actors'][0]['utility_weights']={'cash_cents':10**6,'trust':1}
        world['metrics'][0]['initial']=7
        s=manager.review(s['id'],{'world':world,'actor_route':'gemini','mode':'argmax','worlds':1,'seed':1,'max_calls':96,'max_credits':0})
        manager.run(s['id'],{'review_sha256':s['review']['sha256'],'public_input':True})
        s=ready(manager,s['id'])
        saved=json.loads(manager.download_bytes(s['id']))
        assert saved==s['results']
        assert saved[0]['result']['actor_results']['creator']['utility']==10**18+7
    finally:manager.close()


def test_typesafe_catalog_and_402_reach_safe_product_errors(tmp_path):
    from decision_lab.product_api import ProductManager
    from decision_lab.jev import TypeSafeClient,ENDPOINT
    from urllib.error import HTTPError
    from io import BytesIO
    calls=[]
    def transport(**request):
        calls.append(request)
        if request['method']=='GET':return b'{"models":[{"name":"jev-latest"}]}'
        raise HTTPError(ENDPOINT,402,'SECRET',{},BytesIO(b'{"message":"SECRET"}'))
    client=TypeSafeClient(api_key='PRIVATE_KEY',transport=transport)
    manager=ProductManager(tmp_path,actor_clients={'typesafe':client})
    try:
        catalog=manager.check_typesafe_access()
        assert catalog['status']=='ready'and catalog['models']==['jev-latest']
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        s=manager.review(s['id'],{'world':s['proposal']['world'],'actor_route':'typesafe','mode':'argmax','worlds':1,'seed':1,'max_calls':96,'max_credits':0})
        manager.run(s['id'],{'review_sha256':s['review']['sha256'],'public_input':False})
        s=ready(manager,s['id']);assert s['status']=='failed'
        assert s['error_details']['http_status']==402
        assert 'PRIVATE_KEY'not in json.dumps(s)and 'SECRET'not in json.dumps(s)
        assert len([c for c in calls if c['method']=='POST'])==1
    finally:manager.close()
    restored=ProductManager(tmp_path)
    try:assert restored.snapshot(s['id'])['error_details']['http_status']==402
    finally:restored.close()


def test_typesafe_typed_decisions_settle_rounds_with_private_information_and_replay(tmp_path):
    from decision_lab.product_api import ProductManager
    from decision_lab.jev import TypeSafeClient
    from decision_lab.strategic_worlds import replay_strategic_world
    calls=[]
    def wire(**request):
        payload=json.loads(request['body']);calls.append(payload)
        question=payload['questions']['action'];options=list(question['criteria'])
        probabilities={key:1.0 if i==0 else 0.0 for i,key in enumerate(options)}
        answer={'type':'choice','choice':options[0],'confidence':.8,'probabilities':probabilities}
        return json.dumps({'model':'jev-1.14.0','answers':{'action':answer},
            'usage':{'input_tokens':100,'output_tokens':0}}).encode()
    manager=ProductManager(tmp_path,actor_clients={'typesafe':TypeSafeClient(api_key='PRIVATE_KEY',transport=wire)})
    try:
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        world=s['proposal']['world'];world['rounds']=2
        s=manager.review(s['id'],{'world':world,'actor_route':'typesafe','mode':'sample','worlds':1,'seed':42,'max_calls':96,'max_credits':0})
        manager.run(s['id'],{'review_sha256':s['review']['sha256'],'public_input':False})
        s=ready(manager,s['id']);assert s['status']=='completed',s
        assert len(calls)==len(world['actors'])*2==s['progress']['completed_calls']
        assert replay_strategic_world(s['results'][0]['result'])==s['results'][0]['result']
        assert all(d['receipt']['model_reported']=='jev-1.14.0'for d in s['results'][0]['decisions'])
        from decision_lab.agent_worlds import canonical
        estimate=s['review']['typesafe_estimate']
        assert sum(len(canonical(payload))for payload in calls)<=estimate['input_tokens_upper_bound']
        assert all('credits'not in d['receipt']for d in s['results'][0]['decisions'])
        for payload in calls:
            obs=payload['state']
            assert set(payload['questions'])=={'action'}and payload['model']=='jev-latest'
            for actor in world['actors']:
                if actor['id']!=obs['actor_id']:assert actor['information']not in json.dumps(obs)
        assert 'PRIVATE_KEY'not in json.dumps(s)
    finally:manager.close()


def test_typesafe_call_cap_and_zero_legacy_credits_before_dispatch(tmp_path):
    from decision_lab.product_api import ProductManager,estimate_typesafe_usage
    manager=ProductManager(tmp_path,actor_clients={'typesafe':FakeModel()})
    try:
        ex=manager.bootstrap()['examples'][0]
        s=manager.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        world=s['proposal']['world'];budget=len(world['actors'])*world['rounds']
        data={'world':world,'actor_route':'typesafe','mode':'sample','worlds':1,'seed':42,'max_calls':budget,'max_credits':0}
        with pytest.raises(ValueError):manager.review(s['id'],{**data,'max_calls':budget-1})
        with pytest.raises(ValueError):manager.review(s['id'],{**data,'max_credits':1})
        s=manager.review(s['id'],data)
        estimate=s['review']['typesafe_estimate']
        assert estimate['actor_call_ceiling']==budget and estimate['estimate_only']
        assert estimate['input_cost_upper_estimate_usd']==pytest.approx(estimate['input_tokens_upper_bound']*.042/1000000)
        assert s['review']['max_credits']==0 and 'credit_estimate'not in s['review']
        assert not manager.actors['typesafe'].calls
    finally:manager.close()


def test_removed_station_route_is_rejected_without_aliasing_keys(tmp_path):
    from decision_lab.product_api import ProductManager
    with pytest.raises(ValueError):ProductManager(tmp_path/'old',actor_clients={'jevstation':FakeModel()})
    manager=ProductManager(tmp_path/'new')
    try:
        with pytest.raises(ValueError):manager.configure_access({'mode':'jevstation','api_key':'never-use-this-key','accept_host_access':True})
        assert not manager.actors and manager.bootstrap()['typesafe_health']is None
        assert 'never-use-this-key'not in json.dumps(manager.bootstrap())
    finally:manager.close()
