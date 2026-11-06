"""Generate a refreshable, self-contained status report from saved Laya run manifests."""
import argparse
import html
import json
import os
import time
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[2]/'engine/output'
DEFAULT_RUN = OUTPUT/'macron-laya-continuation-2026-11-04'
HOUR = 3600


def save(path, content):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(content)
    os.replace(tmp, path)


def alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def batch_state(root, batch):
    pid = batch.get('runner_pid')
    if pid is None and (root/'batch.pid').is_file():
        text = (root/'batch.pid').read_text().strip()
        pid = int(text) if text.isdigit() else None
    if batch['status'] == 'running' and not alive(pid):
        return 'stopped: batch process is not running'
    return batch['status']


def row(manifest_file):
    manifest = json.loads(manifest_file.read_text())
    s = manifest['summary']
    package = json.loads((Path(manifest['identity']['source'])/'package.json').read_text())
    capital = package['founder']['capital_cents']
    controlled, quote = s['founder_controlled_cash_cents'], s['estimated_inventory_exit_cents']
    source_steps = manifest['identity']['source_steps']
    response = s['response'] or {}
    return {'path': manifest_file.parent.name, 'status': manifest['status'], 'hour': (s['last_second'] or 0)/HOUR,
            'models': 'Laya only' if source_steps == 0 else f'Jev for {source_steps} steps, then Laya',
            'calls': manifest['model_calls'], 'trades': s['trade_count'], 'turnover': s['executed_turnover_cents']/100,
            'cash': (controlled - capital)/100, 'quote': quote/100, 'marked': (controlled + quote - capital)/100,
            'migrated': f"{s['migrated_at']/HOUR:.1f}" if s['migrated_at'] is not None else '—',
            'alert': f"{response['alert_second']/HOUR:.1f}" if 'alert_second' in response else '—'}


COLUMNS = [('Path', 'path', '{}'), ('Status', 'status', '{}'), ('Decisions by', 'models', '{}'),
           ('Last hour', 'hour', '{:g}'), ('Laya calls', 'calls', '{}'), ('Trades', 'trades', '{}'),
           ('Turnover USD', 'turnover', '{:,.2f}'), ('Migration hour', 'migrated', '{}'),
           ('Exit-alert hour', 'alert', '{}'), ('Founder cash vs capital USD', 'cash', '{:,.2f}'),
           ('Unsold inventory quote USD', 'quote', '{:,.2f}'), ('Cash + quote vs capital USD', 'marked', '{:,.2f}')]

NOTES = ('Conditional simulations, not forecasts. Dollar values are simulated. '
         '"Founder cash vs capital" counts cash only. "Unsold inventory quote" is a model price for selling the '
         'founder\'s remaining tokens at the final pool state; it is not an executed sale. Founder buys and staged-exit '
         'sales follow fixed engine rules; the founder\'s model choices are limited to wait, pause_mm and review_campaign. '
         'A completed path reaches hour 336. One seed per path.')


def report(root):
    batch = json.loads((root/'batch-status.json').read_text())
    state = batch_state(root, batch)
    rows = [row(m) for m in sorted(root.glob('*/manifest.json'))]
    complete = sum(r['status'] == 'completed' for r in rows)
    title = 'MACRON: Laya from hour 0' if batch.get('mode') == 'laya_from_start' else 'MACRON: Laya continuations'
    lines = ['# ' + title, '', f"Batch status: {state}; {complete} of {batch['total_paths']} paths complete.", '', NOTES, '',
             '| ' + ' | '.join(c[0] for c in COLUMNS) + ' |', '|' + '|'.join('---' if i < 3 else '---:' for i in range(len(COLUMNS))) + '|']
    lines += ['| ' + ' | '.join(fmt.format(r[key]) for _, key, fmt in COLUMNS) + ' |' for r in rows]
    lines += ['', 'Paths not listed have not started.']
    save(root/'REPORT.md', '\n'.join(lines) + '\n')
    head = ''.join('<th>' + html.escape(c[0]) + '</th>' for c in COLUMNS)
    body = ''.join('<tr>' + ''.join('<td>' + html.escape(fmt.format(r[key])) + '</td>' for _, key, fmt in COLUMNS) + '</tr>' for r in rows)
    page = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="refresh" content="60"><title>' + html.escape(title) + '</title><style>body{font:16px/1.55 system-ui;'
            'background:#f2f5fa;color:#17223b;margin:0}main{max-width:1240px;margin:auto;padding:22px}header{background:#193255;'
            'color:white;padding:24px;border-radius:16px}h1{font-size:clamp(1.7rem,5vw,2.6rem);line-height:1.15}section{background:white;'
            'border-radius:16px;padding:20px;margin:18px 0}.scroll{overflow-x:auto}table{min-width:1100px;border-collapse:collapse;width:100%}'
            'td,th{padding:9px;text-align:left;border-bottom:1px solid #e3e9f0}small{color:#556680}</style><main><header>'
            '<p>BOYUN · RUN MONITOR</p><h1>' + html.escape(title) + '</h1><p>' + html.escape(state) + ' · ' + str(complete) + ' of '
            + str(batch['total_paths']) + ' paths completed</p></header><section><h2>Saved path results</h2><div class="scroll"><table>'
            '<thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table></div><p><small>' + html.escape(NOTES)
            + ' This page refreshes once a minute.</small></p></section></main></html>')
    save(root/'REPORT.html', page)
    return state


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run-dir', type=Path, default=DEFAULT_RUN)
    p.add_argument('--watch', action='store_true')
    args = p.parse_args()
    while True:
        state = report(args.run_dir)
        if not args.watch or state != 'running':
            break
        time.sleep(30)
