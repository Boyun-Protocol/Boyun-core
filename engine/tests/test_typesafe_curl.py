"""Explicit curl uses native endpoints and keeps credentials out of argv."""
import os
from pathlib import Path
from urllib.error import HTTPError
import pytest

ENDPOINT='https://api.typesafe.ai/v1/systemone'
CATALOG='https://api.typesafe.ai/v1/models'


def test_curl_pins_post_and_keeps_key_in_private_stdin_and_body_in_private_temp_file():
    from decision_lab.typesafe_curl import curl_transport
    captured={}
    def runner(argv,config,timeout,maximum,cwd):
        captured.update(argv=argv,config=config,cwd=cwd)
        assert os.stat(cwd).st_mode&0o777==0o700
        assert 'PRIVATE_KEY' not in ' '.join(argv)
        assert 'Authorization: Bearer PRIVATE_KEY' in config.decode()
        files=list(Path(cwd).glob('*.json'))
        assert len(files)==1 and files[0].stat().st_mode&0o777==0o600
        assert files[0].read_bytes()==b'{"state":"private"}'
        return b'HTTP/2 200\r\nContent-Type: application/json\r\n\r\n{"ok":true}'
    raw=curl_transport(endpoint=ENDPOINT,headers={'Authorization':'Bearer PRIVATE_KEY'},body=b'{"state":"private"}',method='POST',timeout_seconds=10,max_response_bytes=1000,runner=runner,binary='/usr/bin/curl')
    assert raw==b'{"ok":true}' and not os.path.exists(captured['cwd'])
    args=captured['argv']
    assert args[1]=='-q' and args[args.index('--proxy')+1]=='' and args[args.index('--noproxy')+1]=='*'
    assert '--location' not in args and '--retry' not in args


def test_free_catalog_get_has_no_request_body_and_preserves_cooldown_headers():
    from decision_lab.typesafe_curl import curl_transport
    def runner(argv,config,timeout,maximum,cwd):
        assert not list(Path(cwd).iterdir()) and 'data-binary' not in config.decode()
        return b'HTTP/1.1 100 Continue\r\n\r\nHTTP/2 429\r\nRetry-After: 45\r\n\r\nprivate'
    with pytest.raises(HTTPError) as error:
        curl_transport(endpoint=CATALOG,headers={},body=None,method='GET',timeout_seconds=1,max_response_bytes=1000,runner=runner,binary='/usr/bin/curl')
    assert error.value.code==429 and error.value.headers.get('Retry-After')=='45'
    assert 'private' not in str(error.value)
    error.value.close()


@pytest.mark.parametrize('endpoint,method,body,headers',[
    ('https://evil.test/v1/systemone','POST',b'{}',{}),
    (ENDPOINT,'GET',None,{}),(CATALOG,'POST',b'{}',{}),(CATALOG,'GET',b'{}',{}),
    (ENDPOINT,'POST',b'{}',{'Authorization':'Bearer key\nInjected: yes'}),
])
def test_unsupported_operation_or_header_is_rejected_before_process(endpoint,method,body,headers):
    from decision_lab.typesafe_curl import curl_transport
    calls=[]
    def runner(*args):calls.append(args);return b''
    with pytest.raises(ValueError):curl_transport(endpoint=endpoint,headers=headers,body=body,method=method,timeout_seconds=1,max_response_bytes=1000,runner=runner,binary='/usr/bin/curl')
    assert not calls


@pytest.mark.parametrize('wire',[
    b'HTTP/2 200\r\n\r\ntoo many bytes', b'HTTP/2 302\r\nLocation: https://evil.test\r\n\r\n', b'malformed',
])
def test_redirect_malformed_and_oversized_responses_fail_without_following(wire):
    from decision_lab.typesafe_curl import curl_transport
    with pytest.raises((ValueError,HTTPError)):
        curl_transport(endpoint=CATALOG,headers={},body=None,method='GET',timeout_seconds=1,max_response_bytes=4,runner=lambda *args:wire,binary='/usr/bin/curl')
