import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from decision_lab.laya_server import make_server, MODEL
from decision_lab.laya_http_client import LayaHTTPClient


class Client:
    def evaluate(self, *, state, questions):
        return {'answers': {'q': {'type':'noul', 'noul':0.3}},
                'receipt': {'usage': {'input_tokens':4, 'output_tokens':0}}}


def test_systemone_endpoint_has_jev_wire_shape_and_rejects_other_models():
    server = make_server(Client())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = 'http://127.0.0.1:%d/v1/systemone' % server.server_port
    request = {'model':MODEL, 'state':'test', 'questions':{'q':{'type':'noul', 'instructions':'test'}}}
    def post():
        return urlopen(Request(url, data=json.dumps(request).encode(), headers={'Content-Type':'application/json'}))
    try:
        with post() as response:
            data = json.load(response)
        assert set(data) == {'model', 'answers', 'usage'}
        assert data['model'] == MODEL and data['answers']['q']['noul'] == 0.3
        client = LayaHTTPClient(endpoint=url)
        decision = client.evaluate(state='test', questions=request['questions'])
        assert decision['answers']['q']['noul'] == 0.3
        assert decision['receipt']['transport'] == 'laya-http-systemone'
        request['model'] = 'jev-1.14.0'
        with pytest.raises(HTTPError) as error:
            post()
        assert error.value.code == 422
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
