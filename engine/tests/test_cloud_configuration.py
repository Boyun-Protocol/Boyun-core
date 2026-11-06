from argparse import ArgumentParser
import pytest


def test_configuration_no_network_and_explicit_key_loading(tmp_path,monkeypatch):
    from decision_lab.cloud_configuration import add_cloud_arguments,configured_author
    p=ArgumentParser();add_cloud_arguments(p)
    assert configured_author(p.parse_args([]))is None
    monkeypatch.setenv('NEAR_AI_CLOUD_API_KEY','cloud-test-key')
    args=p.parse_args(['--enable-near-ai','--near-ai-model','canonical/model'])
    client=configured_author(args)
    assert client.model=='canonical/model'and client.provider=='near_ai'
    env=tmp_path/'keys';env.write_text('NEAR_AI_CLOUD_API_KEY=file-test-key\nIGNORED=value\n')
    client=configured_author(p.parse_args(['--near-ai-env-file',str(env),'--near-ai-model','canonical/model']))
    assert client.api_key=='file-test-key'
    with pytest.raises(ValueError):configured_author(p.parse_args(['--enable-near-ai']))
