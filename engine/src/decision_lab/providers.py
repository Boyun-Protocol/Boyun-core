"""Explicit, single-request provider adapters; usage is reported, never attested.

The caller deliberately selects the full endpoint and supplies an in-memory key.
No endpoint discovery, redirects, retries, cost estimation, or simulation calls
occur here. Injected transports are trusted I/O implementations with this API::

    transport(*, endpoint, headers, body, timeout_seconds, max_response_bytes)

They return response bytes or raise an exception; they must enforce the same
no-redirect/no-retry/size/timeout contract as the default urllib transport.
"""
from hashlib import sha256
import json
import math
import re
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .policy_preparation import _digest, import_response, validate_request


MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class ProviderError(ValueError):
    """Safe public error, with no raw provider body, endpoint, or credentials.

    request_count is the number of application-level transport attempts (0 or 1).
    An attempt cannot prove model execution or billing. After a transport failure
    remote_outcome is unknown; callers must never infer zero usage or retry.
    """

    def __init__(self, code, *, request_count=0, remote_outcome="not_dispatched"):
        self.code = code
        self.request_count = request_count
        self.remote_outcome = remote_outcome
        super().__init__(f"Provider request failed ({code}); attempts={request_count}; "
                         f"remote outcome={remote_outcome}.")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_transport(*, endpoint, headers, body, timeout_seconds, max_response_bytes):
    # Explicit direct endpoint: do not inherit proxy destinations from the shell.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    req = Request(endpoint, data=body, headers=headers, method="POST")
    with opener.open(req, timeout=timeout_seconds) as reply:
        if reply.status != 200:
            raise ValueError("unexpected HTTP status")
        content = reply.read(max_response_bytes + 1)
        if len(content) > max_response_bytes:
            raise ValueError("response exceeds byte limit")
        return content


def _endpoint_origin(endpoint):
    if (type(endpoint) is not str or not endpoint or "?" in endpoint or "#" in endpoint
            or "\\" in endpoint or any(ord(c) <= 32 or ord(c) == 127 for c in endpoint)):
        raise ValueError("invalid endpoint")
    url = urlsplit(endpoint)
    host, port = url.hostname, url.port
    if (url.scheme not in {"http", "https"} or not host or not url.netloc
            or url.username is not None or url.password is not None
            or (url.scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"})
            or not re.fullmatch(r"[A-Za-z0-9.:-]+", host)):
        raise ValueError("invalid endpoint")
    host_text = f"[{host}]" if ":" in host else host
    return f"{url.scheme}://{host_text}" + (f":{port}" if port is not None else "")


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      sort_keys=True, allow_nan=False).encode("utf-8")


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite JSON number")
    return number


def _reject_constant(_):
    raise ValueError("nonfinite JSON constant")


def _parse_json(raw):
    if type(raw) is not bytes or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("invalid response bytes")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_pairs,
                       parse_constant=_reject_constant, parse_float=_finite_float)
    if type(value) is not dict or "error" in value:
        raise ValueError("invalid provider response")
    return value


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("invalid token count")
    return value


def _openai_response(value):
    choices = value.get("choices")
    if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
        raise ValueError("one completed choice required")
    choice = choices[0]
    message = choice.get("message")
    if (choice.get("finish_reason") != "stop" or type(message) is not dict
            or message.get("role") != "assistant"
            or message.get("refusal") is not None
            or message.get("tool_calls") not in (None, [])
            or message.get("function_call") is not None):
        raise ValueError("non-text or incomplete choice")
    text = message.get("content")
    if type(text) is not str or not text.strip():
        raise ValueError("nonempty text required")
    usage = value.get("usage")
    if usage is not None:
        if type(usage) is not dict:
            raise ValueError("invalid usage")
        usage = {"input_tokens": _count(usage.get("prompt_tokens")),
                 "output_tokens": _count(usage.get("completion_tokens"))}
    return text, usage, None


def _gemini_response(value):
    feedback = value.get("promptFeedback")
    if feedback is not None and (type(feedback) is not dict or feedback.get("blockReason")):
        raise ValueError("blocked prompt")
    candidates = value.get("candidates")
    if type(candidates) is not list or len(candidates) != 1 or type(candidates[0]) is not dict:
        raise ValueError("one completed candidate required")
    candidate = candidates[0]
    content = candidate.get("content")
    if (candidate.get("finishReason") != "STOP" or type(content) is not dict
            or content.get("role") != "model"):
        raise ValueError("incomplete candidate")
    safety = candidate.get("safetyRatings", [])
    if (type(safety) is not list or any(type(rating) is not dict or rating.get("blocked")
                                       for rating in safety)):
        raise ValueError("blocked candidate")
    parts = content.get("parts")
    if type(parts) is not list or not parts:
        raise ValueError("text parts required")
    texts = []
    for part in parts:
        if (type(part) is not dict or set(part) - {"text", "thought", "thoughtSignature"}
                or part.get("thought", False) is not False
                or ("thoughtSignature" in part and (type(part["thoughtSignature"]) is not str
                                                    or not part["thoughtSignature"]))
                or type(part.get("text")) is not str or not part["text"].strip()):
            raise ValueError("only nonthought text parts supported")
        texts.append(part["text"])
    usage = value.get("usageMetadata")
    thoughts = None
    if usage is not None:
        if type(usage) is not dict:
            raise ValueError("invalid usage")
        output_count = _count(usage.get("candidatesTokenCount"))
        if "thoughtsTokenCount" in usage:
            thoughts = _count(usage["thoughtsTokenCount"])
            output_count += thoughts
        usage = {"input_tokens": _count(usage.get("promptTokenCount")),
                 "output_tokens": output_count}
    return "".join(texts), usage, thoughts


def generate_response(request, pool, *, endpoint, api_key, protocol, timeout_seconds=60, transport=None):
    """Generate and validate an inert proposal with exactly one explicit request.

    Credentials belong only in headers and never enter the returned receipt.
    The response envelope contains private model output; retain it privately.
    Token limits are provider requests, not hard local spend limits. Gemini
    output usage includes separately reported thought tokens; absent thought
    counts remain unknown in the receipt. No price or billing is inferred.
    """
    try:
        if protocol not in {"openai", "gemini"}:
            raise ValueError("invalid protocol")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
            raise ValueError("invalid timeout")
        if (type(api_key) is not str or not api_key.strip()
                or any(ord(c) <= 32 or ord(c) >= 127 for c in api_key)):
            raise ValueError("invalid key")
        if transport is not None and not callable(transport):
            raise ValueError("invalid transport")
        origin = _endpoint_origin(endpoint)
        validated = validate_request(request, pool)
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if protocol == "openai":
            payload = {"model": validated["model"], "messages": validated["messages"],
                       "max_tokens": validated["max_output_tokens"]}
            headers["Authorization"] = "Bearer " + api_key
        else:
            model = validated["model"]
            model_path = model if model.startswith("models/") else "models/" + model
            if not unquote(urlsplit(endpoint).path).endswith("/" + model_path + ":generateContent"):
                raise ValueError("endpoint must identify the declared Gemini model")
            payload = {
                "systemInstruction": {"parts": [{"text": validated["messages"][0]["content"]}]},
                "contents": [{"role": "user", "parts": [{"text": validated["messages"][1]["content"]}]}],
                "generationConfig": {"maxOutputTokens": validated["max_output_tokens"]},
            }
            headers["x-goog-api-key"] = api_key
        body = _json_bytes(payload)
    except Exception:
        raise ProviderError("invalid_input") from None

    try:
        raw = (transport or _urllib_transport)(endpoint=endpoint, headers=headers, body=body,
            timeout_seconds=timeout_seconds, max_response_bytes=MAX_RESPONSE_BYTES)
    except TimeoutError:
        raise ProviderError("timeout", request_count=1, remote_outcome="unknown") from None
    except Exception:
        raise ProviderError("transport", request_count=1, remote_outcome="unknown") from None

    try:
        value = _parse_json(raw)
        text, usage, thoughts = (_openai_response(value) if protocol == "openai"
                                 else _gemini_response(value))
        envelope = {"schema_version": "policy-response.v1", "request_sha256": validated["request_sha256"],
                    "output_text": text, "usage": usage}
        # Also checks exact template coverage, policy capabilities, and token cap.
        import_response(validated, envelope, pool, bundle_id="provider-proposal")
        receipt = {
            "schema_version": "provider-transport.v1", "protocol": protocol,
            "model": validated["model"], "endpoint_origin": origin,
            "request_sha256": validated["request_sha256"],
            "prompt_sha256": _digest(validated["messages"]),
            "transport_request_sha256": sha256(body).hexdigest(),
            "provider_response_sha256": sha256(raw).hexdigest(),
            "output_sha256": sha256(text.encode("utf-8")).hexdigest(),
            "max_output_tokens": validated["max_output_tokens"],
            "usage": dict(usage) if usage is not None else None,
            "usage_status": "provider_reported_unverified" if usage is not None else "unknown",
            "thought_tokens": thoughts,
            "inference_calls_performed": 1, "cost_usd": None,
            "provenance_status": "provider_reported_unverified",
            "limitations": "One transport attempt does not attest model identity, billing, policy quality, "
                           "or forecasting accuracy. Token limits are requested, not dollar caps. "
                           "Missing usage and thought counts remain unknown. Retain output privately.",
        }
        return envelope, receipt
    except Exception:
        raise ProviderError("invalid_response", request_count=1, remote_outcome="response_received") from None
