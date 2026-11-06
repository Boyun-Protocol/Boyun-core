import json
import threading
from test_web_server import request


def test_actual_product_http_example_review_csrf_and_no_secrets(tmp_path):
    from decision_lab.web_server import create_server
    server=create_server(port=0,output_dir=tmp_path)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        status,headers,page=request(server,'GET','/')
        assert status==200 and b'/product.js'in page
        assert request(server,'GET','/lab')[0]==200
        assert request(server,'GET','/product.js')[0]==200
        status,_,body=request(server,'GET','/api/product');boot=json.loads(body)
        assert status==200 and boot['csrf_token']
        assert 'api_key' not in body.decode()
        example=boot['examples'][0]
        data=json.dumps({'mode':'example','example_id':example['id'],'question':example['question'],'public_input':False})
        assert request(server,'POST','/api/product/sessions',data,{'Content-Type':'application/json'})[0]==403
        valid={'Content-Type':'application/json','X-CSRF-Token':boot['csrf_token']}
        status,_,body=request(server,'POST','/api/product/sessions',data,valid)
        assert status==202
        session=json.loads(body);assert session['status']=='ready'
        assert request(server,'GET','/api/product/sessions/'+session['id'])[0]==200
        assert request(server,'GET','/api/product/sessions/../../.env')[0]==404
        assert request(server,'GET','/api/product',headers={'Origin':'https://evil.test'})[0]==403
    finally:
        server.shutdown();server.server_close();thread.join(3)


def test_typesafe_catalog_requires_explicit_same_origin_get(tmp_path):
    from decision_lab.web_server import create_server
    from decision_lab.jev import TypeSafeClient
    calls=[]
    def wire(**request):
        calls.append(request)
        assert request['method']=='GET' and request['body']is None
        return b'{"models":[{"name":"jev-latest","description":"SECRET"}]}'
    client=TypeSafeClient(api_key='PRIVATE_KEY',transport=wire)
    server=create_server(port=0,output_dir=tmp_path,product_actor_clients={'typesafe':client})
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        boot=json.loads(request(server,'GET','/api/product')[2])
        assert not calls and boot['typesafe_health']is None
        path='/api/product/typesafe/models'
        assert request(server,'GET',path,headers={'Origin':'https://evil.test'})[0]==403
        assert request(server,'GET','/api/product/jevstation/credits')[0]==404
        assert not calls
        status,_,body=request(server,'GET',path)
        value=json.loads(body)
        assert status==200 and value['status']=='ready'and value['models']==['jev-latest']
        assert 'PRIVATE_KEY'not in body.decode()and 'SECRET'not in body.decode()and len(calls)==1
        assert json.loads(request(server,'GET','/api/product')[2])['typesafe_health']==value
        assert len(calls)==1
    finally:
        server.shutdown();server.server_close();thread.join(3)


def test_public_how_it_works_and_lighting_assets_are_local_and_no_inference(tmp_path):
    from decision_lab.web_server import create_server
    server=create_server(port=0,output_dir=tmp_path)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        status,headers,page=request(server,'GET','/docs')
        assert status==200 and b'Runtime guide'in page and b'Return to the workspace'in page
        assert b'Offline rules'in page and b'NEAR testnet'in page and b'calibrated'in page
        assert headers['Cache-Control']=='no-store'
        assert request(server,'GET','/ambient.js')[0]==200
        assert request(server,'GET','/docs',headers={'Origin':'https://evil.test'})[0]==403
        assert request(server,'GET','/docs/../../.env')[0]==404
    finally:server.shutdown();server.server_close();thread.join(3)
