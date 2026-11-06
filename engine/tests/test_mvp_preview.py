"""Invite-only preview routes each reviewer to an isolated real backend."""
import hashlib
import http.client
import json
import threading
from urllib.parse import urlencode
import pytest


def request(server,method,path,body=None,headers=None):
    c=http.client.HTTPConnection(*server.server_address,timeout=5)
    c.request(method,path,body=body,headers=headers or {})
    r=c.getresponse();result=r.status,dict(r.getheaders()),r.read();c.close();return result


@pytest.fixture
def preview(tmp_path):
    from decision_lab.mvp_preview import create_preview_server
    invites=[{'id':name,'token_sha256':hashlib.sha256(code.encode()).hexdigest()}for name,code in [('reviewer-a','a'*48),('reviewer-b','b'*48)]]
    server=create_preview_server(port=0,public_origin='http://127.0.0.1:0',invites=invites,output_dir=tmp_path/'users')
    thread=threading.Thread(target=server.serve_forever);thread.start()
    yield server
    server.shutdown();server.server_close();thread.join(3)
    assert not thread.is_alive()


def login(server,code):
    status,headers,_=request(server,'POST','/preview/login',urlencode({'code':code}),{'Content-Type':'application/x-www-form-urlencoded','Origin':server.public_origin})
    assert status==303
    cookie=headers['Set-Cookie'];assert 'HttpOnly'in cookie and 'SameSite=Strict'in cookie
    return {'Cookie':cookie.split(';',1)[0],'Origin':server.public_origin}


def test_no_unauthenticated_api_or_result_access_and_strict_origin(preview):
    assert request(preview,'GET','/')[0]==200
    for path in ('/api/product','/api/product/results','/docs','/lab'):
        assert request(preview,'GET',path)[0]==401
    assert request(preview,'GET','/',headers={'Host':'evil.test'})[0]==403
    assert request(preview,'POST','/preview/login','code='+('a'*48),{'Content-Type':'application/x-www-form-urlencoded','Origin':'https://evil.test'})[0]==403
    assert request(preview,'POST','/preview/login','code='+('a'*48),{'Content-Type':'application/x-www-form-urlencoded'})[0]==403
    status,_,body=request(preview,'POST','/preview/login','code='+('x'*48),{'Content-Type':'application/x-www-form-urlencoded','Origin':preview.public_origin})
    assert status==401 and ('x'*48).encode()not in body


def test_users_have_independent_results_csrf_and_download_roots(preview):
    a=login(preview,'a'*48);b=login(preview,'b'*48)
    boot_a=json.loads(request(preview,'GET','/api/product',headers=a)[2]);boot_b=json.loads(request(preview,'GET','/api/product',headers=b)[2])
    assert boot_a['csrf_token']!=boot_b['csrf_token']
    ex=boot_a['examples'][0]
    data=json.dumps({'mode':'example','example_id':ex['id'],'question':'Private reviewer A question','public_input':False})
    status,_,body=request(preview,'POST','/api/product/sessions',data,{**a,'Content-Type':'application/json','X-CSRF-Token':boot_a['csrf_token']})
    assert status==202;sid=json.loads(body)['id']
    assert request(preview,'GET','/api/product/sessions/'+sid,headers=a)[0]==200
    assert request(preview,'GET','/api/product/sessions/'+sid,headers=b)[0]==404
    assert request(preview,'POST','/api/product/sessions',data,{**b,'Content-Type':'application/json','X-CSRF-Token':boot_a['csrf_token']})[0]==403
    assert request(preview,'GET','/api/product/results',headers=b)[0]==200
    assert not json.loads(request(preview,'GET','/api/product/results',headers=b)[2])['runs']
    assert request(preview,'GET','/api/product',headers={**a,'Origin':'https://evil.test'})[0]==403


def test_logout_revokes_session_and_login_rotation_revokes_old_cookie(preview):
    a=login(preview,'a'*48);new=login(preview,'a'*48)
    assert request(preview,'GET','/api/product',headers=a)[0]==401
    assert request(preview,'GET','/api/product',headers=new)[0]==200
    status,headers,_=request(preview,'POST','/preview/logout','',new)
    assert status==303 and 'Max-Age=0'in headers['Set-Cookie']
    assert request(preview,'GET','/api/product',headers=new)[0]==401


def test_no_query_tokens_no_arbitrary_proxy_and_bounded_input(preview):
    a=login(preview,'a'*48)
    for path in ('http://evil.test/api/product','/api/product?key=private','//evil.test/api/product','/../.env'):
        assert request(preview,'GET',path,headers=a)[0]in (400,403,404)
    assert request(preview,'POST','/api/product/sessions','{}',{**a,'Content-Type':'application/json','Transfer-Encoding':'chunked'})[0]==400
    assert request(preview,'POST','/api/product/sessions','{}',{**a,'Content-Type':'application/json','Content-Length':str(2*1024*1024+1)})[0]==413


def test_configuration_private_files_and_maximum_three_invites(tmp_path):
    from decision_lab.mvp_preview import initialize_preview,load_config,create_preview_server
    root=tmp_path/'private';config_path,codes_path=initialize_preview(root,public_origin='https://demo.example',users=3)
    assert root.stat().st_mode&0o777==0o700
    assert config_path.stat().st_mode&0o777==0o600 and codes_path.stat().st_mode&0o777==0o600
    config=load_config(config_path);codes=json.loads(codes_path.read_text())
    assert len(config['invites'])==3
    for item in codes['invites']:assert item['code']not in config_path.read_text()
    config_path.chmod(0o644)
    with pytest.raises(ValueError):load_config(config_path)
    with pytest.raises(ValueError):initialize_preview(tmp_path/'bad',public_origin='https://demo.example',users=4)
    with pytest.raises(ValueError):create_preview_server(port=0,public_origin='http://public.example',invites=[],output_dir=tmp_path/'none')


def test_login_rate_limit_session_expiry_and_no_automatic_proxy_retry(preview):
    cookie=login(preview,'a'*48)
    with preview._lock:
        for key,value in preview._sessions.items():preview._sessions[key]=(value[0],0)
    assert request(preview,'GET','/api/product',headers=cookie)[0]==401
    for _ in range(11):
        assert request(preview,'POST','/preview/login','code='+('x'*48),{'Content-Type':'application/x-www-form-urlencoded','Origin':preview.public_origin})[0]==401
    status,headers,_=request(preview,'POST','/preview/login','code='+('x'*48),{'Content-Type':'application/x-www-form-urlencoded','Origin':preview.public_origin})
    assert status==429 and headers['Retry-After']=='60'


def test_login_throttle_blocks_guessers_but_never_an_invited_reviewer(preview):
    """One caller's wrong-code spam must not lock every reviewer out of the preview."""
    for _ in range(12):
        request(preview,'POST','/preview/login','code='+('x'*48),{'Content-Type':'application/x-www-form-urlencoded','Origin':preview.public_origin})
    status,headers,_=request(preview,'POST','/preview/login','code='+('x'*48),{'Content-Type':'application/x-www-form-urlencoded','Origin':preview.public_origin})
    assert status==429 and headers['Retry-After']=='60'
    cookie=login(preview,'a'*48)
    assert request(preview,'GET','/api/product',headers=cookie)[0]==200
    assert login(preview,'b'*48)


def test_https_cookie_and_downstream_header_scrubbing(tmp_path):
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    from decision_lab.mvp_preview import create_preview_server
    captured=[]
    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self):
            captured.append(dict(self.headers));body=b'{"safe":true}'
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Set-Cookie','unexpected=SECRET');self.end_headers();self.wfile.write(body)
        def log_message(self,*_):pass
    def factory(name,path):return ThreadingHTTPServer(('127.0.0.1',0),Upstream)
    server=create_preview_server(port=0,public_origin='https://demo.example',invites=[{'id':'reviewer-a','token_sha256':hashlib.sha256(('a'*48).encode()).hexdigest()}],output_dir=tmp_path/'users',backend_factory=factory)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        status,headers,_=request(server,'POST','/preview/login','code='+('a'*48),{'Host':'demo.example','Origin':'https://demo.example','Content-Type':'application/x-www-form-urlencoded'})
        assert status==303 and '; Secure'in headers['Set-Cookie']
        cookie=headers['Set-Cookie'].split(';',1)[0]
        status,headers,body=request(server,'GET','/api/product',headers={'Host':'demo.example','Origin':'https://demo.example','Cookie':cookie,'Authorization':'Bearer NOT_FOR_BACKEND','X-Forwarded-Host':'evil.test'})
        assert status==200 and json.loads(body)=={'safe':True}and 'Set-Cookie'not in headers
        assert len(captured)==1 and 'Authorization'not in captured[0]and 'Cookie'not in captured[0]and 'X-Forwarded-Host'not in captured[0]
        assert captured[0]['Host'].startswith('127.0.0.1:')and captured[0]['Origin']=='http://'+captured[0]['Host']
    finally:server.shutdown();server.server_close();thread.join(3)


def test_three_reviewers_run_real_numeric_jobs_in_parallel_with_separate_results(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from decision_lab.mvp_preview import create_preview_server
    import time
    codes=['a'*48,'b'*48,'c'*48]
    invites=[{'id':f'reviewer-{i}','token_sha256':hashlib.sha256(code.encode()).hexdigest()}for i,code in enumerate(codes)]
    server=create_preview_server(port=0,public_origin='http://127.0.0.1:0',invites=invites,output_dir=tmp_path/'users')
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        sessions=[login(server,code)for code in codes]
        def run(headers):
            boot=json.loads(request(server,'GET','/api/bootstrap',headers=headers)[2])
            valid={**headers,'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
            status,_,body=request(server,'POST','/api/jobs',json.dumps({'kind':'run','worlds':1,'seed':7}),valid)
            assert status==202;job=json.loads(body)['job_id']
            for _ in range(200):
                value=json.loads(request(server,'GET','/api/jobs/'+job,headers=headers)[2])
                if value['status']=='completed':break
                assert value['status']!='failed';time.sleep(.01)
            assert value['status']=='completed'and value['result']['usage']['model_calls']==0
            return job
        with ThreadPoolExecutor(max_workers=3)as pool:jobs=list(pool.map(run,sessions))
        assert len(set(jobs))==3
        for i,headers in enumerate(sessions):
            assert request(server,'GET','/api/jobs/'+jobs[(i+1)%3],headers=headers)[0]==404
    finally:server.shutdown();server.server_close();thread.join(3)


def test_proxy_failure_is_one_attempt_and_does_not_forward_a_client_secret(tmp_path):
    from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
    from decision_lab.mvp_preview import create_preview_server
    attempts=[]
    class Broken(BaseHTTPRequestHandler):
        def do_GET(self):attempts.append(self.path);self.connection.close()
        def log_message(self,*_):pass
    def factory(name,path):return ThreadingHTTPServer(('127.0.0.1',0),Broken)
    server=create_preview_server(port=0,public_origin='http://127.0.0.1:0',invites=[{'id':'reviewer-a','token_sha256':hashlib.sha256(('a'*48).encode()).hexdigest()}],output_dir=tmp_path/'users',backend_factory=factory)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        headers=login(server,'a'*48)
        status,_,body=request(server,'GET','/api/product',headers=headers)
        assert status==502 and len(attempts)==1 and b'No automatic retry'in body
    finally:server.shutdown();server.server_close();thread.join(3)


def test_internal_map_paths_never_proxy_even_to_an_enabled_backend(tmp_path):
    from decision_lab.mvp_preview import create_preview_server
    from decision_lab.web_server import create_server
    server=create_preview_server(port=0,public_origin='http://127.0.0.1:0',invites=[{'id':'reviewer','token_sha256':hashlib.sha256(('a'*48).encode()).hexdigest()}],output_dir=tmp_path,
        backend_factory=lambda name,path:create_server(port=0,output_dir=path,enable_internal_map=True))
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        auth=login(server,'a'*48)
        for headers in ({},auth):
            for path in ('/internal/flow','/internal/flow.js','/internal/flow.css','/api/internal/flow'):
                assert request(server,'GET',path,headers=headers)[0]==404
                assert request(server,'POST',path,'{}',{**headers,'Content-Type':'application/json'})[0]==404
    finally:server.shutdown();server.server_close();thread.join(3)


def test_imported_keys_are_reviewer_isolated_and_released_on_logout_rotation_expiry(preview):
    a=login(preview,'a'*48);b=login(preview,'b'*48)
    def import_key(headers):
        boot=json.loads(request(preview,'GET','/api/product',headers=headers)[2]);assert boot['access']['hosted']
        h={**headers,'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        body=json.dumps({'mode':'typesafe','api_key':'unit-not-real-key','accept_host_access':False})
        assert request(preview,'POST','/api/product/access',body,h)[0]==400
        body=json.dumps({'mode':'typesafe','api_key':'unit-not-real-key','accept_host_access':True})
        assert request(preview,'POST','/api/product/access',body,h)[0]==200
    import_key(a)
    assert 'typesafe'in preview.backends['reviewer-a'].product.actors
    assert 'typesafe'not in preview.backends['reviewer-b'].product.actors
    a=login(preview,'a'*48)
    assert 'typesafe'not in preview.backends['reviewer-a'].product.actors
    import_key(a)
    assert request(preview,'POST','/preview/logout','',a)[0]==303
    assert 'typesafe'not in preview.backends['reviewer-a'].product.actors
    a=login(preview,'a'*48);import_key(a)
    with preview._lock:
        for key,value in preview._sessions.items():
            if value[0]=='reviewer-a':preview._sessions[key]=(value[0],0)
    preview.service_actions()
    assert 'typesafe'not in preview.backends['reviewer-a'].product.actors
    assert preview.backends['reviewer-a'].product.access_status()['completed']is False


def test_other_reviewers_login_releases_expired_imported_access(preview):
    login(preview,'a'*48)
    product=preview.backends['reviewer-a'].product
    product.configure_access({'mode':'typesafe','api_key':'unit-key-not-real','accept_host_access':True})
    with preview._lock:
        for key,value in preview._sessions.items():
            if value[0]=='reviewer-a':preview._sessions[key]=(value[0],0)
    login(preview,'b'*48);preview.service_actions()
    assert not product.actors and product.access_status()['mode']=='unconfigured'


def test_signout_form_has_nonempty_payload_for_https_proxies(preview):
    headers=login(preview,'a'*48)
    status,_,body=request(preview,'GET','/preview',headers=headers)
    assert status==200 and b'type="hidden" name="action" value="logout"'in body
    assert request(preview,'POST','/preview/logout','action=logout',{**headers,'Content-Type':'application/x-www-form-urlencoded'})[0]==303
    assert request(preview,'GET','/api/product',headers=headers)[0]==401


@pytest.mark.parametrize('role',['actor','author'])
@pytest.mark.parametrize('invalidation',['logout','rotation','expiry'])
def test_stale_authenticated_credential_import_cannot_outlive_session(preview,monkeypatch,role,invalidation):
    headers=login(preview,'a'*48)
    boot=json.loads(request(preview,'GET','/api/product',headers=headers)[2])
    headers={**headers,'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token'],
        'X-Scenario-Credential-Context':'2:9999999999'}  # Caller context must be overwritten.
    product=preview.backends['reviewer-a'].product
    entered=threading.Event();finish=threading.Event();results=[]
    original=preview.allow_request
    def pause_after_auth(user):
        if threading.current_thread().name!=threading.main_thread().name:
            entered.set();assert finish.wait(3)
        return original(user)
    monkeypatch.setattr(preview,'allow_request',pause_after_auth)
    path='/api/product/author-access'if role=='author'else'/api/product/access'
    body={'mode':'near_ai'if role=='author'else'typesafe','api_key':'race-test-key','accept_host_access':True}
    if role=='author':body['model']='canonical/model'
    worker=threading.Thread(target=lambda:results.append(request(preview,'POST',path,json.dumps(body),headers)[0]))
    worker.start()
    try:
        assert entered.wait(3)
        token=headers['Cookie'].split('=',1)[1]
        if invalidation=='logout':preview.revoke(token)
        elif invalidation=='rotation':assert preview.authenticate('a'*48)[0]
        else:
            with preview._lock:
                for key,value in preview._sessions.items():
                    if value[0]=='reviewer-a':preview._sessions[key]=(value[0],0)
            preview.service_actions()
        finish.set();worker.join(3)
        assert results==[401]
        assert product.author is None and not product.actors
    finally:finish.set();worker.join(3)


@pytest.mark.parametrize('gateway_timeout',[False,True])
def test_logout_waits_for_local_author_import_then_releases_it(preview,monkeypatch,gateway_timeout):
    if gateway_timeout:
        from decision_lab.web_server import Handler
        original_reply=Handler._reply
        def disconnected_reply(self,*args,**kwargs):
            try:return original_reply(self,*args,**kwargs)
            except (BrokenPipeError,ConnectionResetError):pass
        monkeypatch.setattr(Handler,'_reply',disconnected_reply)
        monkeypatch.setattr('decision_lab.mvp_preview.UPSTREAM_TIMEOUT',.05)
    headers=login(preview,'a'*48)
    boot=json.loads(request(preview,'GET','/api/product',headers=headers)[2])
    product=preview.backends['reviewer-a'].product
    entered=threading.Event();finish=threading.Event();revoking=threading.Event();revoked=threading.Event();results=[]
    original_import=product.configure_author;original_release=preview._release_user_access
    def paused_import(data):
        entered.set();assert finish.wait(3)
        return original_import(data)
    def release(user):
        revoking.set();original_release(user);revoked.set()
    monkeypatch.setattr(product,'configure_author',paused_import)
    monkeypatch.setattr(preview,'_release_user_access',release)
    body=json.dumps({'mode':'near_ai','api_key':'race-test-key','model':'canonical/model','accept_host_access':True})
    importer=threading.Thread(target=lambda:results.append(request(preview,'POST','/api/product/author-access',body,{**headers,'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']})[0]))
    logout=threading.Thread(target=lambda:preview.revoke(headers['Cookie'].split('=',1)[1]))
    importer.start()
    try:
        assert entered.wait(3);logout.start();assert revoking.wait(3)
        # A local import already committing must finish before revocation returns.
        completed_before_import=revoked.wait(.1)
        finish.set();importer.join(3);logout.join(3)
        assert not completed_before_import
        assert results==[502 if gateway_timeout else 200]and revoked.is_set()
        assert product.author is None
    finally:
        finish.set();importer.join(3)
        if logout.ident is not None:logout.join(3)


def test_gateway_timeout_before_backend_commit_cannot_restore_revoked_key(preview,monkeypatch):
    from contextlib import contextmanager
    from decision_lab.web_server import Handler
    headers=login(preview,'a'*48)
    boot=json.loads(request(preview,'GET','/api/product',headers=headers)[2])
    backend=preview.backends['reviewer-a'];entered=threading.Event();finish=threading.Event();exited=threading.Event();results=[]
    original=backend.credential_guard;original_reply=Handler._reply
    @contextmanager
    def delayed_guard(request_headers):
        entered.set();assert finish.wait(3)
        try:
            with original(request_headers):yield
        finally:exited.set()
    def disconnected_reply(self,*args,**kwargs):
        try:return original_reply(self,*args,**kwargs)
        except (BrokenPipeError,ConnectionResetError):pass
    monkeypatch.setattr(backend,'credential_guard',delayed_guard)
    monkeypatch.setattr(Handler,'_reply',disconnected_reply)
    monkeypatch.setattr('decision_lab.mvp_preview.UPSTREAM_TIMEOUT',.05)
    body=json.dumps({'mode':'near_ai','api_key':'race-test-key','model':'canonical/model','accept_host_access':True})
    worker=threading.Thread(target=lambda:results.append(request(preview,'POST','/api/product/author-access',body,{**headers,'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']})[0]))
    worker.start()
    try:
        assert entered.wait(3);worker.join(3);assert results==[502]
        preview.revoke(headers['Cookie'].split('=',1)[1])
        finish.set();assert exited.wait(3)
        assert backend.product.author is None
    finally:finish.set();worker.join(3)
