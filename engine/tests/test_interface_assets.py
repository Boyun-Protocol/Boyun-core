import json
import threading
from decision_lab.interface_assets import InterfaceUnavailable
from decision_lab.web_server import create_server
from test_web_server import request

def test_missing_interface_preserves_apis_and_explains_page_install(monkeypatch, tmp_path):
    def missing():
        raise InterfaceUnavailable('Install Boyun-interface')
    monkeypatch.setattr('decision_lab.web_server.web_assets', missing)
    server = create_server(port=0, output_dir=tmp_path)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        status, _, body = request(server, 'GET', '/')
        assert status == 503 and 'Boyun-interface' in json.loads(body)['error']
        assert request(server, 'GET', '/api/product')[0] == 200
        assert request(server, 'GET', '/', headers={'Origin': 'https://evil.example'})[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
