"""Offline fixtures for the documented native TypeSafe HTTP boundary."""
import json
from io import BytesIO
from urllib.error import HTTPError
import pytest
from decision_lab import jev
from decision_lab.agent_models import ModelFailure
from test_jev import Transport

QUESTION={'relevant':{'type':'noul','instructions':'Is it relevant?'}}
ENDPOINT='https://api.typesafe.ai/v1/systemone'

@pytest.mark.parametrize('endpoint',[
    'https://evil.test/v1/systemone','https://api.typesafe.ai.evil.test/v1/systemone',
    'https://api.typesafe.ai:443/v1/systemone','https://api.typesafe.ai/v1/systemone?key=private',
    'https://api.typesafe.ai/v1/%73ystemone','http://127.0.0.1/v1/systemone',
    'https://api.typesafe.ai/v1/systemone#fragment',
])
def test_only_exact_documented_endpoint_can_receive_a_key(endpoint):
    with pytest.raises(ValueError):
        jev.TypeSafeClient(api_key='fixture-key',model='jev-latest',endpoint=endpoint,transport=Transport())


def test_native_defaults_and_explicit_curl_selection_use_native_wire(monkeypatch):
    from decision_lab import typesafe_curl
    wire=Transport();monkeypatch.setattr(typesafe_curl,'curl_transport',wire)
    client=jev.TypeSafeClient(api_key='fixture-key',http_client='curl')
    result=client.evaluate(state='bounded public fixture',questions=QUESTION)
    assert client.endpoint==ENDPOINT and client.protocol=='typesafe-systemone'
    assert wire.calls[0]['method']=='POST'
    assert result['receipt']['transport']=='typesafe_systemone_curl'
    assert result['receipt']['model_declared']=='jev-latest'
    assert result['receipt']['model_reported']=='jev-1.14.0'
    with pytest.raises(ValueError):jev.TypeSafeClient(api_key='fixture-key',http_client='automatic')
    with pytest.raises(ValueError):jev.TypeSafeClient(api_key='fixture-key',http_client='curl',transport=wire)


@pytest.mark.parametrize('status,expected',[(401,'key'),(402,'billing'),(429,'Wait'),(502,'service'),(503,'capacity')])
def test_safe_actionable_http_failures_never_read_raw_body_or_retry(status,expected):
    calls=[]
    class PrivateBody(BytesIO):
        def read(self,*args):raise AssertionError('raw private error body must not be inspected')
    def error(**kwargs):
        calls.append(kwargs)
        raise HTTPError(ENDPOINT,status,'PRIVATE_KEY diagnostic',{},PrivateBody(b'PRIVATE body'))
    client=jev.TypeSafeClient(api_key='PRIVATE_KEY',transport=error)
    with pytest.raises(ModelFailure) as failed:client.evaluate(state='fixture',questions=QUESTION)
    assert failed.value.code==f'typesafe_http_{status}'
    details=failed.value.safe_details()
    assert expected in details['message'] and details['automatic_retry'] is False
    assert details['http_status']==status and len(calls)==1
    assert 'PRIVATE' not in json.dumps(details)+str(failed.value)
    assert not any(k in details for k in ('top_up_url','refund_status','credits'))


@pytest.mark.parametrize('status',[429,503])
def test_retry_after_blocks_later_calls_without_hidden_retry(monkeypatch,status):
    now=[100.0];monkeypatch.setattr(jev.time,'monotonic',lambda:now[0]);calls=[]
    def limited(**kwargs):
        calls.append(kwargs)
        if len(calls)==1:raise HTTPError(ENDPOINT,status,'private',{'Retry-After':'20'},None)
        return b'{"model":"jev-1.14.0","answers":{"relevant":{"type":"noul","noul":0.8}},"usage":{"input_tokens":1,"output_tokens":0}}'
    client=jev.TypeSafeClient(api_key='fixture-key',transport=limited)
    with pytest.raises(ModelFailure):client.evaluate(state='fixture',questions=QUESTION)
    now[0]+=2
    with pytest.raises(ModelFailure) as cooling:client.evaluate(state='fixture',questions=QUESTION)
    assert cooling.value.code=='typesafe_cooldown'
    assert cooling.value.remote_outcome=='not_dispatched' and cooling.value.safe_details()['retry_after_seconds']==18
    assert len(calls)==1
    now[0]+=19
    assert client.evaluate(state='fixture',questions=QUESTION)['answers']['relevant']['noul']==.8
    assert len(calls)==2


def test_free_models_catalog_is_get_and_sanitizes_unrecognized_provider_fields():
    calls=[]
    def catalog(**kwargs):
        calls.append(kwargs)
        return b'{"models":[{"name":"jev-latest","description":"General-purpose system one model.","private_account":"PRIVATE"},{"name":"jev-1.14.0"}],"private":"PRIVATE"}'
    result=jev.TypeSafeClient(api_key='fixture-key',transport=catalog).get_models()
    assert calls[0]['endpoint']=='https://api.typesafe.ai/v1/models'
    assert calls[0]['method']=='GET' and calls[0]['body'] is None and len(calls)==1
    assert result['models'][0]=='jev-latest'
    assert result['model_requests']==0 and result['cost_usd']==0
    assert 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('reply',[
    b'{"models":[{"name":"jev-latest\\nprivate"}]}',b'{"models":[{"name":"jev-latest"},{"name":"jev-latest"}]}',
    b'{"models":[]}',b'{"models":[{"id":"missing name"}]}',b'{"code":0,"data":{"models":[{"name":"jev-latest"}]}}',
])
def test_malformed_catalog_is_rejected_without_inference(reply):
    calls=[]
    def catalog(**kwargs):calls.append(kwargs);return reply
    with pytest.raises(ModelFailure) as error:jev.TypeSafeClient(api_key='fixture-key',transport=catalog).get_models()
    assert error.value.code=='typesafe_invalid_models_response' and len(calls)==1
    assert calls[0]['body'] is None
