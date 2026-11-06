"""Explicit standard curl client for TypeSafe; no redirects or retry/fallback.

Credentials are passed through stdin configuration, never argv or environment.
The temporary request body is owner-only and removed after the operation. Curl
uses its genuine default identity, not a browser fingerprint or imported cookies.
"""
from email.parser import BytesParser
from io import BytesIO
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
from tempfile import TemporaryDirectory
import time
from urllib.error import HTTPError

ENDPOINT='https://api.typesafe.ai/v1/systemone'
MODELS_ENDPOINT='https://api.typesafe.ai/v1/models'


def _run(argv,config,timeout,maximum,cwd):
    allowed=('PATH','LANG','LC_ALL','TMPDIR','SSL_CERT_FILE','SSL_CERT_DIR','CURL_CA_BUNDLE')
    process=subprocess.Popen(argv,cwd=cwd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        start_new_session=True,env={key:os.environ[key]for key in allowed if key in os.environ})
    selector=selectors.DefaultSelector();output=bytearray();diagnostic=bytearray();deadline=time.monotonic()+timeout+2
    try:
        process.stdin.write(config);process.stdin.close()
        for pipe,label in ((process.stdout,'out'),(process.stderr,'error')):selector.register(pipe,selectors.EVENT_READ,label)
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('curl timed out; remote outcome unknown')
            for entry,_ in selector.select(min(remaining,.25)):
                data=os.read(entry.fd,65536)
                if not data:selector.unregister(entry.fileobj);continue
                target=output if entry.data=='out'else diagnostic;target.extend(data)
                if len(target)>(maximum if entry.data=='out'else 65536):raise ValueError('curl response limit exceeded')
        if process.wait(timeout=max(.01,deadline-time.monotonic()))!=0:raise ValueError('curl transport failed')
        return bytes(output)
    finally:
        selector.close()
        if process.poll()is None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        process.wait(timeout=5)
        for pipe in (process.stdin,process.stdout,process.stderr):
            if not pipe.closed:pipe.close()


def curl_transport(*,endpoint,headers,body,method,timeout_seconds,max_response_bytes,runner=None,binary=None):
    if not ((endpoint==ENDPOINT and method=='POST' and body is not None) or
            (endpoint==MODELS_ENDPOINT and method=='GET' and body is None)):
        raise ValueError('pinned TypeSafe operation required')
    if type(timeout_seconds)is not int or not 1<=timeout_seconds<=300:raise ValueError('bounded timeout required')
    if type(max_response_bytes)is not int or not 1<=max_response_bytes<=1048576:raise ValueError('bounded response required')
    if type(headers)is not dict:raise ValueError('header map required')
    for name,value in headers.items():
        if (type(name)is not str or not re.fullmatch(r'[A-Za-z-]{1,80}',name)or type(value)is not str
            or len(value)>8192 or any(ord(c)<32 or ord(c)>=127 for c in value)):
            raise ValueError('printable safe HTTP headers required')
    if body is not None and (type(body)is not bytes or len(body)>524288):raise ValueError('bounded request body required')
    binary=binary or shutil.which('curl')
    if not binary:raise ValueError('explicit curl transport unavailable')
    argv=[binary,'-q','--silent','--show-error','--include','--max-time',str(timeout_seconds),
          '--max-filesize',str(max_response_bytes),'--proto','=https','--max-redirs','0','--noproxy','*','--proxy','',
          '--request',method,'--config','-']
    with TemporaryDirectory(prefix='decision-lab-typesafe-')as folder:
        config='url = '+json.dumps(endpoint)+'\n'
        for name,value in headers.items():config+='header = '+json.dumps(name+': '+value)+'\n'
        if body is not None:
            path=Path(folder)/'request.json'
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'wb')as file:file.write(body)
            config+='data-binary = '+json.dumps('@'+str(path))+'\n'
        raw=(runner or _run)(argv,config.encode(),timeout_seconds,max_response_bytes+65536,folder)
    if type(raw)is not bytes or len(raw)>max_response_bytes+65536:raise ValueError('bounded HTTP result required')
    header_bytes=0
    while True:
        header,separator,rest=raw.partition(b'\r\n\r\n')
        if not separator:raise ValueError('missing HTTP header boundary')
        first,_,fields=header.partition(b'\r\n')
        match=re.fullmatch(rb'HTTP/(?:1\.[01]|2|3) ([0-9]{3})(?: .*)?',first)
        header_bytes+=len(header)+4
        if not match or header_bytes>65536:raise ValueError('invalid bounded HTTP response')
        status=int(match[1]);parsed=BytesParser().parsebytes(fields+b'\r\n')
        if 100<=status<200:raw=rest;continue
        if len(rest)>max_response_bytes:raise ValueError('HTTP body exceeds response budget')
        if status!=200:raise HTTPError(endpoint,status,'TypeSafe HTTP error',parsed,BytesIO(rest))
        return rest
