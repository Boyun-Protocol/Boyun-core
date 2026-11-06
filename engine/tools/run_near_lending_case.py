"""Run the user-selected 90-day NEAR lending case with local Laya; resumable via decision cache.

Usage: .venv/bin/python tools/run_near_lending_case.py [--days 90] [--out DIR]
Re-running with the same --out reuses every cached Laya decision, so an interrupted run
continues without repeating model calls.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

from decision_lab.lending import ENGINE_SHA256, encoded, replay_lending
from decision_lab.lending_case import run_case
from decision_lab.laya_choices import LayaChoiceClient

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / 'engine/examples/near-lending'
DEFAULTS = {'settings': 'proposed-settings.json', 'cast': 'funded-cast-proposal.json',
            'calendar': 'campaign-calendar.json', 'path': 'price-path-choppy-2025-08.json'}
MODEL = 'convaiinnovations/laya-typed-decisions'
MAX_RETRIES = 5


class BudgetedJev:
    """Jev client with a hard estimated-spend stop and bounded waits on provider cooldowns."""
    def __init__(self, client, max_cost_usd):
        self.client, self.max_cost, self.spent = client, max_cost_usd, 0.0

    def evaluate(self, *, state, questions):
        from decision_lab.jev import TypeSafeError
        if self.spent >= self.max_cost:
            raise RuntimeError(f'Jev budget reached (${self.spent:.4f} of ${self.max_cost}); rerun to resume')
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.evaluate(state=state, questions=questions)
                break
            except TypeSafeError as error:
                if error.retry_after_seconds is None or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(min(error.retry_after_seconds, 300) + 1)
        self.spent += response['receipt']['input_cost_estimate_usd']
        return response


def actor_client(args):
    if args.actor_model == 'laya':
        return LayaChoiceClient(MODEL), MODEL
    from decision_lab.env_config import load_env_key
    from decision_lab.jev import TypeSafeClient
    key = load_env_key(args.env_file, name='TYPESAFE_API_KEY')
    return BudgetedJev(TypeSafeClient(api_key=key, model='jev-latest'), args.max_cost_usd), 'jev-latest'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--out', default=str(ROOT / 'engine/output/near-lending-case-2026-11-05'))
    parser.add_argument('--actor-model', choices=('laya', 'jev'), default='laya')
    parser.add_argument('--env-file', help='explicit file holding TYPESAFE_API_KEY (jev only)')
    parser.add_argument('--max-cost-usd', type=float, default=0.25, help='hard estimated Jev spend stop')
    for key, name in DEFAULTS.items():
        parser.add_argument(f'--{key}', default=name, help='file name inside the case folder')
    args = parser.parse_args()
    inputs = [getattr(args, key) for key in DEFAULTS]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = {name: (CASE / name).read_bytes() for name in inputs}
    data = [json.loads(raw[name]) for name in inputs]
    started = time.monotonic()
    client, model = actor_client(args)
    result = run_case(*data, client, days=args.days, cache_path=out / 'decisions.jsonl')
    report = result['pool'].report()
    replay_lending(report)
    (out / 'kernel-report.json').write_text(json.dumps(report, indent=1) + '\n')
    for key in ('decisions', 'campaign', 'daily', 'triggers'):
        (out / f'{key}.json').write_text(json.dumps(encoded(result[key]), indent=1) + '\n')
    manifest = {'kind': 'near_lending_case_run', 'model': model, 'days': args.days,
                'estimated_new_spend_usd': round(getattr(client, 'spent', 0.0), 6),
                'inputs_sha256': {n: sha256(b).hexdigest() for n, b in raw.items()},
                'engine_sha256': ENGINE_SHA256, 'model_calls': result['calls'],
                'aware_since_hour': result['aware_since'], 'replay_passed': True,
                'elapsed_seconds': round(time.monotonic() - started, 1),
                'limitations': 'Synthetic cast and calendar; real replayed NEAR prices scaled to the 2026-11-05 '
                               'level. Laya scores are not calibrated odds. Not a forecast.'}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(json.dumps(manifest['model_calls']), manifest['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    main()
