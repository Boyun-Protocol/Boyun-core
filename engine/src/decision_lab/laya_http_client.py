"""Local HTTP client with the same evaluate contract as TypeSafeClient."""
import json
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from .agent_models import ModelFailure, _receipt
from .agent_worlds import canonical
from .jev import MAX_REPLY, validate_answers, validate_request
from .laya_server import MODEL


class LayaHTTPClient:
    def __init__(self, endpoint='http://127.0.0.1:8765/v1/systemone', timeout_seconds=180):
        url = urlsplit(endpoint)
        if (url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path != '/v1/systemone'
                or url.username or url.password or url.query or url.fragment or not url.port):
            raise ValueError('Laya endpoint must be an explicit IPv4 loopback /v1/systemone URL')
        self.endpoint, self.timeout = endpoint, timeout_seconds
        self.model, self.protocol = MODEL, 'laya-http-systemone'

    def evaluate(self, *, state, questions):
        validate_request(state=state, questions=questions, model='jev-latest')
        payload = {'model':self.model, 'state':state, 'questions':questions}
        request = Request(self.endpoint, data=canonical(payload), method='POST',
                          headers={'Content-Type':'application/json'})
        started = time.monotonic()
        try:
            with build_opener(ProxyHandler({})).open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_REPLY + 1)
            if len(raw) > MAX_REPLY:
                raise ValueError('response too large')
            data = json.loads(raw)
            if set(data) != {'model','answers','usage'} or data['model'] != self.model:
                raise ValueError('unexpected response shape or model')
            answers = validate_answers(data['answers'], questions)
            usage = data['usage']
            if set(usage) != {'input_tokens','output_tokens'} or any(type(v) is not int or v < 0 for v in usage.values()):
                raise ValueError('invalid usage')
        except Exception as error:
            raise ModelFailure('laya_http_invalid_or_unavailable', 'local_only') from error
        receipt = _receipt(self.model, self.protocol, payload, raw, canonical(answers).decode(), usage, time.monotonic()-started)
        receipt.update(cost_usd=0, usage_status='local_inference_no_api_fee',
                       limitations='Local decision scores are not calibrated market odds. Endpoint requires an input-truncation-checking server.')
        return {'answers':answers, 'receipt':receipt}
