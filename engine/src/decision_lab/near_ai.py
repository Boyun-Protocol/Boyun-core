"""Pinned, single-request NEAR AI Cloud world author.

Keys are supplied in memory by the caller. Construction performs no discovery,
quota check or inference. The plain HTTPS route does not verify confidential
inference, attestation, model identity, usage or billing. Injected transports use
the NativeTextModel bytes contract and must enforce the same bounded direct,
no-redirect/no-retry behavior as the default transport.
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from .agent_models import ModelFailure, _messages, _receipt, parse_object
from .agent_worlds import _int, canonical
from .providers import _NoRedirect, _openai_response, _parse_json, _urllib_transport


ENDPOINT = 'https://cloud-api.near.ai/v1/chat/completions'
MODELS_ENDPOINT = 'https://cloud-api.near.ai/v1/models'
MAX_REPLY = 1024 * 1024
MAX_RETRY_AFTER_SECONDS = 86400
CAPABILITIES = {'chat', 'reasoning', 'streaming', 'structured_outputs', 'tool_calling',
                'tools', 'json_mode', 'json_schema', 'vision', 'embeddings'}
PRICE_FIELDS = {'input', 'output', 'prompt', 'completion', 'input_cost_per_token',
                'output_cost_per_token', 'input_per_million_tokens', 'output_per_million_tokens'}

ERROR_MESSAGES = {
    400: 'NEAR AI Cloud rejected the request. Check the selected model and structured-output support.',
    401: 'NEAR AI Cloud rejected the API key. Check the selected session key and account.',
    402: 'NEAR AI Cloud requires available credits. Check the Cloud account before explicitly retrying.',
    403: 'NEAR AI Cloud denied access. Check account access and the selected model.',
    404: 'NEAR AI Cloud did not find the selected model or operation.',
    429: 'NEAR AI Cloud rate limited the request. Wait before explicitly retrying.',
}


def _retry_after(value):
    """Retain only a bounded delay, never arbitrary provider header content."""
    if type(value) is not str or len(value) > 128:
        return None
    try:
        text = value.strip()
        if text.isascii() and text.isdecimal():
            return min(int(text), MAX_RETRY_AFTER_SECONDS)
        date = parsedate_to_datetime(text)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        delay = math.ceil(date.timestamp() - datetime.now(timezone.utc).timestamp())
        return min(MAX_RETRY_AFTER_SECONDS, max(0, delay))
    except (ValueError, OverflowError, TypeError):
        return None


class NearAIError(ModelFailure):
    """Public HTTP failure without provider bodies, secrets or automatic retry."""

    def __init__(self, status, *, retry_after_seconds=None):
        self.status = status
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f'near_ai_http_{status}', 'response_received')

    def safe_details(self):
        message = ERROR_MESSAGES.get(self.status,
            'NEAR AI Cloud request failed. No automatic retry was performed.')
        if 500 <= self.status <= 599:
            message = 'NEAR AI Cloud could not complete the request. Check account usage before explicitly retrying.'
        details = {'http_status': self.status, 'message': message,
                   'remote_outcome': self.remote_outcome, 'automatic_retry': False}
        if self.retry_after_seconds is not None:
            details['retry_after_seconds'] = self.retry_after_seconds
        return details


def _model_id(model):
    # Canonical catalog IDs are namespaced. Refuse shorthand routing selectors
    # and moving latest aliases; the server must also honor x-no-aliasing.
    if (type(model) is not str or len(model) > 160
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*', model)
            or any(part.lower() in {'auto', 'default', 'latest'}
                   for part in re.split(r'[/._-]', model))):
        raise ValueError('explicit canonical NEAR AI model ID required')


def _reflects_key(value, key):
    if type(value) is str:
        return key in value
    if type(value) is dict:
        return any(_reflects_key(name, key) or _reflects_key(item, key)
                   for name, item in value.items())
    if type(value) is list:
        return any(_reflects_key(item, key) for item in value)
    return False


def _catalog_transport(*, endpoint, headers, method, body, timeout_seconds, max_response_bytes):
    if endpoint != MODELS_ENDPOINT or method != 'GET' or body is not None:
        raise ValueError('pinned read-only model catalog required')
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    with opener.open(Request(endpoint, headers=headers, method='GET'),
                     timeout=timeout_seconds) as reply:
        if reply.status != 200:
            raise ValueError('unexpected catalog status')
        raw = reply.read(max_response_bytes + 1)
        if len(raw) > max_response_bytes:
            raise ValueError('catalog response exceeds byte limit')
        return raw


def _catalog_models(parsed):
    entries = parsed.get('data')
    if type(entries) is not list or not 1 <= len(entries) <= 500:
        raise ValueError('bounded catalog model list required')
    models, seen = [], set()
    for entry in entries:
        if type(entry) is not dict:
            raise ValueError('catalog object required')
        identifier = entry.get('id')
        _model_id(identifier)
        if identifier in seen:
            raise ValueError('duplicate catalog model')
        seen.add(identifier)
        item = {'id': identifier}
        if 'capabilities' in entry:
            capabilities = entry['capabilities']
            if type(capabilities) is not dict:
                raise ValueError('catalog capability map required')
            selected = {name: value for name, value in capabilities.items() if name in CAPABILITIES}
            if any(type(value) is not bool for value in selected.values()):
                raise ValueError('boolean model capability required')
            item['capabilities'] = selected
        if 'supported_features' in entry:
            features=entry['supported_features']
            if type(features)is not list or len(features)>64 or any(type(f)is not str or len(f)>80 for f in features):
                raise ValueError('bounded model features required')
            item.setdefault('capabilities',{}).update({name:True for name in features if name in CAPABILITIES})
        if 'is_ready' in entry:
            if type(entry['is_ready'])is not bool:raise ValueError('boolean readiness required')
            item['is_ready']=entry['is_ready']
        if 'max_output_length' in entry:
            _int(entry['max_output_length'],1,10**9)
            item['max_output_tokens']=entry['max_output_length']
        if 'pricing' in entry:
            pricing = entry['pricing']
            if type(pricing) is not dict:
                raise ValueError('catalog price map required')
            selected = {name: value for name, value in pricing.items() if name in PRICE_FIELDS}
            for price in selected.values():
                if type(price) in (int, float):
                    if not math.isfinite(price) or not 0 <= price <= 10**9:
                        raise ValueError('bounded catalog price required')
                elif (type(price) is not str or len(price) > 64
                        or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?', price)
                        or not math.isfinite(float(price)) or not 0 <= float(price) <= 10**9):
                    raise ValueError('bounded numeric catalog price required')
            item['pricing'] = selected
        for field in ('context_length', 'max_output_tokens'):
            if field in entry:
                _int(entry[field], 1, 10**9)
                item[field] = entry[field]
        models.append(item)
    return models


class NearAITextModel:
    provider = 'near_ai'
    public_only = False
    protocol = 'openai'
    endpoint = ENDPOINT

    def __init__(self, *, model, api_key, timeout_seconds=180,
                 max_output_tokens=8192, transport=None, catalog_transport=None):
        _model_id(model)
        _int(timeout_seconds, 1, 300)
        _int(max_output_tokens, 1, 16384)
        if (type(api_key) is not str or not api_key or len(api_key) > 4096
                or any(ord(char) <= 32 or ord(char) >= 127 for char in api_key)):
            raise ValueError('explicit printable NEAR AI Cloud key required')
        if any(value is not None and not callable(value) for value in (transport, catalog_transport)):
            raise ValueError('invalid transport')
        self.model = model
        self.api_key = api_key
        self.timeout = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.transport = transport or _urllib_transport
        self.catalog_transport = catalog_transport or _catalog_transport

    def _request(self, transport, **kwargs):
        try:
            return transport(**kwargs)
        except HTTPError as error:
            try:
                status = error.code if type(error.code) is int and 100 <= error.code <= 599 else 500
                delay = _retry_after(error.headers.get('Retry-After')) if error.headers else None
                raise NearAIError(status, retry_after_seconds=delay) from None
            finally:
                error.close()
        except Exception:
            raise ModelFailure('near_ai_transport', 'unknown') from None

    def get_models(self):
        """Explicit metadata GET; never called by author import or generation.

        Catalog fields are provider-reported, not attestation or a billing
        guarantee. Unknown prose/fields are omitted. Numeric prices retain their
        original field names and units; no inference dollar cost is calculated.
        """
        raw = self._request(self.catalog_transport, endpoint=MODELS_ENDPOINT,
            headers={'Authorization': 'Bearer ' + self.api_key, 'Accept': 'application/json'},
            method='GET', body=None, timeout_seconds=self.timeout, max_response_bytes=MAX_REPLY)
        try:
            if type(raw) is not bytes or len(raw) > MAX_REPLY:
                raise ValueError('bounded catalog bytes required')
            parsed = _parse_json(raw)
            if _reflects_key(parsed, self.api_key):
                raise ValueError('credential reflection')
            return {'models': _catalog_models(parsed), 'source': MODELS_ENDPOINT,
                    'metadata_status': 'provider_reported_unverified',
                    'cost_usd': None, 'model_requests': 0, 'catalog_only': True,
                    'inference_requested': False}
        except Exception:
            raise ModelFailure('near_ai_invalid_catalog', 'response_received') from None

    def generate(self, messages):
        _messages(messages)
        payload = {'model': self.model, 'messages': messages,
                   'max_tokens': self.max_output_tokens, 'stream': False,
                   'response_format': {'type': 'json_object'}}
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
                   'Authorization': 'Bearer ' + self.api_key, 'x-no-aliasing': 'true'}
        started = time.monotonic()
        raw = self._request(self.transport, endpoint=ENDPOINT, headers=headers,
            body=canonical(payload), timeout_seconds=self.timeout, max_response_bytes=MAX_REPLY)
        try:
            if type(raw) is not bytes or len(raw) > MAX_REPLY:
                raise ValueError('bounded response bytes required')
            parsed = _parse_json(raw)
            # Refuse provider reflections before any output or metadata can enter
            # a receipt/export. Error bodies are never read at all.
            if _reflects_key(parsed, self.api_key):
                raise ValueError('credential reflection')
            if parsed.get('model') != self.model:
                raise ModelFailure('near_ai_model_mismatch', 'response_received')
            text, usage, _ = _openai_response(parsed)
            if text.strip().startswith('```'):
                raise ValueError('strict JSON object required')
            value = parse_object(text)
            if _reflects_key(value, self.api_key):
                raise ValueError('credential reflection')
            if usage is not None:
                for count in usage.values():
                    _int(count, 0, 10**9)
                total = parsed['usage'].get('total_tokens')
                if total is not None:
                    _int(total, 0, 10**9)
                    if total != usage['input_tokens'] + usage['output_tokens']:
                        raise ValueError('inconsistent usage')
                    usage['total_tokens'] = total
            request_id = parsed.get('id')
            if request_id is not None and (type(request_id) is not str
                    or not re.fullmatch(r'[A-Za-z0-9._:-]{1,200}', request_id)):
                raise ValueError('bounded request ID required')
            receipt = _receipt(self.model, 'near_ai_cloud_http', payload, raw,
                               text, usage, time.monotonic() - started)
            receipt.update(provider=self.provider, model_reported=parsed['model'],
                           request_id=request_id, privacy_status='UNVERIFIED',
                           requested_max_output_tokens=self.max_output_tokens)
            receipt['limitations'] += (
                ' Privacy is UNVERIFIED: this plaintext HTTPS adapter performs no '
                'attestation, response-signature verification or client encryption. '
                'The application host and provider receive the prompt. '
                'Model matching checks provider declarations only. No automatic retry.')
            return {'value': value, 'receipt': receipt}
        except ModelFailure:
            raise
        except Exception:
            raise ModelFailure('near_ai_invalid_response', 'response_received') from None
