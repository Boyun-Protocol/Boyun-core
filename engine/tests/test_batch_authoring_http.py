"""Staged construction/cancellation use the actual guarded HTTP product routes."""
import json
from threading import Event,Thread
import time
from test_batch_authoring import Author,plan
from test_web_server import request


def test_staged_http_plan_and_stop_obey_csrf_origin_and_no_redispatch(tmp_path):
    from decision_lab.web_server import create_server
    entered=Event();release=Event()
    class Blocking(Author):
        def generate(self,messages):
            if not self.calls:entered.set();assert release.wait(3)
            return super().generate(messages)
    author=Blocking(2);server=create_server(port=0,output_dir=tmp_path,product_author_client=author)
    thread=Thread(target=server.serve_forever);thread.start()
    try:
        boot=json.loads(request(server,'GET','/api/product')[2]);valid={'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        data={'mode':'author','example_id':None,'question':'A public fictional bounded experiment.','public_input':True,'authoring_plan':plan(2)}
        assert request(server,'POST','/api/product/sessions',json.dumps({**data,'authoring_plan':{**plan(2),'max_calls':1}}),valid)[0]==400
        assert not author.calls
        status,_,body=request(server,'POST','/api/product/sessions',json.dumps(data),valid)
        assert status==202;sid=json.loads(body)['id'];assert entered.wait(3)
        path='/api/product/sessions/'+sid+'/cancel_author'
        assert request(server,'POST',path,'{}',{'Content-Type':'application/json'})[0]==403
        assert request(server,'POST',path,'{}',{**valid,'Origin':'https://evil.test'})[0]==403
        assert request(server,'POST',path,'{"retry":true}',valid)[0]==400
        status,_,body=request(server,'POST',path,'{}',valid)
        assert status==202 and json.loads(body)['authoring_cancel_requested']is True
        release.set()
        for _ in range(100):
            s=json.loads(request(server,'GET','/api/product/sessions/'+sid)[2])
            if s['status']!='authoring':break
            time.sleep(.01)
        assert s['status']=='failed'and s['error']=='authoring_cancelled'and len(author.calls)==1
        assert request(server,'GET',path)[0]==405
    finally:
        release.set();server.shutdown();server.server_close();thread.join(3)
