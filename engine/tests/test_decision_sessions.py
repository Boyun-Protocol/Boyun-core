from copy import deepcopy
import json
import os
import pytest
from decision_lab import decision_sessions as sessions
from decision_lab.agent_worlds import digest
from decision_lab.decision_evidence import build_evidence_context
from test_agent_orchestration import Fake, brief


class Planner(Fake):
    model = 'fixture-model'
    def __init__(self, *, missing=False, unsupported=False, invalid=False, fail_at=None):
        super().__init__(fail_at=fail_at)
        self.missing, self.unsupported, self.invalid = missing, unsupported, invalid
    def generate(self, messages):
        data = json.loads(messages[1]['content'])
        if data['task'] != 'plan_decision':
            response=super().generate(messages)
            response['receipt']['model_declared']=self.model
            return response
        self.calls.append(deepcopy(messages))
        if len(self.calls) == self.fail_at:
            raise RuntimeError('SECRET provider detail')
        b = brief()
        value = {'schema_version':'decision-proposal.v1', 'context_sha256':data['context_sha256'],
                 'decision_type':'unsupported' if self.unsupported else 'launch',
                 'summary':'Inspect launch cash feasibility with supplied assumptions.',
                 'questions':[{'id':'costs','prompt':'What expenses should be included?', 'choices':['Use illustrative costs','I will supply costs'], 'required':True}] if self.missing else [],
                 'brief':None if self.unsupported else b, 'exit_token_units':None if self.unsupported else 2000000,
                 'assumptions':['All outside actor funds are hypothetical.'],
                 'limitations':['Not a calibrated prediction.']}
        if self.invalid:
            value['context_sha256']='0'*64
        return {'value':value,'receipt':{'model_declared':self.model,'transport':'fixture','request_attempts':1}}


def start(tmp_path, client=None, **kwargs):
    client = client or Planner()
    path = tmp_path/'session'
    state = sessions.start_session(session_dir=path, question='Should I launch on NEAR with $10k?', client=client,
        evidence_context=build_evidence_context(), **kwargs)
    return path,client,state


def test_guided_intake_questions_then_review_and_real_engine_report(tmp_path):
    client=Planner(missing=True)
    path,client,state=start(tmp_path,client)
    assert state['status']=='needs_answers'
    with pytest.raises(ValueError):sessions.review_session(session_dir=path,client=client,max_calls=7)
    client.missing=False
    state=sessions.reply_session(session_dir=path,message='Use illustrative costs for this demonstration.',client=client)
    assert state['status']=='ready' and state['revision']==2
    assert state['proposal']['brief']['evidence'][0]['source_ref'].startswith('decision-evidence:')
    review=sessions.review_session(session_dir=path,client=client,max_calls=7)
    assert review['required_model_calls']==7 and len(review['review_sha256'])==64
    assert review['project_capital_cents']==1000000 and review['outside_actor_cash_cents']==250000
    state=sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    assert state['status']=='completed' and len(client.calls)==9
    report=(path/state['run_path']/'decision-report.md').read_text()
    assert 'probab' in report.lower() and 'break' in report.lower()
    analysis=json.loads((path/state['run_path']/'decision-analysis.json').read_text())
    assert analysis['actual']['cash_profit_cents']==-500000
    assert analysis['no_launch']['profit_cents']==0
    assert sessions.read_session(path)==state
    for file in path.rglob('*.json'):
        assert file.stat().st_mode&0o777==0o600
    assert path.stat().st_mode&0o777==0o700


def test_stale_review_and_model_change_block_without_dispatch(tmp_path):
    path,client,_=start(tmp_path)
    review=sessions.review_session(session_dir=path,client=client,max_calls=7)
    client.model='other'
    with pytest.raises(ValueError):sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    client.model='fixture-model'
    sessions.reply_session(session_dir=path,message='Clarify the assumptions again.',client=client)
    with pytest.raises(ValueError):sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    assert len(client.calls)==2


def test_unsupported_decision_stays_blocked(tmp_path):
    path,client,state=start(tmp_path,Planner(unsupported=True))
    assert state['status']=='unsupported'
    with pytest.raises(ValueError):sessions.review_session(session_dir=path,client=client,max_calls=7)
    assert len(client.calls)==1


def test_invalid_model_and_failed_followup_are_preserved_without_secret_or_fallback(tmp_path):
    path,client,state=start(tmp_path,Planner(invalid=True))
    assert state['status']=='planning_failed' and len(client.calls)==1
    assert (path/'planning-001.response.json').exists()
    client.invalid=False
    sessions.reply_session(session_dir=path,message='Try this explicit new clarification.',client=client)
    review=sessions.review_session(session_dir=path,client=client,max_calls=7)
    client.fail_at=3
    state=sessions.reply_session(session_dir=path,message='Change the scenario.',client=client)
    assert state['status']=='planning_failed' and state['review'] is None
    assert 'SECRET' not in (path/'state.json').read_text()
    with pytest.raises(ValueError):sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    assert len(client.calls)==3


def test_budgets_lock_and_symlink_fail_closed(tmp_path):
    path,client,_=start(tmp_path,planning_call_limit=1)
    with pytest.raises(ValueError):sessions.reply_session(session_dir=path,message='Another call.',client=client)
    with pytest.raises(ValueError):sessions.review_session(session_dir=path,client=client,max_calls=6)
    import fcntl
    with (path/'.session.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(ValueError):sessions.review_session(session_dir=path,client=client,max_calls=7)
    actual=path/'state.json'; copy=path/'copy.json';actual.rename(copy);actual.symlink_to(copy)
    with pytest.raises((OSError,ValueError)):sessions.read_session(path)
    assert len(client.calls)==1


def test_failed_live_run_does_not_publish_completed_decision(tmp_path):
    path,client,_=start(tmp_path)
    review=sessions.review_session(session_dir=path,client=client,max_calls=7)
    client.fail_at=5
    state=sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    assert state['status']=='execution_failed'
    assert not (path/state['run_path']/'decision-report.md').exists()
    assert (path/state['run_path']/'manifest.json').exists()
    with pytest.raises(ValueError):sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])


def test_recovery_after_report_failure_uses_no_model_calls(tmp_path,monkeypatch):
    path,client,_=start(tmp_path)
    review=sessions.review_session(session_dir=path,client=client,max_calls=7)
    real=sessions._finish_report
    monkeypatch.setattr(sessions,'_finish_report',lambda *a: (_ for _ in ()).throw(OSError('disk problem')))
    with pytest.raises(OSError):sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    assert sessions.read_session(path)['status']=='running'
    count=len(client.calls)
    monkeypatch.setattr(sessions,'_finish_report',real)
    state=sessions.recover_session(session_dir=path)
    assert state['status']=='completed' and len(client.calls)==count


def test_future_model_response_cannot_override_context_or_attach_fabricated_evidence(tmp_path):
    class Forged(Planner):
        def generate(self,messages):
            r=super().generate(messages)
            r['value']['brief']['evidence']=[{'source_ref':'fake','summary':'known buyers','limitations':'none'}]
            return r
    path,client,state=start(tmp_path,Forged())
    assert state['status']=='planning_failed'


def test_session_report_uses_recorded_deliveries_and_action_counts(tmp_path):
    path,client,_=start(tmp_path)
    review=sessions.review_session(session_dir=path,client=client,max_calls=7)
    state=sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    text=(path/state['run_path']/'decision-report.md').read_text()
    assert 'Recorded agent interactions' in text
    assert 'Peer messages newly delivered: 5' in text
    assert '| analyst | 2 | 0 | 0 |' in text


def test_interrupted_pending_call_requires_recovery_without_inference(tmp_path):
    path,client,state=start(tmp_path)
    state['status']='planning';sessions._save(path,state)
    with pytest.raises(ValueError):sessions.reply_session(session_dir=path,message='Do not auto retry.',client=client)
    state=sessions.recover_session(session_dir=path)
    assert state['status']=='planning_failed' and state['error']['remote_outcome']=='unknown'
    assert len(client.calls)==1


def test_reply_blocks_during_entire_model_dispatch(tmp_path):
    class Concurrent(Planner):
        def generate(self,messages):
            with pytest.raises(ValueError,match='busy'):
                sessions.reply_session(session_dir=tmp_path/'session',message='Conflicting revision.',client=self)
            return super().generate(messages)
    path,client,state=start(tmp_path,Concurrent())
    assert state['revision']==1 and len(client.calls)==1


def test_review_binds_selected_cli_executable(tmp_path):
    client=Planner();client.binary='/tmp/selected-public-cli'
    path,client,_=start(tmp_path,client)
    review=sessions.review_session(session_dir=path,client=client,max_calls=7)
    client.binary='/tmp/different-cli'
    with pytest.raises(ValueError):sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    assert len(client.calls)==1


class AlternativePlanner(Planner):
    change=None
    def generate(self,messages):
        response=super().generate(messages)
        data=json.loads(messages[1]['content'])
        if data['task']=='plan_decision' and data.get('comparison_constraints'):
            response['value']['brief']=deepcopy(data['prior_proposal']['brief'])
            response['value']['brief']['evidence']=[]
            field,value=self.change or ('lp_cash_cents',200000)
            response['value']['brief']['market'][field]=value
        return response


def completed_parent(tmp_path):
    client=AlternativePlanner()
    path,client,_=start(tmp_path,client)
    review=sessions.review_session(session_dir=path,client=client,max_calls=7,seed=73)
    state=sessions.run_session(session_dir=path,client=client,review_hash=review['review_sha256'])
    return path,client,state


def test_matched_branch_preserves_actual_cast_evidence_and_parent_bytes(tmp_path):
    parent,client,parent_state=completed_parent(tmp_path)
    before={str(f.relative_to(parent)):f.read_bytes()for f in parent.rglob('*')if f.is_file()}
    child=tmp_path/'alternative'
    state=sessions.branch_session(source_dir=parent,session_dir=child,message='Use $2,000 locked LP cash; keep all controls fixed.',client=client)
    assert state['status']=='ready'
    assert state['evidence_context']==parent_state['evidence_context']
    review=sessions.review_session(session_dir=child,client=client,max_calls=6)
    assert review['seed']==73 and review['required_model_calls']==6
    assert review['construction_mode']=='reuse_reviewed_cast'
    assert review['input_changes']==[{'field':'lp_cash_cents','baseline':400000,'value':200000}]
    count=len(client.calls)
    state=sessions.run_session(session_dir=child,client=client,review_hash=review['review_sha256'])
    assert state['status']=='completed' and len(client.calls)==count+6
    old=json.loads((parent/parent_state['run_path']/'result.json').read_text())
    new=json.loads((child/state['run_path']/'result.json').read_text())
    assert old['world']['agents']==new['world']['agents']
    assert all(a in new['world']['assumptions']for a in old['world']['assumptions'])
    inputs=[json.loads(m[1]['content'])for m in client.calls[count:]]
    assert all(d['task']=='actor_turn' for d in inputs)
    assert inputs[0]['observation']['public_market']['cash_cents']==200000
    assert before=={str(f.relative_to(parent)):f.read_bytes()for f in parent.rglob('*')if f.is_file()}


@pytest.mark.parametrize('change',[('project_capital_cents',2000000),('project_token_units',4000000),('lp_token_units',2500000)])
def test_matched_branch_rejects_changed_controls_or_unfunded_exit(tmp_path,change):
    parent,client,_=completed_parent(tmp_path)
    client.change=change
    state=sessions.branch_session(source_dir=parent,session_dir=tmp_path/'alternative',message='Try an invalid comparison.',client=client)
    assert state['status']=='planning_failed'


def test_branch_binds_parent_route_and_review_seed_before_actor_calls(tmp_path):
    parent,client,_=completed_parent(tmp_path)
    child=tmp_path/'alternative'
    client.model='different-model'
    with pytest.raises(ValueError):sessions.branch_session(source_dir=parent,session_dir=child,message='Try a different route.',client=client)
    assert not child.exists()
    client.model='fixture-model'
    sessions.branch_session(source_dir=parent,session_dir=child,message='Use smaller LP.',client=client)
    with pytest.raises(ValueError):sessions.review_session(session_dir=child,client=client,max_calls=6,seed=42)
    assert len(client.calls)==9


def test_branch_refuses_incomplete_source_and_reuses_no_calls(tmp_path):
    parent,client,_=start(tmp_path)
    with pytest.raises(ValueError):sessions.branch_session(source_dir=parent,session_dir=tmp_path/'alternative',message='Compare.',client=client)
    assert len(client.calls)==1 and not (tmp_path/'alternative').exists()


def test_branch_inherits_bounded_analysis_and_rechecks_prepared_world(tmp_path):
    client=AlternativePlanner();parent,client,_=start(tmp_path,client)
    review=sessions.review_session(session_dir=parent,client=client,max_calls=7,seed=73,max_external_cash_cents=12345)
    sessions.run_session(session_dir=parent,client=client,review_hash=review['review_sha256'])
    child=tmp_path/'alternative'
    sessions.branch_session(source_dir=parent,session_dir=child,message='Change LP cash only.',client=client)
    review=sessions.review_session(session_dir=child,client=client,max_calls=6)
    assert review['max_external_cash_cents']==12345
    with pytest.raises(ValueError):sessions.review_session(session_dir=child,client=client,max_calls=6,max_external_cash_cents=100000000)
    state=sessions.read_session(child)
    state['comparison_parent']['world']['agents'][0]['goal']='Different actual goal.'
    sessions._save(child,state)
    count=len(client.calls)
    with pytest.raises(ValueError):sessions.run_session(session_dir=child,client=client,review_hash=review['review_sha256'])
    assert len(client.calls)==count


def test_branch_retains_recent_bounded_conversation_and_parent_identity(tmp_path):
    parent,client,state=completed_parent(tmp_path)
    state['conversation']=[{'role':'user','content':f'Past input {i}.'} for i in range(16)]
    sessions._save(parent,state)
    child=tmp_path/'alternative'
    branched=sessions.branch_session(source_dir=parent,session_dir=child,message='Change LP cash only.',client=client)
    assert branched['status']=='ready'
    assert len(branched['conversation'])==9
    assert branched['comparison_parent']['history_omitted_messages']==8
    assert branched['comparison_parent']['source_state_sha256']==state['state_sha256']
    actual=json.loads(client.calls[-1][1]['content'])
    assert actual['comparison_constraints']['omitted_earlier_parent_messages']==8


def test_branch_preflights_parent_execution_receipts_before_new_inference(tmp_path):
    parent,client,state=completed_parent(tmp_path)
    path=parent/state['run_path']/'manifest.json';manifest=json.loads(path.read_text())
    manifest['completed_calls']=0;path.write_text(json.dumps(manifest))
    count=len(client.calls)
    with pytest.raises(ValueError):sessions.branch_session(source_dir=parent,session_dir=tmp_path/'alternative',message='Compare only valid sources.',client=client)
    assert len(client.calls)==count and not (tmp_path/'alternative').exists()
