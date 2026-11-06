"""Run the accepted MACRON matrix; native paths stop honestly at the shared dollar cap."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from datetime import datetime, timezone
import json
from pathlib import Path

from decision_lab.agent_orchestration import _Artifacts
from decision_lab.agent_worlds import digest
from decision_lab.env_config import load_env_key
from decision_lab.event_schedule import calendar_sessions
from decision_lab.io_helpers import read_json
from decision_lab.jev import TypeSafeClient
from decision_lab.launch_decision_policy import decision_schedule, HOUR
from decision_lab.launch_lifecycle import LaunchLifecycle, LIFECYCLE_HASH
from decision_lab.lifecycle_runs import (SpendGuard, RUNNER_HASH, lifecycle_targets, review_lifecycle,
                                          step_choices, run_lifecycle, replay_lifecycle)


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'engine/output/cases/macron-solana-2026-10-29'


def build_package(position_usd, upfront_usd, regime):
    calendar = read_json(ROOT / 'docs/decision-lab/MACRON_EVENT_CALENDAR.json')
    sessions = calendar_sessions(calendar)
    actors = [
        ('founder', 'founder', 'Maximize controlled realizable cash; protect the reserve and compare responses, not price hype.', 0, 20000),
        ('market-maker', 'mm', 'Manage own inventory, fees and adverse selection; obey delivered team pause instructions.', 1025000, 50000),
        ('retail-momentum', 'retail', 'Trade public momentum within own small wallet; exit reversals.', 40000, 10000),
        ('retail-contrarian', 'retail', 'Wait for public dislocations; buy only when own downside appears bounded.', 37500, 9375),
        ('retail-skeptic', 'retail', 'Protect own cash; demand evidence beyond paid ads, sell deteriorating holdings.', 77500, 19375),
        ('retail-patient', 'retail', 'Build a small community position only when current participation supports it.', 77500, 19375),
        ('large-buyer', 'large_holder', 'Use own cash only where real exit depth supports position size; avoid chasing shallow pools.', 5250000, 250000),
        ('attention-trader', 'trader', 'Trade changing attention; reduce exposure when public catalysts and volume fade.', 260000, 65000),
        ('kol-a', 'kol', 'Deliver a disclosed sponsorship; manage acquired tokens without promising returns.', 0, 15000),
        ('kol-b', 'kol', 'Protect audience trust and own holdings; advertising is not demand evidence.', 0, 15000),
        ('kol-c', 'kol', 'Explain French political schedule uncertainty; do not invent vote results.', 0, 15000),
        ('kol-d', 'kol', 'Cover a French meme for a global audience; assess relevance and own inventory.', 0, 15000),
        ('meme-curator', 'organic', 'Share voluntarily only when public content remains relevant; no trading capital.', 0, 0),
        ('organic-supporter', 'organic', 'Participate voluntarily, stop when the story is stale; no paid endorsement.', 0, 0),
        ('campaign-operator', 'partnership', 'Deliver the funded campaign within scope; assess real responses, not promised pumps.', 0, 0),
        ('foundation', 'foundation', 'Cross-promote credible ecosystem discussion; reject unsupported price claims.', 0, 0),
    ]
    events = [{'id': row['id'], 'second': row['elapsed_seconds'],
               'text': 'Scheduled Assembly session, not a known vote result: ' + row['topic'],
               'source_ref': 'https://www.assemblee-nationale.fr/dyn/static/seance/conference.pdf',
               'evidence_status': 'dated_schedule_assumption; later_capture_not_independently_archived_asof'} for row in sessions]
    events.insert(0, {'id': 'launch-plan', 'second': 0,
                      'text': 'User-planned MACRON launch. US federal election is scheduled for Nov 3; exact results and token effects are unknown.',
                      'source_ref': 'User launch plan and FEC election-date reference; not an outcome forecast.',
                      'evidence_status': 'user_plan_and_date_only_context'})
    campaigns = [{'id': 'launch-post', 'due_second': 0, 'expires_second': 6 * HOUR, 'delivery_bps': 10000,
                   'text': 'Conditional executed launch publication; no audience-conversion guarantee.'},
                 {'id': 'token-info', 'due_second': 12 * HOUR, 'expires_second': 14 * 24 * HOUR, 'delivery_bps': 10000,
                  'text': 'Conditional paid token-information delivery; not a Boost or verified endorsement.'}]
    for index, hour in enumerate((1, 6, 24, 72)):
        campaigns.append({'id': 'kol-' + 'abcd'[index], 'due_second': hour * HOUR,
                           'expires_second': (hour + 12) * HOUR, 'delivery_bps': 10000,
                           'text': 'Conditional funded, disclosed KOL publication. Timing is a staged campaign hypothesis, not an actual contract.'})
    return {'schema_version': 'launch-lifecycle.v1', 'id': f'macron-{regime.lower()}-p{position_usd}-c{upfront_usd}',
            'start_time': '2026-11-02T08:00:00Z',
            'decision_seconds': decision_schedule([row['elapsed_seconds'] for row in sessions]),
            'supply': 1000000000, 'curve_inventory': 793100000,
            'virtual_cash_cents': 270000, 'virtual_tokens': 1073000000,
            'fee_bps': 100, 'max_slippage_bps': 1500,
            'founder': {'id': 'founder', 'capital_cents': 5000000, 'reserve_cents': 1000000,
                        'position_cents': position_usd * 100, 'upfront_cents': upfront_usd * 100,
                        'loss_budget_cents': 1000000, 'response_delay_seconds': 600},
            'actors': [{'id': actor, 'role': role, 'goal': goal, 'cash_cents': cash, 'ticket_cents': ticket}
                       for actor, role, goal, cash, ticket in actors],
            'kol_ids': ['kol-a', 'kol-b', 'kol-c', 'kol-d', 'campaign-operator'],
            'kol_cash_cents': 300000, 'kol_supply_bps': 300,
            'events': events, 'campaigns': campaigns, 'regime': regime, 'activity_multiplier': 1,
            'assumptions': [
                'Conditional estimate, not an observed token or calibrated forecast. Static 1% fees and simplified immediate migration omit the exact program, MEV, chain delay and creator-fee collection.',
                'Virtual reserves price the curve; only real cash paid by funded actors can leave it. SOL/USD is held at the explicit 90 USD scenario assumption, not a live price.',
                'Actor endowments use the saved library-range midpoints, not observed people. A fourth retail splits the original momentum wallet into 400/375 USD; no extra cash is created to restore sixteen actors.',
                'KOL/operator cash totals 3000 USD inside upfront costs, with equal 600 USD payments. The 3% token grant comes only from founder-purchased tokens, never free mint allocations.',
                'Upfront cost envelopes are assumed fully spent once. Token Info and staged paid posts are included, not charged again; private reach/conversion evidence is unavailable.',
                'Campaign delivery is a conditional fully-delivered plan, not 100% empirical reliability. Exact delivery timing and twelve-hour exposure are uncalibrated staging hypotheses.',
                'The dated Assembly agenda is a scenario schedule with later capture; it does not disclose votes or actual future announcements. No fitted six-to-twelve-month audience-arrival model exists.',
                'BULL and BEAR are qualitative risk-appetite hypotheses in actor context, not an inferred current regime. The artificial 4x activity stress is a separate offline reference arm.',
                'Human response is modeled at ten minutes within the accepted under-thirty-minute bound. MM instruction latency is one minute. Compare response branches; neither latency is an observed contract.',
                'The reserve is inaccessible to discretionary trading. The loss-budget alert uses an estimated current liquidation quote, not a guaranteed stop fill or paper market cap.',
                'Context stores cumulative own activity, last own choice, recent public prices, available campaigns, recent dated topics and delivered private instructions. Full states persist on disk; this is bounded memory, not omniscient perfect recall.',
            ]}


def evidence_register(package):
    claims = [
        {'id': 'scenario-constraints', 'kind': 'input', 'status': 'assumed', 'depends_on': [],
         'statement': 'User-selected budgets, reserve, horizon and volume/response rules plus explicitly bounded resource and execution hypotheses.',
         'rationale': 'Finite funded wallets and explicit controls make costs, exits and loss exposure testable without duplicating capital. Scope and assumptions are retained in package.assumptions.',
         'sensitivity': 'Compare all six accepted position/upfront combinations, both conditional regimes and both response policies at common seeds; compare the separately labeled 4x offline load arm.',
         'falsification': 'Reject any interpretation as observed wallet wealth, vendor invoices, known future results or verified market timing; replace hypotheses with applicable dated observations when available.'},
        {'id': 'conditional-delivery', 'kind': 'probability', 'status': 'assumed', 'depends_on': ['scenario-constraints'],
         'statement': 'Condition on the funded launch/KOL plan being delivered; actor responses remain independent constrained choices.',
         'probability_kind': 'assumed_probability', 'uncertainty': 'A fully delivered conditional scenario is not an empirical delivery probability.',
         'rationale': 'This isolates what happens after the user-requested executed plan, rather than attributing inactivity to a plan never paid or delivered.',
         'sensitivity': 'A separate failure test sets one KOL delivery to zero; future observed delivery rates require contracts and actual timestamps.',
         'falsification': 'Reject guaranteed buying or price uplift from advertising, and reject treating this conditional delivery as real-world reliability.'},
        {'id': 'action-scores', 'kind': 'probability', 'status': 'assumed', 'depends_on': ['scenario-constraints'],
         'statement': 'Sample typed current-state Jev action scores without argmax suppression; offline references use disclosed synthetic policies instead.',
         'probability_kind': 'model_score', 'uncertainty': 'Persona, framing, model/version and missing historical calibration remain structural uncertainty.',
         'rationale': 'Fresh own-information decisions update positions and preserve alternatives while code enforces feasibility. Identical paired actor/time/seed/observations may share one receipt.',
         'sensitivity': 'Regime context, cash/cost plans and matched response branches are explicit dimensions; artificial activity changes are not silently called a BULL regime.',
         'falsification': 'Invalidate any result that leaks a private peer plan, bypasses resource limits, reuses scores across different hours/states, or labels scores calibrated event odds.'},
        {'id': 'cash-and-curve', 'kind': 'mechanism', 'status': 'derived', 'depends_on': ['scenario-constraints', 'conditional-delivery', 'action-scores'],
         'statement': 'Versioned integer estimated curve/pool settlement with conserved cash/tokens and timed founder responses.',
         'method': 'Use documented virtual-reserve constant-product form as a disclosed estimate; quote and bound real outputs, settle actual payments, exclude virtual cash from migration, and replay checkpoints. Constants follow the locally captured 30 October official pump documentation; no full venue adapter is claimed.'},
        {'id': 'conditional-outcomes', 'kind': 'outcome', 'status': 'derived', 'depends_on': ['cash-and-curve'],
         'statement': 'Recorded conditional price, turnover, liquidity and founder net cash, only through each completed path boundary.',
         'method': 'Regenerate from exact replayed states and settlements; cash profit excludes residual tokens, subtracts capital once, preserves reserve and counts prepaid costs once. Unfinished horizons have no fourteen-day terminal result.'},
    ]
    bindings = {target: 'conditional-outcomes' if kind == 'outcome' else
                'conditional-delivery' if kind == 'probability' and '/campaigns/' in target else
                'action-scores' if kind == 'probability' else 'scenario-constraints'
                for target, kind in lifecycle_targets(package).items()}
    return {'schema_version': 'simulation-evidence.v1', 'as_of': package['start_time'],
            'target_sha256': digest(package), 'sources': [], 'claims': claims, 'bindings': bindings}


def run_matrix(destination, *, mode, cap_usd='2.00', workers=4, seed=31, activity_multiplier=1):
    if mode == 'jev' and Decimal(str(cap_usd)) > Decimal('2.00'):
        raise ValueError('saved user authorization caps the full matrix at 2 USD')
    if activity_multiplier not in {1, 4} or mode == 'jev' and activity_multiplier != 1:
        raise ValueError('the separate 4x activity stress is offline only under this authorization')
    root = _Artifacts(destination)
    if mode not in {'offline_reference', 'jev'}:
        raise ValueError('explicit matrix mode required')
    if not 1 <= workers <= 4:
        raise ValueError('one to four independent case workers required')
    guard = SpendGuard(cap_usd)
    key = load_env_key(ROOT / '.env', name='TYPESAFE_API_KEY') if mode == 'jev' else None
    groups = []
    for position in (5000, 10000, 15000):
        for upfront in (5000, 10000):
            for regime in ('BULL', 'BEAR'):
                package = build_package(position, upfront, regime)
                package['activity_multiplier'] = activity_multiplier
                register = evidence_register(package)
                audit = review_lifecycle(package, register)
                group = {'id': package['id'], 'cache': {}, 'runs': [],
                          'client': TypeSafeClient(api_key=key, model='jev-1.14.0', http_client='curl', timeout_seconds=60) if key else None}
                for policy in ('pause-and-observe', 'staged-exit'):
                    directory = root.root / package['id'] / policy
                    store = _Artifacts(directory)
                    store.new('package.json', package)
                    store.new('evidence-register.json', register)
                    engine = LaunchLifecycle(package, seed, policy)
                    manifest = {'schema_version': 'launch-lifecycle-run.v1', 'engine_sha256': LIFECYCLE_HASH,
                                'runner_sha256': RUNNER_HASH, 'status': 'running',
                                'mode': 'jev' if mode == 'jev' else 'offline_reference_not_jev',
                                'seed': seed, 'response_policy': policy, 'completed_steps': 0, 'model_calls': 0,
                                'evidence_audit': audit if key else None, 'error': None, 'summary': engine.summary()}
                    store.new('manifest.json', manifest)
                    group['runs'].append({'store': store, 'engine': engine, 'manifest': manifest})
                groups.append(group)
    matrix = {'schema_version': 'macron-lifecycle-matrix.v1', 'mode': mode, 'status': 'running',
              'authorized_cap_usd': str(cap_usd), 'authorization': 'User selected 2 USD across the full matrix; explicitly mark unfinished paths when cap is reached.',
              'scenario_count': 24, 'independent_seed_count_per_plan': 1, 'completed_paths': 0,
              'completed_steps': 0, 'budget': guard.snapshot(), 'paths': [],
              'research_status': 'Conditional assumptions; six-to-twelve-month empirical arrival calibration is not available.'}
    matrix['activity_multiplier'] = activity_multiplier
    matrix['stress_label'] = 'ARTIFICIAL 4x ACTIVITY STRESS / not a forecast' if activity_multiplier == 4 else None
    root.new('matrix.json', matrix)

    def advance_group(group):
        for run in group['runs']:
            manifest, engine, store = run['manifest'], run['engine'], run['store']
            if manifest['status'] != 'running':
                continue
            try:
                engine.prepare()
                selections, evidence = step_choices(engine, client=group['client'], store=store, guard=guard,
                                                    mode=mode, cache=group['cache'] if key else None)
                checkpoint = engine.advance(selections)
                store.new(f'step-{checkpoint["step"]:05d}.json', {'checkpoint': checkpoint, 'decision_evidence': evidence})
                manifest['completed_steps'] += 1
                manifest['model_calls'] += sum(item.get('new_model_calls', 0) for item in evidence.values())
                manifest['summary'] = engine.summary()
                if engine.index == len(engine.schedule):
                    manifest['status'] = 'completed'
            except Exception as error:
                manifest['status'] = 'budget_exhausted' if isinstance(error, ValueError) and 'budget' in str(error) else 'failed'
                manifest['error'] = {'code': getattr(error, 'code', 'stopped_before_next_complete_barrier'),
                                     'message': 'No fabricated continuation or automatic retry. Partial dispatch receipts remain private.'}
            store.replace('manifest.json', manifest)
        return group

    with ThreadPoolExecutor(max_workers=workers) as executor:
        cycle = 0
        while any(run['manifest']['status'] == 'running' for group in groups for run in group['runs']):
            active = [group for group in groups if any(run['manifest']['status'] == 'running' for run in group['runs'])]
            list(executor.map(advance_group, active))
            cycle += 1
            matrix['completed_paths'] = sum(run['manifest']['status'] == 'completed' for group in groups for run in group['runs'])
            matrix['completed_steps'] = sum(run['manifest']['completed_steps'] for group in groups for run in group['runs'])
            matrix['budget'] = guard.snapshot()
            matrix['paths'] = [{'case': group['id'], 'policy': run['manifest']['response_policy'],
                                'status': run['manifest']['status'], 'completed_steps': run['manifest']['completed_steps'],
                                'summary': run['manifest']['summary']} for group in groups for run in group['runs']]
            root.replace('matrix.json', matrix)
            if cycle % 12 == 0 or matrix['completed_paths'] == 24:
                print(json.dumps({'cycle': cycle, 'paths_complete': matrix['completed_paths'],
                                  'completed_steps': matrix['completed_steps'], 'budget': matrix['budget']}, separators=(',', ':')), flush=True)
            if any(run['manifest']['status'] == 'failed' for group in groups for run in group['runs']):
                for group in groups:
                    for run in group['runs']:
                        if run['manifest']['status'] == 'running':
                            run['manifest']['status'] = 'stopped_after_peer_failure'
                            run['store'].replace('manifest.json', run['manifest'])
                break
    matrix['status'] = 'completed' if matrix['completed_paths'] == 24 else 'partial_budget_limited' if any(
        run['manifest']['status'] == 'budget_exhausted' for group in groups for run in group['runs']) else 'failed'
    matrix['budget'] = guard.snapshot()
    matrix['paths'] = [{'case': group['id'], 'policy': run['manifest']['response_policy'],
                        'status': run['manifest']['status'], 'completed_steps': run['manifest']['completed_steps'],
                        'summary': run['manifest']['summary']} for group in groups for run in group['runs']]
    root.replace('matrix.json', matrix)
    return matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--mode', choices=('offline_reference', 'jev'), required=True)
    parser.add_argument('--cap-usd', default='2.00')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--activity-multiplier', type=int, choices=(1, 4), default=1)
    parser.add_argument('--seed', type=int, default=31)
    args = parser.parse_args()
    if args.mode == 'jev' and Decimal(args.cap_usd) > 2:
        raise ValueError('saved user authorization caps this experiment at 2 USD')
    result = run_matrix(args.output_dir, mode=args.mode, cap_usd=args.cap_usd, workers=args.workers, seed=args.seed,
                        activity_multiplier=args.activity_multiplier)
    print(json.dumps({'status': result['status'], 'paths_complete': result['completed_paths'], 'budget': result['budget']}, indent=2))


if __name__ == '__main__':
    main()
