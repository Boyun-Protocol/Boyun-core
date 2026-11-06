"""Single-call provider boundaries; fixtures are synthetic, never live inference."""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

from decision_lab.policy_preparation import prepare_request
from decision_lab.providers import ProviderError, generate_response
from decision_lab.simulation import default_scenario, load_pool


KEY = "private-key-do-not-echo"
OPENAI = "https://provider.example/v1/chat/completions"
GEMINI = "https://provider.example/v1beta/models/test-model:generateContent"


def request():
    return prepare_request(default_scenario(), load_pool(), model="test-model",
                           template_ids=["retail-01"], max_output_tokens=1000)


def output():
    return json.dumps({"policies": [{"template_id": "retail-01", "entry_signal": "none",
        "entry_fraction_bps": 0, "exit_on_contradiction": True,
        "rationale": "Synthetic proposal.", "assumptions": ["Unmeasured behavior."]}]})


def openai():
    return {"choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant", "content": output()}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 100, "total_tokens": 150}}


def gemini():
    return {"candidates": [{"index": 0, "finishReason": "STOP", "content": {
        "role": "model", "parts": [{"text": output()}]}}],
        "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 100,
                          "thoughtsTokenCount": 25, "totalTokenCount": 175}}


def test_gemini_accepts_opaque_thought_signature_on_final_text_without_exposing_it():
    reply = gemini()
    reply["candidates"][0]["content"]["parts"][0]["thoughtSignature"] = "c2lnbmF0dXJl"
    envelope, receipt = call(reply, protocol="gemini")
    assert envelope["output_text"] == output()
    assert receipt["usage"]["output_tokens"] == 125
    assert "c2lnbmF0dXJl" not in json.dumps(envelope)
    assert "c2lnbmF0dXJl" not in json.dumps(receipt)


@pytest.mark.parametrize("signature", [None, True, 123, {}, ""])
def test_gemini_rejects_malformed_thought_signature_metadata(signature):
    reply = gemini()
    reply["candidates"][0]["content"]["parts"][0]["thoughtSignature"] = signature
    with pytest.raises(ProviderError):
        call(reply, protocol="gemini")


def call(reply=None, *, req=None, protocol="openai", endpoint=None, transport=None, **kwargs):
    return generate_response(req if req is not None else request(), load_pool(),
        endpoint=endpoint or (OPENAI if protocol == "openai" else GEMINI), api_key=KEY,
        protocol=protocol, transport=transport or (lambda **_: json.dumps(reply).encode()),
        **kwargs)


@pytest.mark.parametrize("protocol", ["openai", "gemini"])
def test_payload_auth_limit_and_minimal_private_receipt(protocol):
    sent = []
    raw = json.dumps(openai() if protocol == "openai" else gemini()).encode()

    def transport(**kwargs):
        sent.append(kwargs)
        return raw

    req = request()
    envelope, receipt = call(req=req, protocol=protocol, transport=transport)
    assert len(sent) == 1
    wire = json.loads(sent[0]["body"])
    assert sent[0]["timeout_seconds"] == 60
    assert sent[0]["max_response_bytes"] <= 2 * 1024 * 1024
    assert sent[0]["endpoint"] == (OPENAI if protocol == "openai" else GEMINI)
    if protocol == "openai":
        assert wire == {"model": "test-model", "messages": req["messages"], "max_tokens": 1000}
        assert sent[0]["headers"]["Authorization"] == f"Bearer {KEY}"
    else:
        assert wire == {"systemInstruction": {"parts": [{"text": req["messages"][0]["content"]}]},
            "contents": [{"role": "user", "parts": [{"text": req["messages"][1]["content"]}]}],
            "generationConfig": {"maxOutputTokens": 1000}}
        assert sent[0]["headers"]["x-goog-api-key"] == KEY
    assert KEY not in sent[0]["body"].decode()
    assert envelope == {"schema_version": "policy-response.v1", "request_sha256": req["request_sha256"],
        "output_text": output(), "usage": {"input_tokens": 50, "output_tokens": 100 if protocol == "openai" else 125}}
    assert receipt["schema_version"] == "provider-transport.v1"
    assert receipt["endpoint_origin"] == "https://provider.example"
    assert receipt["protocol"] == protocol
    assert receipt["model"] == "test-model"
    assert receipt["request_sha256"] == req["request_sha256"]
    assert receipt["transport_request_sha256"] == sha256(sent[0]["body"]).hexdigest()
    assert receipt["provider_response_sha256"] == sha256(raw).hexdigest()
    assert receipt["output_sha256"] == sha256(output().encode()).hexdigest()
    assert len(receipt["prompt_sha256"]) == 64
    assert receipt["max_output_tokens"] == 1000
    assert receipt["inference_calls_performed"] == 1
    assert receipt["usage_status"] == "provider_reported_unverified"
    assert receipt["cost_usd"] is None
    assert receipt["usage"] == envelope["usage"]
    assert KEY not in json.dumps(receipt)
    assert "Synthetic proposal" not in json.dumps(receipt)
    assert "/v1" not in json.dumps(receipt)


@pytest.mark.parametrize("endpoint", ["http://provider.example/v1", "ftp://localhost/a", "https://u:p@host/a",
    "https://host/a?key=private", "https://host/a#private", "https://host/a?", "https://host/a#",
    "https://host:99999/a", "https:///a", "https://host/a\nX:secret", "http://127.0.0.2/a"])
def test_invalid_endpoint_fails_before_transport_without_leaking(endpoint):
    def forbidden(**_):
        pytest.fail("must validate before disclosing request")
    with pytest.raises(ProviderError) as caught:
        call(openai(), endpoint=endpoint, transport=forbidden)
    assert caught.value.request_count == 0
    assert "private" not in str(caught.value)
    assert endpoint not in str(caught.value)


@pytest.mark.parametrize("changes", [{"timeout_seconds": True}, {"timeout_seconds": 0},
    {"timeout_seconds": 301}, {"timeout_seconds": 1.5}, {"protocol": "other"}])
def test_invalid_settings_never_dispatch(changes):
    with pytest.raises(ProviderError) as caught:
        call(openai(), transport=lambda **_: pytest.fail("unexpected dispatch"), **changes)
    assert caught.value.request_count == 0


def test_tampered_request_never_dispatches():
    req = request()
    req["messages"][0]["content"] = KEY
    with pytest.raises(ProviderError) as caught:
        call(openai(), req=req, transport=lambda **_: pytest.fail("unexpected dispatch"))
    assert caught.value.request_count == 0
    assert KEY not in str(caught.value)


@pytest.mark.parametrize("key", [None, "", " ", "secret\r\nX-Injected: value", "secret\x00", 123])
def test_invalid_api_key_is_rejected_before_dispatch(key):
    with pytest.raises(ProviderError) as caught:
        generate_response(request(), load_pool(), endpoint=OPENAI, api_key=key,
            protocol="openai", transport=lambda **_: pytest.fail("unexpected dispatch"))
    assert caught.value.request_count == 0


def test_gemini_endpoint_must_identify_the_exact_declared_model():
    with pytest.raises(ProviderError) as caught:
        call(gemini(), protocol="gemini", endpoint=GEMINI.replace("test-model", "other-model"),
             transport=lambda **_: pytest.fail("unexpected dispatch"))
    assert caught.value.request_count == 0


def test_gemini_unreported_thought_count_remains_unknown():
    reply = gemini()
    reply["usageMetadata"].pop("thoughtsTokenCount")
    _, receipt = call(reply, protocol="gemini")
    assert receipt["thought_tokens"] is None
    assert receipt["cost_usd"] is None


def test_gemini_thought_usage_counts_toward_the_requested_output_limit():
    reply = gemini()
    reply["usageMetadata"]["thoughtsTokenCount"] = 901
    with pytest.raises(ProviderError):
        call(reply, protocol="gemini")


@pytest.mark.parametrize("protocol", ["openai", "gemini"])
def test_missing_usage_is_unknown_and_never_zero_cost(protocol):
    reply = openai() if protocol == "openai" else gemini()
    reply.pop("usage" if protocol == "openai" else "usageMetadata")
    envelope, receipt = call(reply, protocol=protocol)
    assert envelope["usage"] is None
    assert receipt["usage_status"] == "unknown"
    assert receipt["cost_usd"] is None


@pytest.mark.parametrize("mutation", ["length", "refusal", "tool_calls", "multiple", "empty", "role",
    "no_choices", "tool_finish", "legacy_function", "no_finish", "invalid_policy"])
def test_openai_rejects_incomplete_refused_or_non_policy_output(mutation):
    reply = openai()
    choice = reply["choices"][0]
    if mutation == "length": choice["finish_reason"] = "length"
    elif mutation == "refusal": choice["message"]["refusal"] = KEY
    elif mutation == "tool_calls": choice["message"]["tool_calls"] = [{"function": KEY}]
    elif mutation == "multiple": reply["choices"].append(deepcopy(choice))
    elif mutation == "empty": choice["message"]["content"] = " "
    elif mutation == "role": choice["message"]["role"] = "tool"
    elif mutation == "no_choices": reply["choices"] = []
    elif mutation == "tool_finish": choice["finish_reason"] = "tool_calls"
    elif mutation == "legacy_function": choice["message"]["function_call"] = {"name": KEY}
    elif mutation == "no_finish": choice.pop("finish_reason")
    else: choice["message"]["content"] = '{"policies": []}'
    with pytest.raises(ProviderError) as caught:
        call(reply)
    assert caught.value.request_count == 1
    assert KEY not in str(caught.value)


@pytest.mark.parametrize("mutation", ["safety", "tool", "thought", "multiple", "empty", "blocked", "role", "partial"])
def test_gemini_rejects_safety_tools_thoughts_or_partial_output(mutation):
    reply = gemini()
    candidate = reply["candidates"][0]
    if mutation == "safety": candidate["finishReason"] = "SAFETY"
    elif mutation == "tool": candidate["content"]["parts"].append({"functionCall": {"name": KEY}})
    elif mutation == "thought": candidate["content"]["parts"][0]["thought"] = True
    elif mutation == "multiple": reply["candidates"].append(deepcopy(candidate))
    elif mutation == "empty": candidate["content"]["parts"] = []
    elif mutation == "blocked": reply["promptFeedback"] = {"blockReason": "SAFETY"}
    elif mutation == "role": candidate["content"]["role"] = "user"
    else: candidate["finishReason"] = "MAX_TOKENS"
    with pytest.raises(ProviderError):
        call(reply, protocol="gemini")


@pytest.mark.parametrize("raw", [b'{"choices": [], "choices": []}', b'{"usage": NaN}',
    b'{"usage": 1e999}', b'[]', b'\xff', b'x' * (2 * 1024 * 1024 + 1), "not bytes"])
def test_transport_body_requires_bounded_strict_json(raw):
    with pytest.raises(ProviderError) as caught:
        call(transport=lambda **_: raw)
    assert caught.value.request_count == 1


@pytest.mark.parametrize("usage", [{"prompt_tokens": True, "completion_tokens": 1},
    {"prompt_tokens": -1, "completion_tokens": 1}, {"prompt_tokens": 1, "completion_tokens": 1001},
    {"prompt_tokens": 1}, {"prompt_tokens": 1, "completion_tokens": 1.5}])
def test_malformed_or_overlimit_usage_is_rejected(usage):
    reply = openai()
    reply["usage"] = usage
    with pytest.raises(ProviderError):
        call(reply)


@pytest.mark.parametrize("error", [TimeoutError(KEY), OSError(KEY), RuntimeError(KEY)])
def test_transport_failure_is_one_attempt_with_unknown_remote_outcome(error):
    attempts = []
    def transport(**_):
        attempts.append(1)
        raise error
    with pytest.raises(ProviderError) as caught:
        call(transport=transport)
    assert attempts == [1]
    assert caught.value.request_count == 1
    assert caught.value.remote_outcome == "unknown"
    assert KEY not in str(caught.value)
    assert caught.value.__suppress_context__


@contextmanager
def local_server(responder):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append({"path": self.path, "headers": dict(self.headers),
                "body": self.rfile.read(int(self.headers["Content-Length"]))})
            responder(self)
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_default_transport_posts_once_to_explicit_local_endpoint():
    def respond(handler):
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(json.dumps(openai()).encode())
    with local_server(respond) as (endpoint, received):
        envelope, receipt = generate_response(request(), load_pool(), endpoint=endpoint,
            api_key=KEY, protocol="openai")
    assert len(received) == 1
    assert received[0]["headers"]["Authorization"] == f"Bearer {KEY}"
    assert KEY not in received[0]["path"]
    assert envelope["output_text"] == output()
    assert receipt["inference_calls_performed"] == 1


def test_default_transport_never_follows_redirect_or_leaks_key():
    def destination(handler):
        pytest.fail("redirect must never be followed")
    with local_server(destination) as (destination_url, leaked):
        def redirect(handler):
            handler.send_response(307)
            handler.send_header("Location", destination_url)
            handler.end_headers()
            handler.wfile.write(KEY.encode())
        with local_server(redirect) as (endpoint, received):
            with pytest.raises(ProviderError) as caught:
                generate_response(request(), load_pool(), endpoint=endpoint,
                    api_key=KEY, protocol="openai")
    assert len(received) == 1
    assert leaked == []
    assert KEY not in str(caught.value)
    assert destination_url not in str(caught.value)
    assert caught.value.request_count == 1


def test_default_transport_http_errors_hide_raw_body():
    def respond(handler):
        handler.send_response(429)
        handler.end_headers()
        handler.wfile.write((KEY + output()).encode())
    with local_server(respond) as (endpoint, received):
        with pytest.raises(ProviderError) as caught:
            generate_response(request(), load_pool(), endpoint=endpoint,
                api_key=KEY, protocol="openai")
    assert len(received) == 1
    assert KEY not in str(caught.value)
    assert "Synthetic proposal" not in str(caught.value)
    assert caught.value.remote_outcome == "unknown"


def test_default_transport_enforces_the_response_byte_limit():
    def respond(handler):
        handler.send_response(200)
        handler.end_headers()
        try:
            handler.wfile.write(b" " * (2 * 1024 * 1024 + 1))
        except (BrokenPipeError, ConnectionResetError):
            pass
    with local_server(respond) as (endpoint, received):
        with pytest.raises(ProviderError):
            generate_response(request(), load_pool(), endpoint=endpoint,
                api_key=KEY, protocol="openai")
    assert len(received) == 1
