"""No-cost release preparation and usable invite recovery, without real secrets."""
import json
from test_mvp_preview import preview
from decision_lab.mvp_preview import initialize_preview,main


def test_check_uses_real_configuration_but_no_provider_or_chain_requests(tmp_path,monkeypatch,capsys):
    from decision_lab.jev import TypeSafeClient
    import socket
    def forbidden(*args,**kwargs):raise AssertionError('No provider dispatch during readiness')
    monkeypatch.setattr(TypeSafeClient,'get_models',forbidden)
    monkeypatch.setattr(TypeSafeClient,'evaluate',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    config,_=initialize_preview(tmp_path/'private',public_origin='https://preview.example',users=3)
    key=tmp_path/'test.env';key.write_text('TYPESAFE_API_KEY=FIXTURE_SECRET\n');key.chmod(0o600)
    args=['check','--config',str(config),'--typesafe-env-file',str(key)]
    assert main(args)==0
    output=capsys.readouterr().out;value=json.loads(output)
    assert value['configuration_valid']and value['reviewer_count']==3
    assert value['provider_requests']==value['chain_requests']==0 and value['inference_verified']is False
    assert all(r['typesafe_configured']and r['operator_allowance']['remaining_calls']==200 for r in value['reviewers'])
    assert 'FIXTURE_SECRET'not in output and 'token_sha256'not in output
    assert main(args)==0
    assert all(r['operator_allowance']['reserved_calls']==0 for r in json.loads(capsys.readouterr().out)['reviewers'])


def test_check_rejects_bad_key_without_echoing_it(tmp_path,capsys):
    config,_=initialize_preview(tmp_path/'private',public_origin='https://preview.example',users=1)
    key=tmp_path/'test.env';key.write_text('TYPESAFE_API_KEY="bad secret"\n');key.chmod(0o600)
    assert main(['check','--config',str(config),'--typesafe-env-file',str(key)])==2
    assert 'bad secret'not in capsys.readouterr().out


def test_check_reports_the_operator_funded_author_allowance(tmp_path,monkeypatch,capsys):
    """The gateway must wrap the author route, not only the native Jev actor."""
    import shutil,socket
    from decision_lab.jev import TypeSafeClient
    monkeypatch.setattr(TypeSafeClient,'get_models',lambda *a,**k:_forbidden())
    monkeypatch.setattr(TypeSafeClient,'evaluate',lambda *a,**k:_forbidden())
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:_forbidden())
    monkeypatch.setattr(shutil,'which',lambda name:'/usr/local/bin/agy')
    config,_=initialize_preview(tmp_path/'private',public_origin='https://preview.example',users=2)
    assert main(['check','--config',str(config),'--enable-gemini'])==0
    reviewers=json.loads(capsys.readouterr().out)['reviewers']
    assert all(r['author_configured']for r in reviewers)
    assert all(r['author_allowance']['call_limit']==200 and r['author_allowance']['reserved_calls']==0
               for r in reviewers)


def test_author_allowance_is_configured_separately_from_the_native_one(tmp_path,monkeypatch,capsys):
    """--operator-author-call-budget bounds text generation; the Jev cap stays distinct."""
    import shutil,socket
    from decision_lab.jev import TypeSafeClient
    monkeypatch.setattr(TypeSafeClient,'get_models',lambda *a,**k:_forbidden())
    monkeypatch.setattr(TypeSafeClient,'evaluate',lambda *a,**k:_forbidden())
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:_forbidden())
    monkeypatch.setattr(shutil,'which',lambda name:'/usr/local/bin/agy')
    config,_=initialize_preview(tmp_path/'private',public_origin='https://preview.example',users=1)
    key=tmp_path/'test.env';key.write_text('TYPESAFE_API_KEY=FIXTURE_SECRET\n');key.chmod(0o600)
    assert main(['check','--config',str(config),'--enable-gemini','--operator-author-call-budget','7',
                 '--typesafe-env-file',str(key)])==0
    reviewer=json.loads(capsys.readouterr().out)['reviewers'][0]
    assert reviewer['author_allowance']['call_limit']==7
    assert reviewer['operator_allowance']['call_limit']==200


def test_check_rejects_an_unbounded_author_allowance(tmp_path,monkeypatch,capsys):
    import shutil
    monkeypatch.setattr(shutil,'which',lambda name:'/usr/local/bin/agy')
    config,_=initialize_preview(tmp_path/'private',public_origin='https://preview.example',users=1)
    assert main(['check','--config',str(config),'--operator-author-call-budget','0'])==2


def _forbidden(*args,**kwargs):raise AssertionError('No provider dispatch during readiness')


def test_new_invite_page_is_explanatory_and_error_keeps_the_form(preview):
    from test_mvp_preview import request
    status,headers,body=request(preview,'GET','/')
    assert status==200 and b'Explore a decision'in body
    assert b'/preview/style.css'in body and b'calibrated market forecasts'in body
    assert b'API key or wallet'in body
    status,headers,css=request(preview,'GET','/preview/style.css')
    assert status==200 and 'text/css'in headers['Content-Type']and b'.access'in css
    status,headers,body=request(preview,'POST','/preview/login','code='+'x'*48,
        {'Content-Type':'application/x-www-form-urlencoded','Origin':preview.public_origin})
    assert status==401 and 'text/html'in headers['Content-Type']
    assert b'role="alert"'in body and b'form action="/preview/login"'in body
    assert ('x'*48).encode()not in body


def test_allowance_failure_is_actionable_http_409_before_dispatch(preview):
    from test_mvp_preview import request,login
    from decision_lab.preview_budget import PreviewJevClient
    from test_preview_budget import Client
    actor=Client()
    manager=preview.backends['reviewer-a'].product
    manager.actors={'typesafe':PreviewJevClient(actor,root=manager.root/'operator-jev-budget',call_limit=1)}
    headers=login(preview,'a'*48)
    boot=json.loads(request(preview,'GET','/api/product',headers=headers)[2])
    headers={**headers,'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
    example=boot['examples'][0]
    status,_,body=request(preview,'POST','/api/product/sessions',json.dumps({'mode':'example',
        'example_id':example['id'],'question':example['question'],'public_input':False}),headers)
    assert status==202
    state=json.loads(body)
    data={'world':state['proposal']['world'],'actor_route':'typesafe','mode':'sample','worlds':1,'seed':42,'max_calls':800,'max_credits':0}
    status,_,body=request(preview,'POST','/api/product/sessions/'+state['id']+'/review',json.dumps(data),headers)
    assert status==409 and b'Reduce the run'in body and b'local rules'in body
    assert actor.calls==0 and manager.actors['typesafe'].budget_status()['reserved_calls']==0


def test_form_document_preserves_same_origin_for_native_browser_posts(preview):
    from test_mvp_preview import request,login
    # Chromium gives native POST forms an opaque Origin with no-referrer.
    # Keep cross-origin referrers suppressed without breaking strict Origin checks.
    status,headers,_=request(preview,'GET','/')
    assert status==200 and headers['Referrer-Policy']=='same-origin'
    auth=login(preview,'a'*48)
    status,headers,_=request(preview,'GET','/preview',headers=auth)
    assert status==200 and headers['Referrer-Policy']=='same-origin'
    assert request(preview,'POST','/preview/logout','action=logout',
        {**auth,'Origin':'null','Content-Type':'application/x-www-form-urlencoded'})[0]==403
