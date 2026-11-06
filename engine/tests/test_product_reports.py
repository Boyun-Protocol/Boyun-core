import io
import pytest
from decision_lab.product_reports import markdown,pdf,report_data,pdf_available
from decision_lab.product_api import ProductManager
from test_private_onboarding import offline
from test_product_api import ready


def finished(tmp_path):
    m=ProductManager(tmp_path);offline(m);ex=m.bootstrap()['examples'][0]
    s=m.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
    r=m.review(s['id'],{'world':s['proposal']['world'],'actor_route':'offline','mode':'argmax','worlds':2,'seed':42,'max_calls':96,'max_credits':0})
    m.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':False});s=ready(m,s['id'])
    assert s['status']=='completed'
    return m,s


def test_markdown_real_run_and_saved_report_agree_private_no_inference(tmp_path):
    m,s=finished(tmp_path)
    try:
        report=m.report(s['id'],'md');saved=m.report(s['id'],'md',s['run_id'])
        assert report==saved
        text=report.decode();assert '2 / 2'in text and 'attempted provider calls: 0'in text
        assert 'local rule turns: 8'in text
        assert 'not net financial profit'in text
        assert 'Jev returns no reasoning trace' in text
        assert 'Replay checks settlement with saved choices' in text
        value=report_data(s);value['description']='<script>bad()</script>\n# heading | cell'
        assert b'<script>'not in markdown(value)and b'&lt;script&gt;'in markdown(value)
        assert b'\\|'in markdown(value)
    finally:m.close()


def test_partial_failed_world_accounting_includes_responses_not_completed(tmp_path):
    import json
    from decision_lab.decision_sessions import _write
    m,s=finished(tmp_path)
    try:
        folder=m.root/s['id']/s['run_id']
        review=json.loads((folder/'review.json').read_text());review['actor_route']='typesafe'
        from decision_lab.agent_worlds import digest
        review.pop('sha256');review['sha256']=digest(review)
        _write(folder,'review.json',review,replace=True)
        _write(folder,'call-9.request.json',{'state':'incomplete world'})
        _write(folder,'call-9.response.json',{'receipt':{'transport':'typesafe_systemone_http','usage':{'input_tokens':700},'input_cost_estimate_usd':0.0000294,'model_reported':'jev-latest'}})
        _write(folder,'call-10.request.json',{'state':'response missing'})
        text=m.report(s['id'],'md').decode()
        assert 'recorded input tokens: 700'in text
        assert 'input cost estimate usd:'in text and 'billing'in text
        # Existing local rule response files are not provider receipts.
        assert 'unknown remote outcomes: 9'in text
    finally:m.close()


def test_pdf_is_local_unicode_and_no_external_resource(tmp_path):
    if not pdf_available():pytest.skip('optional PDF extra')
    m,s=finished(tmp_path)
    try:
        value=report_data(s);value['title']='Kế hoạch thử nghiệm - NEAR'
        raw=pdf(value);assert raw.startswith(b'%PDF-')and len(raw)>10000
        assert b'/URI'not in raw
        (tmp_path/'sample.pdf').write_bytes(raw)
    finally:m.close()


def test_report_uses_frozen_world_after_mutable_rereview(tmp_path):
    from copy import deepcopy
    m,s=finished(tmp_path)
    try:
        old=m.report(s['id'],'md');changed=deepcopy(s['proposal']['world']);changed['title']='NEVER EXECUTED NEW WORLD'
        m.review(s['id'],{'world':changed,'actor_route':'offline','mode':'argmax','worlds':1,'seed':42,'max_calls':96,'max_credits':0})
        assert m.report(s['id'],'md')==old
        assert b'NEVER EXECUTED'not in m.report(s['id'],'md',s['run_id'])
    finally:m.close()


def test_zero_completion_run_can_be_exported_with_explicit_run_id(tmp_path):
    from test_product_api import FakeModel
    from decision_lab.agent_models import ModelFailure
    class Failing(FakeModel):
        def generate(self,*a):raise ModelFailure('unit-failure','unknown')
    m=ProductManager(tmp_path,actor_clients={'gemini':Failing()})
    try:
        ex=m.bootstrap()['examples'][0];s=m.create({'mode':'example','example_id':ex['id'],'question':ex['question'],'public_input':False})
        r=m.review(s['id'],{'world':s['proposal']['world'],'actor_route':'gemini','mode':'argmax','worlds':1,'seed':42,'max_calls':96,'max_credits':0})
        m.run(s['id'],{'review_sha256':r['review']['sha256'],'public_input':True});s=ready(m,s['id']);assert s['status']=='failed'
        text=m.report(s['id'],'md',s['run_id']).decode();assert '0 / 1'in text and 'unknown remote outcomes: 1'in text
        assert 'No complete world'in text
    finally:m.close()


def test_saved_report_does_not_reclassify_historical_usage_as_native_acceptance(tmp_path):
    import json
    from decision_lab.decision_sessions import _write
    from decision_lab.agent_worlds import digest
    m,s=finished(tmp_path)
    try:
        folder=m.root/s['id']/s['run_id']
        review=json.loads((folder/'review.json').read_text());review['actor_route']='historical-provider'
        review.pop('sha256');review['sha256']=digest(review)
        _write(folder,'review.json',review,replace=True)
        _write(folder,'call-9.request.json',{'state':'historical saved request'})
        _write(folder,'call-9.response.json',{'receipt':{'transport':'historical-provider',
            'usage':{'input_tokens':700},'input_cost_estimate_usd':10,'credits':{'charged':1},'model_reported':'historical-model-identity'}})
        text=m.report(s['id'],'md',s['run_id']).decode().replace('\\','')
        assert 'route: historical-provider'in text and 'recorded models: historical-model-identity'in text
        assert 'recorded input tokens: None'in text and 'input cost estimate usd: None'in text
        assert 'native typesafe receipts: 0'in text and 'cost usd: None'in text
        assert 'do not independently establish direct TypeSafe live acceptance'in text
        assert 'Provider-reported model identity'in text and 'credit'not in text.lower()
    finally:m.close()
