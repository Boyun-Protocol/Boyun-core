"""Build the NEAR lending financial casebook from the six frozen 90-day runs.

No inference or simulation. Reuses the Boyun casebook renderer (PDF with linked
contents, standalone HTML, Markdown, SVG exhibits with JSON data).
Usage: engine/.venv/bin/python tools/build_lending_casebook.py --output DIR
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_financial_casebook import draw_chart, make_html, make_markdown, make_pdf  # noqa: E402
from lending_casebook_data import CASE, load_all  # noqa: E402
import lending_casebook_docs as docs  # noqa: E402

ASOF = '5 November 2026'


def base(kind, title, subtitle, ctx):
    return {'kind': kind, 'title': title, 'subtitle': subtitle, 'asof': ASOF, 'project': 'NEAR LENDING',
            'result_sha256': ctx['identity'], 'sections': [], 'highlights': [], 'cast_panel': False,
            'footer_note': 'Conditional research. Synthetic cast, real replayed prices. No calibrated odds.',
            'cover_note': 'Synthetic cast, real replayed NEAR prices. No calibrated odds.'}


def write_package(documents, ctx, output):
    destination = Path(output).resolve()
    if destination.exists():
        raise ValueError('output must be a new directory; preserve earlier editions')
    destination.mkdir(parents=True, mode=0o700)
    for folder in ('DATA', 'FIGURES'):
        (destination / folder).mkdir()
    from reportlab.graphics import renderSVG
    files = []
    for index, doc in enumerate(documents):
        count = 0
        for s in doc['sections']:
            for b in s['blocks']:
                if b['kind'] == 'chart':
                    count += 1
                    b['figure_id'] = f'{index + 1:02d}-F{count:02d}'
                    (destination / 'DATA' / f'{b["figure_id"]}.json').write_text(json.dumps(b, indent=2) + '\n')
                    renderSVG.drawToFile(draw_chart(b), str(destination / 'FIGURES' / f'{b["figure_id"]}.svg'))
        name = f'{index + 1:02d}-' + doc['kind']
        make_pdf(doc, destination / (name + '.pdf'))
        (destination / (name + '.html')).write_text(make_html(doc))
        (destination / (name + '.md')).write_text(make_markdown(doc))
        files.append({'id': name, 'title': doc['title'], 'figures': count, 'sections': len(doc['sections'])})
    manifest = {'schema_version': 'financial-casebook.v1', 'case': 'near-lending', 'source_result_sha256': ctx['identity'],
                'worlds': {w['code']: str(w['root'].relative_to(CASE.parents[3])) for w in ctx['worlds'].values()},
                'documents': files, 'new_model_calls': 0, 'world_odds': 'unknown_uncalibrated',
                'builder_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}
    (destination / 'DATA' / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    links = ''.join(f'<article><h2>{f["title"]}</h2><p><a href="{f["id"]}.html">Read HTML</a> · '
                    f'<a href="{f["id"]}.pdf">Download PDF</a> · <a href="{f["id"]}.md">Markdown</a></p>'
                    f'<p>{f["figures"]} numbered exhibits.</p></article>' for f in files)
    (destination / 'index.html').write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>NEAR lending launch research</title><style>body{max-width:780px;margin:60px auto;padding:20px;background:#FAF6EC;'
        'font:18px/1.7 system-ui;color:#1C1D18}h1{font-size:44px;line-height:1.05}article{background:#FFFDF8;border:1px solid #E6DFCF;'
        'border-radius:24px;padding:20px 24px;margin:14px 0}a{color:#2A52D1}</style><h1>NEAR lending launch research</h1>'
        '<p>Read World Creation first, then the Choppy and Bear cases. The Bull case was not run. The technical report records '
        'execution and cost; the decision record keeps the user\'s choices.</p>' + links)
    (destination / 'README.md').write_text('# NEAR lending launch research\n\nStart with [the index](index.html).\n\n' +
                                           '\n'.join(f'- [{f["title"]}]({f["id"]}.pdf)' for f in files) +
                                           '\n\nNo new model calls. Real-world odds unknown.\n')
    return {'status': 'built', 'output': str(destination), 'documents': files, 'result_sha256': ctx['identity']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    ctx = load_all()
    documents = [docs.world_creation(ctx, base), docs.choppy_case(ctx, base), docs.bear_case(ctx, base),
                 docs.bull_case(ctx, base), docs.technical(ctx, base), docs.decision_record(ctx, base)]
    print(json.dumps(write_package(documents, ctx, args.output), indent=2))


if __name__ == '__main__':
    main()
