from decision_lab.cli import main


def test_serve_refuses_nonloopback_address_before_creating_artifacts(tmp_path):
    output = tmp_path / "private-results"
    assert main(["serve", "--host", "0.0.0.0", "--port", "0", "--output-dir", str(output)]) == 2
    assert not output.exists()


def _stub_server(monkeypatch):
    import decision_lab.web_server as web
    captured = {}

    class Server:
        server_address = ("0.0.0.0", 0)

        def serve_forever(self):
            pass

        def server_close(self):
            pass

    def create(**kwargs):
        captured.update(kwargs)
        return Server()

    monkeypatch.setattr(web, "create_server", create)
    return captured


def test_container_bind_widens_only_the_socket(tmp_path, monkeypatch):
    captured = _stub_server(monkeypatch)
    assert main(["serve", "--port", "0", "--output-dir", str(tmp_path), "--container-bind"]) == 0
    assert captured["container_bind"] is True
    assert captured["host"] == "127.0.0.1"
    assert captured["hosted"] is False


def test_serve_without_the_flag_stays_on_loopback(tmp_path, monkeypatch):
    captured = _stub_server(monkeypatch)
    assert main(["serve", "--port", "0", "--output-dir", str(tmp_path)]) == 0
    assert captured["container_bind"] is False
    assert captured["host"] == "127.0.0.1"


def test_host_trust_acknowledgment_selects_the_notice(tmp_path, monkeypatch):
    captured = _stub_server(monkeypatch)
    assert main(["serve", "--port", "0", "--output-dir", str(tmp_path),
                 "--acknowledge-host-access"]) == 0
    assert captured["hosted"] is True
    assert captured["container_bind"] is False
