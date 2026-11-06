"""Local Ollama structured-choice backend for the existing actor menu."""
import json
import time
from urllib.request import Request, build_opener, ProxyHandler

from .agent_models import ModelFailure, _receipt, parse_object
from .agent_worlds import canonical
from .jev import validate_answers, validate_request


class LocalChoiceClient:
    def __init__(self, model, timeout_seconds=300, transport=None):
        self.model = model
        self.endpoint = 'http://127.0.0.1:11434/api/chat'
        self.protocol = 'ollama-local-structured-choice'
        self.timeout = timeout_seconds
        self.transport = transport or self._send

    def _send(self, payload):
        request = Request(self.endpoint, data=canonical(payload),
                          headers={'Content-Type': 'application/json'}, method='POST')
        with build_opener(ProxyHandler({})).open(request, timeout=self.timeout) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Local model response exceeds byte limit')
        return raw

    def evaluate(self, *, state, questions):
        validate_request(state=state, questions=questions, model='jev-latest')
        instruction = ('Return only JSON with an answers object. Answer every named question. '
                       'For choice return type, choice, confidence, probabilities; probabilities '
                       'must cover every criterion, sum to 1, and choice must be a maximum. '
                       'For noul return type and noul between 0 and 1. Scores are subjective '
                       'decision scores, not real-world event probabilities.')
        payload = {'model': self.model, 'stream': False, 'think': False, 'format': 'json',
                   'messages': [{'role': 'system', 'content': instruction},
                                {'role': 'user', 'content': json.dumps({'state': state, 'questions': questions})}],
                   'options': {'temperature': 0, 'num_predict': 2048}}
        start = time.monotonic()
        try:
            raw = self.transport(payload)
            response = json.loads(raw)
            text = response['message']['content']
            answers = validate_answers(parse_object(text)['answers'], questions)
        except Exception as error:
            raise ModelFailure('local_choice_invalid_or_unavailable', 'local_only') from error
        usage = {'input_tokens': response.get('prompt_eval_count'), 'output_tokens': response.get('eval_count')}
        receipt = _receipt(self.model, self.protocol, payload, raw, text, usage, time.monotonic() - start)
        receipt.update(cost_usd=0, usage_status='local_inference_no_api_fee',
                       limitations='Local model scores are uncalibrated; model quality and electricity cost are not established.')
        return {'answers': answers, 'receipt': receipt}
