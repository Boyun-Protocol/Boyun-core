"""Only one explicitly named secret is read; never execute dotenv syntax."""
import os
import pytest
from decision_lab.env_config import load_env_key


def test_only_named_key_is_parsed_and_not_exported(tmp_path):
    source = tmp_path/'.env'
    source.write_text('UNRELATED=$(evil)\nexport TYPESAFE_API_KEY="sk_test-safe"\nOTHER=ignored\n')
    before = dict(os.environ)
    assert load_env_key(source) == 'sk_test-safe'
    assert dict(os.environ) == before


@pytest.mark.parametrize('raw', ['TYPESAFE_API_KEY=\n', 'OTHER=secret\n',
    'TYPESAFE_API_KEY=a\nTYPESAFE_API_KEY=b\n',
    'TYPESAFE_API_KEY=$(command)\n', 'TYPESAFE_API_KEY="has space"\n',
    'TYPESAFE_API_KEY="unterminated\n', 'TYPESAFE_API_KEY=`command`\n'])
def test_invalid_named_secret_is_redacted(tmp_path, raw):
    source=tmp_path/'.env';source.write_text(raw)
    with pytest.raises(ValueError) as failure: load_env_key(source)
    assert raw.strip() not in str(failure.value)


def test_symlinks_and_oversized_and_fifo_inputs_rejected(tmp_path):
    source=tmp_path/'actual';source.write_text('TYPESAFE_API_KEY=sk_test\n')
    link=tmp_path/'link';link.symlink_to(source)
    with pytest.raises(ValueError):load_env_key(link)
    source.write_text('x' * 65537)
    with pytest.raises(ValueError):load_env_key(source)
    fifo=tmp_path/'fifo';os.mkfifo(fifo)
    with pytest.raises(ValueError):load_env_key(fifo)
