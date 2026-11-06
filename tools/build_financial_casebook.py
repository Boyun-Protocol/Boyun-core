"""Build a three-volume financial casebook from frozen MACRON lifecycle records.

No inference or simulation is dispatched. Original reports and run records are
read-only inputs. Every exhibit includes machine-readable values and provenance.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
import re

from decision_lab.agent_worlds import digest
from decision_lab.lifecycle_runs import replay_lifecycle


MODES = {'native': 'Native Jev · unfinished', 'offline_reference': 'Offline reference',
         'offline_stress_4x': 'Offline artificial 4x activity'}
ROOTS = {'native': 'native-jev', 'offline_reference': 'offline-reference',
         'offline_stress_4x': 'offline-stress4x'}
COLORS = ['#1C1D18', '#F47B3B', '#2A52D1', '#D9A100', '#4C8A2E', '#D6679F', '#7A786C']  # sticker identity: ink, orange sun, cobalt, gold, green, pink, grey
ACTS = ['Buy', 'Sell', 'Wait', 'Publish', 'Other']
GROUPS = ['Founder', 'Market maker', 'Large buyer', 'Retail', 'KOL / operator', 'Attention trader', 'Community']
RESEARCH = [
    ('State of DeFi 2025', 'state-of-defi-2025'),
    ('Curation as an Infrastructure Layer: kpk', 'curation-as-an-infrastructure-layer-kpks-design-philosophy'),
    ('Risk-Aware DeFi: Credora', 'the-year-of-riskaware-defi-credora-ratings-as-the-1t-unlock-primitive'),
    ('Tokenized Equities', 'tokenized-equities-approach-1b-mark-as-institutional-rails-emerge'),
    ('The Katana Flywheel', 'report-katana-flywheel-rethinking-incentives-liquidity-for-sustainability'),
    ('Katana: ve(3,3) at Chain Level', 'katana-bringing-ve33-to-the-chain-level'),
    ('World Crypto Rankings', 'bybit-report-the-world-crypto-rankings'),
    ('State of RWAfi Q1 2026', 'the-state-of-rwafi-q1-2026-report'),
]


def money(value):
    return 'Unknown' if value is None else ('−' if value < 0 else '') + f'${abs(value):,.2f}'


def action(value):
    if value.startswith('buy'):
        return 'Buy'
    if value.startswith('sell'):
        return 'Sell'
    return {'wait': 'Wait', 'publish': 'Publish'}.get(value, 'Other')


def group(actor):
    if actor == 'founder':
        return 'Founder'
    if actor == 'market-maker':
        return 'Market maker'
    if actor == 'large-buyer':
        return 'Large buyer'
    if actor.startswith('retail'):
        return 'Retail'
    if actor.startswith('kol') or actor == 'campaign-operator':
        return 'KOL / operator'
    if actor == 'attention-trader':
        return 'Attention trader'
    return 'Community'


def title_plan(path):
    return f"${path['position_usd']/1000:g}k position / ${path['upfront_usd']/1000:g}k upfront"


def paired(paths):
    result = defaultdict(dict)
    for path in paths:
        result[path['case']][path['policy']] = path
    return dict(result)


def common_rows(pair):
    left = {r['second']: r for r in pair['pause-and-observe']['rows']}
    right = {r['second']: r for r in pair['staged-exit']['rows']}
    seconds = sorted(left.keys() & right.keys())
    if not seconds:
        raise ValueError('paired paths need at least one exact common saved timestamp')
    return [(left[s], right[s]) for s in seconds]


def load_bundle(root, verify=False):
    root = Path(root).resolve()
    data = json.loads((root / 'reports/results.json').read_text())
    expected = digest({'paths': data['paths'], 'market_context': data.get('market_context')})
    if expected != data['result_sha256']:
        raise ValueError('frozen aggregate result digest does not match')
    packages, streams, inputs, checks = {}, {}, [], []
    seeds,models=set(),set()
    for path in data['paths']:
        directory = root / ROOTS[path['mode']] / path['case'] / path['policy']
        package_file, manifest_file = directory / 'package.json', directory / 'manifest.json'
        pkg = json.loads(package_file.read_text())
        manifest = json.loads(manifest_file.read_text())
        if (manifest['completed_steps'] != path['steps'] or manifest['summary'] != path['summary']
                or pkg['regime'] != path['regime'] or manifest['status'] != path['status']):
            raise ValueError('aggregate and run manifest disagree')
        packages[path['mode'], path['id']] = pkg
        seeds.add(manifest['seed'])
        for file in (package_file, manifest_file):
            inputs.append({'path': str(file.relative_to(root)), 'sha256': sha256(file.read_bytes()).hexdigest()})
        if verify:
            result = replay_lifecycle(directory)
            checks.append({'mode': path['mode'], 'id': path['id'], **result})
        if path['mode'] == 'native':
            sequence = []
            chain = sha256()
            for index in range(manifest['completed_steps']):
                raw = (directory / f'step-{index:05d}.json').read_bytes()
                chain.update(raw)
                saved = json.loads(raw)
                if index==0:
                    for decision in saved.get('decision_evidence',{}).values():
                        model=decision.get('receipt',{}).get('model_declared')
                        if model:models.add(model)
                point = saved['checkpoint']
                row = path['rows'][index]
                if (point['second'] != row['second'] or point['checkpoint_sha256'] != row['checkpoint_sha256']):
                    raise ValueError('checkpoint identity mismatch')
                if index and point['previous_hash'] != sequence[-1]['checkpoint_sha256']:
                    raise ValueError('checkpoint chain discontinuity')
                entry = {key: point[key] for key in (
                    'second', 'step', 'choices', 'settlements', 'events', 'campaigns', 'response',
                    'balances_before', 'balances_after', 'market_before', 'market_after', 'checkpoint_sha256')}
                entry['scores'] = {actor: {'probabilities': d.get('answers',{}).get('action',{}).get('probabilities',{}),
                                           'provider_choice': d.get('sampling',{}).get('provider_choice'),
                                           'sampled_choice': d.get('sampling',{}).get('sampled_choice'),
                                           'request_sha256':d.get('request_sha256'),
                                           'observation_sha256':d.get('observation_sha256')}
                                   for actor,d in saved.get('decision_evidence',{}).items()}
                sequence.append(entry)
            streams[path['id']] = sequence
            inputs.append({'path': str(directory.relative_to(root)) + '/step-*.json',
                           'files': len(sequence), 'ordered_bytes_sha256': chain.hexdigest()})
    return {'data': data, 'packages': packages, 'streams': streams, 'inputs': inputs,
            'checks': checks, 'root': root, 'verify': verify,'seeds':sorted(seeds),'models':sorted(models)}


def points_at(context, path, second):
    return [p for p in context['streams'][path['id']] if p['second'] <= second]


def flow_values(points):
    flows = {g: {'buy': 0, 'sell': 0, 'fills': 0, 'rejected': 0} for g in GROUPS}
    for point in points:
        for receipt in point['settlements']:
            row = flows[group(receipt['actor'])]
            if receipt['status'] == 'executed':
                row[receipt['side']] += receipt.get('cash_cents', 0) / 100
                row['fills'] += 1
            elif receipt['status'].startswith('rejected'):
                row['rejected'] += 1
    return flows


def choice_values(points, actor=None):
    result = Counter()
    for point in points:
        for who, choice in point['choices'].items():
            if actor is None or actor == who:
                result[action(choice)] += 1
    return result


def hourly_market(points):
    """Hourly close and executed activity; partial final hour is retained explicitly."""
    hours = defaultdict(list)
    for point in points:
        hours[point['second']//3600].append(point)
    result = []
    for hour, bucket in sorted(hours.items()):
        fills = [r for point in bucket for r in point['settlements'] if r['status'] == 'executed']
        result.append({'hour': hour, 'price': float(Fraction(bucket[-1]['market_after']['price_usd_exact'])),
                       'trades': len(fills), 'volume': sum(r.get('cash_cents', 0) for r in fills)/100,
                       'last_second': bucket[-1]['second']})
    return result


def end_activity(points):
    """Describe evidence at the last recorded point without guessing project death."""
    end=points[-1]['second'];start=max(0,end-21600)
    fills=[r for p in points if start<=p['second']<=end for r in p['settlements'] if r['status']=='executed']
    return {'start_second':start,'end_second':end,'filled_trades':len(fills),
            'volume_usd':sum(r.get('cash_cents',0) for r in fills)/100,
            'buys':sum(r['side']=='buy' for r in fills),'sells':sum(r['side']=='sell' for r in fills),
            'phase':points[-1]['market_after']['phase']}


def world_name(position, upfront):
    names={(5000,5000):'Guarded Launch', (5000,10000):'Campaign First',
           (10000,5000):'Balanced Exposure', (10000,10000):'Balanced Campaign',
           (15000,5000):'Position First', (15000,10000):'Maximum Commitment'}
    return names[(int(position),int(upfront))]


def paragraph(text):
    return {'kind': 'paragraph', 'text': text}


def table(headers, rows, note=''):
    return {'kind': 'table', 'headers': headers, 'rows': [[str(v) for v in row] for row in rows], 'note': note}


def chart(kind, title, labels, series, finding, explanation, implication, source, **kwargs):
    for s in series:
        if len(s['values'])!=len(labels):raise ValueError('exhibit series/label length mismatch')
        for v in s['values']:
            if v is None and kind in {'line','multi'}:continue
            if type(v) not in {int,float} or not math.isfinite(v):raise ValueError('exhibit values must be finite; preserve missing line values as null')
    if kind in {'line','multi'} and labels!=sorted(set(labels)):raise ValueError('line exhibit timestamps must be strictly increasing')
    return {'kind': 'chart', 'chart_kind': kind, 'title': title, 'labels': labels,
            'series': series, 'finding': finding, 'explanation': explanation,
            'implication': implication, 'source': source, **kwargs}


def section(title, *blocks):
    return {'title': title, 'blocks': list(blocks)}


def base_document(kind, title, subtitle, context):
    return {'kind': kind, 'title': title, 'subtitle': subtitle, 'asof': '3 November 2026',
            'result_sha256': context['data']['result_sha256'], 'sections': [], 'highlights': []}


def world_creation(context):
    data = context['data']
    first = next(p for p in data['paths'] if p['mode'] == 'native' and p['position_usd'] == 10000 and p['upfront_usd'] == 5000)
    pkg = context['packages']['native', first['id']]
    doc = base_document('WORLD-CREATION', 'World Creation',
                        'MACRON / experiment design, economic actors and evidence', context)
    doc['highlights'] = [
        'Six funding designs × two risk-appetite contexts × two response policies; one matched seed per design.',
        'Sixteen finite-resource roles; campaign exposure is modeled separately from actual buying.',
        'Native records are incomplete. Full fourteen-day reference and stress paths are separate calculations.']
    sec = doc['sections']
    sec.append(section('1. Mandate and reading map',
        paragraph('The decision is how to allocate a $50,000 founder budget across a MACRON launch, campaign costs and protected cash, and how pause-and-observe compares with staged exit when the declared risk rule fires. No real token, trade or campaign was executed.'),
        paragraph('Read this volume before Bear Case or Bull Case. Each case contains six funding worlds, each with two response paths. The 24 native paths are a comparison matrix, not 24 equally likely futures. Offline reference and artificial stress are supporting appendices within each world.'),
        table(['Experiment identity','Recorded value'],[
            ['Native decision model',', '.join(context['models'])+' (provider-reported identity is not independently attested)'],
            ['Execution / replay','launch-lifecycle.v1; integer cash/token accounting; saved receipt and checkpoint chain'],
            ['Declared seeds',', '.join(str(x) for x in context['seeds'])+'; one matched seed per funding design'],
            ['Evidence as-of / later captures','Declared launch cutoff 2 Nov 2026 08:00 UTC; later calendar/context captures are explicitly labeled']]),
        table(['Document', 'Question it answers'], [['World Creation', 'Who acts, what can they do, what is assumed, and how is money conserved?'],
            ['Bear Case', 'How do the funding plans proceed under a cautious risk-appetite context?'],
            ['Bull Case', 'How do the same funding plans proceed under a receptive risk-appetite context?']]),
        paragraph('Research edition date is 3 November. Launch root is 2 November 2026 at 08:00 UTC (12:00 UTC+4); target end is +336h. All comparisons disclose their actual saved endpoints.')))
    sec.append(section('2. Real-world setting and modeled relationships',
        paragraph('The case links a French political meme narrative, scheduled parliamentary discussion and an assumed Solana token launch. The Assembly agenda supports session dates and topics; it does not establish vote outcomes, public attention, token demand or price effects. Election-date context likewise supports a calendar, not a directional market forecast.'),
        table(['Relationship', 'Meaning in this model', 'Evidence boundary'], [
            ['Founder → operator / KOLs', 'Funded services and a grant drawn from purchased inventory', '$3,000 inside the upfront envelope; private reach and conversion not observed'],
            ['KOL / community → audience', 'Publications become visible information', 'Exposure is not a purchase or guaranteed arrival'],
            ['Political calendar → actors', 'Dated topics can enter permitted context', 'No verified future result or fitted attention response'],
            ['MM / large buyer / retail → venue', 'Finite wallets choose feasible buy, sell or wait actions', 'Role templates and endowments are illustrative, not identified people'],
            ['Token venue → execution', 'Conserved curve-to-pool estimate with fees and rejection', 'Not a live program adapter; MEV and dynamic fees absent']]),
        chart('flow', 'Information can influence a choice; only a funded fill changes market cash', [], [],
            'Marketing and news enter the observation channel. Money moves only through declared funding and settlement.',
            'The diagram distinguishes designed channels from a measured conversion function. No arrow assigns an empirical response rate.',
            'Inspect actor choices and fills after exposure before interpreting turnover as successful marketing.',
            'Source: native package actors/campaigns/events and launch_lifecycle.py; structural diagram, not empirical flow magnitude.',
            nodes=['Funded plan\nFounder → services', 'Public exposure\nKOLs / dated topics', 'Permitted context\nOwn state + memory', 'Actor choice\nBuy / sell / wait', 'Settlement\nCash + tokens + fees', 'New state\nRisk response / feedback'])))
    actor_rows = []
    for a in pkg['actors']:
        funds = '$50,000 controlled capital; $10,000 protected' if a['id'] == 'founder' else money(a['cash_cents']/100)
        rights = 'Own reserve and response policy; delivered instructions' if a['id'] == 'founder' else (
            'Own inventory; delivered team pause instruction' if a['id'] == 'market-maker' else 'Own wallet, bounded public memory; no peer private plan')
        actor_rows.append([a['id'], funds, a['goal'], rights])
    sec.append(section('3. Actors, incentives and information boundaries',
        paragraph('Sixteen roles do not mean sixteen observed investor types. Their goals create conflicting priorities: the founder protects controlled cash, the market maker manages inventory, the large buyer checks exit depth, retail variants differ in willingness to chase, and publishing roles can create visibility without having capital to trade.'),
        table(['Actor', 'Declared initial cash', 'Goal / incentive', 'Information'], actor_rows),
        chart('bar', 'Declared spending capacity is concentrated before the first decision',
            [a['id'] for a in pkg['actors'] if a['cash_cents'] > 0],
            [{'name': 'Initial non-founder wallet USD', 'values': [a['cash_cents']/100 for a in pkg['actors'] if a['cash_cents'] > 0]}],
            'The large-buyer role begins with $52,500, compared with $10,250 for the market maker and $375–$775 per retail wallet.',
            'These are assumed endowments. KOLs receive modeled service cash/grants later; a zero initial wallet is not proof of no later participation. Founder capital is shown separately to avoid double-counting the protected reserve.',
            'A turnover concentration result may follow partly from this funding design. Test wallet sizes before treating dominance as discovered market behavior.',
            'Source: representative native package actors; identical non-founder starting endowments across the funding matrix.', unit='USD'),
        paragraph('Each actor receives current permitted state and bounded memory. Full disk records are analyst evidence, not authority to reveal other actors’ balances or private instructions. Jev returns typed action judgments without a free-text reasoning trace.')))
    designs = sorted({(p['position_usd'], p['upfront_usd']) for p in data['paths']})
    sec.append(section('4. Funding worlds and financial accounting',
        paragraph('The six worlds isolate the tradeoff between inventory commitment and sunk launch/campaign cost. Position means a funded purchase budget, not a gift of founder tokens. Upfront envelopes are assumed spent once. The $10,000 reserve remains unavailable to discretionary trades.'),
        paragraph('These dollar amounts are user-selected scenario inputs, not measured averages for comparable launches. The available local token crawl is incomplete and selection-biased, so it does not support a defensible peer average for prices, trading volume, trader counts or marketing spend. Each chart therefore compares the selected worlds, baseline or adjacent hours, and does not imply an industry norm.'),
        table(['World design', 'Position', 'Upfront', 'Protected', 'Other uncommitted cash'],
            [[f'W{i+1} · {world_name(p,c)}', money(p), money(c), money(10000), money(50000-10000-p-c)] for i,(p,c) in enumerate(designs)]),
        chart('stack', 'Increasing position or upfront costs reduces remaining optional cash',
            [f'W{i+1}: {int(p/1000)}k / {int(c/1000)}k' for i,(p,c) in enumerate(designs)],
            [{'name': 'Protected reserve', 'values': [10000]*6}, {'name': 'Position budget', 'values': [p for p,c in designs]},
             {'name': 'Upfront expense', 'values': [c for p,c in designs]},
             {'name': 'Other uncommitted', 'values': [40000-p-c for p,c in designs]}],
            'Every design begins with the same $50,000 founder capital. Reallocation changes the exposed budget, not total wealth.',
            'This is a budget envelope, not a claim that all position capital was filled immediately. Actual fills, service payments, tokens and reserves reconcile in run receipts.',
            'Compare funding designs with their cash and retained inventory together; an expensive campaign must earn its cost through separately observed responses.',
            'Source: package founder capital/reserve/position/upfront fields; values are scenario assumptions.', unit='USD', max_value=50000),
        paragraph('No-launch is a mechanical cash baseline: $50,000 retained and zero cash change. It is not a separately sampled Jev arm or a risk-free investment benchmark. Net cash excludes retained tokens; estimated liquidation proceeds are hypothetical quotes, not executed sales or total economic profit.')))
    sec.append(section('5. Action rules, execution and response policies',
        table(['Rule', 'Declared mechanism', 'Interpretation'], [
            ['Venue', 'Virtual pricing reserves on curve; real cash tracked separately; simplified pool migration', 'Virtual cash cannot become withdrawable funds'],
            ['Fee / SOL assumption', f"Static {pkg['fee_bps']/100:g}% fee; SOL/USD assumed $90", 'Scenario inputs, not live venue terms or a quote'],
            ['Trading', 'Integer-funded orders, slippage bounds and rejection', 'A choice is an attempt; an attempt is not necessarily a fill'],
            ['6H turnover reference', 'Completed pre-decision windows; warmup until 6h; reference freezes after 48h', 'Selling and recycled cash can sustain total turnover'],
            ['Funding gate', 'At least 60% of eligible turnover peak', 'A user policy boundary, not empirical confidence'],
            ['Exit alert', 'At or below 25% of peak OR declared loss-budget condition', 'Loss condition can fire at launch; not all alerts mean a later crash'],
            ['Pause branch', 'Pause / observe under the recorded instruction timing', 'Retains exposure; not an executable liquidation guarantee'],
            ['Staged exit', 'Four planned tranches at response +0/15/30/45m; 10m response / 1m MM instruction hypotheses', 'Delay, overshoot, inventory limits and rejection remain possible']]),
        paragraph('The two response paths share the declared plan and seed. They can diverge after different actions change inventories and market state. That is a conditional policy comparison within this model, not identification of a real-market causal effect.')))
    sec.append(section('6. Calendar, information timing and campaign exposure',
        paragraph('The base schedule retains 362 decision timestamps, including every hour through day fourteen, minute launch steps and dated session boundaries. Response acknowledgements can add saved states. The political schedule is a source of information timing; it does not pre-write vote results or actor reactions.'),
        chart('timeline', 'Staged campaign delivery creates distinct observation windows',
            [c['id'] for c in pkg['campaigns']],
            [{'name': 'Starts / hours', 'values': [c['due_second']/3600 for c in pkg['campaigns']]},
             {'name': 'Ends / hours', 'values': [min(c['expires_second']/3600,48) for c in pkg['campaigns']]}],
            'KOL exposures are staged rather than represented as one instant price boost. The chart displays the first 48 hours; token information continues beyond it.',
            'Delivery is conditioned as successful in these packages. Its empirical reliability and audience conversion are unknown. Other events and actor actions overlap the exposure windows.',
            'Use event-aligned choices and executed flows to assess association. A before/after change alone cannot establish incremental marketing ROI.',
            'Source: representative native package campaigns; declared schedule, not historical reach.', unit='hours'),
        table(['Event / source', 'What is known', 'What remains unknown'], [
            ['Assembly agenda dated 27 October', 'Scheduled sessions inside the fourteen-day interval', 'Exact votes, outcomes and token effects'],
            ['3 November election date', 'Calendar context in the accepted launch plan', 'Unified result-release time or token impact'],
            ['Launch / token info / KOLs', 'Modeled delivery schedule and recorded exposure', 'Real contract performance, unique reach and purchase conversion'],
            ['Chain-wide DEX context', '184 daily observations captured after package freeze', 'MACRON-specific demand or calibration of earlier actor decisions']])) )
    sec.append(section('7. Assumption register and falsification agenda',
        table(['ID', 'Declared assumption', 'Test that could change the conclusion'],
            [[f'A{i+1:02d}', t, [
                'Replay with venue-specific fees, delay and execution constraints.',
                'Sweep numeraire and reserve values without creating real money.',
                'Sweep wallet distribution and add independently grounded arrivals.',
                'Reconcile grant and service costs to funded receipts.',
                'Compare alternative delivery/cost envelopes at matched capital.',
                'Run failed/delayed delivery arms with supported authority.',
                'Replace assumed attention response with out-of-sample event evidence.',
                'Compare context-only regimes under unchanged selection rules.',
                'Sweep latency and quantify missed/blocked exits.',
                'Reconcile quotes against actual modeled fills and residual exposure.',
                'Test memory sensitivity and private-information isolation.'
            ][i]] for i,t in enumerate(pkg['assumptions'])]),
        paragraph('These tests are a research agenda, not completed experiments. Unknown arrival rates, conversion, correlated failures, MEV, RPC outages and LP withdrawal remain unavailable unless their mechanics and inputs are implemented.')))
    native = [p for p in data['paths'] if p['mode'] == 'native']
    labels, coverage_series = [], [[], []]
    for case, pair in sorted(paired(native).items(), key=lambda kv:(kv[1]['staged-exit']['regime'],kv[1]['staged-exit']['position_usd'],kv[1]['staged-exit']['upfront_usd'])):
        p = pair['staged-exit']; labels.append(p['regime']+' '+title_plan(p))
        for j,policy in enumerate(('pause-and-observe','staged-exit')):
            coverage_series[j].append(pair[policy]['last_hour'])
    sec.append(section('8. Execution coverage, world odds and verification',
        table(['Funding design / regime', 'Pause recorded through', 'Staged exit recorded through', 'Target'],
              [[labels[i],f'+{coverage_series[0][i]:g}h',f'+{coverage_series[1][i]:g}h','+336h'] for i in range(len(labels))],
              'Source: frozen run manifests. A budget or dispatch stop is not a market event; later outcomes are unobserved.'),
        paragraph('Real-world odds for BULL, BEAR and every funded world are unknown. Each funding variant has one matched seed and was deliberately included; there is no evidence that the six variants are equally likely. Native action scores, event assumptions, sample counts and observed market frequencies are different quantities.'),
        paragraph(f"Frozen result ID: {data['result_sha256']}. This build {'independently replays all 72 source paths' if context['verify'] else 'checks aggregate identity, source manifests and native checkpoint chains; it reuses the saved replay record rather than claiming a new full replay'}. No new model calls are made.")))
    sec.append(section('9. Sources and definitions',
        *source_blocks(context)))
    return doc


def source_blocks(context):
    return [paragraph('Sources below support the real-world context or the modeled observations. Exhibit data files identify the exact underlying simulation records. Native incomplete, offline reference and artificial stress are separate evidence families.'),
        table(['Source', 'Supported use'], [
            ['French Assembly agenda · https://www.assemblee-nationale.fr/dyn/static/seance/conference.pdf', 'Dated session schedule, not vote outcomes; later capture is not independently archived as of the simulation cutoff'],
            ['US Federal Election Commission · https://www.fec.gov/introduction-campaign-finance/election-and-voting-information/', 'Election calendar context, not an election-result or token-price forecast'],
            ['Pump program documentation · https://github.com/pump-fun/pump-public-docs', 'Venue mechanism reference; runtime remains a simplified estimate'],
            ['Accepted MACRON policy and evidence registers', 'User constraints, source/assumption labels and execution boundaries'],
            ['Frozen lifecycle records · result '+context['data']['result_sha256'][:16], 'Recorded model choices, state transitions and conserved settlement']])]


def case_document(context, regime):
    data = context['data']
    live = [p for p in data['paths'] if p['mode'] == 'native' and p['regime'] == regime]
    pairs = sorted(paired(live).items(), key=lambda kv:(kv[1]['staged-exit']['position_usd'],kv[1]['staged-exit']['upfront_usd']))
    is_bear = regime == 'BEAR'
    label = 'Bear' if is_bear else 'Bull'
    doc = base_document(regime+'-CASE', label+' Case',
                        'MACRON / conditional risk appetite, actor responses and financial outcomes', context)
    deltas = []
    for case,pair in pairs:
        a,b = common_rows(pair)[-1];deltas.append(b['founder_net_cash_usd']-a['founder_net_cash_usd'])
    total_fills = sum(p['statistics']['filled_trades'] for p in live)
    doc['highlights'] = [
        f'Staged exit records more realized cash in 6 of 6 matched funding comparisons: {money(min(deltas))} to {money(max(deltas))}.',
        f'{total_fills:,} fills across 12 dependent native paths; activity is not a count of unique investors or fresh capital.',
        'One matched seed per funding design. Real-world world odds are unknown; native fourteen-day outcomes are unobserved.']
    sec = doc['sections']
    sec.append(section('1. Executive investment findings',
        paragraph(f'The {label.lower()} context does not select a winning investment. Across the six native matched comparisons, staged exit realizes more cash by {money(min(deltas))}–{money(max(deltas))}, while pause retains inventory. That answers a cash-realization question, not whether selling maximizes total wealth.'),
        paragraph('The unchanged no-launch baseline retains $50,000 cash and zero cash change. All native recorded endpoints in the accepted matrix remain cash-negative. Launch expenses, fees, acquired inventory and residual exposure explain why turnover or a high market-cap peak can coexist with a negative cash result.'),
        paragraph('Read findings in three layers: recorded actor actions and fills; supported financial mechanics; hypotheses about why a role responded. Jev supplies no economic rationale trace. A convincing narrative must not be invented in the model’s voice.'),
        table(['Finding', 'Evidence', 'Decision implication'], [
            ['Cash realization differs by response', '6 exact-common-time pairs; one seed per design', 'Compare liquidity and remaining inventory, not just terminal cash'],
            ['Participation is economically concentrated', 'Actor-level executed cash flow', 'Dependence on the large-buyer role needs wallet/arrival sensitivity'],
            ['Publications do not equal demand', 'Publications, buy attempts and fills measured separately', 'Require observed conversion before treating higher upfront cost as productive'],
            ['Fourteen-day native coverage is absent', 'All 12 native paths in this volume stopped early', 'Do not extrapolate recorded endpoints to day fourteen']])) )
    sec.append(section('2. What this case means and what it assumes',
        paragraph(('BEAR is a cautious risk-appetite hypothesis delivered to actors: preservation, selectivity and concern about exit depth can weigh against chasing publicity. ' if is_bear else
                   'BULL is a receptive risk-appetite hypothesis delivered to actors: willingness to participate in attention and momentum can be greater, within the same wallet and execution limits. ')+
                  'It is not a diagnosis of the real market, a calibrated macro regime or a forced falling/rising price path.'),
        table(['Held constant', 'Changes / uncertainty'], [
            ['$50k founder capital / $10k protected reserve', 'Six position/upfront allocations are swept explicitly'],
            ['Finite actor roster, funded campaigns and static-fee venue', 'Risk-appetite context is '+regime+'; later actor choices/state evolve'],
            ['Native sampled typed action policy; activity multiplier 1', '4x activity is a separate offline arm, not the meaning of BULL'],
            ['Same declared seed within each paired response comparison', 'Pause versus staged exit changes actions, cash and future state'],
            ['Known session schedule; fully delivered conditional campaigns', 'Vote outcomes, arrivals and campaign conversion are not calibrated']]),
        paragraph('The native regime labels are qualitative input assumptions. Actor goals and constraints must carry the mechanism; a label alone is weak evidence of behavioral realism. Future validation should compare context-only changes under matched funding and policies and examine whether actions respond meaningfully.'),
        paragraph('These two contexts were included as user-selected sensitivity arms to probe the same launch plan under different willingness-to-risk narratives. The actor-facing instruction calls BULL/BEAR conditional risk-appetite hypotheses; no observed price threshold, fitted participation multiplier or external data series establishes their present applicability. The regime label is the intervention, not an independently calibrated behavioral model.'),
        paragraph('World probability: unknown for this case and for each funding design below. There is one matched seed per design. Twelve dependent policy paths are not twelve independent market samples, and six plan variants do not imply a 1/6 chance per world.')))
    overview_labels, overview_values, inventory_values = [], [], []
    inventory_pair_rows = []
    for idx,(case,pair) in enumerate(pairs,1):
        a,b = common_rows(pair)[-1];p=pair['staged-exit'];second=a['second']
        overview_labels.append(f'W{idx} · {int(p["position_usd"]/1000)}k / {int(p["upfront_usd"]/1000)}k · +{second/3600:g}h')
        overview_values.append(b['founder_net_cash_usd']-a['founder_net_cash_usd'])
        l=points_at(context,pair['pause-and-observe'],second)[-1]['balances_after']['founder']['tokens']
        r=points_at(context,p,second)[-1]['balances_after']['founder']['tokens']
        inventory_values.append([l/1e6,r/1e6])
        inventory_pair_rows.append([f'W{idx}',f'+{second/3600:g}h',money(a['founder_net_cash_usd']),money(b['founder_net_cash_usd']),f'{l:,}',f'{r:,}'])
    sec.append(section('3. Capital comparison: cash recovery has an inventory tradeoff',
        chart('bar', 'Staged exit realizes more cash at the exact common saved time', overview_labels,
            [{'name': 'Staged minus pause · USD', 'values': overview_values}],
            f'The cash difference is positive in all six '+regime+f' funding worlds, ranging from {money(min(deltas))} to {money(max(deltas))}.',
            'Each bar is a dependent paired policy contrast at its own latest exact common timestamp, labeled beside the world. Different worlds have different cutoffs; this figure does not rank their total wealth or claim a day-fourteen result.',
            'Treat staged exit as a cash-recovery option. Check retained tokens and execution rejection before inferring that it is the better investment.',
            'Source: native rows joined on exact seconds; one seed per funding world; no endpoint extrapolation.', unit='USD'),
        chart('bar', 'Pause preserves token exposure that the cash comparison leaves out', [f'W{i+1}' for i in range(6)],
            [{'name': 'Pause · million token units', 'values':[r[0] for r in inventory_values]},
             {'name': 'Staged exit · million token units', 'values':[r[1] for r in inventory_values]}],
            'The paired branches hold different token inventories at the same comparison times.',
            'These are original ledger token units divided by one million, not independently priced wealth. An estimated liquidation quote can differ from proceeds because selling moves price, fees apply and depth is finite.',
            'Keep both cash and exposure visible. A cash-only conclusion misses the upside and downside still held by the pause branch.',
            'Source: matched native checkpoint balances_after/founder/tokens; same cutoffs as the cash exhibit.', unit='million units'),
        table(['World', 'Common time', 'Pause cash change', 'Staged cash change', 'Pause tokens', 'Staged tokens'], inventory_pair_rows)))
    # Compare regimes at common timestamps with the same funded plan and response.
    other=[p for p in data['paths'] if p['mode']=='native' and p['regime']!=regime and p['policy']=='staged-exit']
    cross_rows=[];cross_labels=[];cross_deltas=[];cross_sources=[]
    for idx,(case,pair) in enumerate(pairs,1):
        own=pair['staged-exit']
        match=next(p for p in other if p['position_usd']==own['position_usd'] and p['upfront_usd']==own['upfront_usd'])
        bear,bull=(own,match) if regime=='BEAR' else (match,own)
        a,b=common_rows({'pause-and-observe':bear,'staged-exit':bull})[-1]
        cut=a['second'];delta=b['founder_net_cash_usd']-a['founder_net_cash_usd']
        cb=choice_values(points_at(context,bear,cut));cu=choice_values(points_at(context,bull,cut))
        cross_labels.append(f'W{idx} · +{cut/3600:g}h');cross_deltas.append(delta)
        cross_rows.append([f'W{idx}',f'+{cut/3600:g}h',money(a['founder_net_cash_usd']),money(b['founder_net_cash_usd']),money(delta),
            f'{cb["Buy"]}/{sum(cb.values())}',f'{cu["Buy"]}/{sum(cu.values())}'])
        cross_sources.append({'bear':bear['id'],'bull':bull['id'],'cutoff_second':cut,
                              'bear_checkpoint':a['checkpoint_sha256'],'bull_checkpoint':b['checkpoint_sha256']})
    sec[-1]['blocks'] += [chart('bar','A Bull context does not uniformly improve realized cash',cross_labels,
        [{'name':'Bull minus Bear · USD','values':cross_deltas}],
        f'At matched staged-exit cutoffs, Bull has more realized cash in {sum(v>0 for v in cross_deltas)} of six funding designs and less in {sum(v<0 for v in cross_deltas)}.',
        'Each comparison holds the declared funding design, response policy and seed fixed and joins exact saved times. Regime context changes; later actions, execution and states can diverge. This is a descriptive model-context contrast, not a measured causal bull-market effect or an independent sample of market regimes.',
        'Inspect how the actors changed actions. A receptive context can coincide with more churn, costs or exposure; the label alone is not a profitability thesis.',
        'Source: native BEAR/BULL staged-exit rows and choices, per-design common seconds; exact path/hash map in this exhibit JSON.',
        unit='USD',paired_source_records=cross_sources),
        table(['World','Shared hour','Bear cash change','Bull cash change','Bull − Bear','Bear buy choices','Bull buy choices'],cross_rows,
            'Choice denominators are all 16 actors’ recorded decision opportunities up to the same cutoff; not unique buyers, fill counts or calibrated propensities.')]
    all_points = []
    for case,pair in pairs:
        second=common_rows(pair)[-1][0]['second']
        all_points.extend(points_at(context,pair['staged-exit'],second))
    groups=defaultdict(Counter)
    for p in all_points:
        for actor,choice in p['choices'].items():groups[group(actor)][action(choice)]+=1
    sec.append(section('4. Participation: choices, executed money and concentration',
        chart('stack', 'The participation mix distinguishes waiting, publicity and trading', GROUPS,
            [{'name':a,'values':[100*groups[g][a]/sum(groups[g].values()) if groups[g] else 0 for g in GROUPS]} for a in ACTS],
            'Publication and waiting remain separate from buy/sell choices; the bars normalize each role group to its own saved decision opportunities.',
            'This pools the six staged native branches only through each pair’s common cutoff. Role groups contain different numbers of actors; decisions are temporally dependent. Shares describe recorded menus/actions, not observed human propensities or fill rates.',
            'A busy publication lane can coexist with little buying. Validate audience conversion independently before scaling campaign spending.',
            'Source: native checkpoint choices; group denominators included in exhibit JSON.', unit='percent', max_value=100,
            denominators={g:sum(groups[g].values()) for g in GROUPS}),
        paragraph('The world chapters below compare these intentions with actual executed cash. Filled buy debits and net sell receipts are kept apart. Recycled MM cash can inflate turnover without adding a new participant; this is why volume alone is not our success measure.')))
    for index,(case,pair) in enumerate(pairs,1):
        add_world(doc,context,regime,index,case,pair)
    prefix='BR' if regime=='BEAR' else 'BU'
    hourly_worlds=[]
    for case,pair in pairs:
        cutoff=common_rows(pair)[-1][0]['second']
        hourly_worlds.append(hourly_market(points_at(context,pair['staged-exit'],cutoff)))
    hours=sorted({row['hour'] for rows in hourly_worlds for row in rows})
    compare_blocks=[paragraph('All six series use the staged-exit branch and stop at each world’s latest exact common timestamp with its pause branch. Unequal line lengths show missing coverage; they are not token failures. Each hourly endpoint is the last saved state, and the last hour can be partial.'),
        table(['Code','Name','Position purchase budget','Launch / campaign upfront'],[
            [f'{prefix}-P{int(pair["staged-exit"]["position_usd"]/1000)}U{int(pair["staged-exit"]["upfront_usd"]/1000)}',world_name(pair['staged-exit']['position_usd'],pair['staged-exit']['upfront_usd']),money(pair['staged-exit']['position_usd']),money(pair['staged-exit']['upfront_usd'])] for case,pair in pairs])]
    for field,title,unit in [('price','Simulated token price across the six worlds','USD / token'),('trades','Filled trades per hour across the six worlds','trades / hour'),('volume','Executed turnover per hour across the six worlds','USD / hour')]:
        compare_series=[]
        for (case,pair),rows in zip(pairs,hourly_worlds):
            path=pair['staged-exit'];code=f'{prefix}-P{int(path["position_usd"]/1000)}U{int(path["upfront_usd"]/1000)}';lookup={r['hour']:r[field] for r in rows}
            compare_series.append({'name':code,'values':[lookup.get(h) for h in hours]})
        compare_blocks.append(chart('line',title,hours,compare_series,
            'The six lines represent selected funding designs under one conditional regime, not six independently sampled market outcomes.',
            'Lines end at their actual paired comparison cutoff. Price is the final recorded marginal quote per hour; activity is summed within hourly bins. Early launch activity and a partial final hour can make neighboring bars or points uneven.',
            'Compare the same hours and then inspect the relevant world’s actors and event timeline. Differences may reflect funding, sampled actions, response feedback and incomplete coverage.',
            'Source: native staged-exit checkpoint market states and executed settlements; matching cutoffs are stated in each world.',unit=unit,x_unit='hours'))
    sec.append(section('10A. Comparing price and activity across all worlds',*compare_blocks))
    supporting = [p for p in data['paths'] if p['regime']==regime and p['mode']!='native']
    refpairs=paired([p for p in supporting if p['mode']=='offline_reference'])
    stresspairs=paired([p for p in supporting if p['mode']=='offline_stress_4x'])
    refdelta=[];stressdelta=[]
    for case,_ in pairs:
        l,r=common_rows(refpairs[case])[-1];refdelta.append(r['founder_net_cash_usd']-l['founder_net_cash_usd'])
        l,r=common_rows(stresspairs[case])[-1];stressdelta.append(r['founder_net_cash_usd']-l['founder_net_cash_usd'])
    sec.append(section('11. Full-horizon reference and artificial stress',
        paragraph('The twelve offline reference paths and twelve artificial 4x activity paths in this case reach +336h. They test accounting and declared synthetic behavior. They are not extensions, imputations or replacements for the incomplete native paths.'),
        chart('bar', 'Full-horizon policy differences depend on the declared synthetic behavior', [f'W{i+1}' for i in range(6)],
            [{'name':'Reference cash difference · USD','values':refdelta}, {'name':'4x stress cash difference · USD','values':stressdelta}],
            'Both series compare staged exit minus pause at +336h, using separate fully completed offline families.',
            'The 4x arm changes synthetic activity thresholds within finite-wallet constraints. It does not promise four times the real volume and is not a likely bull-market forecast. Different results expose model sensitivity.',
            'Use offline stress to test failure and resource mechanisms, then seek observed behavior before attaching probabilities or selecting an optimum.',
            'Source: offline_reference and offline_stress_4x exact-common-time rows at +336h; no native endpoints mixed.', unit='USD'),
        table(['World', 'Evidence family', 'Response', 'Hours', 'Cash change', 'Residual inventory units'],
            [[f'W{next(i for i,(c,_) in enumerate(pairs,1) if c==p["case"])}',MODES[p['mode']],p['policy'],f'{p["last_hour"]:g}',
              money(p['summary']['founder_net_cash_cents']/100),f'{p["summary"]["founder_inventory_tokens"]:,}'] for p in supporting])))
    sec.append(section('12. Risk register, decision conditions and falsification',
        table(['Risk / question', 'Coverage', 'What would change the interpretation'], [
            ['Negative cash despite trading', 'Recorded in native / offline paths', 'Reconcile costs and inventory; test lower sunk costs and better conversion'],
            ['Concentrated buying / turnover', 'Recorded, conditional on assumed wallets', 'Use grounded participant arrivals and wallet-size sensitivity'],
            ['Rejected or delayed exit', 'Saved execution and response records', 'Venue-specific depth/fees/latency may alter cash recovery'],
            ['Campaign fails to deliver', 'Main paths condition on delivery; not a sampled reliability result', 'Run explicit failed/delayed delivery arms'],
            ['LP withdrawal, MEV, RPC outage', 'Unsupported here', 'Implement mechanism and source inputs before quantifying losses'],
            ['Political surprise / late demand', 'Schedule visible; outcomes and arrival calibration absent', 'Out-of-sample event and audience evidence'],
            ['Day-fourteen native recovery', 'Unobserved after budget/dispatch stops', 'Complete separately authorized runs; no extrapolation']]),
        paragraph('The appropriate next decision is what to test, not a guaranteed trade. Compare smaller upfront costs, more conservative exposure and exit feasibility under supported data. Preserve the no-launch cash baseline. Do not combine unknown world weights into an expected-profit number.'),
        paragraph('Sources of uncertainty include actor policy, initial wallets, exposure delivery, attention, venue mechanics, random sampling and missing horizon. More model calls reduce neither all structural uncertainty nor evidence gaps.')))
    sec.append(section('13. Sources, definitions and reproduction',*source_blocks(context)))
    return doc


def technical_document(context):
    matrix=json.loads((context['root']/'native-jev'/'matrix.json').read_text())
    budget=matrix['budget']; data=context['data']; native=[p for p in data['paths'] if p['mode']=='native']
    status=Counter(p['status'] for p in native)
    choices=Counter(); score_sums=defaultdict(float); score_n=Counter()
    for points in context['streams'].values():
        for point in points:
            for actor,selected in point['choices'].items(): choices[action(selected)]+=1
            for actor,record in point['scores'].items():
                probabilities=record['probabilities']
                if probabilities:
                    g=group(actor);score_n[g]+=1
                    for option,value in probabilities.items():score_sums[g,action(option)]+=value
    subset_dir=context['root'].parent/'jev-subset-2026-11-03-bull-p10u5'
    subset_manifest=subset_dir/'manifest.json'; subset_budget=subset_dir/'budget.json'
    if subset_manifest.is_file() and subset_budget.is_file():
        sm=json.loads(subset_manifest.read_text());sb=json.loads(subset_budget.read_text())
        subset_text=(f"A fresh representative BULL $10k position / $5k upfront staged-exit path was started with a separate $0.40 estimated cap. "
                     f"At report generation its status was {sm['status']}; {sm['completed_steps']} completed barriers reached +{sm['summary']['last_second']/3600:g}h. "
                     f"The separate guard recorded {sb['completed_calls']:,} confirmed calls and estimated ${sb['spent_estimate_micro_usd']/1e6:.6f} spent, with ${sb['uncertain_reserved_micro_usd']/1e6:.6f} reserved. "
                     'This is a snapshot, not a fourteen-day result; see the separate manifest and budget for current progress.')
    else:
        subset_text='No separate 20% subset run was present when this report was generated.'
    surrogate_file=context['root'].parent/'surrogate-decision-holdout-2026-11-03.json'
    if surrogate_file.is_file():
        sr=json.loads(surrogate_file.read_text());folds=sr['folds']
        low=min(f['provider_top_choice_agreement'] for f in folds);high=max(f['provider_top_choice_agreement'] for f in folds)
        sample_low=min(f['sampled_action_agreement'] for f in folds);sample_high=max(f['sampled_action_agreement'] for f in folds)
        surrogate_text=(f"A zero-call test used {sr['unique_confirmed_decisions']:,} unique saved decisions in {sr['blocks']} case/time blocks. "
                        f"Across five folds, the mean-score baseline trained on approximately one fifth of decision records matched Jev's reported choice on {low:.1%}–{high:.1%} of supported held-out decisions, "
                        f"and matched the sampled action on {sample_low:.1%}–{sample_high:.1%}. "
                        'The comparison uses recorded states and feasible menus from one seed; it does not validate a closed-loop trajectory, later unseen states, market realism, or a fourteen-day forecast. Full fold counts and per-actor results are in the separate holdout JSON.')
    else:
        surrogate_text='No independent holdout results were present at report generation.'
    doc=base_document('TECHNICAL-REPORT','Technical Report','MACRON / execution, evidence, decisions and project record',context)
    doc['highlights']=[f"{budget['completed_calls']:,} confirmed Jev calls; {budget['attempted_calls']-budget['completed_calls']} dispatches have no confirmed response.",
        f"Estimated provider usage ${budget['spent_estimate_micro_usd']/1e6:.6f} against the original $2 shared cap; actual billing is not verified.",
        'Native paths are incomplete; alternative full-horizon calculations are explicitly offline.']
    doc['sections']=[
        section('1. Execution summary and scope',
            paragraph('This report documents the saved experiment and its limits. The case reports interpret financial scenarios; this technical volume explains how evidence was generated and what would be needed to improve it.'),
            table(['Measure','Recorded value','Interpretation'],[
                ['Confirmed provider calls',f"{budget['completed_calls']:,}",'Includes confirmed calls in unfinished barriers'],
                ['Attempted dispatches',f"{budget['attempted_calls']:,}",'Includes three with unknown outcomes'],
                ['Published-tariff estimate',f"${budget['spent_estimate_micro_usd']/1e6:.6f}",'Estimated from provider-reported input usage, not an invoice'],
                ['Uncertain reservations',f"${budget['uncertain_reserved_micro_usd']/1e6:.6f}",'Held against cap for unknown dispatches'],
                ['Native checkpoints',f"{matrix['completed_steps']:,}",'Complete decision barriers only'],
                ['Native completed paths',f"{matrix['completed_paths']} / {len(native)}",'Target +336 hours'],
                ['Stops',', '.join(f'{v} {k}' for k,v in sorted(status.items())),'Inspect source manifests for path-specific status']]),
            paragraph('The cap is a local guard using the published tariff and estimated reservation. It is not a billing receipt. Unknown calls remain reserved and must not be silently retried or counted as failures.')),
        section('2. Decision pipeline and model information',
            paragraph('For each saved barrier, each actor receives its role, public market, own resources, bounded memory, campaign and event context, and a feasible menu. The provider returns typed menu scores; the seeded sampler chooses an action. Forced choices do not require a provider call. The engine then applies funding, transaction and execution rules, producing receipts and a chained checkpoint.'),
            paragraph('The recorded responses do not include a free-text chain of reasoning or an attributable ranking of which inputs the model considered most. The aggregates below describe outputs, not the model’s private reasoning or evidence of causal importance.'),
            table(['Actor group','Scored menus','Mean buy score','Mean sell score','Mean wait score'],[
                [g,f'{score_n[g]:,}',*[f'{score_sums[g,a]/score_n[g]:.1%}' if score_n[g] else 'Unavailable' for a in ('Buy','Sell','Wait')]] for g in GROUPS],
                'Menu availability changes with actor holdings and constraints. Mean action scores are model outputs, not calibrated real-world odds; options outside these categories remain in the denominator.'),
            paragraph('Across saved native barriers, selected actions are '+', '.join(f'{name}: {choices[name]:,}' for name in ACTS)+'. These are dependent, repeated decisions, not unique people or independent scenarios.')),
        section('3. Coverage, blockers and 20% approach',
            paragraph('Twenty-one paths stopped at the shared budget guard and three have unresolved dispatches. This does not establish a provider-wide Jev outage: the guard stopped the next dispatch when available funds were insufficient. A path can only advance after its entire decision barrier is committed.'),
            paragraph('A smaller set of fully simulated paths can provide deeper examples, but cannot establish the other worlds’ trajectories. A 20% sampling or surrogate approach must specify which paths and decision opportunities are sampled, maintain independent validation, show differences against held-out native decisions, and label all generated continuations as approximations. A provider score is not a calibrated forecast. The existing full-horizon offline paths are a separate rule-based reference, not Jev-generated missing outcomes.'),
            paragraph('The historical $2 cap is exhausted. Preserve the frozen evidence and never overwrite or redispatch an unresolved request.'),
            paragraph(subset_text),paragraph(surrogate_text)),
        section('4. Data integrity and reproducibility',
            table(['Artifact','Function / limitation'],[
                ['matrix.json and per-path manifests','Budget ledger, completion status, seed, run summaries'],
                ['step-NNNNN.json','Checkpoint, selected choices, settlements and model decision evidence'],
                ['Call requests, responses and dispatch records','Provider usage receipts and unresolved dispatch accounting'],
                ['Financial exhibit JSON','Values, denominators, transformations and source identifiers'],
                ['Offline reference and 4x stress','Completed synthetic mechanics, separate from native Jev outcomes']]),
            paragraph('The report builder verifies the aggregate identity and checkpoint chain. Exact replay is a separate optional operation and makes no model calls. The simulation has one matched seed per design; additional seeds and held-out validation are required before estimating uncertainty.')),
        section('5. User and agent decision record',
            paragraph('The entries below are a concise, reconstructed decision record from the available conversation and accepted project documents. They are not a complete verbatim transcript. Earlier details are attributed to the project’s confirmed policy and acceptance records.'),
            table(['Topic / user direction','Agent response or resulting decision'],[
                ['Fourteen-day scope','Hourly and event-based dynamics retained; report incomplete native coverage honestly.'],
                ['Six-hour volume and crash response','Use total traded volume and matched pause-versus-staged-exit policies.'],
                ['Original Jev spend','User authorized a $2 shared cap across the matrix, with unfinished paths explicitly disclosed.'],
                ['Financial presentation','World Creation, Bear and Bull volumes, early contents, meaningful actor and event charts.'],
                ['Report corrections','Fix chart scales, name worlds, add market timelines, crowd/actor analysis and useful contextual references.'],
                ['Smaller Jev sample and extension','User proposed 20% scale and generating remaining cases; any modeled inference must be validated and clearly labeled.'],
                ['Current package direction','Add a technical report and decision record; generalize repeatable guidance for future cases.']]),
            paragraph('The records do not retain every question, answer, or rationale from earlier conversations. Future cases should append decisions at the time they happen, distinguish user statements from agent interpretations, and avoid inventing missing dialogue.')),
        section('6. Limitations and next validation',
            table(['Question','State','Next evidence'],[
                ['Full native fourteen-day outcomes','Not observed','Run a budget-bounded representative subset with honest coverage labels'],
                ['Predicting unrun paths','Not validated','Hold out observed paths; compare price, flows, actor choices and failure rates'],
                ['Partner negotiation and dedication','Not modeled','Add negotiated menus, costs, conditions, timing and grounded inputs'],
                ['Comparable token and user averages','Insufficient cohort','Construct a sourced, matched and time-aligned benchmark'],
                ['Provider consideration / reasoning','Not exposed','Treat score sensitivity experiments as output sensitivity, not hidden reasoning'],
                ['Real-world probabilities','Uncalibrated','Independent historical evaluation with uncertainty and leakage controls']]))]
    return doc


def decision_record_document(context):
    case_root=context['root'].parent
    state_file=case_root/'world-grounding-2026-10-30/interview-state.round-nineteen.json'
    state=json.loads(state_file.read_text())
    doc=base_document('DECISION-RECORD','User and Agent Decision Record',
                      'MACRON / available interview questions, answers and later directions',context)
    doc['highlights']=['A source-linked interview record, not a complete chat transcript.',
                       'Original answer text is retained where the local record provides it.',
                       'Later decisions can supersede earlier assumptions; consult the case reports for the executed policy.']
    doc['sections']=[section('1. Scope and how to read this record',
        paragraph('This volume preserves the questions and answers available in the local structured interview and summarizes the later directions visible to this report builder. Some prompts appeared only inline in conversation and were not archived as separate question files. Those prompts are marked unavailable; they are not reconstructed as quotations.'),
        paragraph('A recorded answer reflects the decision at that interview stage. Later approved policies or corrections can supersede it; this log is not itself the current simulation specification.'))]
    for entry in state['interview_rounds']:
        answers_file=case_root/entry['answers']
        if not answers_file.exists():continue
        answers=json.loads(answers_file.read_text())
        qfile=case_root/entry.get('file','__no_file__')
        qmap={}
        if qfile.is_file():
            qdata=json.loads(qfile.read_text())
            for q in qdata.get('questions',[]):
                if isinstance(q,dict):qmap[q.get('id')]=q.get('question','Question text unavailable')
        rows=[]
        for answer in answers.get('answers',[]):
            if not isinstance(answer,dict):continue
            qid=answer.get('question_id',answer.get('id','Unidentified'))
            received=answer.get('answer_as_received',answer.get('answer','Unavailable in structured record'))
            if isinstance(received,(dict,list)):received=json.dumps(received,ensure_ascii=False)
            rows.append([qid,qmap.get(qid,'Exact prompt was not archived in a separate question file.'),str(received)])
        if not rows:
            rows=[['Record','Structured directions; no answer array',json.dumps(answers,ensure_ascii=False)[:500]+' … See source file for the full record.']]
        doc['sections'].append(section(f'{len(doc["sections"])+1}. Interview round {entry["round"]}',
            paragraph(f'Answer record: {entry["answers"]}. '+('Question record: '+entry['file']+'.' if 'file' in entry else 'Prompt text was recorded inline and is not available as a separate file.')),
            table(['Question ID','Question as archived','Answer as received'],rows)))
    doc['sections'].append(section(f'{len(doc["sections"])+1}. Later directions in this conversation',
        table(['Direction','Resulting instruction'],[
            ['Research references','Keep research internal and do not push; Kronos remains a consideration, with no integration yet.'],
            ['Financial report layout','Use World Creation, Bear and Bull; early contents; meaningful actor, event and scenario visuals.'],
            ['Review and correction','Fix chart scaling and spacing; add comparable context, named worlds, timelines, price, trade and volume comparisons and actor/crowd detail.'],
            ['Smaller Jev experiment','Try a smaller representative subset; generated results for other worlds require explicit approximation labels and validation.'],
            ['Report package and reusable framework','Improve typography and backgrounds; add technical and Q&A reporting, skills and detailed reusable guidance.']]),
        paragraph('These are paraphrased direction summaries, not verbatim quotations. The original conversation is the authority for exact wording.')))
    return doc


def add_world(doc,context,regime,index,case,pair):
    p=pair['staged-exit'];pkg=context['packages']['native',p['id']]
    common=common_rows(pair);left,right=common[-1];cut=left['second']
    pause=points_at(context,pair['pause-and-observe'],cut)
    stage=points_at(context,p,cut)
    rows=[b for a,b in common]
    flows=flow_values(stage);total=sum(x['buy']+x['sell'] for x in flows.values())
    dominant=max(flows,key=lambda g:flows[g]['buy']+flows[g]['sell']) if total else None
    share=(flows[dominant]['buy']+flows[dominant]['sell'])/total if total else None
    choices=choice_values(stage);opportunities=sum(choices.values())
    prefix='BR' if regime=='BEAR' else 'BU'
    world_id=f'{prefix}-P{int(p["position_usd"]/1000)}U{int(p["upfront_usd"]/1000)} · {world_name(p["position_usd"],p["upfront_usd"])}'
    purposes={
        (5000,5000):'is the low-position / low-cost corner of the accepted grid. It supplies the funded reference for asking whether more exposed capital or more sunk cost earns its place.',
        (5000,10000):'keeps W1’s $5,000 position budget and adds $5,000 of upfront cost. The W2–W1 contrast tests the financial drag of that larger sunk envelope; no measured conversion gain is granted to compensate for it.',
        (10000,5000):'keeps W1’s $5,000 upfront cost and raises the position budget by $5,000. The W3–W1 contrast tests an intermediate exposure commitment while keeping the lower cost envelope.',
        (10000,10000):'keeps W3’s $10,000 position budget and raises upfront cost by $5,000. Compared with W2 at the same cost, it also tests a larger position; those are two distinct comparisons, not one isolated treatment.',
        (15000,5000):'keeps the lower upfront envelope and reaches the maximum accepted position budget. Compare W5–W3 for the incremental $5,000 exposure step; compare W5–W1 for the full position sweep.',
        (15000,10000):'is the high-position / high-cost corner. Compare W6–W5 to isolate the extra upfront envelope within this grid, or W6–W4 for the position step. W6–W1 bundles both changes and does not identify one cause.'}
    blocks=[paragraph(f'{world_id} '+purposes[int(p['position_usd']),int(p['upfront_usd'])]+' All other declared role, venue and campaign contracts remain explicit. The higher cost envelope is not evidence of proportionally more reach.'),
        table(['World contract','Value'],[
            ['Plan / exact case ID',title_plan(p)+' / '+case],['Regime / response variants',regime+' / pause-and-observe versus staged-exit'],
            ['Probability / independent sampling','Real-world odds unknown; one matched seed; deliberately selected funding variant'],
            ['Native coverage',f"Pause +{pair['pause-and-observe']['last_hour']:g}h; staged +{p['last_hour']:g}h; compare at +{cut/3600:g}h"],
            ['Recorded branch status',pair['pause-and-observe']['status']+' / '+p['status']],
            ['Baseline','No launch: $50,000 retained; zero cash change; mechanical baseline, not another Jev rollout']]),
        paragraph(f'At the common +{cut/3600:g}h boundary, pause records {money(left["founder_net_cash_usd"])} net cash change and staged exit {money(right["founder_net_cash_usd"])}. The difference of {money(right["founder_net_cash_usd"]-left["founder_net_cash_usd"])} is realized cash only. All charts in this chapter stop at that common time even when one native branch continues further.')]
    full_stage=context['streams'][p['id']]
    end=end_activity(full_stage)
    manifest=json.loads((context['root']/'native-jev'/p['id']/'manifest.json').read_text())
    conclusion=(f"Trading was still active in the last observed window: {end['filled_trades']} fills "
                f"({end['buys']} buys, {end['sells']} sells), {money(end['volume_usd'])} turnover."
                if end['filled_trades'] else
                'No fills were recorded in the final observed six hours; that alone does not establish the project has ended.')
    blocks.append(paragraph(f"Recorded duration and endpoint. The staged-exit path has {manifest['completed_steps']:,} completed barriers through +{end['end_second']/3600:g}h, with {manifest['model_calls']:,} Jev calls included in those completed barriers. {conclusion} The market was in the {end['phase']} phase at the last saved checkpoint. What happens after that observation is unknown."))
    hourly=hourly_market(stage)
    blocks.append(chart('multi','Hourly token price, filled trades and executed volume',
        [r['hour'] for r in hourly],
        [{'name':'Price · USD / token','values':[r['price'] for r in hourly]},
         {'name':'Filled trades / hour','values':[r['trades'] for r in hourly]},
         {'name':'Executed USD / hour','values':[r['volume'] for r in hourly]}],
        f'The staged-exit branch records {sum(r["trades"] for r in hourly):,} executed trades and {money(sum(r["volume"] for r in hourly))} turnover through +{cut/3600:g}h.',
        'Each panel has its own scale. Price is the last saved marginal simulated USD price in the hour; turnover sums executed buy debits and net sell receipts, not unique investor capital. The last hour may be partial; launch hour includes the dense launch barriers.',
        'Compare price direction, trade count and turnover together. A price move accompanied by concentrated turnover can reflect one funded role rather than broad adoption.',
        f'Source: {p["id"]} native staged-exit checkpoints through {cut}s; hourly bins [h,h+1), final hour partial.',unit='hours',hourly_records=hourly))
    timeline=[]
    for point in stage:
        for ev in point['events']:
            classification = ('Engine detector: '+ev['kind']+'; descriptive, not an external event' if ev.get('kind') else
                              ev.get('evidence_status','Recorded event; see source checkpoint'))
            timeline.append([point['second']/3600,ev.get('text',ev.get('id','Recorded event')),classification])
    for campaign in pkg['campaigns']:
        if campaign['due_second']<=cut:
            timeline.append([campaign['due_second']/3600,'Campaign: '+campaign['id'],'Scheduled delivery; conversion unknown'])
    response=next((pt for pt in stage if pt['response']),None)
    if response:timeline.append([response['second']/3600,'Risk response begins','Recorded engine response'])
    migration=next((pt for pt in stage if pt['market_after']['phase']=='pool'),None)
    if migration:timeline.append([migration['second']/3600,'Curve to pool migration','Recorded state transition'])
    timeline.sort(key=lambda x:x[0])
    unique=[];seen_events=set();detectors=defaultdict(list)
    for entry in timeline:
        if entry[2].startswith('Engine detector:'):
            detectors[(int(entry[0]//24)+1,entry[1],entry[2])].append(entry[0]);continue
        key=(entry[1],entry[2])
        if key not in seen_events:unique.append(entry);seen_events.add(key)
    for (day,name,status),times in detectors.items():
        unique.append([min(times),f'{len(times)} detections on day {day}; {name}',status+f'; first +{min(times):g}h, last +{max(times):g}h'])
    timeline=sorted(unique,key=lambda r:r[0])
    blocks.append(table(['Hour from launch','Event / action','Evidence'],[[f'+{h:g}h',name,note] for h,name,note in timeline],
        'Full recorded event and campaign starts through the matched cutoff; later scheduled days are not observed in this native branch. See the timeline exhibit for relative timing.'))
    if timeline:
        event_buckets=defaultdict(list)
        for h,name,note in timeline:
            key=f'hour {int(h)}' if h<24 else f'day {int(h//24)+1}'
            event_buckets[key].append((h,name))
        lanes=list(event_buckets.items())
        blocks.append(chart('timeline','Recorded event and delivery timeline through the observed window',
            [f'{key} · {len(items)} event(s)' for key,items in lanes],
            [{'name':'Start','values':[min(t for t,n in items) for key,items in lanes]},
             {'name':'End','values':[max(t for t,n in items) for key,items in lanes]}],
            f'{len(timeline)} event, delivery and state-transition entries are shown through +{cut/3600:g}h; repeated detector hits are grouped by day.',
            'Each lane groups event starts in an early hour or a later day; a span joins the earliest and latest starts and does not imply a continuous event. The adjacent table preserves full labels.',
            'Read the hourly price and activity panels beside these timestamps, then inspect actor choices before attributing any change to an event.',
            f'Source: {p["id"]} checkpoint events and response, market phase, and declared campaign due times.',unit='hours',max_value=max(1,cut/3600)))
    actor_rows=[]
    for actor in sorted({a for point in stage for a in point['choices']}):
        counts=choice_values(stage,actor);n=sum(counts.values())
        score_records=[point['scores'][actor] for point in stage if actor in point['scores'] and point['scores'][actor]['probabilities']]
        buy_scores=[sum(v for name,v in r['probabilities'].items() if name.startswith('buy')) for r in score_records]
        sell_scores=[sum(v for name,v in r['probabilities'].items() if name.startswith('sell')) for r in score_records]
        actor_rows.append([actor,str(n),str(counts['Buy']),str(counts['Sell']),str(counts['Wait']),
            f'{sum(buy_scores)/len(buy_scores):.1%} / {sum(sell_scores)/len(sell_scores):.1%}' if score_records else 'Unavailable'])
    blocks.append(table(['Actor','Choices','Buy','Sell','Wait','Avg model score: buy / sell'],actor_rows,
        'Each action is a sampled model choice; averages sum available buy/sell option scores within each actor menu and are not real-world odds. Menus change with inventory and constraints. Forced actions and fills are accounted separately.'))
    examples=[];example_groups=set()
    for point in stage:
        for actor,score in point['scores'].items():
            actor_group=group(actor);actual=point['choices'].get(actor,'unavailable')
            if actor_group in example_groups or actor_group not in {'Retail','Large buyer','Market maker','KOL / operator'} or not actual.startswith(('buy','sell')):
                continue
            probabilities=score['probabilities']; choice_score=probabilities.get(actual)
            if choice_score is None:continue
            receipts=[r for r in point['settlements'] if r['actor']==actor]
            outcome=', '.join(r['status'] for r in receipts) or 'no settlement recorded'
            examples.append([f'+{point["second"]/3600:g}h',actor,actual,f'{choice_score:.1%}',score['provider_choice'] or 'unknown',outcome])
            example_groups.add(actor_group)
    if examples:
        blocks.append(table(['Hour','Actor','Sampled action','Action score','Provider choice','Settlement'],examples,
            'Illustrative first recorded buy or sell per role group, not selected for profitability. Provider choice can differ from sampled action; a model score is not a real-world probability. A sampled action can fail or produce no fill.'))
    daily=defaultdict(list)
    for point in stage:daily[int(point['second']//86400)+1].append(point)
    day_rows=[]
    for day,pts in sorted(daily.items()):
        retail_choices=Counter()
        for pt in pts:
            for actor,choice in pt['choices'].items():
                if actor.startswith('retail'):retail_choices[action(choice)]+=1
        flows_day=flow_values(pts)
        day_rows.append([f'Day {day}',f'{pts[0]["second"]/3600:g}–{pts[-1]["second"]/3600:g}h',
            f'{retail_choices["Buy"]} / {retail_choices["Sell"]} / {retail_choices["Wait"]}',
            money(flows_day['Retail']['buy']),money(flows_day['Retail']['sell']),
            f'{sum(1 for pt in pts for a,c in pt["choices"].items() if a.startswith("kol") and action(c)=="Publish")}'])
    blocks.append(table(['Period','Saved hours','Retail buy / sell / wait choices','Retail buy debit','Retail sell receipt','KOL publish choices'],day_rows,
        'Day buckets aggregate recorded decisions and executed settlement; the first and last days may be partial. Choices and fills are distinct; counts are not unique people.'))
    retail=[r for r in actor_rows if r[0].startswith('retail')]
    rb=sum(int(r[2]) for r in retail);rs=sum(int(r[3]) for r in retail);rw=sum(int(r[4]) for r in retail);rn=sum(int(r[1]) for r in retail)
    kol_actors=[r[0] for r in actor_rows if r[0].startswith('kol')]
    kol_choices=sum((choice_values(stage,a) for a in kol_actors),Counter())
    blocks.append(paragraph(f'Crowd interpretation: the four retail personas make {rn:,} recorded choices: {rb:,} buys ({rb/rn:.1%}), {rs:,} sells ({rs/rn:.1%}), and {rw:,} waits ({rw/rn:.1%}). '+
        ('Waiting dominates this modelled retail sample; this is compatible with hesitation under these menus, not evidence of real-world sentiment. ' if rw>rb+rs else 'Buy and sell choices both appear, indicating mixed modeled behavior rather than a single crowd direction. ')+
        f'The KOL roles make {kol_choices["Publish"]:,} publication choices and {kol_choices["Sell"]:,} sell choices; these do not measure audience conversion. '+
        'The run has no modeled negotiation, price renegotiation, contract conditions, or partner commitment horizon: partner acceptance speed and dedication are unknown.'))
    event_rows=[]
    for name,sequence in [('Pause',pause),('Staged exit',stage)]:
        initial=sequence[0];response=next((x for x in sequence if x['response']),None)
        migration=next((x for x in sequence if x['market_after']['phase']=='pool'),None)
        first_sale=next(((x,r) for x in sequence for r in x['settlements'] if r['actor']=='founder' and r['side']=='sell' and r['status']=='executed'),None)
        if response:
            alert=response['response']['alert_second'];signal=response['market_before']['six_hour_signal']
            reason='6H turnover trigger is true' if signal.get('exit_trigger') is True else '6H trigger is not established here; recorded loss-budget channel is also available'
            event_rows.append([name,f'+{alert/3600:g}h','Risk response begins',reason])
        if first_sale:event_rows.append([name,f'+{first_sale[0]["second"]/3600:g}h','First recorded founder sale',money(first_sale[1]['cash_cents']/100)+' cash receipt; not a guaranteed stop price'])
        event_rows.append([name,f'+{migration["second"]/3600:g}h' if migration else 'Not recorded by common cutoff','Curve → pool',
                           'Implemented simplified migration' if migration else 'No completed migration in this comparison window'])
    blocks.append(table(['Branch','Time','Turning point','Evidence / interpretation'],event_rows))
    blocks.append(paragraph('The event ordering matters. A response at launch must not be narrated as a later market crash. Its trigger can come from the declared loss budget and current liquidation estimate even before a six-hour volume reference exists. Scheduled KOL delivery and Assembly topics overlap actor trading; neither proves the cause of a subsequent choice.'))
    phases=[(0,21600,'Launch 0–6h'),(21600,86400,'6–24h'),(86400,cut+1,f'24–{cut/3600:g}h')]
    phasecounts=[choice_values([x for x in stage if a<=x['second']<b]) for a,b,_ in phases]
    phase_labels=[label for (_,_,label),counts in zip(phases,phasecounts) if sum(counts.values())]
    phasecounts=[x for x in phasecounts if sum(x.values())]
    if phasecounts:
        early,late=phasecounts[0],phasecounts[-1]
        early_n,late_n=sum(early.values()),sum(late.values())
        blocks.append(paragraph(f'Participation trajectory. In {phase_labels[0]}, buy choices account for {early["Buy"]}/{early_n} decisions ({early["Buy"]/early_n:.1%}) and sell choices {early["Sell"]}/{early_n} ({early["Sell"]/early_n:.1%}). In {phase_labels[-1]}, the corresponding shares are {late["Buy"]}/{late_n} ({late["Buy"]/late_n:.1%}) and {late["Sell"]}/{late_n} ({late["Sell"]/late_n:.1%}). This distinguishes a change in trading inclination from the number of scheduled opportunities. It does not isolate publicity, inventory depletion or regime context as the cause.'))
    blocks.append(chart('stack','Actor behavior changes across launch, campaign and later participation',phase_labels,
        [{'name':a,'values':[100*c[a]/sum(c.values()) for c in phasecounts]} for a in ACTS],
        f'Across {len(stage)} saved staged-exit barriers, {opportunities:,} actor decisions contain {choices["Buy"]:,} buy choices, {choices["Sell"]:,} sell choices and {choices["Publish"]:,} publication choices.',
        'Each period is normalized to its own decision count; early minute-level barriers are denser than later hourly barriers. These are selected actions, not successful fills. Founder commitments and forced response trades are accounted for in settlement, separately from a sampled choice.',
        'Read changes in composition alongside actual money flow. Publication growth with few buys can indicate attention without conversion, but that hypothesis requires a controlled campaign comparison.',
        f'Source: {p["id"]} native choices, t≤{cut}s; first/last checkpoints {stage[0]["checkpoint_sha256"][:12]} / {stage[-1]["checkpoint_sha256"][:12]}.',
        unit='percent',max_value=100,denominators=[sum(c.values()) for c in phasecounts]))
    blocks.append(chart('bar','Executed money identifies who actually supplies and removes trading cash',GROUPS,
        [{'name':'Filled buy debit · USD','values':[flows[g]['buy'] for g in GROUPS]},
         {'name':'Filled sell receipt · USD','values':[flows[g]['sell'] for g in GROUPS]}],
        f'{dominant} accounts for {share:.1%} of buy debits plus sell receipts in this staged branch.' if share is not None else 'No filled money flow is recorded in this window.',
        'Buys are actor cash debits; sells are net receipts under the modeled fee. These are repeated flows, not fresh investor capital or a net inflow measure. The same role can appear on both sides. Zero flows are preserved.',
        'If one assumed wallet supplies most turnover, the result depends on that wallet’s endowment and behavior. Validate that dependence before interpreting campaign reach as broad demand.',
        f'Source: {p["id"]} native executed settlements, t≤{cut}s; same common cutoff; grouped actor roles.',unit='USD',flow_records=flows))
    blocks.append(chart('line','Response actions change realized cash while pause retains exposure',
        [a['hours'] for a,b in common],
        [{'name':'Pause · cash change USD','values':[a['founder_net_cash_usd'] for a,b in common]},
         {'name':'Staged exit · cash change USD','values':[b['founder_net_cash_usd'] for a,b in common]}],
        f'At +{cut/3600:g}h staged exit has {money(right["founder_net_cash_usd"]-left["founder_net_cash_usd"])} more realized cash than pause, after costs counted once.',
        'The x-axis includes only exact timestamps saved in both branches. Unmatched intrabranch timestamps are omitted. Cash changes include upfront costs, funding and actual sale receipts; token inventory is excluded. A higher line therefore does not prove higher total wealth.',
        'Relate cash steps to recorded founder sales and risk-response timing. Compare remaining units and hypothetical liquidation capacity before selecting a response.',
        f'Source: {case} native paired rows, exact-common-time join; last hashes {left["checkpoint_sha256"][:12]} / {right["checkpoint_sha256"][:12]}.',unit='USD',x_unit='hours'))
    event=next((c for c in pkg['campaigns'] if c['id']=='token-info'),None)
    if event:
        t=event['due_second'];windows=[('Prior six hours',max(0,t-21600),t),('Following six hours',t,t+21600)]
        evrows=[]
        for label,a,b in windows:
            pts=[x for x in stage if a<=x['second']<b]
            counts=choice_values(pts);f=flow_values(pts)
            evrows.append([label,f'{a/3600:g}–{b/3600:g}h',str(len(pts)),str(counts['Buy']),str(counts['Publish']),
                           money(sum(v['buy'] for v in f.values())),money(sum(v['sell'] for v in f.values()))])
        before_flow=flow_values([x for x in stage if max(0,t-21600)<=x['second']<t])
        after_flow=flow_values([x for x in stage if t<=x['second']<t+21600])
        before_buy=sum(v['buy'] for v in before_flow.values());after_buy=sum(v['buy'] for v in after_flow.values())
        after_sell=sum(v['sell'] for v in after_flow.values())
        blocks.append(paragraph(f'Event association at token-info delivery (+{t/3600:g}h). Filled buy debits are {money(before_buy)} during the preceding six hours and {money(after_buy)} during the following six hours; following sell receipts total {money(after_sell)}. '+
            ('Sell receipts exceed buy debits in that following window, so elevated turnover should not be read as one-way new demand. ' if after_sell>after_buy else 'Buy debits exceed sell receipts in that following window, but neither figure identifies newly arrived capital. ')+
            'Other campaign exposures, scheduled topics and changing wallets overlap this event; incremental marketing return remains unidentified.'))
        blocks.append(table(['Token-info window','Hours','Barriers','Buy choices','Publish choices','Buy debit','Sell receipt'],evrows,
            'Descriptive event association, not causal campaign ROI. Windows use [start,end); differing decision density and overlapping exposures remain visible.'))
    event_topics=[];seen=set()
    for point in stage:
        for e in point['events']:
            event_id=e.get('id',digest(e))
            if event_id not in seen:
                seen.add(event_id);event_topics.append([f'+{point["second"]/3600:g}h',e.get('text',e.get('kind','Recorded engine event')),e.get('evidence_status','engine-derived / see checkpoint'),e.get('source_ref','')])
    blocks.append(table(['First visible / hours','Dated topic','Evidence status'],[r[:3] for r in event_topics[:4]],
        f'{len(event_topics)} distinct recorded topics by the common cutoff; a topic is not a verified outcome or measured attention shock. Full source references remain in the native event records.'))
    blocks.append(table(['Evidence locator','Exact record'],[
        ['Package','native-jev/'+p['id']+'/package.json'],
        ['First / last staged checkpoint','native-jev/'+p['id']+'/step-'+f'{stage[0]["step"]:05d}'+'.json / step-'+f'{stage[-1]["step"]:05d}'+'.json'],
        ['Last pause checkpoint','native-jev/'+pair['pause-and-observe']['id']+'/step-'+f'{pause[-1]["step"]:05d}'+'.json'],
        ['Calendar references','; '.join(dict.fromkeys(r[3] for r in event_topics if r[3])) or 'No sourced calendar topic in this window']
    ],'Paths are relative to the evidence root in the sources appendix. Checkpoint hashes in the exhibit sidecars bind the exact common-time state.'))
    failures=sum(v['rejected'] for v in flows.values());fills=sum(v['fills'] for v in flows.values())
    residual_pause=pause[-1]['balances_after']['founder']['tokens'];residual_stage=stage[-1]['balances_after']['founder']['tokens']
    blocks.append(paragraph(f'Execution and competing explanations. The staged branch has {fills:,} fills and {failures:,} rejected trade attempts by the common cutoff. Its founder retains {residual_stage:,} token units versus {residual_pause:,} in pause. Sunk costs, position size, fees, funded response timing and concentrated wallets can explain cash differences without assuming that the regime label or marketing caused them.'))
    blocks.append(paragraph('Decision / falsification. Use this world to compare the exposed budget and response mechanics. A useful next test would keep capital, campaigns, timestamps and policy sampling fixed while changing one grounded input, such as arrival evidence or delivery latency. A different seed, wallet distribution or venue execution model may reverse a ranking; this single matched seed does not establish future odds.'))
    support=[x for x in context['data']['paths'] if x['case']==case and x['mode']!='native']
    blocks.append(table(['Supporting path','Hours','Cash change','Meaning'],[[MODES[x['mode']]+' / '+x['policy'],f'{x["last_hour"]:g}',
        money(x['summary']['founder_net_cash_cents']/100),'Complete synthetic mechanics; not native continuation'] for x in support]))
    doc['sections'].append(section(f'{index+4}. {world_id}: {title_plan(p)}',*blocks))


def compact(value):
    """Readable axis number: 374k / 1.2M instead of scientific notation."""
    if abs(value) >= 1e6:
        return f'{value / 1e6:.3g}M'
    if abs(value) >= 1e3:
        return f'{value / 1e3:.3g}k'
    return f'{value:.3g}'


def tick(value, block):
    """Time-axis tick; day axes round to whole days, hour axes keep MACRON's format."""
    unit = block.get('x_unit', 'h')
    return f'+{round(value)}{unit}' if unit == 'd' else f'+{value:g}{unit}'


def draw_chart(block):
    ensure_fonts()
    from reportlab.graphics.shapes import Drawing, Line, Rect, String, PolyLine, Circle
    from reportlab.lib.colors import HexColor
    kind=block['chart_kind'];labels=block['labels'];series=block['series']
    n=max(1,len(labels));h=max(190,55+n*24) if kind not in {'line','multi'} else (300 if kind=='multi' else 235)
    if kind=='flow':h=405
    d=Drawing(490,h)
    def text(x,y,t,size=8,anchor='start',color=INK,font='BoyunText'):
        if any(g in str(t) for g in '→≤'):font='BoyunSymbols'
        d.add(String(x,y,str(t),fontName=font,fontSize=size,textAnchor=anchor,fillColor=HexColor(color)))
    if kind=='flow':
        for i,label in enumerate(block['nodes']):
            x=55;y=342-i*62
            d.add(Rect(x,y,360,47,rx=10,fillColor=HexColor('#FCF0C2'),strokeColor=HexColor(COLORS[0]),strokeWidth=1.2))
            for j,line in enumerate(label.split('\n')):text(x+12,y+29-j*15,line,10)
            if i<5:
                d.add(PolyLine([235,y,235,y-12,231,y-8,235,y-12,239,y-8],strokeColor=HexColor(COLORS[1]),strokeWidth=1.2))
        d.add(PolyLine([415,55,455,55,455,241,415,241],strokeColor=HexColor(COLORS[1]),strokeWidth=1))
        text(245,8,'Declared channels and ledger feedback; no empirical conversion rates.',8,'middle')
        return d
    if kind=='multi':
        lo=min(labels,default=0);hi=max(max(labels,default=1),lo+1)
        for k,s in enumerate(series):
            top=270-k*88; bottom=top-55
            vals=[v for v in s['values'] if v is not None]; maximum=max(vals,default=0) or 1
            text(8,top+4,s['name'],8,font='BoyunTextBold')
            for j in range(3):
                yy=bottom+(top-bottom)*j/2
                d.add(Line(85,yy,480,yy,strokeColor=HexColor(LINE),strokeWidth=.4))
                text(80,yy-3,compact(maximum*j/2),7,'end')
            segments=[];pts=[]
            for t,v in zip(labels,s['values']):
                if v is None:
                    if pts:segments.append(pts);pts=[]
                else:pts.extend((85+(t-lo)/(hi-lo)*395,bottom+v/maximum*55))
            if pts:segments.append(pts)
            for pts in segments:
                if len(pts)>=4:d.add(PolyLine(pts,strokeColor=HexColor(COLORS[k]),strokeWidth=1.5))
        for j in range(5):text(85+395*j/4,5,tick(lo+(hi-lo)*j/4,block),7,'middle')
        return d
    left=155 if kind!='line' else 65;right=480;top=h-(44 if len(series)>3 else 30);bottom=32
    if kind in {'stack','timeline'}:
        default_max=max((sum(s['values'][i] for s in series) for i in range(len(labels))),default=1) if kind=='stack' else 48
        maximum=block.get('max_value',default_max or 1);minimum=0
    else:
        vals=[v for s in series for v in s['values'] if v is not None]
        minimum=min(0,min(vals,default=0));maximum=max(vals,default=1)
        if kind=='line' and block.get('unit')=='USD / token' and vals:
            low,high=min(vals),max(vals);padding=(high-low)*.08 or max(abs(high)*.05,1e-12)
            minimum=max(0,low-padding);maximum=high+padding
        if maximum<=minimum:maximum=minimum+1
        if 'max_value'in block:maximum=block['max_value']
        elif kind!='line':
            rough=(maximum-minimum)/4
            scale=10**math.floor(math.log10(rough))
            step=next(v*scale for v in (1,2,2.5,5,10) if v*scale>=rough)
            minimum=math.floor(minimum/step)*step;maximum=math.ceil(maximum/step)*step
    span=maximum-minimum or 1
    def x(v):return left+(v-minimum)/span*(right-left)
    for j in range(5):
        v=minimum+span*j/4;xx=x(v)
        if kind!='line':
            d.add(Line(xx,bottom,xx,top,strokeColor=HexColor(LINE),strokeWidth=.4))
            label=(f'{v/1000:.1f}k' if abs(v)>=1000 else f'{v:.0f}')
            text(xx,18,label,7,'middle')
    if kind=='line':
        xs=labels;lo=min(xs,default=0);hi=max(xs,default=1);hi=max(hi,lo+1)
        for j in range(5):
            yy=bottom+(top-bottom)*j/4;v=minimum+span*j/4
            d.add(Line(left,yy,right,yy,strokeColor=HexColor(LINE),strokeWidth=.4));text(left-7,yy-3,(f'{v/1000:.1f}k' if abs(v)>=1000 else f'{v:.3g}'),7,'end')
            xx=left+(right-left)*j/4;text(xx,18,tick(lo+(hi-lo)*j/4,block),7,'middle')
        for k,s in enumerate(series):
            segments=[];pts=[]
            for t,value in zip(xs,s['values']):
                if value is None:
                    if pts:segments.append(pts);pts=[]
                    continue
                pts.extend((left+(t-lo)/(hi-lo)*(right-left),bottom+(value-minimum)/span*(top-bottom)))
            if pts:segments.append(pts)
            for segment in segments:
                if len(segment)>=4:d.add(PolyLine(segment,strokeColor=HexColor(COLORS[k%len(COLORS)]),strokeWidth=1.7,strokeDashArray=[4,2] if k%2 else None))
    else:
        rowheight=(top-bottom)/n
        for i,label in enumerate(labels):
            y=top-(i+.5)*rowheight
            text(left-8,y-3,label,7.4,'end')
            if kind=='timeline':
                a=series[0]['values'][i];b=series[1]['values'][i]
                d.add(Rect(x(a),y-5,max(1,x(b)-x(a)),10,fillColor=HexColor(COLORS[0]),strokeColor=None))
                d.add(Circle(x(a),y,3,fillColor=HexColor(COLORS[1]),strokeColor=None))
            elif kind=='stack':
                offset=0
                for k,s in enumerate(series):
                    value=s['values'][i]
                    width=max(0,x(offset+value)-x(offset))
                    d.add(Rect(x(offset),y-6,width,12,fillColor=HexColor(COLORS[k%len(COLORS)]),strokeColor=None))
                    if width>42:
                        label=f'{value/1000:g}k' if block.get('unit')=='USD' else f'{value:.0f}%'
                        text(x(offset)+width/2,y-2.5,label,7,'middle',color='#FFFFFF' if k%len(COLORS) in (0,2,4,6) else INK)
                    offset+=value
            else:
                barh=min(8,rowheight/max(2,len(series)+1))
                for k,s in enumerate(series):
                    value=s['values'][i];yy=y+(len(series)-1)/2*barh-k*barh
                    d.add(Rect(min(x(0),x(value)),yy-barh/2,max(.5,abs(x(value)-x(0))),barh-1,
                               fillColor=HexColor(COLORS[k%5]),strokeColor=None))
    text(left,3,block.get('unit',''),7)
    if kind!='timeline':
        # Legends occupy a dedicated band, outside the plotting area.
        dx=left
        for k,s in enumerate(series):
            name=s['name'];short=name.replace(' · USD','').replace(' · million token units','')
            d.add(Rect(dx,h-10-(k//3)*10-1,6,6,rx=2,fillColor=HexColor(COLORS[k%len(COLORS)]),strokeColor=None));text(dx+9,h-10-(k//3)*10,short,6.8,color=INK);dx+=max(52,len(short)*3.5+19)
            if k%3==2:dx=left
    return d


INK = '#1C1D18'
MUTED = '#5D5C52'
PAPER = '#FFFDF8'
GROUND = '#FAF6EC'
LINE = '#E6DFCF'
ILL = '#F0EAE5'
PINK, GREEN, ORANGE, YELLOW, BLUE = '#F5B3D3', '#D4EC7E', '#F47B3B', '#F9D95C', '#2A52D1'
TINTS = ['#FBE4F0', '#EEF6CC', '#FCF0C2', '#E0E7FB', '#FDE4D3']
_FONTS_READY = []


def ensure_fonts():
    """Register the landing-page fonts: Bricolage Grotesque (display) and Instrument Sans (text), both SIL OFL."""
    if _FONTS_READY:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fonts = Path(__file__).resolve().parent / 'fonts'
    for name, file in (('BoyunText', 'InstrumentSans-400.ttf'), ('BoyunTextBold', 'InstrumentSans-700.ttf'),
                       ('BoyunDisplay', 'BricolageGrotesque-700.ttf'), ('BoyunDisplayBold', 'BricolageGrotesque-800.ttf')):
        pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
    # The two fonts lack arrows and ≤; Manrope (already shipped with the app) covers them.
    pdfmetrics.registerFont(TTFont('BoyunSymbols', str(Path(__file__).resolve().parents[1] / 'engine/src/decision_lab/resources/fonts/manrope-regular.ttf')))
    pdfmetrics.registerFontFamily('BoyunText', normal='BoyunText', bold='BoyunTextBold', italic='BoyunText', boldItalic='BoyunTextBold')
    pdfmetrics.registerFontFamily('BoyunDisplay', normal='BoyunDisplay', bold='BoyunDisplayBold', italic='BoyunDisplay', boldItalic='BoyunDisplayBold')
    _FONTS_READY.append(True)


def symbols(markup):
    for glyph in ('→', '≤'):
        markup = markup.replace(glyph, '<font name="BoyunSymbols">' + glyph + '</font>')
    return markup


def draw_mark(canvas, x, y, scale=1.0):
    """The Boyun mark from the site: a sun above two offset cloud pills."""
    from reportlab.lib.colors import HexColor
    canvas.saveState()
    canvas.translate(x, y)
    canvas.scale(scale, scale)
    canvas.setLineWidth(1.6)
    canvas.setStrokeColor(HexColor(INK))
    canvas.setFillColor(HexColor(ORANGE))
    canvas.circle(19, 32 - 11.5, 6.5, stroke=1, fill=1)
    canvas.setFillColor(HexColor(PAPER))
    canvas.roundRect(2.5, 32 - 22.5, 18, 9, 4.5, stroke=1, fill=1)
    canvas.setFillColor(HexColor(PINK))
    canvas.roundRect(12.5, 32 - 27.5, 17, 8.5, 4.25, stroke=1, fill=1)
    canvas.restoreState()


def sticker(canvas, cx, cy, w, h, rotation, fill, label='', shape='pill', size=17):
    """A die-cut sticker as on the site: solid fill, warm-white edge, soft cast shadow, no outline."""
    import math
    from reportlab.lib.colors import HexColor
    radius = {'pill': h / 2, 'circle': h / 2, 'square': 18}[shape]
    canvas.saveState()
    canvas.translate(cx, cy)
    canvas.rotate(rotation)
    canvas.setFillColor(HexColor(INK))
    canvas.setFillAlpha(.16)
    canvas.roundRect(-w / 2 + 2, -h / 2 - 6, w, h, radius, stroke=0, fill=1)
    canvas.setFillAlpha(1)
    canvas.setFillColor(HexColor(PAPER))
    canvas.roundRect(-w / 2 - 5, -h / 2 - 5, w + 10, h + 10, radius + 5, stroke=0, fill=1)
    canvas.setFillColor(HexColor(fill))
    canvas.roundRect(-w / 2, -h / 2, w, h, radius, stroke=0, fill=1)
    if shape == 'circle':
        canvas.setStrokeColor(HexColor(INK))
        canvas.setLineWidth(2.2)
        canvas.setLineCap(1)
        canvas.circle(0, 0, h * .17, stroke=1, fill=0)
        for k in range(8):
            a = k * math.pi / 4
            canvas.line(math.cos(a) * h * .27, math.sin(a) * h * .27, math.cos(a) * h * .36, math.sin(a) * h * .36)
    lines = label.split('\n') if label else []
    canvas.setFillColor(HexColor(INK))
    canvas.setFont('BoyunDisplayBold', size)
    for i, line in enumerate(lines):
        canvas.drawCentredString(0, (len(lines) - 1) * size * .5 - i * size * 1.05 - size * .3, line.upper())
    canvas.restoreState()


def load_art(name, target=(240, 234, 229)):
    """Actor drawing from tools/report_assets, background levelled to the panel colour."""
    from PIL import Image
    im = Image.open(Path(__file__).resolve().parent / 'report_assets' / name).convert('RGB')
    bg = im.getpixel((6, 6))
    tables = [[max(0, min(255, v + (target[b] - bg[b]) * v // 255)) for v in range(256)] for b in range(3)]
    return im.point(tables[0] + tables[1] + tables[2])


def make_flowables():
    from reportlab.platypus import Flowable
    from reportlab.lib.colors import HexColor
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.lib.utils import ImageReader

    class Card(Flowable):
        """A rounded card as on the site: paper (or a tint), hairline edge, soft shadow. Tints have no edge."""
        def __init__(self, inner, fill=PAPER, pad=12, radius=16, edge=True):
            super().__init__()
            self.inner, self.fill, self.pad, self.radius, self.edge = inner, fill, pad, radius, edge

        def wrap(self, availWidth, availHeight):
            self.width = availWidth
            w, h = self.inner.wrap(self.width - 2 * self.pad, availHeight - 2 * self.pad)
            self.inner_height = h
            self.height = h + 2 * self.pad + 3
            return self.width, self.height

        def draw(self):
            c = self.canv
            h = self.inner_height + 2 * self.pad
            c.saveState()
            c.translate(0, 3)
            if self.edge:
                c.setFillColor(HexColor(INK))
                c.setFillAlpha(.07)
                c.roundRect(0, -3, self.width, h, self.radius, stroke=0, fill=1)
                c.setFillAlpha(1)
            c.setFillColor(HexColor(self.fill))
            if self.edge:
                c.setStrokeColor(HexColor(LINE))
                c.setLineWidth(.9)
            c.roundRect(0, 0, self.width, h, self.radius, stroke=1 if self.edge else 0, fill=1)
            self.inner.drawOn(c, self.pad, self.pad)
            c.restoreState()

    class Pill(Flowable):
        """A small tinted tag, like the site's chips."""
        def __init__(self, text, tint):
            super().__init__()
            self.text, self.tint = text, tint
            self.hAlign = 'LEFT'

        def wrap(self, availWidth, availHeight):
            self.pill_w = stringWidth(self.text, 'BoyunTextBold', 8.2) + 22
            return self.pill_w, 24

        def draw(self):
            c = self.canv
            c.setFillColor(HexColor(self.tint))
            c.roundRect(0, 2, self.pill_w, 20, 10, stroke=0, fill=1)
            c.setFillColor(HexColor(INK))
            c.setFont('BoyunTextBold', 8.2)
            c.drawString(11, 8.5, self.text)

    class CastPanel(Flowable):
        """The site's illustration frame: line-art actors on the illustration paper, each with a small role tag."""
        def __init__(self, items, height=232):
            super().__init__()
            self.items, self.panel_h = items, height

        def wrap(self, availWidth, availHeight):
            self.width = availWidth
            return availWidth, self.panel_h

        def draw(self):
            c = self.canv
            c.setFillColor(HexColor(ILL))
            c.roundRect(0, 0, self.width, self.panel_h, 22, stroke=0, fill=1)
            n = len(self.items)
            slot = self.width / n
            for i, (image, role, tint) in enumerate(self.items):
                art_h = self.panel_h - 56
                art_w = art_h * image.size[0] / image.size[1]
                cx = slot * (i + .5)
                c.drawImage(ImageReader(image), cx - art_w / 2, 40, art_w, art_h)
                tag_w = stringWidth(role, 'BoyunTextBold', 8.2) + 22
                c.setFillColor(HexColor(tint))
                c.roundRect(cx - tag_w / 2, 12, tag_w, 20, 10, stroke=0, fill=1)
                c.setFillColor(HexColor(INK))
                c.setFont('BoyunTextBold', 8.2)
                c.drawCentredString(cx, 18.5, role)
    return Card, Pill, CastPanel


def make_pdf(doc, output):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.utils import simpleSplit
    from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether, NextPageTemplate
    from reportlab.platypus.tableofcontents import TableOfContents
    ensure_fonts()
    Card, Pill, CastPanel = make_flowables()
    hx = colors.HexColor
    styles = getSampleStyleSheet()

    def style(name, **kw):
        styles.add(ParagraphStyle(name=name, **kw))
    style('BodyResearch', fontName='BoyunText', fontSize=10.2, leading=15, spaceAfter=10, textColor=hx(INK))
    style('FindingResearch', fontName='BoyunTextBold', fontSize=10.6, leading=15.5, spaceAfter=8, textColor=hx(INK))
    style('CaptionResearch', fontName='BoyunText', fontSize=8, leading=11, spaceAfter=8, textColor=hx(MUTED))
    style('CellResearch', fontName='BoyunText', fontSize=8, leading=11, textColor=hx(INK))
    style('CellHead', fontName='BoyunTextBold', fontSize=8, leading=11, textColor=hx(INK))
    style('FigureResearch', fontName='BoyunDisplayBold', fontSize=13, leading=16.5, spaceBefore=8, spaceAfter=9, textColor=hx(INK))
    style('ChapterResearch', fontName='BoyunDisplayBold', fontSize=26, leading=28, textColor=hx(INK), spaceBefore=10, spaceAfter=18)
    style('GlanceHead', fontName='BoyunDisplayBold', fontSize=30, leading=33, textColor=hx(INK), spaceBefore=8, spaceAfter=16)
    style('CoverCard', fontName='BoyunText', fontSize=10.4, leading=15, textColor=hx(INK))
    style('ContentsHead', fontName='BoyunDisplayBold', fontSize=36, leading=40, textColor=hx(INK), spaceAfter=18)
    style('ImplicationResearch', fontName='BoyunText', fontSize=10, leading=14.5, textColor=hx(INK), backColor=hx('#FCF0C2'),
          borderPadding=7, borderRadius=7, leftIndent=9, rightIndent=9, spaceBefore=9, spaceAfter=14)

    class ResearchDoc(BaseDocTemplate):
        def afterFlowable(self, flowable):
            if isinstance(flowable, Paragraph) and flowable.style.name == 'ChapterResearch':
                title = flowable.getPlainText()
                key = 'chapter-' + str(self.seq.nextf('chapter'))
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(title, key, level=0)
                self.notify('TOCEntry', (0, title, self.page, key))

    def ground(canvas):
        canvas.setFillColor(hx(GROUND))
        canvas.rect(0, 0, 595, 842, stroke=0, fill=1)

    def wordmark(canvas, size=15):
        draw_mark(canvas, 44, 790, .95)
        canvas.setFillColor(hx(INK))
        canvas.setFont('BoyunDisplayBold', size)
        canvas.drawString(44 + 36, 797, 'Boyun')

    def research_page(canvas, document):
        canvas.saveState()
        ground(canvas)
        wordmark(canvas)
        canvas.setFont('BoyunText', 7.8)
        canvas.setFillColor(hx(MUTED))
        canvas.drawRightString(551, 799, doc.get('project', 'MACRON') + ' · ' + doc['title'])
        canvas.drawString(44, 30, doc.get('footer_note', 'Conditional research. No calibrated market odds. No real token or trading execution.'))
        number = str(document.page)
        pill_w = 16 + 6 * len(number)
        canvas.setFillColor(hx(INK))
        canvas.roundRect(551 - pill_w, 22, pill_w, 20, 10, stroke=0, fill=1)
        canvas.setFillColor(hx(GROUND))
        canvas.setFont('BoyunTextBold', 8.6)
        canvas.drawCentredString(551 - pill_w / 2, 28, number)
        canvas.restoreState()

    def cover_page(canvas, document):
        """The site's hero: outlined pill, centred uppercase headline, one muted line, the sticker pile, one ink pill, dark footer."""
        canvas.saveState()
        ground(canvas)
        wordmark(canvas, 17)
        pill = 'Boyun · financial scenario research'
        canvas.setFont('BoyunTextBold', 8.4)
        pw = canvas.stringWidth(pill, 'BoyunTextBold', 8.4) + 26
        canvas.setStrokeColor(hx(INK))
        canvas.setLineWidth(.9)
        canvas.roundRect(297.5 - pw / 2, 706, pw, 22, 11, stroke=1, fill=0)
        canvas.setFillColor(hx(INK))
        canvas.drawCentredString(297.5, 713.5, pill)
        title_lines = [doc.get('project', 'MACRON')]
        size = 56
        while size > 34:
            lines = simpleSplit(doc['title'].upper(), 'BoyunDisplayBold', size, 480)
            if len(lines) <= 2:
                break
            size -= 3
        title_lines += simpleSplit(doc['title'].upper(), 'BoyunDisplayBold', size, 480)
        y = 650
        canvas.setFont('BoyunDisplayBold', size)
        for line in title_lines:
            canvas.drawCentredString(297.5, y, line)
            y -= size * 1.02
        canvas.setFont('BoyunText', 12)
        canvas.setFillColor(hx(MUTED))
        y -= 8
        for line in simpleSplit(doc['subtitle'], 'BoyunText', 12, 380):
            canvas.drawCentredString(297.5, y, line)
            y -= 17
        pile = min(y - 118, 420)
        sticker(canvas, 168, pile + 8, 188, 74, 16, PINK, 'Recorded\ndecisions.')
        sticker(canvas, 322, pile + 40, 214, 74, -10, GREEN, 'Conditional\nestimates.')
        sticker(canvas, 302, pile - 28, 86, 86, -14, ORANGE, '', 'circle')
        sticker(canvas, 478, pile - 6, 134, 134, 9, YELLOW, 'No market\nodds.', 'square', 15)
        label = 'Research edition · ' + doc['asof']
        canvas.setFont('BoyunTextBold', 10)
        lw = canvas.stringWidth(label, 'BoyunTextBold', 10) + 44
        canvas.setFillColor(hx(INK))
        canvas.roundRect(297.5 - lw / 2, pile - 128, lw, 40, 20, stroke=0, fill=1)
        canvas.setFillColor(hx(GROUND))
        canvas.drawCentredString(297.5, pile - 112, label)
        canvas.setFillColor(hx(INK))
        canvas.roundRect(0, 0, 595, 118, 0, stroke=0, fill=1)
        canvas.setFillColor(hx(GROUND))
        canvas.setFont('BoyunDisplayBold', 60)
        canvas.drawString(44, 46, 'Boyun')
        canvas.setFont('BoyunText', 7.6)
        canvas.setFillColor(hx('#CFC9B6'))
        canvas.drawRightString(551, 70, 'Recorded native decisions and conditional financial estimates.')
        canvas.drawRightString(551, 58, doc.get('cover_note', 'No calibrated market odds. No real token or trading execution.'))
        canvas.drawRightString(551, 40, 'Result identity: ' + doc['result_sha256'][:32] + '…')
        canvas.restoreState()

    pdf = ResearchDoc(str(output), pagesize=(595, 842), leftMargin=44, rightMargin=44, topMargin=44, bottomMargin=60,
                      title=doc.get('project', 'MACRON') + ' — ' + doc['title'], author='Boyun Research', subject='Boyun financial scenario research')
    pdf.addPageTemplates([
        PageTemplate(id='cover', frames=[Frame(44, 700, 40, 20, id='cover', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=cover_page),
        PageTemplate(id='research', frames=[Frame(44, 62, 507, 706, id='normal', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=research_page)])

    def p(t, name='BodyResearch'):
        return Paragraph(symbols(escape(t).replace('\n', '<br/>')), styles[name])

    story = [Spacer(1, 1), NextPageTemplate('research'), PageBreak(), Pill(doc['title'], TINTS[2]), p('The short version.', 'GlanceHead')]
    if doc.get('cast_panel', True):
        cast = [(load_art('actor-founder.png'), 'Founder', TINTS[0]), (load_art('actor-large.png'), 'Large buyer', TINTS[1]),
                (load_art('actor-retail.png'), 'Retail', TINTS[2])]
        story += [CastPanel(cast), Spacer(1, 6),
                  p('Line drawings generated for Boyun. Founder, Large buyer and Retail are three of this study’s seven actor groups; the drawings are not likenesses of real people.', 'CaptionResearch'), Spacer(1, 8)]
    for i, text in enumerate(doc['highlights']):
        story += [Card(p(text, 'CoverCard'), fill=TINTS[i % 4], pad=12, radius=16, edge=False), Spacer(1, 8)]
    story += [PageBreak(), p('Contents', 'ContentsHead')]
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle(name='TOCResearch', fontName='BoyunText', fontSize=10.5, leading=19, leftIndent=0, firstLineIndent=0, spaceBefore=6, textColor=hx(INK))]
    story += [toc, PageBreak()]
    for index, s in enumerate(doc['sections']):
        tint = TINTS[index % len(TINTS)]
        story += [Pill(doc['title'], tint), p(s['title'], 'ChapterResearch')]
        for b in s['blocks']:
            if b['kind'] == 'paragraph':
                story.append(p(b['text']))
            elif b['kind'] == 'table':
                rows = [[p(str(c), 'CellHead') for c in b['headers']]] + [[p(str(c), 'CellResearch') for c in row] for row in b['rows']]
                n = len(b['headers'])
                t = Table(rows, colWidths=[507 / n] * n, repeatRows=1, hAlign='LEFT')
                t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (-1, 0), hx(tint)),
                                       ('BACKGROUND', (0, 1), (-1, -1), hx(PAPER)),
                                       ('BOX', (0, 0), (-1, -1), .9, hx(LINE)), ('ROUNDEDCORNERS', [12, 12, 12, 12]),
                                       ('LINEBELOW', (0, 1), (-1, -2), .5, hx(LINE)),
                                       ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                                       ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
                story += [t, Spacer(1, 9)]
                if b['note']:
                    story.append(p(b['note'], 'CaptionResearch'))
            else:
                title = Paragraph(symbols('<font color="' + ORANGE + '">' + escape(b['figure_id']) + '</font> · ' + escape(b['title'])), styles['FigureResearch'])
                story.append(KeepTogether([title, Card(draw_chart(b), fill=PAPER, pad=10, radius=18), Spacer(1, 8), p(b['finding'], 'FindingResearch'),
                                           p(b['explanation']),
                                           Paragraph(symbols('<b>Decision implication.</b> ' + escape(b['implication'])), styles['ImplicationResearch']),
                                           p(b['source'] + ' Exhibit data: DATA/' + b['figure_id'] + '.json', 'CaptionResearch')]))
        story.append(PageBreak())
    if isinstance(story[-1], PageBreak):
        story.pop()
    pdf.multiBuild(story)


def make_html(doc):
    from reportlab.graphics import renderSVG
    def esc(x):return escape(str(x))
    toc='<nav aria-label="Contents"><h2>Contents</h2><ol>'+''.join(f'<li><a href="#s{i}">{esc(s["title"])}</a></li>'for i,s in enumerate(doc['sections']))+'</ol></nav>'
    body=[]
    for i,s in enumerate(doc['sections']):
        chunks=[f'<section id="s{i}"><h2>{esc(s["title"])}</h2>']
        for b in s['blocks']:
            if b['kind']=='paragraph':chunks.append('<p>'+esc(b['text'])+'</p>')
            elif b['kind']=='table':
                chunks.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in b['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(v)+'</td>'for v in row)+'</tr>'for row in b['rows'])+'</tbody></table></div>')
                if b['note']:chunks.append('<p class="source">'+esc(b['note'])+'</p>')
            else:
                svg=renderSVG.drawToString(draw_chart(b))
                if isinstance(svg,bytes):svg=svg.decode()
                svg=re.sub(r'<\?xml[^>]*\?>','',svg);svg=re.sub(r'<!DOCTYPE[^>]*>','',svg)
                svg=svg.replace('<svg ','<svg role="img" aria-label="'+esc(b['title'])+'" ',1)
                # reportlab names every clip path "clip"; inline SVGs share one ID space, so make it unique per exhibit.
                clip='clip-'+re.sub(r'[^A-Za-z0-9-]','',b['figure_id'])
                svg=svg.replace('id="clip"','id="'+clip+'"').replace('url(#clip)','url(#'+clip+')')
                chunks.append('<figure><h3>'+esc(b['figure_id']+' · '+b['title'])+'</h3><div class="exhibit">'+svg+'</div><figcaption><p class="finding">'+esc(b['finding'])+'</p><p>'+esc(b['explanation'])+'</p><p><strong>Decision implication.</strong> '+esc(b['implication'])+'</p><p class="source">'+esc(b['source'])+' · <a href="DATA/'+b['figure_id']+'.json">Exhibit data</a></p></figcaption></figure>')
        chunks.append('</section>');body.append(''.join(chunks))
    css='''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#fafbf9;color:#243b40;font:17px/1.7 Georgia,serif}main{max-width:1000px;margin:auto;padding:30px clamp(16px,4vw,55px)}header{min-height:65vh;padding:60px 0 30px;border-bottom:2px solid #173f43}h1{font:700 clamp(42px,8vw,78px)/1.05 system-ui;letter-spacing:-.04em;margin:20px 0}h2{font:650 clamp(24px,4vw,34px)/1.25 system-ui;margin:40px 0 20px}h3{font:650 20px/1.4 system-ui;margin:0 0 16px}p{max-width:82ch;overflow-wrap:anywhere}.eyebrow,.source{font:12px/1.6 system-ui;letter-spacing:.015em;color:#53686d}.eyebrow{text-transform:uppercase;letter-spacing:.14em}nav{padding:25px 0;border-bottom:1px solid #cad5d3}nav a,a{color:#175765}nav li{padding:5px 0}section{padding:18px 0 30px;border-bottom:1px solid #cad5d3}figure{margin:30px 0;padding:24px 0;border-top:2px solid #173f43}svg{width:100%;height:auto;display:block}svg text{font-family:Arial,sans-serif}.finding{font-weight:700}.table-wrap{max-width:100%;overflow-x:auto;margin:24px 0}table{width:100%;border-collapse:collapse;font:14px/1.55 system-ui}th{text-align:left;background:#e9efed;font-weight:650}td,th{padding:12px 10px;border-bottom:1px solid #dce4e2;vertical-align:top;overflow-wrap:anywhere}footer{margin:35px 0;font:12px/1.7 system-ui;overflow-wrap:anywhere}.exhibit{min-width:0}@media(max-width:600px){body{font-size:16px}header{min-height:0;padding:25px 0}figure{padding:15px 0}table{font-size:12px}td,th{padding:8px 5px}nav ol{padding-left:22px}.exhibit{overflow-x:auto}svg{min-width:490px}}@media print{body{background:white}header{break-after:page}nav{break-after:page}section{break-before:page}figure{break-inside:avoid}a{color:inherit}main{padding:0}.table-wrap{overflow:visible}}'''
    fonts=Path(__file__).resolve().parent/'fonts'
    def face(family,file,weight):
        data=base64.b64encode((fonts/file).read_bytes()).decode('ascii')
        return "@font-face{font-family:"+family+";src:url(data:font/ttf;base64,"+data+") format('truetype');font-weight:"+str(weight)+";font-display:swap}"
    for old,new in (('#fafbf9','#FAF6EC'),('#243b40','#1C1D18'),('#173f43','#1C1D18'),('#cad5d3','#E6DFCF'),('#dce4e2','#E6DFCF'),
                    ('#53686d','#5D5C52'),('#175765','#2A52D1'),('#e9efed','#FCF0C2'),('Georgia,serif','BoyunText,system-ui,sans-serif'),('system-ui','BoyunText,system-ui')):
        css=css.replace(old,new)
    css+=("h1,h2,h3{font-family:BoyunDisplay,system-ui,sans-serif;font-weight:800}h1{text-transform:uppercase;letter-spacing:-.035em;line-height:1}"
          "h2{font-size:clamp(28px,4.4vw,44px);letter-spacing:-.03em;line-height:1.05}"
          "section{border-bottom:0}nav{border-bottom:0}header{border-bottom:0}"
          "figure{background:#FFFDF8;border:1px solid #E6DFCF;border-radius:24px;padding:22px;box-shadow:0 8px 24px rgba(28,29,24,.07)}"
          "th{background:#FCF0C2}.table-wrap{border:1px solid #E6DFCF;border-radius:18px;background:#FFFDF8}svg text{font-family:BoyunText,Arial,sans-serif}"
          "a{text-underline-offset:.2em}a:focus-visible{outline:3px solid #2A52D1;outline-offset:3px}::selection{background:#F47B3B;color:#fff}"
          ".eyebrow{display:inline-block;border:1px solid #1C1D18;border-radius:999px;padding:4px 12px;color:#1C1D18;font-weight:700}")
    css=(face('BoyunText','InstrumentSans-400.ttf',400)+face('BoyunText','InstrumentSans-700.ttf',700)+face('BoyunDisplay','BricolageGrotesque-800.ttf',800)+css)
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+esc(doc.get('project','MACRON'))+' · '+esc(doc['title'])+'</title><style>'+css+'</style></head><body><main><header><p class="eyebrow">Boyun / financial scenario research</p><h1>'+esc(doc.get('project','MACRON'))+'<br>'+esc(doc['title'])+'</h1><p>'+esc(doc['subtitle'])+'</p><p class="eyebrow">Research edition · '+esc(doc['asof'])+'</p>'+''.join('<p>'+esc(t)+'</p>'for t in doc['highlights'])+'</header>'+toc+''.join(body)+'<footer>Conditional simulation research. No calibrated real-world odds. Result '+doc['result_sha256']+'</footer></main></body></html>'


def make_markdown(doc):
    parts=['# '+doc.get('project','MACRON')+' / '+doc['title'],'',doc['subtitle'],'','Research edition: '+doc['asof'],'','## Contents','']
    parts += [f'{i+1}. {s["title"]}'for i,s in enumerate(doc['sections'])]
    for s in doc['sections']:
        parts+=['','## '+s['title'],'']
        for b in s['blocks']:
            if b['kind']=='paragraph':parts += [b['text'],'']
            elif b['kind']=='table':
                parts += ['| '+' | '.join(b['headers'])+' |','| '+' | '.join(['---']*len(b['headers']))+' |']
                parts += ['| '+' | '.join(v.replace('|','/')for v in row)+' |'for row in b['rows']]
                parts += ['',b['note'],'']
            else:parts += ['### '+b['figure_id']+' · '+b['title'],'',b['finding'],'',f'![{b["title"]}](FIGURES/{b["figure_id"]}.svg)','',b['explanation'],'','Decision implication: '+b['implication'],'',b['source'],'']
    return '\n'.join(parts)


def build(bundle,output,verify=False):
    destination=Path(output).resolve()
    if destination.exists():raise ValueError('output must be a new directory; preserve earlier editions')
    context=load_bundle(bundle,verify)
    documents=[world_creation(context),case_document(context,'BEAR'),case_document(context,'BULL'),technical_document(context),decision_record_document(context)]
    destination.mkdir(parents=True,mode=0o700)
    for folder in ('DATA','FIGURES'):(destination/folder).mkdir()
    from reportlab.graphics import renderSVG
    files=[]
    for index,doc in enumerate(documents):
        count=0
        for s in doc['sections']:
            for b in s['blocks']:
                if b['kind']=='chart':
                    count+=1;b['figure_id']=f'{index+1:02d}-F{count:02d}'
                    (destination/'DATA'/f'{b["figure_id"]}.json').write_text(json.dumps(b,indent=2,ensure_ascii=False)+'\n')
                    renderSVG.drawToFile(draw_chart(b),str(destination/'FIGURES'/f'{b["figure_id"]}.svg'))
        name=f'{index+1:02d}-'+doc['kind']
        make_pdf(doc,destination/(name+'.pdf'))
        (destination/(name+'.html')).write_text(make_html(doc))
        (destination/(name+'.md')).write_text(make_markdown(doc))
        files.append({'id':name,'title':doc['title'],'figures':count,'sections':len(doc['sections'])})
    manifest={'schema_version':'financial-casebook.v1','source_result_sha256':context['data']['result_sha256'],
              'source_bundle':str(context['root']),'source_inputs':context['inputs'],'documents':files,
              'replay_this_build':context['verify'],'replay_checks':context['checks'],
              'new_model_calls':0,'world_odds':'unknown_uncalibrated','native_complete_to_336h':False,
              'builder_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
    (destination/'DATA'/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    index_html='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MACRON financial research</title><style>body{max-width:780px;margin:60px auto;padding:20px;background:#FAF6EC;font:18px/1.7 system-ui;color:#1C1D18}h1{font-size:48px;text-transform:uppercase;letter-spacing:-.03em;line-height:1}article{background:#FFFDF8;border:1px solid #E6DFCF;border-radius:24px;padding:22px 26px;margin:16px 0;box-shadow:0 8px 24px rgba(28,29,24,.07)}a{color:#2A52D1}</style><h1>MACRON<br>Financial research</h1><p>Read World Creation first, then Bear Case or Bull Case. The technical report records execution, cost and decisions. Native paths remain incomplete; offline reference and stress are separate.</p>'
    for f in files:index_html+='<article><h2>'+f['title']+'</h2><p><a href="'+f['id']+'.html">Read HTML</a> · <a href="'+f['id']+'.pdf">Download PDF</a> · <a href="'+f['id']+'.md">Markdown</a></p><p>'+str(f['figures'])+' numbered exhibits, with explanations and source data.</p></article>'
    index_html+='<p>Original interactive actor views and raw run records remain in the prior edition. No new model calls or scenario changes.</p>'
    (destination/'index.html').write_text(index_html)
    (destination/'README.md').write_text('# MACRON financial research\n\nStart with [the report index](index.html).\n\n'+ '\n'.join(f'- [{f["title"]}]({f["id"]}.pdf) · [standalone HTML]({f["id"]}.html)'for f in files)+'\n\nNo new model calls. Real-world odds unknown; native paths remain incomplete. Original run evidence and older report editions are preserved.\n')
    return {'status':'built','output':str(destination),'documents':files,'result_sha256':manifest['source_result_sha256'],
            'new_model_calls':0,'replayed_paths':len(context['checks'])}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--verify-replay',action='store_true',help='Independently replay all source paths without inference')
    args=parser.parse_args()
    print(json.dumps(build(args.bundle,args.output,args.verify_replay),indent=2))
