"""Operator startup must select only native TypeSafe, without access checks."""
from decision_lab.cli import main


def test_native_startup_reads_selected_key_without_request(tmp_path, monkeypatch):
    import decision_lab.web_server as web
    from decision_lab import jev
    captured = {}
    class Server:
        server_address = ('127.0.0.1', 0)
        def serve_forever(self): pass
        def server_close(self): pass
    def create(**kwargs):
        captured.update(kwargs)
        return Server()
    monkeypatch.setattr(web, 'create_server', create)
    monkeypatch.setattr(jev, '_urllib_transport', lambda **_: (_ for _ in ()).throw(AssertionError('no startup request')))
    monkeypatch.setenv('NATIVE_TEST_KEY', 'fixture-native-key')
    assert main(['serve', '--port', '0', '--enable-typesafe',
                 '--typesafe-api-key-env', 'NATIVE_TEST_KEY']) == 0
    assert set(captured['product_actor_clients']) == {'typesafe'}
    client = captured['product_actor_clients']['typesafe']
    assert client.endpoint == 'https://api.typesafe.ai/v1/systemone'
    assert client.api_key == 'fixture-native-key'


def test_native_file_selection_has_no_implicit_key_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'must-not-fallback')
    source = tmp_path / 'missing.env'
    source.write_text('UNRELATED=value\n')
    assert main(['serve', '--port', '0', '--typesafe-env-file', str(source)]) == 2
