from argparse import Namespace
from pathlib import Path
import stat
import pytest
from decision_lab.journey_commands import journey,run_journey_command


def args(tmp_path,**kw):
    return Namespace(command='journey',output_dir=str(tmp_path/'journey'),offline=True,api_key_env=None,format='md',world=None,**kw)


def test_offline_terminal_journey_exports_actual_replayed_run(tmp_path):
    answers=iter(['1','','2','2','2','1','2','1','RUN']);messages=[]
    value=journey(args(tmp_path),read=lambda _:next(answers),write=messages.append)
    assert value==0
    report=tmp_path/'journey/scenario-report.md'
    assert report.is_file()and stat.S_IMODE(report.stat().st_mode)==0o600
    assert stat.S_IMODE(report.parent.stat().st_mode)==0o700
    text=report.read_text();assert '2 / 2'in text and 'attempted provider calls: 0'in text
    assert 'momentum'in text and 'marketing'in text
    assert any('Provider-call ceiling: 0'in s for s in messages)
    assert len(list(report.parent.glob('product/*/run-*/world-*.json')))==2
    assert run_journey_command(args(tmp_path))==2  # Never overwrite.


def test_terminal_cancel_before_run_and_key_not_written(tmp_path):
    a=args(tmp_path);a.offline=False
    answers=iter(['2','1','','1','1','1','1','1','1','n',''])
    secret='unit-test-key-never-real';messages=[]
    assert journey(a,read=lambda _:next(answers),secret_read=lambda _:secret,write=messages.append)==0
    assert not list((tmp_path/'journey').rglob('*.request.json'))
    assert secret not in '\n'.join(messages)
    assert all(secret not in p.read_text()for p in (tmp_path/'journey').rglob('*.json'))


def test_no_scripted_plaintext_password_fallback_and_symlink_output(tmp_path,monkeypatch):
    import sys
    a=args(tmp_path);a.offline=False
    monkeypatch.setattr(sys.stdin,'isatty',lambda:False)
    with pytest.raises(ValueError):journey(a,read=lambda _:'2',write=lambda _:None)
    assert not (tmp_path/'journey').exists()
    (tmp_path/'alias').symlink_to(tmp_path,target_is_directory=True);a.output_dir=str(tmp_path/'alias/new')
    with pytest.raises(ValueError):journey(a,read=lambda _:'2',write=lambda _:None)


def test_pdf_dependency_checked_before_key_and_paid_run(tmp_path,monkeypatch):
    import decision_lab.journey_commands as module
    a=args(tmp_path);a.format='pdf';a.offline=False
    monkeypatch.setattr(module,'pdf_available',lambda:False)
    with pytest.raises(ValueError):journey(a,read=lambda _:pytest.fail('must fail before prompts'),write=lambda _:None)
    assert not Path(a.output_dir).exists()


@pytest.mark.parametrize('execution_token',['RUN',''])
def test_cloud_authored_terminal_journey_requires_author_consent(tmp_path,monkeypatch,execution_token):
    import json
    import decision_lab.near_ai as module
    from decision_lab.product_api import examples
    calls=[]
    class Author:
        provider='near_ai';public_only=False;model='canonical/model'
        def __init__(self,**kwargs):pass
        def generate(self,messages):
            calls.append(messages);context=json.loads(messages[1]['content'])
            return {'value':{'schema_version':'strategic-proposal.v1','context_sha256':context['context_sha256'],
                'summary':'Proposed world','questions':[],'world':examples()[0]['world'],'limitations':['Hypothetical']},'receipt':{'provider':'near_ai'}}
    monkeypatch.setattr(module,'NearAITextModel',Author)
    monkeypatch.setenv('TEST_CLOUD_KEY','never-persist-cloud-test-key')
    a=args(tmp_path);a.offline=False;a.author_near_ai=True;a.author_api_key_env='TEST_CLOUD_KEY';a.author_model='canonical/model'
    answers=iter(['2','My own private decision','AUTHOR','2','1','1','n',execution_token])
    from decision_lab.product_api import ProductManager
    from decision_lab.jev import TypeSafeClient
    def wire(**request):
        payload=json.loads(request['body']);options=list(payload['questions']['action']['criteria'])
        return json.dumps({'model':'jev-1.14.0','answers':{'action':{'type':'choice','choice':options[0],'confidence':.8,'probabilities':{k:float(k==options[0])for k in options}}},'usage':{'input_tokens':100,'output_tokens':0},}).encode()
    class Manager(ProductManager):
        def configure_access(self,data):
            result=super().configure_access(data)
            self.actors['typesafe']=TypeSafeClient(api_key='fixture',transport=wire)
            return result
    messages=[]
    assert journey(a,read=lambda _:next(answers),secret_read=lambda _:'actor-test-key',write=messages.append,manager_factory=Manager)==0
    assert len(calls)==1
    assert not any('No paid calls' in line or 'No paid request yet' in line for line in messages)
    assert any('Authoring already requested' in line for line in messages)
    assert all('never-persist-cloud-test-key'not in p.read_text()for p in (tmp_path/'journey').rglob('*.json'))
