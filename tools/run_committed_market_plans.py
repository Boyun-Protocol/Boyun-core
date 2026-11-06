"""Historical 48-hour mechanics helper, not the requested full fourteen-day run."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path

from decision_lab.campaign_orchestration import run_campaign_experiment
from decision_lab.campaign_stress import stress_config
from decision_lab.campaign_evidence import campaign_evidence_context, review_campaign_evidence
from decision_lab.campaign_stress import stress_package
from decision_lab.env_config import load_env_key
from decision_lab.jev import TypeSafeClient
from decision_lab.io_helpers import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bull-evidence', required=True)
    parser.add_argument('--bear-evidence', required=True)
    args = parser.parse_args()
    base = Path('engine/output/cases/macron-solana-2026-10-29')
    root = base / 'committed-plans-2026-11-02'
    package = json.loads(Path('engine/examples/macron-campaign-world.v1.json').read_text())
    package['id'] = 'macron-committed-marketing'
    package['campaigns'].append({'id': 'launch-post', 'price_cents': 10000, 'delay_seconds': 0,
                                 'duration_seconds': 21600, 'delivery_bps': 10000,
                                 'public_text': 'SIMULATED EXECUTED LAUNCH POST: MACRON launch announcement is published to the modeled public audience. Paid campaign disclosure: no verified real-world endorsement, measured reach or guaranteed buyers.',
                                 'source_ref': 'User requested plan execution. Hypothetical 100 USD production/publication cost, immediate delivery and 6h visibility; not a vendor quote.',
                                 'evidence_status': 'assumed', 'audience': ['public']})
    for actor in package['actors']:
        if actor['id'] == 'marketing-partner':
            actor['campaign_ids'].append('launch-post')
            actor['goal'] = 'A funded launch post, Token Info and KOL publication plan is already committed and executed by the scenario. Assess delivered results, remaining own marketing cash and possible next actions; do not mistake the remaining balance for the pre-plan budget.'
    package['assumptions'].append('MATCHED COMMITTED PLAN: marketing-partner pays 899 USD at root for a 100 USD launch post, 299 USD Token Info and 500 USD KOL order. Token Info delivery takes 12h; KOL delivery takes 1h with an assumed 80% success rate. Public visibility reaches this finite actor cast, not newly generated wallets. No real service or trade is purchased.')
    commitments = [{'payer': 'marketing-partner', 'campaign_id': product, 'order_second': 0}
                   for product in ('launch-post', 'token-info', 'kol-publication')]
    evidence = {'BULL': read_json(args.bull_evidence), 'BEAR': read_json(args.bear_evidence)}
    for arm in ('BULL', 'BEAR'):
        stress = stress_config() if arm == 'BULL' else None
        effective = stress_package(package, stress) if stress else package
        review_campaign_evidence(evidence[arm], campaign_evidence_context(effective, commitments=commitments, stress=stress))
    root.mkdir(mode=0o700)
    (root / 'committed-package.json').write_text(json.dumps(package, indent=2))
    (root / 'committed-plan.json').write_text(json.dumps(commitments, indent=2))
    key = load_env_key('.env', name='TYPESAFE_API_KEY')
    def run(arm):
        client = TypeSafeClient(api_key=key, model='jev-1.14.0', http_client='curl', timeout_seconds=60)
        result = run_campaign_experiment(package=deepcopy(package), client=client,
                                         output_dir=root / arm, worlds=4, max_calls=2048, seed=31,
                                         stress=stress_config() if arm == 'BULL' else None,
                                         commitments=commitments, evidence_register=evidence[arm])
        print(json.dumps({'arm': arm, 'status': result['status'], 'completed_calls': result['completed_calls'],
                          'error': result['error']}), flush=True)
        return result
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, arm) for arm in ('BULL', 'BEAR')]
        results = [future.result() for future in futures]
    if not all(result['status'] == 'completed' for result in results):
        print('A committed-plan arm stopped. Inspect its private manifest. No automatic retry.', flush=True)
        return
    from build_market_regime_reports import build
    destination = root / 'reports'
    build(root / 'BULL', root / 'BEAR', destination, 'docs/decision-lab/MACRON_COMMITTED_PLAN_RESULTS.md')
    print('Saved completed committed-plan reports: ' + str(destination), flush=True)
    from export_market_regime_deck import main as export_deck
    export_deck(destination)


if __name__ == '__main__':
    main()
