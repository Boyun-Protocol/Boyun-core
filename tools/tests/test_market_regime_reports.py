import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    specification = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_deck_chart_contract_and_aggregate_only_payload():
    module = load('export_market_regime_deck')
    row = {'hours': 0, 'world': 0, 'market_cap_usd': 100, 'cumulative_volume_usd': 100, 'founder_cash_usd': 43000}
    data = {'label': 'BULL Market scenario', 'worlds': [{'buys': 1, 'sells': 2}],
            'summary': {'executed_volume_cents': 10000, 'provider_action_counts': {'wait': 2048}}, 'rows': [row]}
    html, slides = module.deck([data, {**data, 'label': 'BEAR Market scenario'}])
    assert slides == 13
    assert html.count('<section ') == 13
    assert html.count('new Chart(') == 6
    assert 'https://fonts.googleapis.com' in html
    assert 'Private proposal' not in html and 'observation_sha256' not in html
    assert 'data:' not in html
    assert '4×' in html and 'not a diagnosis' in html


def test_dashboard_is_self_contained_safely_serialized_and_valid_javascript(tmp_path):
    module = load('build_market_regime_reports')
    module.write_dashboard([{'label': '</script><script>unsafe()</script>', 'nodes': [], 'summary': {},
                             'rows': [], 'worlds': [], 'run': 'private'}], tmp_path)
    html = (tmp_path / 'MACRON-BULL-BEAR-interactive.html').read_text()
    assert '<script src=' not in html and '<link ' not in html
    assert '</script><script>unsafe()' not in html
    assert 'filters the view, not file access' in html
    assert 'not a tree of unexecuted outcomes' in html
    script = html.split('</script><script>', 1)[1].split('</script>', 1)[0]
    source = tmp_path / 'interactive.js'
    source.write_text(script)
    result = subprocess.run(['node', '--check', str(source)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_regime_guidance_avoids_single_indicator_and_incident_causality():
    module = load('build_market_regime_reports')
    text = json.dumps(module.REGIMES)
    assert '200-day' in text and '90-day' in text
    assert 'Dominance alone cannot classify' in text
    assert 'does not establish a Binance-hack explanation' in text
    assert 'Do not add aggregator' in text
