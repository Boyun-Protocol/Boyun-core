import json
import threading
import pytest
from decision_lab.internal_flow import InternalFlow
from decision_lab.web_server import create_server
from test_web_server import request

VALUE={'phase':'setup','current':'starter','actor_route':'typesafe','steps':[{'id':'intent','label':'What to explore?','input':'choices','answer':'Launch','visited':True},{'id':'starter','label':'Where to begin?','input':'choices','answer':'Ready world','visited':False}]}


def test_map_is_bounded_navigation_not_arbitrary_scenario_storage():
    flow=InternalFlow();assert flow.snapshot()['navigation']is None
    assert flow.update(VALUE)['revision']==1
    snapshot=flow.snapshot();snapshot['navigation']['steps'][0]['answer']='changed'
    assert flow.snapshot()['navigation']['steps'][0]['answer']=='Launch'
    for invalid in ({**VALUE,'secret':'no'}, {**VALUE,'steps':VALUE['steps']*100}, {**VALUE,'phase':'line\nbreak'}, {**VALUE,'steps':[{**VALUE['steps'][0],'raw_input':'no'}]}):
        with pytest.raises(ValueError):flow.update(invalid)


@pytest.mark.parametrize('enabled',[False,True])
def test_internal_docs_need_opt_in_and_same_origin_csrf(tmp_path,enabled):
    server=create_server(port=0,output_dir=tmp_path,enable_internal_map=enabled)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        boot=json.loads(request(server,'GET','/api/product')[2]);assert boot['internal_flow']is enabled
        status,_,_=request(server,'GET','/internal/flow');assert status==(200 if enabled else 404)
        assert request(server,'GET','/internal/flow',headers={'Origin':'https://evil.test'})[0]==403
        assert request(server,'POST','/api/internal/flow',json.dumps(VALUE),{'Content-Type':'application/json'})[0]==403
        valid={'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        assert request(server,'POST','/api/internal/flow',json.dumps(VALUE),valid)[0]==(200 if enabled else 404)
        assert request(server,'GET','/internal-flow.html')[0]==404
        if enabled:
            snapshot=json.loads(request(server,'GET','/api/internal/flow')[2]);assert snapshot['navigation']==VALUE
            assert request(server,'GET','/internal/flow.js')[0]==200
    finally:server.shutdown();server.server_close();thread.join(3)
