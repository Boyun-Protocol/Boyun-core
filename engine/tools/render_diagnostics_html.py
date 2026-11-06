"""Render diagnostics.json as one self-contained, interactive HTML page (no network assets)."""
import argparse
import json
from pathlib import Path

PAGE = Path(__file__).with_name('diagnostics_page.html')


def headline(data):
    worlds = data['worlds']
    paths = [p for w in worlds for p in w['paths'].values()]
    pause = [w['paths']['pause-and-observe'] for w in worlds if 'pause-and-observe' in w['paths']]
    model_trades = sum(1 for p in paths if 'Founder model-chosen trades' in p['flows'])
    position_gain = sum(1 for p in pause if p['end']['quote'] + sum(p['flows'].values()) > 0)
    return [
        {'label': 'Paths that reached hour 336', 'value': f"{sum(p['last_hour'] >= 336 for p in paths)} of {len(paths)}",
         'note': f"Most stopped near hour {sorted(p['last_hour'] for p in paths)[len(paths) // 2]:g}: the inference budget ran out."},
        {'label': 'Worlds with an exit alert at hour 0', 'value': f"{sum(1 for p in pause if p['alert'] and p['alert']['hour'] == 0)} of {len(pause)}",
         'note': 'The upfront cost alone breached the loss budget.'},
        {'label': 'Paths with founder trades chosen by a model', 'value': f"{model_trades} of {len(paths)}",
         'note': 'Every founder buy and sale came from a fixed engine rule.'},
        {'label': 'Worlds where the founder token position gained', 'value': f"{position_gain} of {len(pause)}",
         'note': 'Pause policy: token value plus sales, less buys. The upfront cost is not included.'},
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--diagnostics', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    data = json.loads(args.diagnostics.read_text())
    data['headline'] = headline(data)
    payload = json.dumps(data, separators=(',', ':')).replace('</', '<\\/')
    html = PAGE.read_text().replace('/*__DATA__*/null', payload)
    output = args.output or args.diagnostics.with_name('DIAGNOSTICS.html')
    output.write_text(html)
    print('wrote', output)


if __name__ == '__main__':
    main()
