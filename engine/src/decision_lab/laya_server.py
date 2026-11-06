"""Loopback-only Jev wire-compatible endpoint backed by the native Laya adapter."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

from .agent_models import ModelFailure
from .jev import MAX_REQUEST_BYTES, validate_request
from .laya_choices import LayaChoiceClient

MODEL = 'convaiinnovations/laya-typed-decisions'


def make_server(client, port=0):
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log observations or credentials.

        def reply(self, status, body):
            content = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_POST(self):
            if self.path != '/v1/systemone':
                return self.reply(404, {'error':'unknown endpoint'})
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if length < 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError('invalid request length')
                data = json.loads(self.rfile.read(length))
                if type(data) is not dict or set(data) != {'model', 'state', 'questions'} or data['model'] != MODEL:
                    raise ValueError('expected Laya model, state and questions')
                validate_request(state=data['state'], questions=data['questions'], model='jev-latest')
                with lock:
                    result = client.evaluate(state=data['state'], questions=data['questions'])
                usage = result['receipt']['usage']
                self.reply(200, {'model':MODEL, 'answers':result['answers'],
                                 'usage':{'input_tokens':usage['input_tokens'], 'output_tokens':usage['output_tokens']}})
            except (ValueError, TypeError, KeyError, ModelFailure):
                self.reply(422, {'error':'Invalid or incomplete decision input; no answer returned.'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Run a local Jev-shaped Laya endpoint')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = make_server(LayaChoiceClient(MODEL), args.port)
    print('Laya ready on http://127.0.0.1:%s/v1/systemone' % server.server_port, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
