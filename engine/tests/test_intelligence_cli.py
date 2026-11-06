"""Intelligence command adapters: offline, bounded input and private outputs."""
import argparse
import json
import os
import stat

import pytest

from decision_lab import intelligence_commands as cli
from decision_lab.market_sources import CollectionError


def invoke(*words):
    parser = argparse.ArgumentParser()
    cli.register_intelligence_commands(parser.add_subparsers(dest="command", required=True))
    return cli.run_intelligence_command(parser.parse_args([str(x) for x in words]))


def inputs(tmp_path):
    source = tmp_path / "pools.json"
    source.write_text("[]")
    output = tmp_path / "trades.json"
    return source, output


def test_collection_requires_optin_before_key_lookup_or_output(monkeypatch, tmp_path):
    source, output = inputs(tmp_path)
    original_get = cli.os.environ.get
    def guarded_get(name, *rest):
        if name == "TEST_KEY":
            pytest.fail("key lookup before opt-in")
        return original_get(name, *rest)
    monkeypatch.setattr(cli.os.environ, "get", guarded_get)
    assert invoke("intelligence", "collect", "--network", "near", "--pools", source,
                  "--api-key-env", "TEST_KEY", "--output", output) == 2
    assert not output.exists()
    assert not output.with_suffix(".collection.json").exists()


def test_missing_key_does_not_create_artifacts(monkeypatch, tmp_path):
    source, output = inputs(tmp_path)
    monkeypatch.delenv("TEST_HISTORY_KEY", raising=False)
    assert invoke("intelligence", "collect", "--network", "near", "--pools", source,
                  "--api-key-env", "TEST_HISTORY_KEY", "--allow-network", "--output", output) == 2
    assert not output.exists()


def test_collector_reserves_both_artifacts_before_dispatch(monkeypatch, tmp_path):
    source, output = inputs(tmp_path)
    receipt = output.with_suffix(".collection.json")
    monkeypatch.setenv("TEST_HISTORY_KEY", "private-key-value")
    def fake(**kwargs):
        assert kwargs["api_key"] == "private-key-value"
        assert output.exists() and receipt.exists()
        assert json.loads(receipt.read_text())["status"] == "dispatch_pending"
        return {"schema_version": "wallet-observations.v1"}, {"request_count": 1, "coverage": "unverified"}
    monkeypatch.setattr(cli, "collect_pool_trades", fake)
    assert invoke("intelligence", "collect", "--network", "near", "--pools", source,
                  "--api-key-env", "TEST_HISTORY_KEY", "--allow-network", "--output", output) == 0
    assert json.loads(output.read_text())["schema_version"] == "wallet-observations.v1"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert "private-key-value" not in output.read_text() + receipt.read_text()


def test_existing_receipt_or_symlink_prevents_dispatch(monkeypatch, tmp_path):
    source, output = inputs(tmp_path)
    monkeypatch.setenv("TEST_HISTORY_KEY", "private-key-value")
    monkeypatch.setattr(cli, "collect_pool_trades", lambda **_: pytest.fail("must not dispatch"))
    target = tmp_path / "target"
    target.write_text("untouched")
    output.with_suffix(".collection.json").symlink_to(target)
    assert invoke("intelligence", "collect", "--network", "near", "--pools", source,
                  "--api-key-env", "TEST_HISTORY_KEY", "--allow-network", "--output", output) == 2
    assert target.read_text() == "untouched"
    assert not output.exists()


def test_collection_failure_retains_sanitized_attempt_receipt(monkeypatch, tmp_path, capsys):
    source, output = inputs(tmp_path)
    monkeypatch.setenv("TEST_HISTORY_KEY", "private-key-value")
    def fail(**kwargs):
        raise CollectionError("transport_failed", request_count=2)
    monkeypatch.setattr(cli, "collect_pool_trades", fail)
    assert invoke("intelligence", "collect", "--network", "solana", "--pools", source,
                  "--api-key-env", "TEST_HISTORY_KEY", "--allow-network", "--output", output) == 2
    receipt = json.loads(output.with_suffix(".collection.json").read_text())
    assert receipt["request_count"] == 2
    assert receipt["status"] == "failed"
    assert receipt["remote_outcome"] == "unknown"
    assert "private-key-value" not in output.read_text() + output.with_suffix(".collection.json").read_text() + capsys.readouterr().err


def test_wallet_and_topic_commands_invoke_analyzers_and_refuse_overwrite(monkeypatch, tmp_path):
    import decision_lab.wallet_evidence as wallets
    source, output = inputs(tmp_path)
    monkeypatch.setattr(wallets, "analyze_wallets", lambda item: {"actual_input": item})
    assert invoke("intelligence", "wallets", "--input", source, "--output", output) == 0
    assert json.loads(output.read_text()) == {"actual_input": []}
    assert invoke("intelligence", "wallets", "--input", source, "--output", output) == 2
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_non_intelligence_command_is_untouched():
    assert cli.run_intelligence_command(argparse.Namespace(command="simulate")) is None


def test_topics_command_runs_actual_metadata_analyzer(tmp_path):
    source, output = inputs(tmp_path)
    source.write_text(json.dumps({"schema_version": "topic-observations.v1", "topic": "Crypto launch", "entities": ["Named person"], "captured_at": "2026-10-22T00:00:00Z", "target_days": 30, "source_url": "https://api.gdeltproject.org/api/v2/doc/doc?mode=artlist&timespan=30d", "articles": [], "social_posts": []}))
    assert invoke("intelligence", "topics", "--input", source, "--output", output) == 0
    result = json.loads(output.read_text())
    assert result["summary"]["articles"] == 0
    assert result["simulation_effect"] == "none"
