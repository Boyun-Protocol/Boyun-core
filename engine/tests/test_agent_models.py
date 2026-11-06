import json
import pytest
from decision_lab.agent_models import NativeTextModel, AgyTextModel, ModelFailure

MESSAGES=[{'role':'system','content':'Return JSON.'},{'role':'user','content':'Public synthetic test'}]


def test_native_openai_actual_wire_contract():
    sent=[]
    def io(**kw):
        sent.append(kw);return json.dumps({'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'{"value":3}'}}],'usage':{'prompt_tokens':12,'completion_tokens':5}}).encode()
    model=NativeTextModel(model='test',endpoint='https://example.test/v1/chat/completions',api_key='private-test-key',protocol='openai',transport=io)
    result=model.generate(MESSAGES)
    assert result['value']=={'value':3};assert len(sent)==1
    assert json.loads(sent[0]['body'])['messages']==MESSAGES
    assert result['receipt']['usage']['input_tokens']==12
    assert 'private-test-key'not in json.dumps(result)
    assert result['receipt']['cost_usd']is None


def test_native_failure_does_not_retry_or_expose_payload():
    calls=[]
    def io(**kw):calls.append(kw);raise ValueError('sensitive provider body')
    model=NativeTextModel(model='test',endpoint='https://example.test/v1/chat/completions',api_key='test-key',protocol='openai',transport=io)
    with pytest.raises(ModelFailure)as caught:model.generate(MESSAGES)
    assert len(calls)==1 and caught.value.remote_outcome=='unknown'
    assert 'sensitive'not in str(caught.value)


@pytest.mark.parametrize('text',['{"a":1,"a":2}','{"a":NaN}','not json'])
def test_native_rejects_malformed_structured_output(text):
    def io(**kw):return json.dumps({'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':text}}]}).encode()
    with pytest.raises(ModelFailure):NativeTextModel(model='t',endpoint='https://e.test',api_key='key',protocol='openai',transport=io).generate(MESSAGES)


def test_cli_adapter_uses_exact_selected_model_no_approval_and_bounded_runner(tmp_path):
    calls=[]
    def runner(argv,prompt,timeout,cwd,max_bytes):
        calls.append((argv,prompt,timeout,cwd,max_bytes));return json.dumps({'status':'SUCCESS','response':'{"value":4}','num_turns':1,'usage':{'input_tokens':3,'output_tokens':2}}).encode()
    model=AgyTextModel(model='gemini-3.8-flash-high',binary='/explicit/agy',public_input=True,runner=runner)
    result=model.generate(MESSAGES)
    assert result['value']=={'value':4}
    argv,prompt,timeout,cwd,limit=calls[0]
    assert '--dangerously-skip-permissions'not in argv and '--sandbox'in argv
    assert argv[argv.index('--model')+1]=='gemini-3.8-flash-high'
    assert '--mode'in argv and 'plan'in argv and timeout<=300 and limit<=2*1024*1024
    assert result['receipt']['transport']=='antigravity_cli_development'


def test_cli_requires_public_input_and_empty_output_is_not_success():
    with pytest.raises(ValueError):AgyTextModel(model='m',public_input=False)
    def runner(*args):return b'{"status":"SUCCESS","response":"","usage":{}}'
    with pytest.raises(ModelFailure):AgyTextModel(model='m',public_input=True,runner=runner).generate(MESSAGES)


def test_cli_duration_has_units():
    captured=[]
    def runner(argv,*args):
        captured.append(argv);return b'{"status":"SUCCESS","response":"{}"}'
    AgyTextModel(model='m',public_input=True,timeout_seconds=180,runner=runner).generate(MESSAGES)
    argv=captured[0]
    assert argv[argv.index('--print-timeout')+1]=='180s'


def test_cli_timeout_kills_pipe_holding_descendant_after_leader_exit(tmp_path):
    import os,signal,sys,time
    from decision_lab.agent_models import _run_cli
    pidfile=tmp_path/'child.pid'
    child=f'import os,time;open({str(pidfile)!r},"w").write(str(os.getpid()));time.sleep(30)'
    parent=f'import subprocess,sys;subprocess.Popen([sys.executable,"-c",{child!r}])'
    try:
        with pytest.raises(TimeoutError):_run_cli([sys.executable,'-c',parent],'public',1,str(tmp_path),4096)
        pid=int(pidfile.read_text())
        for _ in range(50):
            try:os.kill(pid,0)
            except ProcessLookupError:break
            time.sleep(.02)
        else:pytest.fail('Timed-out CLI left a running descendant')
    finally:
        if pidfile.exists():
            try:os.kill(int(pidfile.read_text()),signal.SIGKILL)
            except ProcessLookupError:pass


def test_selected_cli_variant_does_not_conflict_with_effort_override():
    seen=[]
    def runner(argv,*args):seen.append(argv);return b'{"status":"SUCCESS","response":"{}"}'
    AgyTextModel(model='gemini-3.8-flash-high',public_input=True,runner=runner).generate(MESSAGES)
    assert '--effort'not in seen[0]
