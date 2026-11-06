"""Loopback-only stdlib HTTP adapter for explicit product decisions and the offline lab."""
from .interface_assets import web_assets, InterfaceUnavailable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import nullcontext
from importlib.resources import files
import re
import secrets
import sqlite3
from threading import BoundedSemaphore
from urllib.parse import urlsplit

from .policy_preparation import _strict_json
from .preview_budget import PreviewAllowanceError
from .studio_api import RevisionConflict
from .web_jobs import BusyError, JobManager, MAX_BODY, _bounded_json, encode


_JOB_ROUTE = re.compile(r'/api/jobs/([0-9a-f]{32})(?:/(download|commitment|opening|near-action))?\Z')
_WORLD_ROUTE = re.compile(r'/api/studio/worlds/([0-9a-f]{32})(?:/(step|fork))?\Z')
_PRODUCT_ROUTE = re.compile(r'/api/product/sessions/([0-9a-f]{32})(?:/(say|review|run|download|cancel_author|presentation|report-md|report-pdf))?\Z')
_PRODUCT_RESULT_ROUTE = re.compile(r'/api/product/results/([0-9a-f]{32})/(run-[0-9a-f]{32})(?:/(download|presentation|report-md|report-pdf))?\Z')
_PRODUCT_NEAR_ROUTE = re.compile(r'/api/product/(?:sessions/([0-9a-f]{32})|results/([0-9a-f]{32})/(run-[0-9a-f]{32}))/near/(prepare|submit|verify|opening|wallet-prepare|wallet-attempt|wallet-verify|wallet-opening|wallet-resume)\Z')
_STATIC = {'/': ('product.html', 'text/html; charset=utf-8'),
           '/product.html': ('product.html', 'text/html; charset=utf-8'),
           '/product.js': ('product.js', 'text/javascript; charset=utf-8'),
           '/product.css': ('product.css', 'text/css; charset=utf-8'),
           '/ambient.js': ('ambient.js', 'text/javascript; charset=utf-8'),
           '/onboarding.js': ('onboarding.js', 'text/javascript; charset=utf-8'),
           '/wallet-sdk.js.LEGAL.txt': ('wallet-sdk.js.LEGAL.txt', 'text/plain; charset=utf-8'),
           '/wallet-sdk.js': ('wallet-sdk.js', 'text/javascript; charset=utf-8'),
           '/presentation.js': ('presentation.js', 'text/javascript; charset=utf-8'),
           '/docs': ('docs.html', 'text/html; charset=utf-8'),
           '/docs.html': ('docs.html', 'text/html; charset=utf-8'),
           '/lab': ('index.html', 'text/html; charset=utf-8'),
           '/index.html': ('index.html', 'text/html; charset=utf-8'),
           '/style.css': ('style.css', 'text/css; charset=utf-8'),
           '/studio.js': ('studio.js', 'text/javascript; charset=utf-8'),
           '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
           '/fonts/manrope.ttf': ('fonts/manrope.ttf', 'font/ttf'),
           '/fonts/OFL-Manrope.txt': ('fonts/OFL-Manrope.txt', 'text/plain; charset=utf-8')}


class CredentialAccessDenied(ValueError):
    """The gateway session expired before a local credential commit."""


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, address, manager, product):
        self.manager = manager
        self.product = product
        self.credential_guard = None
        self._slots = BoundedSemaphore(16)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def server_close(self):
        super().server_close()
        self.manager.close()
        self.product.close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'DecisionLabLocal'
    sys_version = ''
    protocol_version = 'HTTP/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        # URLs and inputs may be confidential; no default access/error log.
        pass

    def _reply(self, status, value, *, content_type='application/json; charset=utf-8', filename=None):
        data = value if type(value) is bytes else encode(value)
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self' https://rpc.testnet.near.org https://logout-bridge-service.intear.tech wss://logout-bridge-service.intear.tech; frame-src https://wallet.intear.tech; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, message):
        self._reply(status, {'error': message})

    def _trusted(self):
        hosts = self.headers.get_all('Host', [])
        port = self.server.server_address[1]
        allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if port == 80:
            allowed.update({'127.0.0.1', 'localhost'})
        if len(hosts) != 1 or hosts[0] not in allowed:
            return False
        origins = self.headers.get_all('Origin', [])
        if origins and (len(origins) != 1 or origins[0] != 'http://' + hosts[0]):
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return False
        return True

    def _path(self):
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            return None
        return parsed.path

    def do_GET(self):
        if not self._trusted():
            self._error(403, 'Loopback same-origin requests only.')
            return
        try:
            path = self._path()
            if path in _STATIC:
                name, content_type = _STATIC[path]
                resource = web_assets().joinpath(name)
                self._reply(200, resource.read_bytes(), content_type=content_type)
                return
            if path == '/api/studio':
                self._reply(200, self.server.manager.studio.bootstrap())
                return
            if path in {'/internal/flow','/internal/flow.js','/internal/flow.css','/api/internal/flow'}:
                if self.server.internal_flow is None:self._error(404,'Local resource not found.');return
                if path=='/api/internal/flow':self._reply(200,self.server.internal_flow.snapshot())
                else:
                    name,mime={'/internal/flow':('internal-flow.html','text/html; charset=utf-8'),'/internal/flow.js':('internal-flow.js','text/javascript; charset=utf-8'),'/internal/flow.css':('internal-flow.css','text/css; charset=utf-8')}[path]
                    self._reply(200,web_assets().joinpath(name).read_bytes(),content_type=mime)
                return
            if path == '/api/product':
                from .product_reports import pdf_available
                near=self.server.product_near.capabilities()
                if self.server.product.access_status()['mode']=='offline':near={**near,'enabled':False,'wallet_enabled':False}
                self._reply(200, {**self.server.product.bootstrap(), 'csrf_token': self.server.manager.csrf_token,
                    'near':near,'near_demo':{'available':self.server.manager._public_archive_path is not None},'internal_flow':self.server.internal_flow is not None,'reports':{'md':True,'pdf':pdf_available()}})
                return
            if path == '/api/product/typesafe/models':
                self._reply(200,self.server.product.check_typesafe_access())
                return
            if path == '/api/product/results':
                self._reply(200,self.server.product.saved_results())
                return
            near_match=_PRODUCT_NEAR_ROUTE.fullmatch(path or '')
            if near_match and near_match.group(4)=='opening':
                session,archived,run,_=near_match.groups()
                artifact=self.server.product.download_bytes(session)if session else self.server.product.saved_result_bytes(archived,run)
                self._reply(200,self.server.product_near.opening(artifact),filename='private-result-opening.json')
                return
            result_match=_PRODUCT_RESULT_ROUTE.fullmatch(path or '')
            if result_match:
                identifier,run_id,action=result_match.groups()
                if action=='download':
                    self._reply(200,self.server.product.saved_result_bytes(identifier,run_id),filename=f'{run_id}.results.json')
                elif action in ('report-md','report-pdf'):
                    fmt=action.split('-')[1];self._reply(200,self.server.product.report(identifier,fmt,run_id),content_type='application/pdf'if fmt=='pdf'else'text/markdown; charset=utf-8',filename='scenario-report.'+fmt)
                elif action=='presentation':self._reply(200,self.server.product.saved_presentation(identifier,run_id))
                else:self._reply(200,self.server.product.saved_result(identifier,run_id))
                return
            product_match = _PRODUCT_ROUTE.fullmatch(path or '')
            if product_match:
                identifier, action = product_match.groups()
                if action in ('report-md','report-pdf'):
                    fmt=action.split('-')[1];self._reply(200,self.server.product.report(identifier,fmt),content_type='application/pdf'if fmt=='pdf'else'text/markdown; charset=utf-8',filename='scenario-report.'+fmt)
                elif action == 'download':
                    self._reply(200, self.server.product.download_bytes(identifier),filename=f'{identifier}.results.json')
                elif action=='presentation':self._reply(200,self.server.product.presentation(identifier))
                elif action is not None:
                    self._error(405, 'Use POST for this operation.')
                else:
                    self._reply(200, self.server.product.snapshot(identifier))
                return
            world_match = _WORLD_ROUTE.fullmatch(path or '')
            if world_match:
                world_id, action = world_match.groups()
                if action is not None:
                    self._error(405, 'Use POST for this operation.')
                else:
                    self._reply(200, self.server.manager.studio.get_world(world_id))
                return
            if path == '/api/bootstrap':
                self._reply(200, self.server.manager.bootstrap())
                return
            if path == '/api/public-history':
                self._reply(200, self.server.manager.public_history())
                return
            if re.fullmatch(r'/api/evidence/[0-9a-f]{32}', path or ''):
                self._reply(200, self.server.manager.evidence(path.rsplit('/', 1)[1]))
                return
            match = _JOB_ROUTE.fullmatch(path or '')
            if not match:
                self._error(404, 'Local resource not found.')
                return
            job_id, action = match.groups()
            if action is None:
                self._reply(200, self.server.manager.snapshot(job_id))
            elif action == 'download':
                self._reply(200, self.server.manager.result_bytes(job_id), filename=f'{job_id}.json')
            elif action == 'opening':
                self._reply(200, self.server.manager.opening_bytes(job_id), filename=f'{job_id}.opening.json')
            else:
                self._error(405, 'Use POST for this operation.')
        except InterfaceUnavailable as error:
            self._error(503, str(error))
        except (KeyError, FileNotFoundError):
            self._error(404, 'Local resource not found.')
        except BusyError:
            self._error(429, 'Local choice session capacity reached.')
        except ValueError:
            self._error(409, 'The local artifact is not available in this job state.')
        except (OSError, TypeError, UnicodeError, RecursionError, OverflowError, sqlite3.Error):
            self._error(500, 'Local resource unavailable.')

    def do_POST(self):
        if not self._trusted():
            self._error(403, 'Loopback same-origin requests only.')
            return
        tokens = self.headers.get_all('X-CSRF-Token', [])
        if len(tokens) != 1 or not secrets.compare_digest(tokens[0].encode('utf-8'), self.server.manager.csrf_token.encode('utf-8')):
            self._error(403, 'Valid local CSRF token required.')
            return
        types = self.headers.get_all('Content-Type', [])
        if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
            self._error(415, 'Content-Type application/json required.')
            return
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not re.fullmatch(r'[0-9]+', lengths[0]) or self.headers.get_all('Transfer-Encoding'):
            self._error(400, 'One valid Content-Length required.')
            return
        decimal_length = lengths[0].lstrip('0') or '0'
        if len(decimal_length) > len(str(MAX_BODY)) or (len(decimal_length) == len(str(MAX_BODY)) and decimal_length > str(MAX_BODY)):
            self._error(413, 'Request exceeds the 2 MiB local limit.')
            return
        length = int(decimal_length)
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('incomplete body')
            data = _strict_json(raw.decode('utf-8'))
            _bounded_json(data)
            if type(data) is not dict:
                raise ValueError('JSON object required')
            path = self._path()
            if path=='/api/product/near-demo':
                if data!={}:raise ValueError('empty evidence demo request required')
                from .public_archive import PublicArchive
                from .near_demo import build_near_demo
                from .product_api import _write
                archive_path=self.server.manager._public_archive_path
                if archive_path is None:raise ValueError('public NEAR archive not configured')
                with PublicArchive(archive_path,read_only=True)as archive:
                    demo=build_near_demo(archive.export_snapshot('near',limit=1000))
                result=self.server.product.import_world(demo['world'],demo['decision_brief']['question'])
                _write(self.server.product.root/result['id'],'near-evidence.json',demo['evidence'])
                # Public source snapshot is preserved privately; the model input
                # contains only reviewed source summaries and explicit assumptions.
                result['evidence_summary']={k:v for k,v in demo['evidence'].items()if k!='snapshot'}
                self._reply(202,result);return
            if path=='/api/product/author-models':
                if data!={}:raise ValueError('empty catalog request required')
                from .agent_models import ModelFailure
                try:catalog=self.server.product.author_models()
                except ModelFailure as error:
                    self._reply(200,{'status':'failed','error':error.code,'details':error.safe_details()if callable(getattr(error,'safe_details',None))else None});return
                self._reply(200,catalog);return
            if path=='/api/product/author-access':
                with self.server.credential_guard(self.headers)if self.server.credential_guard else nullcontext():
                    result=self.server.product.configure_author(data)
                self._reply(200,result);return
            if path=='/api/product/access':
                with self.server.credential_guard(self.headers)if self.server.credential_guard else nullcontext():
                    result=self.server.product.configure_access(data)
                self._reply(200,result);return
            if path=='/api/internal/flow':
                if self.server.internal_flow is None:self._error(404,'Local resource not found.');return
                self._reply(200,self.server.internal_flow.update(data));return
            near_match=_PRODUCT_NEAR_ROUTE.fullmatch(path or '')
            if near_match:
                if self.server.product.access_status()['mode']=='offline':raise ValueError('NEAR network operations disabled in offline mode')
                session,archived,run,action=near_match.groups()
                if action=='opening':raise ValueError('opening export requires private download route')
                artifact=self.server.product.download_bytes(session)if session else self.server.product.saved_result_bytes(archived,run)
                if action=='wallet-prepare':result=self.server.product_near.wallet_prepare(artifact,data)
                elif action=='wallet-resume':result=self.server.product_near.wallet_resume(artifact,data)
                elif action=='wallet-attempt':result=self.server.product_near.wallet_attempt(artifact,data)
                elif action=='wallet-verify':result=self.server.product_near.wallet_verify(artifact,data)
                elif action=='wallet-opening':
                    if set(data)!={'plan_id'}:raise ValueError('exact wallet opening request required')
                    result=self.server.product_near.wallet_opening(artifact,data['plan_id'])
                elif action=='prepare':
                    if data:raise ValueError('prepare takes an empty object')
                    result=self.server.product_near.prepare(artifact)
                elif action=='verify':
                    if data:raise ValueError('verify takes an empty object')
                    result=self.server.product_near.verify(artifact)
                else:result=self.server.product_near.submit(artifact,data)
                self._reply(200,result)
                return
            if path == '/api/product/sessions':
                self._reply(202, self.server.product.create(data))
                return
            product_match = _PRODUCT_ROUTE.fullmatch(path or '')
            if product_match:
                identifier, action = product_match.groups()
                if action not in {'say', 'review', 'run','cancel_author'}:
                    self._error(405, 'Operation does not accept POST.')
                else:
                    result = getattr(self.server.product, action)(identifier, data)
                    self._reply(200 if action == 'review' else 202, result)
                return
            if path in {'/api/studio/validate', '/api/studio/prepare', '/api/studio/apply'}:
                self._reply(200, self.server.manager.studio.author(path.rsplit('/', 1)[1], data))
                return
            if path == '/api/studio/worlds':
                self._reply(201, self.server.manager.studio.create_world(data))
                return
            if path == '/api/studio/restore':
                self._reply(201, self.server.manager.studio.restore_world(data))
                return
            world_match = _WORLD_ROUTE.fullmatch(path or '')
            if world_match:
                world_id, action = world_match.groups()
                if action not in {'step', 'fork'}:
                    self._error(405, 'Operation does not accept POST.')
                else:
                    self._reply(201 if action == 'fork' else 200, self.server.manager.studio.mutate_world(world_id, action, data))
                return
            if path == '/api/jobs':
                self._reply(202, self.server.manager.submit(data))
                return
            match = _JOB_ROUTE.fullmatch(path or '')
            if not match:
                self._error(404, 'Local resource not found.')
                return
            job_id, action = match.groups()
            if action == 'commitment':
                if data:
                    raise ValueError('commitment takes an empty object')
                self._reply(200, self.server.manager.commitment(job_id))
            elif action == 'near-action':
                self._reply(200, self.server.manager.near_action(job_id, data))
            else:
                self._error(405, 'Operation does not accept POST.')
        except PreviewAllowanceError as error:
            self._reply(409,{'error':error.safe_details()['message'],'details':error.safe_details()})
        except RevisionConflict:
            self._error(409, 'The saved world revision changed; reload it before choosing again.')
        except FileNotFoundError:
            self._error(404, 'Local resource not found.')
        except BusyError:
            self._error(429, 'Local job capacity reached; wait for queued jobs or restart this session.')
        except KeyError:
            self._error(404, 'Local resource or required field not found.')
        except CredentialAccessDenied:
            self._error(401, 'A current private reviewer session is required.')
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            self._error(400, 'Invalid input or workbench workload limit exceeded; check the supplied fields.')
        except OSError:
            self._error(500, 'Local artifact could not be saved.')


def create_server(*, host='127.0.0.1', port=8769, output_dir=None,
                  policy_bundle_path=None, policy_evidence_path=None,
                  wallet_observation_paths=(), topic_observation_paths=(), public_archive_path=None,
                  product_author_client=None, product_actor_clients=None, product_route_status=None,product_near_relayer=None,enable_internal_map=False,hosted=False,container_bind=False):
    """Construct a server. Caller owns serve_forever/shutdown/server_close.

    container_bind only widens the socket, never the trust boundary: a container
    cannot answer a published port while bound to its own loopback, and requests
    still have to present a loopback Host header to reach any route.
    """
    if host != '127.0.0.1' or type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('only 127.0.0.1 and a valid local port are supported')
    if container_bind not in (True, False):
        raise ValueError('container bind is a flag, not an address')
    bind_host = '0.0.0.0' if container_bind else host
    manager = JobManager(output_dir, policy_bundle_path=policy_bundle_path, policy_evidence_path=policy_evidence_path,
                         wallet_observation_paths=wallet_observation_paths, topic_observation_paths=topic_observation_paths,
                         public_archive_path=public_archive_path)
    try:
        from .product_api import ProductManager
        product = ProductManager(manager.output_dir/'product',
            author_client=product_author_client, actor_clients=product_actor_clients, route_status=product_route_status,hosted=hosted)
        try:
            from .product_near import ProductNear
            near=ProductNear(manager.output_dir/'near-result-anchors',product_near_relayer)
            server=LocalServer((bind_host, port), manager, product)
            server.product_near=near
            from .internal_flow import InternalFlow
            server.internal_flow=InternalFlow()if enable_internal_map else None
            return server
        except BaseException:
            product.close()
            raise
    except BaseException:
        manager.close()
        raise


def serve(host='127.0.0.1', port=8769, output_dir=None, policy_bundle_path=None, policy_evidence_path=None):
    server = create_server(host=host, port=port, output_dir=output_dir,
        policy_bundle_path=policy_bundle_path, policy_evidence_path=policy_evidence_path)
    try:
        server.serve_forever()
    finally:
        server.server_close()
