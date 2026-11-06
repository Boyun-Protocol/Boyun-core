"""Native Laya decision adapter. Actor state must fit without truncation."""
import json
import math
import time

from .agent_models import ModelFailure, _receipt
from .agent_worlds import canonical
from .jev import validate_answers, validate_request


class LayaChoiceClient:
    def __init__(self, model, timeout_seconds=180, agent=None):
        if model != 'convaiinnovations/laya-typed-decisions':
            raise ValueError('Use the fine-tuned Laya typed-decisions checkpoint')
        self.model = model
        self.endpoint = 'local-process'
        self.protocol = 'laya-native-local'
        self.timeout = timeout_seconds  # local inference is synchronous; no timeout guarantee
        if agent is None:
            import laya
            agent = laya.load(model, device='cpu', revision='reviewed')
        self.agent = agent

    def _check_input(self, state, questions):
        from laya.common import build_sequence, render_options
        agent = self.agent
        tok = agent.tok
        max_len = agent.cfg.get('max_len', 512)
        head_len = agent.cfg.get('head_max_len', 192)
        for question in questions.values():
            q = agent._to_internal(question)
            instruction = '%s question: %s' % (q['t'], q['ins'].replace(tok.mask_token, ' '))
            ins_ids = tok(instruction, add_special_tokens=False)['input_ids']
            options = [tok(' ' + x.replace(tok.mask_token, ' '), add_special_tokens=False)['input_ids']
                       for x in render_options(q)]
            if any(len(option) > 48 for option in options):
                raise ValueError('Laya would truncate an option')
            option_budget = head_len - sum(len(option) + 1 for option in options)
            if option_budget < 16 or len(ins_ids) > max(8, option_budget):
                raise ValueError('Laya would truncate the question')
            _, _, stats, truncation = build_sequence(tok, state, q, max_len, head_len,
                                                       return_stats=True, return_truncation_stats=True)
            if truncation['truncated'] or stats['options_distinct'] != stats['options']:
                raise ValueError('Laya would truncate state or collapse options')

    def evaluate(self, *, state, questions):
        validate_request(state=state, questions=questions, model='jev-latest')
        request = {'state': state, 'questions': questions}
        start = time.monotonic()
        try:
            self._check_input(state, questions)
            result = self.agent.system_one(state, questions)
            usage = result['usage']
            if usage.get('truncated') or usage.get('options'):
                raise ValueError('Laya reported incomplete input')
            answers = {}
            for name, q in questions.items():
                raw_answer = result['answers'][name]
                keys = ('type', 'noul') if q['type'] == 'noul' else ('type', 'choice', 'confidence', 'probabilities')
                answers[name] = {key: raw_answer[key] for key in keys}
                if q['type'] == 'choice':
                    probabilities = answers[name]['probabilities']
                    total = math.fsum(probabilities.values())
                    # Laya rounds outputs to four decimals. Correct only rounding drift.
                    if 0 < abs(total - 1) <= 0.001:
                        answers[name]['probabilities'] = {k: v / total for k, v in probabilities.items()}
            answers = validate_answers(answers, questions)
        except Exception as error:
            raise ModelFailure('laya_incomplete_input_or_invalid_response', 'local_only') from error
        raw = canonical(result)
        receipt = _receipt(self.model, self.protocol, request, raw, json.dumps(answers, sort_keys=True),
                           usage, time.monotonic() - start)
        receipt.update(cost_usd=0, usage_status='local_inference_no_api_fee',
                       limitations='Laya rounds scores; distributions may be normalized to correct rounding drift. Scores are not validated market odds; Laya has not been calibrated against Boyun or Jev. Local inference has no enforced timeout.')
        return {'answers': answers, 'receipt': receipt}
