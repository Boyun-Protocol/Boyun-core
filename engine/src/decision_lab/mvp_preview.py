"""Optional three-reviewer preview gateway with isolated loopback backends.

This is an explicitly bounded submission preview, not public SaaS authentication
or billing. The gateway owns all backends and chooses their loopback addresses;
no browser input selects an upstream. No provider calls happen during startup.
"""
from .interface_assets import web_assets, InterfaceUnavailable
from collections import deque
from contextlib import contextmanager
from hashlib import sha256
from http.cookies import SimpleCookie
from importlib.resources import files
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import argparse
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
from urllib.parse import parse_qs,urlsplit

from .io_helpers import _unique_object

MAX_BODY=2*1024*1024
MAX_RESPONSE=16*1024*1024
CREDENTIAL_CONTEXT='X-Scenario-Credential-Context'
UPSTREAM_TIMEOUT=30
COOKIE='scenario_preview'
SESSION_SECONDS=2*60*60
_ID=re.compile(r'[a-z][a-z0-9-]{0,39}\Z')
_HASH=re.compile(r'[0-9a-f]{64}\Z')
_TOKEN=re.compile(r'[A-Za-z0-9_-]{32,128}\Z')
def _access_page(*,account=False,message=None):
    from html import escape
    heading='Your preview workspace' if account else 'Explore a decision before you commit.'
    content=('<p>Return to your scenarios or sign out. Signing out clears imported keys from your workspace; an already dispatched request may finish.</p><a class="button" href="/">Return to Boyun</a><form action="/preview/logout" method="post"><input type="hidden" name="action" value="logout"><button class="secondary" type="submit">Sign out of this browser</button></form>' if account else
        '<p>Use your private invite code to open a workspace. No API key or wallet is needed to try the local-rule example.</p><form action="/preview/login" method="post"><label for="code">Invite code</label><input id="code" name="code" type="password" required minlength="32" maxlength="128" autocomplete="off" spellcheck="false" aria-describedby="invite-help"><p id="invite-help" class="muted">Paste the code shared privately by the host. It is not your wallet secret or API key.</p><button type="submit">Open my workspace</button></form>')
    notice='<p class="notice" role="alert">'+escape(message)+'</p>' if message else ''
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Boyun · invite-only test</title><link rel="stylesheet" href="/preview/style.css"><body><main><a class="brand" href="/">Boyun</a><span class="badge">Invite-only test · up to three reviewers</span><h1>'+heading+'</h1><p class="lead">Bring your decision into view. Review the participants and rules, then compare how their choices play out.</p><ol class="journey"><li><b>Describe</b> the decision</li><li><b>Review</b> the world</li><li><b>Compare</b> the scenarios</li></ol><section class="access" aria-label="Preview access">'+notice+content+'</section><aside><h2>Before you start</h2><p>Your workspace is separate from other reviewers. The host can read stored scenarios and imported keys. Selected remote model providers receive their supplied inputs.</p><p>Local rules make no model requests. Jev runs require a separate usage review and approval. Results describe hypothetical scenarios, not calibrated market forecasts. Wallet actions are optional and testnet-only.</p></aside></main></body></html>')


_LOGIN=_access_page()
_ACCOUNT=_access_page(account=True)


def _origin(value):
    if type(value)is not str or len(value)>512:raise ValueError('explicit public origin required')
    try:p=urlsplit(value);port=p.port
    except ValueError:raise ValueError('invalid public origin')from None
    if (p.scheme not in ('http','https')or not p.hostname or p.username or p.password
        or p.path or p.query or p.fragment or p.netloc!=p.netloc.lower()
        or not re.fullmatch(r'[a-z0-9.-]+(?::[0-9]{1,5})?',p.netloc)):
        raise ValueError('plain exact origin required')
    if p.scheme=='http'and p.hostname not in ('127.0.0.1','localhost'):raise ValueError('public preview requires HTTPS')
    if port is not None and not 0<=port<=65535:raise ValueError('invalid origin port')
    return p


def _invites(value):
    if type(value)is not list or not 1<=len(value)<=3:raise ValueError('one to three explicit reviewers required')
    result={};hashes=set()
    for item in value:
        if type(item)is not dict or set(item)!={'id','token_sha256'}:raise ValueError('invalid reviewer schema')
        name=item['id'];digest=item['token_sha256']
        if type(name)is not str or not _ID.fullmatch(name)or type(digest)is not str or not _HASH.fullmatch(digest):raise ValueError('invalid reviewer identity')
        if name in result or digest in hashes:raise ValueError('reviewers and tokens must be distinct')
        result[name]=digest;hashes.add(digest)
    return result


def _private_write(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'w')as handle:json.dump(value,handle,indent=2);handle.write('\n')


def initialize_preview(output_dir,*,public_origin,users=3):
    _origin(public_origin)
    if type(users)is not int or not 1<=users<=3:raise ValueError('one to three reviewers required')
    root=Path(output_dir);root.parent.mkdir(parents=True,exist_ok=True);root.mkdir(mode=0o700)
    codes=[{'id':f'reviewer-{i+1}','code':secrets.token_urlsafe(32)}for i in range(users)]
    config={'schema_version':'mvp-preview.v1','public_origin':public_origin,
        'invites':[{'id':item['id'],'token_sha256':sha256(item['code'].encode()).hexdigest()}for item in codes]}
    config_path=root/'preview-config.json';codes_path=root/'invite-codes.private.json'
    _private_write(config_path,config);_private_write(codes_path,{'invites':codes})
    return config_path,codes_path


def load_config(path):
    path=Path(path)
    fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(fd,'rb')as handle:
        info=os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode)or info.st_mode&0o077 or info.st_size>65536:raise ValueError('owner-only regular preview configuration required')
        raw=handle.read(65537)
    if len(raw)>65536:raise ValueError('bounded preview configuration required')
    value=json.loads(raw,object_pairs_hook=_unique_object)
    if type(value)is not dict or set(value)!={'schema_version','public_origin','invites'}or value['schema_version']!='mvp-preview.v1':raise ValueError('invalid preview configuration')
    _origin(value['public_origin']);_invites(value['invites'])
    return value


class PreviewServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    request_queue_size=16
    def __init__(self,address,*,public_origin,invites,output_dir,backend_factory=None):
        origin=_origin(public_origin);self.invites=_invites(invites)
        self._lock=threading.RLock();self._sessions={};self._login_attempts=deque();self._requests={};self._slots=threading.BoundedSemaphore(16)
        self._credential_locks={user:threading.RLock()for user in self.invites}
        self._credential_generations={user:0 for user in self.invites}
        self.backends={};self.backend_threads=[];self.output_dir=Path(output_dir)
        if self.output_dir.is_symlink():raise ValueError('regular private output directory required')
        self.output_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.output_dir.stat().st_mode&0o077:raise ValueError('owner-only preview output directory required')
        super().__init__(address,PreviewHandler)
        if origin.port==0:
            if origin.scheme!='http'or origin.hostname not in ('127.0.0.1','localhost'):
                self.server_close();raise ValueError('only local development may select a dynamic origin port')
            public_origin=f'http://{origin.hostname}:{self.server_address[1]}'
        self.public_origin=public_origin;self.public_host=urlsplit(public_origin).netloc;self.secure_cookie=origin.scheme=='https'
        try:
            for name in self.invites:
                path=self.output_dir/name
                if path.is_symlink():raise ValueError('regular reviewer directory required')
                path.mkdir(mode=0o700,exist_ok=True)
                if path.stat().st_mode&0o077:raise ValueError('owner-only reviewer directory required')
                if backend_factory:backend=backend_factory(name,path)
                else:
                    from .web_server import create_server
                    backend=create_server(port=0,output_dir=path,hosted=True)
                if backend.server_address[0]!='127.0.0.1':
                    backend.server_close();raise ValueError('only owned loopback backends are allowed')
                self.backends[name]=backend
                backend.credential_guard=lambda headers,user=name:self.credential_write(user,headers)
                thread=threading.Thread(target=backend.serve_forever,name='preview-'+name,daemon=True);thread.start();self.backend_threads.append(thread)
        except BaseException:self.server_close();raise

    def process_request(self,request,address):
        if not self._slots.acquire(blocking=False):request.close();return
        try:super().process_request(request,address)
        except BaseException:self._slots.release();raise

    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self._slots.release()

    def server_close(self):
        super().server_close()
        for backend in self.backends.values():backend.shutdown();backend.server_close()
        for thread in self.backend_threads:thread.join(5)
        self.backends.clear()

    def authenticate(self,code):
        with self._lock:
            now=time.monotonic()
            while self._login_attempts and self._login_attempts[0]<=now-60:self._login_attempts.popleft()
            digest=sha256(code.encode()).hexdigest()
            user=next((name for name,value in self.invites.items()if hmac.compare_digest(value,digest)),None)
            if not user:
                # Only wrong codes consume the window. It is shared across clients
                # because a tunnel presents one source address, so counting correct
                # logins too let any caller lock out every reviewer for a rolling
                # minute. Invites are 256-bit, so guessing is not the threat here;
                # twelve attempts a minute still bounds the check itself.
                self._login_attempts.append(now)
                if len(self._login_attempts)>=12:return None,True
                return None,False
            self._release_user_access(user)
            for expired_user in {value[0]for value in self._sessions.values()if value[1]<=now}:
                self._release_user_access(expired_user)
            # One browser session per invite bounds memory and permits revocation
            # by signing in again. Raw invite codes are never retained.
            self._sessions={key:value for key,value in self._sessions.items()if value[0]!=user and value[1]>now}
            token=secrets.token_urlsafe(32);self._sessions[sha256(token.encode()).hexdigest()]=(user,now+SESSION_SECONDS)
            return token,False

    def user(self,token,*,include_generation=False):
        with self._lock:
            if not token:return None
            key=sha256(token.encode()).hexdigest();value=self._sessions.get(key)
            if not value:return None
            if value[1]<=time.monotonic():
                self._sessions.pop(key,None);self._release_user_access(value[0]);return None
            user=value[0]
            return (user,self._credential_generations[user],value[1])if include_generation else user

    def revoke(self,token):
        with self._lock:
            if token:
                value=self._sessions.pop(sha256(token.encode()).hexdigest(),None)
                if value:self._release_user_access(value[0])

    def _release_user_access(self,user):
        # Serialize only bounded local credential writes with invalidation. Model
        # inference and catalog requests never hold this reviewer-specific lock.
        with self._credential_locks[user]:
            self._credential_generations[user]+=1
            product=getattr(self.backends[user],'product',None)
            if product is not None:product.release_imported_access()

    @contextmanager
    def credential_write(self,user,headers):
        from .web_server import CredentialAccessDenied
        values=headers.get_all(CREDENTIAL_CONTEXT,[])
        if len(values)!=1 or not re.fullmatch(r'[0-9]{1,20}:[0-9]{1,20}(?:\.[0-9]{1,20})?',values[0]):
            raise CredentialAccessDenied('current preview credential context required')
        generation,expires=values[0].split(':')
        with self._credential_locks[user]:
            if self._credential_generations[user]!=int(generation)or float(expires)<=time.monotonic():
                raise CredentialAccessDenied('preview credential context expired')
            yield

    def service_actions(self):
        with self._lock:
            now=time.monotonic()
            for key,value in list(self._sessions.items()):
                if value[1]<=now:
                    self._sessions.pop(key,None);self._release_user_access(value[0])

    def allow_request(self,user):
        with self._lock:
            now=time.monotonic();values=self._requests.setdefault(user,deque())
            while values and values[0]<=now-60:values.popleft()
            if len(values)>=150:return False
            values.append(now);return True


class PreviewHandler(BaseHTTPRequestHandler):
    server_version='BoyunPreview';sys_version='';protocol_version='HTTP/1.0'
    def setup(self):super().setup();self.connection.settimeout(5)
    def log_message(self,*_):pass
    def _reply(self,status,value,*,content_type='application/json; charset=utf-8',headers=None):
        raw=value if type(value)is bytes else json.dumps(value).encode()
        self.send_response(status)
        for name,value in {'Content-Type':content_type,'Content-Length':str(len(raw)),'Cache-Control':'no-store',
            'X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'if content_type.startswith('text/html')else'no-referrer','Cross-Origin-Resource-Policy':'same-origin',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self' https://rpc.testnet.near.org https://logout-bridge-service.intear.tech wss://logout-bridge-service.intear.tech; frame-src https://wallet.intear.tech; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            **(headers or {})}.items():self.send_header(name,value)
        self.end_headers();self.wfile.write(raw)

    def _error(self,status,message):self._reply(status,{'error':message})
    def _login_error(self,status,message,*,cooldown=False):
        self._reply(status,_access_page(message=message).encode(),content_type='text/html; charset=utf-8',
                    headers={'Retry-After':'60'}if cooldown else None)
    def _trusted(self):
        hosts=self.headers.get_all('Host',[]);origins=self.headers.get_all('Origin',[])
        return (len(hosts)==1 and hosts[0]==self.server.public_host
            and (not origins or len(origins)==1 and origins[0]==self.server.public_origin)
            and self.headers.get('Sec-Fetch-Site')!='cross-site')

    def _token(self):
        values=self.headers.get_all('Cookie',[])
        if len(values)>1 or values and len(values[0])>4096:return None
        try:
            parsed=SimpleCookie();parsed.load(values[0]if values else'');token=parsed[COOKIE].value if COOKIE in parsed else None
            return token if type(token)is str and _TOKEN.fullmatch(token)else None
        except Exception:return None

    def _cookie(self,token,*,clear=False):
        value=f'{COOKIE}={token}; Path=/; Max-Age={0 if clear else SESSION_SECONDS}; HttpOnly; SameSite=Strict'
        if self.server.secure_cookie:value+='; Secure'
        return value

    def _body(self):
        lengths=self.headers.get_all('Content-Length',[])
        if self.headers.get_all('Transfer-Encoding')or len(lengths)!=1 or not re.fullmatch(r'[0-9]{1,10}',lengths[0]):
            self._error(400,'One bounded Content-Length is required.');return None
        length=int(lengths[0])
        if length>MAX_BODY:self._error(413,'Preview request exceeds the local limit.');return None
        raw=self.rfile.read(length)
        if len(raw)!=length:self._error(400,'Incomplete request.');return None
        return raw

    def do_GET(self):self._dispatch('GET')
    def do_POST(self):self._dispatch('POST')
    def _dispatch(self,method):
        if not self._trusted():self._error(403,'Configured preview origin only.');return
        p=urlsplit(self.path)
        if p.scheme or p.netloc or p.query or p.fragment or not p.path.startswith('/')or '/..'in p.path or '\\'in p.path:
            self._error(400,'Plain local paths without query parameters are required.');return
        path=p.path
        if path.startswith('/internal')or path.startswith('/api/internal'):
            self._error(404,'Preview resource not found.');return
        if path=='/preview/style.css'and method=='GET':
            self._reply(200,web_assets().joinpath('preview.css').read_bytes(),content_type='text/css; charset=utf-8');return
        body=self._body()if method=='POST'else None
        if method=='POST'and body is None:return
        if path=='/preview/login'and method=='POST':
            if self.headers.get_all('Origin',[])!=[self.server.public_origin]:self._error(403,'Same-origin login required.');return
            if self.headers.get('Content-Type','').split(';')[0]!='application/x-www-form-urlencoded'or len(body)>1024:
                self._error(400,'Use the private reviewer login form.');return
            try:
                values=parse_qs(body.decode('ascii'),strict_parsing=True,max_num_fields=1)
                code=values['code'][0]
                if set(values)!={'code'}or len(values['code'])!=1 or not _TOKEN.fullmatch(code):raise ValueError()
            except (ValueError,KeyError,UnicodeError):self._login_error(401,'That invite code was not accepted. Check the full code or ask the host for access.');return
            token,limited=self.server.authenticate(code)
            if limited:self._login_error(429,'Too many sign-in attempts. Wait one minute before trying again.',cooldown=True);return
            if not token:self._login_error(401,'That invite code was not accepted. Check the full code or ask the host for access.');return
            self._reply(303,b'',headers={'Set-Cookie':self._cookie(token),'Location':'/'});return
        token=self._token();identity=self.server.user(token,include_generation=True)
        if not identity:
            if path=='/'and method=='GET':self._reply(200,_LOGIN.encode(),content_type='text/html; charset=utf-8')
            else:self._error(401,'A private reviewer session is required.')
            return
        user,generation,expires=identity
        if not self.server.allow_request(user):
            self._reply(429,{'error':'Preview request cooldown.'},headers={'Retry-After':'60'});return
        if path=='/preview'and method=='GET':self._reply(200,_ACCOUNT.encode(),content_type='text/html; charset=utf-8');return
        if path=='/preview/logout'and method=='POST':
            if self.headers.get_all('Origin',[])!=[self.server.public_origin]:self._error(403,'Same-origin sign-out required.');return
            self.server.revoke(token);self._reply(303,b'',headers={'Set-Cookie':self._cookie('',clear=True),'Location':'/'});return
        if path.startswith('/preview'):
            self._error(404,'Preview resource not found.');return
        if method=='POST'and path in ('/api/product/access','/api/product/author-access'):
            # Carry the authenticated generation to the backend's local commit
            # boundary. A gateway timeout must not release that boundary early.
            self._forward(user,method,path,body,credential_context=f'{generation}:{expires}')
            return
        self._forward(user,method,path,body)

    def _forward(self,user,method,path,body,*,credential_context=None):
        # The invite, never path/headers/body, determines the owned upstream.
        backend=self.server.backends[user];host=f'127.0.0.1:{backend.server_address[1]}'
        headers={'Host':host,'Origin':'http://'+host,'Sec-Fetch-Site':'same-origin'}
        if credential_context is not None:headers[CREDENTIAL_CONTEXT]=credential_context
        for name in ('Accept','Content-Type','X-CSRF-Token'):
            values=self.headers.get_all(name,[])
            if len(values)>1:self._error(400,'Duplicate forwarding headers are not accepted.');return
            if values:headers[name]=values[0]
        connection=http.client.HTTPConnection('127.0.0.1',backend.server_address[1],timeout=UPSTREAM_TIMEOUT)
        try:
            connection.request(method,path,body=body,headers=headers)
            response=connection.getresponse();raw=response.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:raise ValueError('upstream response budget exceeded')
            safe={}
            for name in ('Content-Disposition','Retry-After'):
                value=response.getheader(name)
                if value and len(value)<1024 and '\r'not in value and '\n'not in value:safe[name]=value
            self._reply(response.status,raw,content_type=response.getheader('Content-Type','application/json; charset=utf-8'),headers=safe)
        except (OSError,ValueError,http.client.HTTPException):self._error(502,'The assigned local workspace is unavailable. No automatic retry was made.')
        finally:connection.close()


def create_preview_server(*,port=8770,public_origin,invites,output_dir,backend_factory=None):
    if type(port)is not int or not 0<=port<=65535:raise ValueError('bounded loopback port required')
    return PreviewServer(('127.0.0.1',port),public_origin=public_origin,invites=invites,output_dir=output_dir,backend_factory=backend_factory)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Private, isolated preview for at most three reviewers. No public SaaS or billing claim.')
    commands=parser.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init');init.add_argument('--output-dir',required=True);init.add_argument('--public-origin',required=True);init.add_argument('--users',type=int,default=3)
    serve_options=argparse.ArgumentParser(add_help=False)
    serve=serve_options
    serve.add_argument('--config',required=True);serve.add_argument('--port',type=int,default=8770);serve.add_argument('--output-dir')
    serve.add_argument('--public-archive',help='Explicit read-only public observation archive path')
    serve.add_argument('--typesafe-model',default='jev-latest');serve.add_argument('--typesafe-env-file');serve.add_argument('--typesafe-api-key-env');serve.add_argument('--typesafe-http-client',choices=('urllib','curl'),default='curl')
    from .cloud_configuration import add_cloud_arguments
    add_cloud_arguments(serve)
    serve.add_argument('--enable-gemini',action='store_true');serve.add_argument('--gemini-model',default='gemini-3.8-flash-high');serve.add_argument('--model-timeout',type=int,default=180)
    serve.add_argument('--near-registry-contract');serve.add_argument('--near-registry-code-hash');serve.add_argument('--near-relayer-credential-file');serve.add_argument('--near-relayer-script')
    serve.add_argument('--operator-jev-call-budget',type=int,default=200,help='Persistent native Jev call allowance per reviewer; not a dollar or token spending cap')
    serve.add_argument('--operator-author-call-budget',type=int,default=200,help='Persistent allowance for operator-funded text generation per reviewer, covering the author route and Gemini decisions')
    commands.add_parser('serve',parents=[serve_options])
    commands.add_parser('check',parents=[serve_options],help='Validate isolated configuration and assets; no provider or chain requests')
    args=parser.parse_args(argv)
    server=None
    try:
        if args.command=='init':
            config,codes=initialize_preview(args.output_dir,public_origin=args.public_origin,users=args.users)
            print(f'Private configuration: {config}\nPrivate reviewer codes: {codes}\nCodes were not printed. Deliver them to invited reviewers privately.');return 0
        for allowance in (args.operator_jev_call_budget,args.operator_author_call_budget):
            if not 1<=allowance<=100000:raise ValueError('bounded operator allowance required')
        config=load_config(args.config)
        output=Path(args.output_dir)if args.output_dir else Path(args.config).parent/'users'
        near=None
        if args.near_relayer_credential_file:
            from .near_registry import NearRegistryClient,NearRegistryRelayer
            near=NearRegistryRelayer(NearRegistryClient(contract_id=args.near_registry_contract,expected_code_hash=args.near_registry_code_hash),credential_file=args.near_relayer_credential_file,output_dir=Path(args.config).parent/'testnet-relay',script_path=args.near_relayer_script)
        elif args.near_registry_contract or args.near_registry_code_hash or args.near_relayer_script:raise ValueError('explicit testnet relayer credential required')
        # Each reviewer gets a distinct application manager and provider client.
        # The operator's provider account remains shared and must be funded/limited.
        def backend_factory(name,path):
            from .web_server import create_server
            actors={};author=None;agy=None
            if args.enable_gemini:
                import shutil
                from .agent_models import AgyTextModel
                binary=shutil.which('agy')
                if not binary:raise ValueError('installed Gemini development route unavailable')
                agy=AgyTextModel(model=args.gemini_model,binary=binary,public_input=True,timeout_seconds=args.model_timeout)
            if args.typesafe_env_file:
                from .env_config import load_env_key
                from .jev import TypeSafeClient
                name=args.typesafe_api_key_env or'TYPESAFE_API_KEY'
                actors['typesafe']=TypeSafeClient(api_key=load_env_key(args.typesafe_env_file,name=name),model=args.typesafe_model,
                    http_client=args.typesafe_http_client,timeout_seconds=args.model_timeout)
                from .preview_budget import PreviewJevClient
                actors['typesafe']=PreviewJevClient(actors['typesafe'],root=path/'operator-typesafe-call-budget',call_limit=args.operator_jev_call_budget)
            elif args.typesafe_api_key_env:raise ValueError('selected file variable requires an explicit env file')
            from .cloud_configuration import configured_author
            from .preview_budget import PreviewAuthorClient
            cloud=configured_author(args)
            # Text generation the operator pays for is capped by one reviewer-scoped
            # allowance covering the author route and the Gemini decision actor, which
            # delegates to the author client it is given. Each raw client is wrapped
            # once, so a provider call reserves exactly one allowance.
            def budgeted(client):
                return PreviewAuthorClient(client,root=path/'operator-author-call-budget',
                    call_limit=args.operator_author_call_budget)
            budgeted_agy=budgeted(agy) if agy is not None else None
            if cloud is not None:author=budgeted(cloud)
            elif agy is not None:author=budgeted_agy
            if budgeted_agy is not None:
                from .gemini_decisions import GeminiDecisions
                actors['gemini']=GeminiDecisions(budgeted_agy)
            return create_server(port=0,output_dir=path,public_archive_path=args.public_archive,product_author_client=author,product_actor_clients=actors,product_near_relayer=near,hosted=True)
        server=create_preview_server(port=0 if args.command=='check'else args.port,public_origin=config['public_origin'],invites=config['invites'],output_dir=output,backend_factory=backend_factory)
        if args.command=='check':
            from .product_reports import pdf_available
            from .preview_readiness import readiness
            print(json.dumps(readiness(server,pdf_available=pdf_available()),indent=2));return 0
        print(f'Private preview listening at http://127.0.0.1:{server.server_address[1]}; configured browser origin {server.public_origin}. No inference at startup.')
        server.serve_forever();return 0
    except KeyboardInterrupt:return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
        print('Preview could not start. Check private configuration, exact origin, owned output paths and explicit provider settings. No secret diagnostics were printed.');return 2
    finally:
        if server is not None:server.server_close()


if __name__=='__main__':raise SystemExit(main())
