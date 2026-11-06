from copy import deepcopy
import json
from pathlib import Path
import pytest
from decision_lab.agent_orchestration import assemble_world, validate_brief, construction_messages, run_live
from decision_lab.agent_worlds import digest,replay_agent_world

EXAMPLE=Path(__file__).parents[1]/'examples/agent-world-brief.public.json'


def brief():return json.loads(EXAMPLE.read_text())


def author(b):
    return {'schema_version':'agent-world-authoring.v1','brief_sha256':digest(b),'personas':[{'id':s['id'],'name':s['id'].title(),'description':'Supplied role, not an identified real trader.','goal':'React to personal evidence while respecting budget.','subscriptions':s['required_sources']}for s in b['slots']], 'assumptions':['Model persona assumptions are not empirical estimates.']}


class Fake:
    def __init__(self,fail_at=None):self.calls=[];self.fail_at=fail_at
    def generate(self,messages):
        self.calls.append(deepcopy(messages))
        if len(self.calls)==self.fail_at:raise RuntimeError('private exception data')
        data=json.loads(messages[1]['content'])
        if data['task']=='construct_world':
            value=author(data['brief']);value['brief_sha256']=data['brief_sha256']
        else:
            o=data['observation'];e=[m['id']for m in o['messages']][:1]
            value={'schema_version':'agent-turn.v1','actor_id':o['actor']['id'],'round':o['round'],'observation_sha256':o['observation_sha256'],'action':{'kind':'hold','amount':0,'evidence_ids':e},'message':{'text':'Real test message from '+o['actor']['id'],'stance':'uncertain','citations':e},'reason':'Fixture'}
        return {'value':value,'receipt':{'transport':'injected_fixture','request_attempts':1,'cost_usd':None,'usage':None}}


def test_world_builder_protects_resources_and_required_links():
    b=brief();w=assemble_world(b,author(b))
    assert w['market']==b['market'] and w['rounds']==b['rounds']
    assert w['agents'][1]['initial_cash_cents']==b['slots'][1]['initial_cash_cents']
    p=author(b);p['personas'][0]['initial_cash_cents']=999
    with pytest.raises(ValueError):assemble_world(b,p)
    p=author(b);p['personas'][1]['subscriptions']=[]
    with pytest.raises(ValueError):assemble_world(b,p)
    p=author(b);p['brief_sha256']='0'*64
    with pytest.raises(ValueError):assemble_world(b,p)


def test_whole_model_loop_delivers_peer_message_into_actual_next_prompt(tmp_path):
    client=Fake();out=tmp_path/'run';result=run_live(brief=brief(),client=client,output_dir=out,max_calls=7)
    assert result['status']=='completed'and len(client.calls)==7
    prompts=[json.loads(messages[1]['content'])for messages in client.calls[1:]]
    retail2=next(p['observation']for p in prompts if p['observation']['actor']['id']=='retail'and p['observation']['round']==2)
    assert any(m['text']=='Real test message from analyst'for m in retail2['messages'])
    report=json.loads((out/'result.json').read_text());assert replay_agent_world(report)==report
    manifest=json.loads((out/'manifest.json').read_text());assert manifest['completed_calls']==7
    assert all((p.stat().st_mode&0o777)==0o600 for p in out.glob('*.json'))
    assert len(list(out.glob('call-*.request.json')))==7


def test_failure_stops_with_durable_partial_world_and_no_fallback(tmp_path):
    client=Fake(fail_at=6);out=tmp_path/'failed'
    status=run_live(brief=brief(),client=client,output_dir=out,max_calls=7)
    assert status['status']=='failed'and len(client.calls)==6
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['completed_rounds']==1 and manifest['attempted_calls']==6
    assert 'private exception'not in json.dumps(manifest)
    partial=json.loads((out/'result.json').read_text());assert partial['completed_rounds']==1
    assert replay_agent_world(partial)==partial
    assert (out/'call-006.receipt.json').exists()


def test_call_budget_blocks_before_any_model_request_or_output(tmp_path):
    client=Fake();out=tmp_path/'limited'
    with pytest.raises(ValueError):run_live(brief=brief(),client=client,output_dir=out,max_calls=6)
    assert not client.calls and not out.exists()


def test_construction_contract_is_inert_and_exact():
    b=brief();validate_brief(b);messages=construction_messages(b)
    assert json.loads(messages[1]['content'])['brief']=={**b,'events':[]}
    assert 'Do not use tools'in messages[0]['content']
    invalid=brief();invalid['slots'][0]['required_sources']=['unknown']
    with pytest.raises(ValueError):validate_brief(invalid)


def test_builder_does_not_see_scheduled_external_event_bodies():
    b=brief();b['events'].append({'id':'future','round':2,'text':'RED-OWL future fact','provenance':'PRIVATE FUTURE PROVENANCE'})
    messages=construction_messages(b)
    assert 'RED-OWL'not in messages[1]['content']and'PRIVATE FUTURE PROVENANCE'not in messages[1]['content']
    data=json.loads(messages[1]['content']);assert data['brief_sha256']==digest(b)
    assert data['brief']['events']==[]


def test_live_prompt_expansion_rejected_before_first_actor_request(tmp_path):
    from test_agent_worlds import spec
    from decision_lab.agent_worlds import validate_agent_world
    p=spec();p['rounds']=8;p['events']=[];p['agents']=p['agents'][:1]
    p['event_description']='😀'*8000
    for key in ('name','role','description','goal'):p['agents'][0][key]='😀'*1600
    p['agents'][0]['attention_capacity']=0;p['agents'][0]['subscriptions']=[]
    validate_agent_world(p)
    client=Fake();out=tmp_path/'oversized-prompts'
    with pytest.raises(ValueError,match='prompt expansion'):run_live(world=p,client=client,output_dir=out,max_calls=8)
    assert not client.calls and not out.exists()
