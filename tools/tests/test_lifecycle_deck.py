import importlib.util
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parents[1]))
spec = importlib.util.spec_from_file_location('lifecycle_deck', Path(__file__).parents[1] / 'export_lifecycle_deck.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def data():
    return {'native': {'status': 'partial_budget_limited', 'completed_paths': 0,
                      'budget': {'completed_calls': 1000, 'spent_estimate_micro_usd': 1000000}},
            'paths': [], 'result_sha256': 'test-hash'}


def test_deck_has_explanatory_slides_and_required_export_structure():
    html, count = module.deck(data())
    assert count >= 14 and html.count('<section ') == count
    assert 'presentation-slides-wrapper' in html
    assert 'Chart' in html and 'responsive' in html
    assert '<style' not in html and 'style=' not in html and 'data:' not in html
    assert 'DM_Serif_Display' in html and 'Manrope' in html
    assert 'unfinished' in html and 'not Jev' in html


def test_deck_omits_private_actor_observations_even_if_present_in_source():
    source = data()
    source['private'] = 'SECRET_RAW_ACTOR_OBSERVATION'
    html, _ = module.deck(source)
    assert 'SECRET_RAW_ACTOR_OBSERVATION' not in html


def test_presenton_validator_accepts_the_exact_font_imports():
    import sys
    import os
    if os.environ.get('BOYUN_PRESENTON_SCRIPTS'):
        sys.path.insert(0, str(Path(os.environ['BOYUN_PRESENTON_SCRIPTS']).expanduser()))
    import pytest
    validate_html = pytest.importorskip('validate_html', reason='Optional Presenton validator is not bundled').validate_html
    html, _ = module.deck(data())
    assert validate_html(html) == []
