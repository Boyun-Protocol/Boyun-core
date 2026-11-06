"""Replay-derived explanatory reports and self-contained actor-specific event views."""
import argparse
import base64
from collections import Counter
import csv
from fractions import Fraction
from html import escape
import json
import gzip
import re
from pathlib import Path

from decision_lab.agent_worlds import digest
from decision_lab.io_helpers import read_json, json_bytes, write_artifacts
from decision_lab.lifecycle_runs import replay_lifecycle


def number(value):
    return float(Fraction(value))


def public_events(checkpoint, campaign_schedule=()):
    events = list(checkpoint['events'])
    due = {campaign['id']: campaign['due_second'] for campaign in campaign_schedule}
    for campaign in checkpoint.get('campaigns', []):
        if due.get(campaign['id']) == checkpoint['second']:
            events.append({'kind': 'campaign_delivery', 'id': campaign['id'], 'second': checkpoint['second'],
                           'text': campaign.get('text', campaign['id']) + ' / status: ' + campaign['status']})
    for actor, choice in checkpoint['choices'].items():
        if choice == 'publish':
            events.append({'kind': 'public_post', 'actor': actor, 'second': checkpoint['second'],
                           'text': actor + ' published a modeled public update. Publication is not guaranteed demand.'})
    return events


def node_guidance(point):
    rejected = [item for item in point['executions'] if item['status'].startswith('rejected')]
    if rejected:
        action, reason = 'Review a smaller order or wait for executable depth.', 'Own last execution was rejected: ' + ', '.join(item['status'] for item in rejected) + '. Repeating the same size does not resolve slippage or liquidity constraints.'
    elif (point.get('own_policy') or {}).get('response'):
        action, reason = 'Review the selected response branch and remaining exposure.', 'A founder alert is active in your own policy state; compare staged realized cash with the residual inventory and pending tranches rather than reading market cap as sale proceeds.'
    elif point['cash_cents'] == 0:
        action, reason = 'Do not place an unfunded buy; review existing exposure or wait.', 'Your available cash is zero. Advertising does not create funds in your wallet or guarantee an executable exit.'
    elif point['tokens'] == 0:
        action, reason = 'Keep entry optional; inspect volume and executable liquidity before buying.', 'You have no token exposure to sell. A paid post or a scheduled session alone is not evidence of favorable net returns after fees.'
    else:
        action, reason = 'Review position size against executable liquidity and your remaining cash.', 'You hold both cash and tokens. Turnover can contain sales or recycled cash; compare the saved choices and fills before increasing exposure.'
    return {'action': action, 'reason': reason, 'basis': 'Transparent own-state risk-control rule, not an additional model call.',
            'limitation': 'No guarantee of the best return; missing future demand and calibrated probabilities prevent an optimal-trade claim.'}


def path_statistics(rows, settlements, decisions):
    peak, drawdown = 0, None
    for row in rows:
        peak = max(peak, row['mc_usd'])
        if peak > 0:
            drawdown = max(drawdown or 0, 1 - row['mc_usd'] / peak)
    turnover = Counter()
    executed = [item for item in settlements if item['status'] == 'executed']
    for item in executed:
        turnover[item['actor']] += item.get('cash_cents', 0)
    rejected = sum(item['status'].startswith('rejected') for item in settlements)
    total = sum(turnover.values())
    return {'trade_attempts': len(settlements), 'filled_trades': len(executed),
            'rejected_trades': rejected, 'rejection_rate': rejected / len(settlements) if settlements else None,
            'sampled_peak_to_trough_drawdown': drawdown,
            'largest_actor_turnover_share': max(turnover.values()) / total if total else None,
            'turnover_by_actor_cents': dict(turnover), 'choices_by_actor': decisions,
            'definition': 'Drawdown uses saved post-settlement market-cap boundaries, not intrabarrier extrema. Turnover sums executed buy debits and sell receipts (sells net of the static modeled fee), not fresh inflow or an exact exchange gross-volume convention.'}


def matched_comparisons(paths):
    groups = {}
    for path in paths:
        groups.setdefault((path['mode'], path['case']), {})[path['policy']] = path
    comparisons = []
    for (mode, case), pair in groups.items():
        pause, exit_path = pair.get('pause-and-observe'), pair.get('staged-exit')
        if not pause or not exit_path:
            continue
        left = {row['second']: row for row in pause['rows']}
        right = {row['second']: row for row in exit_path['rows']}
        common = left.keys() & right.keys()
        if not common:
            continue
        second = max(common)
        comparisons.append({'mode': mode, 'case': case, 'regime': pause['regime'],
                            'position_usd': pause['position_usd'], 'upfront_usd': pause['upfront_usd'],
                            'second': second, 'pause_cash_usd': left[second]['founder_net_cash_usd'],
                            'exit_cash_usd': right[second]['founder_net_cash_usd'],
                            'exit_minus_pause_cash_usd': right[second]['founder_net_cash_usd'] - left[second]['founder_net_cash_usd']})
    return comparisons


def project_actor(checkpoint, evidence, actor, events=None):
    observation = checkpoint['observations'][actor]
    market = checkpoint['market_after']
    own = checkpoint['balances_after'][actor]
    decision = evidence.get(actor, {})
    scores = decision.get('answers', {}).get('action', {})
    value = {'second': checkpoint['second'], 'step': checkpoint['step'], 'hash': checkpoint['checkpoint_sha256'],
            'mc_usd': number(market['market_cap_usd_exact']), 'fdv_usd': number(market['fdv_usd_exact']),
            'venue_cash_usd': market['real_cash_cents'] / 100, 'volume_usd': market['total_volume_cents'] / 100,
            'volume_6h_usd': None if market['six_hour_signal']['current_volume_cents'] is None else market['six_hour_signal']['current_volume_cents'] / 100,
            'peak_fraction': market['six_hour_signal']['fraction_of_peak_exact'],
            'cash_cents': own['cash_cents'], 'tokens': own['tokens'], 'choice': checkpoint['choices'][actor],
            'executions': [receipt for receipt in checkpoint['settlements'] if receipt['actor'] == actor],
            'scores': scores.get('probabilities'), 'provider_choice': scores.get('choice'),
            'events': public_events(checkpoint) if events is None else events, 'visible_topics': observation['events'],
            'coordination': observation['coordination'], 'memory': observation['memory'],
            'own_policy': observation.get('own_policy')}
    value['guidance'] = node_guidance(value)
    return value


def collect_matrix(directory, mode):
    root = Path(directory)
    matrix = read_json(root / 'matrix.json')
    if matrix['status'] == 'running':
        raise ValueError('final reports require a stopped matrix, not a moving result set')
    paths = []
    actors = {}
    for item in matrix['paths']:
        directory = root / item['case'] / item['policy']
        manifest = read_json(directory / 'manifest.json')
        verification = replay_lifecycle(directory)
        package = read_json(directory / 'package.json')
        actors.update({actor['id']: actor for actor in package['actors']})
        rows = []
        projections = {actor['id']: [] for actor in package['actors']}
        attempts = Counter()
        settlements = []
        decisions = {actor['id']: Counter() for actor in package['actors']}
        for index in range(manifest['completed_steps']):
            saved = read_json(directory / f'step-{index:05d}.json')
            checkpoint = saved['checkpoint']
            events = public_events(checkpoint, package['campaigns'])
            market = checkpoint['market_after']
            counts = Counter('buy' if choice.startswith('buy_') else 'sell' if choice.startswith('sell_') else choice
                             for choice in checkpoint['choices'].values())
            controlled = checkpoint['balances_after']['founder']['cash_cents'] + checkpoint['balances_after']['reserve']['cash_cents']
            rows.append({'second': checkpoint['second'], 'hours': checkpoint['second'] / 3600,
                         'mc_usd': number(market['market_cap_usd_exact']), 'fdv_usd': number(market['fdv_usd_exact']),
                         'venue_cash_usd': market['real_cash_cents'] / 100,
                         'volume_usd': market['total_volume_cents'] / 100,
                         'volume_6h_usd': None if market['six_hour_signal']['current_volume_cents'] is None else market['six_hour_signal']['current_volume_cents'] / 100,
                         'founder_net_cash_usd': (controlled - package['founder']['capital_cents']) / 100,
                         'phase': market['phase'], 'events': events,
                         'choice': ' / '.join(f'{counts.get(action, 0)} {action}' for action in ('buy', 'sell', 'wait', 'publish')),
                         'checkpoint_sha256': checkpoint['checkpoint_sha256']})
            for receipt in checkpoint['settlements']:
                settlements.append(receipt)
                attempts[receipt['status']] += 1
                if receipt['status'] == 'executed':
                    attempts[receipt['side']] += 1
            for actor in projections:
                decisions[actor][checkpoint['choices'][actor]] += 1
                projections[actor].append(project_actor(checkpoint, saved['decision_evidence'], actor, events))
        peaks = [row['mc_usd'] for row in rows]
        path = {'id': item['case'] + '/' + item['policy'], 'case': item['case'], 'policy': item['policy'],
                'mode': mode, 'regime': package['regime'], 'position_usd': package['founder']['position_cents'] / 100,
                'upfront_usd': package['founder']['upfront_cents'] / 100,
                'status': manifest['status'], 'steps': manifest['completed_steps'],
                'new_jev_calls_in_settled_barriers': manifest['model_calls'], 'summary': manifest['summary'],
                'verification': verification, 'attempts': dict(attempts), 'rows': rows,
                'recorded_peak_mc_usd': max(peaks) if peaks else None,
                'last_hour': rows[-1]['hours'] if rows else None,
                'assumptions': package['assumptions'], 'actors': projections,
                'statistics': path_statistics(rows, settlements, decisions), 'campaign_windows': []}
        for campaign in package['campaigns']:
            second = campaign['due_second']
            before = next((row for row in reversed(rows) if row['second'] < second), None)
            after = next((row for row in rows if row['second'] >= second + 6 * 3600), None)
            path['campaign_windows'].append({'campaign': campaign['id'], 'scheduled_second': second,
                'window_status': 'recorded' if before and after else 'incomplete_or_no_prelaunch_baseline',
                'six_hour_turnover_change_usd': after['volume_usd'] - before['volume_usd'] if before and after else None,
                'six_hour_mc_return': after['mc_usd'] / before['mc_usd'] - 1 if before and after and before['mc_usd'] > 0 else None,
                'interpretation': 'Before/after descriptive association; intervening actor trades and events overlap. Not incremental campaign ROI or causal uplift.'})
        paths.append(path)
    return matrix, paths, actors


def interpretation(path, metric):
    rows = path['rows']
    if not rows:
        return 'No complete decision barrier is recorded. No path or result is invented.'
    first, last = rows[0], rows[-1]
    label = {'mc_usd': 'modeled circulating market cap', 'venue_cash_usd': 'real venue cash',
             'volume_usd': 'cumulative executed turnover', 'founder_net_cash_usd': 'founder net cash',
             'volume_6h_usd': 'six-hour executed turnover'}[metric]
    available = [row for row in rows if row.get(metric) is not None]
    beginning = available[0][metric] if available else None
    ending = available[-1][metric] if available else None
    trend = ('is unavailable in the recorded window' if not available else
             f'changes from ${beginning:,.2f} at +{available[0]["hours"]:.2f}h to ${ending:,.2f} at +{available[-1]["hours"]:.2f}h')
    return (f'This path’s {label} {trend} across its recorded {last["hours"]:.2f} hours. '
            + ('Initial six-hour warmup values are omitted, not replaced with zero. ' if metric == 'volume_6h_usd' else '')
            + f'The path records {path["attempts"].get("buy", 0)} filled buys and {path["attempts"].get("sell", 0)} filled sells; '
            f'{sum(count for status, count in path["attempts"].items() if status.startswith("rejected"))} attempted executions were rejected. '
            'Those outcomes follow finite actor funds, actual integer settlement, fees and constrained choices—not a price uplift added after marketing. '
            'A rise in turnover can include sales or recycled cash and is not evidence of fresh investors. Market cap and FDV are not executable liquidity. '
            'Founder cash includes upfront costs once but excludes unsold token value; estimated liquidation value is a separate hypothetical quote. '
            + ('This is a complete fourteen-day conditional path, not a calibrated forecast. ' if path['status'] == 'completed' else
               'This native path is unfinished; its last value is not a fourteen-day terminal result. ')
            + ('Jev decisions are current-state model judgments, not observed human behavior.' if path['mode'] == 'native' else
               'This offline reference is a declared synthetic policy calculation, not Jev or empirical behavior.'))


def report_markdown(data, regime=None):
    paths = [path for path in data['paths'] if regime is None or path['regime'] == regime]
    native = data.get('native', {})
    budget = native.get('budget', {})
    context = data.get('market_context')
    live = [path for path in paths if path['mode'] == 'native']
    findings = []
    if live:
        fills = sum(path['summary'].get('trade_count', path.get('attempts', {}).get('buy', 0) + path.get('attempts', {}).get('sell', 0)) for path in live)
        completed = sum(path['mode'] != 'native' and path['status'] == 'completed' for path in paths)
        findings = ['', f'- These dependent native paths record {fills:,} filled trades; delivered marketing did not result in an all-wait simulation.',
                    f'- {completed} separate synthetic paths in this document complete fourteen days. They are engineering references/stress, not native Jev results.',
                    '- Prepaid costs and fees reduce cash; unsold inventory remains separate. Compare policies only at exact common saved times, not unequal unfinished endpoints.', '']
    heading = f'MACRON · {regime} Market scenario' if regime else 'MACRON · fourteen-day lifecycle comparison'
    lines = ['# ' + heading, '', '## 1. Decision brief', '',
             'Compare the accepted founder plans and response branches; no single investment plan is selected.',
             'Launch root: 2 November 2026, 12:00 UTC+4. Target horizon: +336h, ending 16 November.',
             '**Live unfinished paths remain unfinished. Complete offline references are not Jev results.**', '',
             f"Native status: {native.get('status', 'not dispatched')}. Reported-input cost estimate: ${budget.get('spent_estimate_micro_usd', 0) / 1000000:.6f}; authorized cap: $2.", '',
             *findings,
             '## 2. Evidence and assumptions', '',
             'Every input and consequence is linked in the saved evidence registers. These are conditional assumption worlds, not validated market forecasts.',
             'The official Assembly schedule establishes session plans, not known vote results. No six-to-twelve-month arrival/attention dataset has been fitted.', '',
             '## 3. Plans and resources', '',
             'Founder capital is $50,000 with a protected $10,000 reserve. Position budgets are $5k/$10k/$15k and upfront costs $5k/$10k.',
             'The $3,000 KOL/operator cash allocation is inside upfront costs. Token grants come from founder-acquired tokens, not free founder inventory.', '',
             '## 4. Actors and unequal information', '',
             'Sixteen explicit funded/observer roles receive current own state, public market history and only permitted private instructions.',
             'A fourth retail role splits an existing wallet allocation. Public actor files exclude peer private decisions physically, not just through UI filters.', '',
             '## 5. Timeline and turning points', '',
             'Every hourly boundary is retained, alongside minute launch steps, researched session starts and actual response/acknowledgement times.',
             'Open the interactive DAG to inspect actions, resulting events, current statistics and saved scores at a boundary.', '',
             '## 6. Outcomes and cash accounting', '',
             '| Mode | Regime | Position / upfront | Response | Recorded hours | Net cash at recorded endpoint | Status |',
             '|---|---|---|---|---:|---:|---|']
    for path in paths:
        summary = path['summary']
        hour = path['last_hour']
        lines.append(f"| {path['mode']} | {path['regime']} | ${path['position_usd']:,.0f} / ${path['upfront_usd']:,.0f} | {path['policy']} | {hour:.2f} | ${summary['founder_net_cash_cents']/100:,.2f} | {path['status']} |" if hour is not None else
                     f"| {path['mode']} | {path['regime']} | not settled | {path['policy']} | unknown | unknown | {path['status']} |")
    lines += ['', 'Negative net cash does not by itself price remaining tokens. No-launch retains $50,000 cash and has zero cash profit. Compare endpoints only at matching times.', '',
              '### Matched-time cash comparison', '',
              '| Mode / regime | Position / upfront | Common hour | Pause net cash | Exit net cash | Exit minus pause |',
              '|---|---|---:|---:|---:|---:|']
    for pair in matched_comparisons(paths):
        lines.append(f"| {pair['mode']} / {pair['regime']} | ${pair['position_usd']:,.0f} / ${pair['upfront_usd']:,.0f} | {pair['second']/3600:.2f} | ${pair['pause_cash_usd']:,.2f} | ${pair['exit_cash_usd']:,.2f} | ${pair['exit_minus_pause_cash_usd']:,.2f} |")
    lines += ['', 'This difference compares realized cash at the latest exact common saved timestamp. It excludes unsold inventory and is not a ranking of total wealth or future performance.', '',
              '## 7. Statistics and uncertainty', '',
              'There is one matched seed per plan, not a representative population sample. Actor calls are not independent market worlds; paired policies and parameter arms are dependent.',
              'No p95, CVaR, calibrated crash odds or 20% chance of $5M is claimed. Threshold reach is a recorded path property, not an estimated real-market likelihood.', '',
              'Per-path data includes filled buys/sells, rejection counts and denominator, post-settlement peak-to-trough drawdown, turnover concentration and each actor’s choice counts. Zero attempts have undefined rejection rates, not zero execution risk. Traded cash sums buy debits and sell receipts; sells are net of the static modeled fee, not an exact exchange gross-volume convention.', '',
              '## 8. Drivers and counterfactuals', '',
              'Compare pause versus staged sale under common initial conditions. The actual actor state evolves after each fill, so later decisions may differ.',
              'BULL/BEAR change a qualitative risk-appetite hypothesis; differences do not identify a causal real-world regime effect. Offline rules are a separate mechanics reference.', '',
              'Campaign windows record the change in turnover and market cap from the last saved pre-publication state through six hours after delivery. Missing windows remain incomplete. Overlapping campaigns and independent trades prevent attributing that change to paid exposure alone.', '',
              '## 9. Edge cases and coverage', '',
              'Mechanically covered: no-demand periods, campaign publication without purchases, inventory/cash depletion, slippage rejection, incomplete migration, early founder exit, delayed/deferred/pending tranches and continued market activity.',
              'Not established: a fitted arrival process, exact launch-program fees, MEV, chain outages, real vendor delivery reliability, known political outcomes or causal campaign ROI.', '',
              '## 10. Expected and surprising', '',
              'Expect cash losses from fully prepaid costs and fees unless realized proceeds exceed them. Advertising can coincide with selling or waiting; delivery is not conversion.',
              'Compare any apparent surprise against the named no-launch baseline, same-time paired branch and finite wallet constraints, not an invented market expectation.', '',
              '## 11. Decision options and regime applicability', '',
              'Choose regime applicability using your own as-of BTC trend/breadth, CEX versus DEX spot participation, stablecoin/depth conditions, spreads and verified disruptions. No current regime or Binance-incident explanation is asserted.',
              *( [f"Observed market context: {len(context['daily'])} daily Solana DEX volume observations, 2 May–1 November 2026, from DefiLlama. These chain-wide amounts are not memecoin-only arrivals and were collected for the report after the native world was frozen. They do not calibrate persona choices or identify the current regime."] if context else [] ),
              'Founder rules pause discretionary funding on alerts; funding needs at least 60% of first-48h six-hour-volume peak. Exit/defer rules retain the user’s 25% threshold and one-hour price-hold condition.',
              'Guidance explains those supported rules and liquidity constraints; it cannot guarantee an optimal trade or fill.', '',
              '## 12. Limits, reproduction and follow-up', '',
              'Each path includes an engine/version hash and exact zero-call replay. Failed or unsettled decisions are not silently filled in.',
              'Do not mix complete offline reference results with partial live results, or compare partial endpoints as if they were all day fourteen.',
              'The $2 authorization explicitly permits unfinished live paths across the full matrix. Confirmed receipts can be recovered without redispatch; requests with unknown outcomes retain their reservations and their affected paths stop. Further spend above the shared cap needs new authorization.', '',
              '### Primary references', '',
              '- [Official Pump program mechanics](https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md)',
              '- [Assembly dated agenda](https://www.assemblee-nationale.fr/dyn/static/seance/conference.pdf)',
              '- [FEC election-date reference](https://www.fec.gov/introduction-campaign-finance/election-and-voting-information/)',
              '- [Jev published tariff](https://docs.typesafe.ai/models)',
              '- [Pump.fun study: one-month cohort, not six-month calibration](https://arxiv.org/html/2602.14860v1)', '']
    if context:
        lines += ['- [Observed Solana DEX daily series](' + context['source_url'] + ')',
                  '- [DefiLlama metric definitions](https://docs.llama.fi/analysts/data-definitions)',
                  '- [CoinGecko global indicator definitions](https://docs.coingecko.com/reference/crypto-global)', '']
    return '\n'.join(lines)


def interactive_html(data):
    payload = json.dumps(data, separators=(',', ':'), ensure_ascii=True).replace('<', '\\u003c')
    if len(payload) > 2000000:
        payload = json.dumps({'encoding': 'gzip-base64',
                              'payload': base64.b64encode(gzip.compress(payload.encode(), mtime=0)).decode()})
    policy_note = (' Funding gate ≥60%; exit trigger ≤25%. Recovery deferral also requires one-hour price holding.'
                   if data['actor'] in {'analyst', 'founder'} else
                   ' Public turnover is visible; private team funding/exit instructions are not included in this projection.')
    enhancements = '''
const originalRender=render;
render=function(){
  originalRender();
  const paths=data.paths.filter(path=>path.mode===get('mode').value&&path.case===get('case').value);
  const path=paths[lane];if(!path)return;
  let point=path.points[Number(get('step').value)];
  const start=Number(get('start').value),end=start+Number(get('window').value);
  if(point&&(point.second/3600<start||point.second/3600>end)){
    const index=path.points.findIndex(item=>item.second/3600>=start&&item.second/3600<=end);
    if(index>=0){get('step').value=index;originalRender();point=path.points[index]}
  }
  const labeled=new Map();
  get('timeline').querySelectorAll('text').forEach(label=>{
    const y=Number(label.getAttribute('y'));if(![105,122,230,247].includes(y))return;
    const laneKey=y>=200?1:0,x=Number(label.getAttribute('x')),previous=labeled.get(laneKey);
    if(previous!=null&&x-previous<180)label.remove();else labeled.set(laneKey,x);
  });
  if(point?.guidance){const block=element('article');block.append(element('h2','Decision guidance / own permitted state'),element('p',point.guidance.action),element('p',point.guidance.reason),element('small',point.guidance.basis+' '+point.guidance.limitation));get('detail').append(block)}
};
options(get('mode'),modes.map(mode=>[mode,mode==='native'?'LIVE JEV · recorded boundaries':mode==='offline_stress_4x'?'ARTIFICIAL 4x ACTIVITY STRESS · offline':'OFFLINE REFERENCE · not Jev']));
if(innerWidth<600)get('window').value='1';
['case','window','start','metric'].forEach(id=>get(id).oninput=render);cases();
'''
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"><title>MACRON · event paths</title><style>
:root{color-scheme:light dark}*{box-sizing:border-box}body{font:16px/1.5 system-ui;margin:0 auto;max-width:1200px;padding:clamp(14px,4vw,40px);overflow-wrap:anywhere}h1{font-size:clamp(2rem,6vw,4rem);line-height:1.05;letter-spacing:-.045em;max-width:19ch}h2{font-size:1.3rem}p{max-width:80ch}header{border-bottom:2px solid;padding-bottom:24px}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:.8rem}nav,.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr));gap:12px;margin:24px 0}label{display:grid;gap:5px;min-width:0}select,input,button{font:inherit;max-width:100%;min-width:0;padding:9px}select{width:100%}article,section.panel{border:1px solid GrayText;border-radius:8px;padding:18px;margin:18px 0}.stats strong{font-size:1.6rem;display:block}.scroll{overflow:auto}svg{width:100%;min-width:600px;height:auto;display:block}svg text{fill:currentColor;font:12px system-ui}svg .edge{stroke:GrayText;stroke-width:3;cursor:pointer}svg .point{stroke:currentColor;stroke-width:1;cursor:pointer;fill:Canvas}svg .selected{fill:Highlight}svg .quiet{opacity:.65}pre{font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}button{cursor:pointer}dl{display:grid;grid-template-columns:1fr 1fr;gap:10px}dt{font-weight:650}dd{margin:0}#timeline{touch-action:pan-x}small{font-size:.85rem}details{margin-top:14px}a{color:LinkText}svg.chart{min-width:0}footer{border-top:1px solid GrayText;margin-top:30px;padding:18px 0}@media(max-width:599px){nav,dl{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}svg{min-width:720px}}@media print{nav,button,input{display:none}body{max-width:none}.panel{break-inside:avoid}}</style></head><body><header><p class="eyebrow">MACRON / stateful event paths / conditional research</p><h1>Follow the actions. Inspect the consequences.</h1><p id="scope"></p><p><strong>Live unfinished paths are not completed forecasts.</strong> The offline reference uses synthetic policies, not Jev. Scores and path frequencies are not calibrated real-world event odds.</p></header>
<nav><label>Evidence mode<select id="mode"></select></label><label>Plan and market scenario<select id="case"></select></label><label>Visible time window<select id="window"><option value="24">One day</option><option value="6">Six hours</option><option value="1">One hour</option><option value="336">Full fourteen days</option></select></label><label>Window starts at hour<input id="start" type="range" min="0" max="312" step="1" value="0"></label></nav><p id="coverage"></p><div id="stats" class="stats"></div>
<section class="panel"><h2>Actions are edges. Saved event states are nodes.</h2><p>Each response policy is a separate lane. Horizontal position is elapsed UTC hours from launch. Click a node or action edge; use the time-window control to inspect dense periods. Unexecuted time stays blank.</p><div id="timeline" class="scroll"></div><label>Recorded boundary<input id="step" type="range" min="0" max="1" value="0"></label><div id="detail"></div></section>
<section class="panel"><h2>Market cap, liquidity and turnover</h2><label>Chart metric<select id="metric"><option value="mc_usd">Modeled circulating market cap</option><option value="fdv_usd">FDV</option><option value="venue_cash_usd">Real venue cash</option><option value="volume_usd">Cumulative executed turnover</option><option value="volume_6h_usd">Six-hour turnover</option></select></label><div id="chart"></div><p id="explanation"></p></section>
<section class="panel"><h2>Chances, guidance and limits</h2><p id="odds">Above $5M: real-world odds unknown. A threshold reached in one paired scenario is not a calibrated probability.</p><p>Choose market applicability from dated BTC trend/breadth, CEX/DEX spot activity, stablecoin/depth and spread evidence. BULL and BEAR are scenario hypotheses, not a diagnosis of today’s market.</p><p>The six-hour volume signal is total turnover; selling or recycled MM cash can sustain it. Exposure, KOL posts and scheduled sessions do not guarantee new buyers or a price rise.</p><button id="download">Download this view’s data</button></section><footer>Launch: 2 Nov 2026, 08:00 UTC / 12:00 UTC+4. Target: +336h. Full private analyst artifacts and actor-only projections are separate files. This file contains only its declared projection.</footer>
<script id="data" type="application/json">__DATA__</script><script>
(async()=>{
let decoded=JSON.parse(document.getElementById('data').textContent);
if(decoded.encoding==='gzip-base64'){
  if(!globalThis.DecompressionStream)throw new Error('This browser needs gzip decompression support. Open this file in an updated Safari, Chrome or Firefox.');
  const bytes=Uint8Array.from(atob(decoded.payload),character=>character.charCodeAt(0));
  decoded=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
}
const data=decoded,get=id=>document.getElementById(id),ns='http://www.w3.org/2000/svg',money=v=>v==null?'unknown':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(v);let lane=0;
function element(tag,text){const e=document.createElement(tag);if(text!=null)e.textContent=text;return e}function svg(tag,attrs){const e=document.createElementNS(ns,tag);Object.entries(attrs||{}).forEach(([key,value])=>e.setAttribute(key,value));return e}function options(select,values){select.replaceChildren(...values.map(([value,label])=>{const o=element('option',label);o.value=value;return o}))}
const modes=[...new Set(data.paths.map(p=>p.mode))];options(get('mode'),modes.map(m=>[m,m==='native'?'LIVE JEV · recorded boundaries':'OFFLINE REFERENCE · not Jev']));get('scope').textContent=data.actor==='analyst'?'Private analyst projection: founder controlled cash and public market states. Actor-only exports exclude peer private state.':'Actor-only projection: '+data.actor+'. No peer wallets or private team plans are embedded in this file.';
function cases(){const paths=data.paths.filter(p=>p.mode===get('mode').value);options(get('case'),[...new Map(paths.map(p=>[p.case,[p.case,p.position_usd==null?p.regime+' · '+p.case:p.regime+' · position '+money(p.position_usd)+' / upfront '+money(p.upfront_usd)]])).values()]);lane=0;render()}
function render(){const paths=data.paths.filter(p=>p.mode===get('mode').value&&p.case===get('case').value);if(!paths.length){get('coverage').textContent='No recorded paths in this projection.';return}lane=Math.min(lane,paths.length-1);const selectedPath=paths[lane],all=selectedPath.points||[],maxStep=Math.max(0,all.length-1);get('step').max=maxStep;get('step').value=Math.min(Number(get('step').value),maxStep);const point=all[Number(get('step').value)];const span=Number(get('window').value);get('start').max=336-span;const start=Math.min(Number(get('start').value),336-span);get('start').value=start;get('coverage').textContent=paths.map(p=>p.policy+': '+p.status+', recorded to +'+(p.last_hour??0).toFixed(2)+'h').join(' | ')+' · viewing +'+start+' to +'+(start+span)+'h.';
const drawing=svg('svg',{viewBox:'0 0 1000 300',role:'group','aria-label':'Clickable policy event DAG'});for(let tick=0;tick<=6;tick++){const x=95+tick*860/6;drawing.append(svg('line',{x1:x,y1:25,x2:x,y2:265,stroke:'GrayText','stroke-dasharray':'2 6',opacity:.25}));const text=svg('text',{x,y:288,'text-anchor':'middle'});text.textContent='+'+(start+span*tick/6).toFixed(span<=6?1:0)+'h';drawing.append(text)}paths.forEach((path,pathIndex)=>{const y=80+pathIndex*125,label=svg('text',{x:8,y:y-24});label.textContent=path.policy;drawing.append(label);const visible=(path.points||[]).filter(p=>p.second/3600>=start&&p.second/3600<=start+span);visible.forEach((p,index)=>{const x=95+(p.second/3600-start)/span*860;if(index){const prev=visible[index-1],previousX=95+(prev.second/3600-start)/span*860,edge=svg('line',{x1:previousX,y1:y,x2:x,y2:y,class:'edge',tabindex:0,role:'button'});const title=svg('title');title.textContent=(p.choice||'public state')+' → '+(p.events||[]).map(e=>e.kind||e.id).join(', ');edge.append(title);edge.onclick=()=>select(pathIndex,path.points.indexOf(p));edge.onkeydown=e=>{if(e.key==='Enter')edge.onclick()};drawing.append(edge);if(span<=6&&x-previousX>60){const action=svg('text',{x:(x+previousX)/2,y:y-10,'text-anchor':'middle'});action.textContent=p.choice||'state';drawing.append(action)}}const node=svg('circle',{cx:x,cy:y,r:p===point&&pathIndex===lane?8:4,class:'point '+(p===point&&pathIndex===lane?'selected':''),tabindex:0,role:'button','aria-label':'Inspect +'+(p.second/3600).toFixed(2)+'h'});const title=svg('title');title.textContent='+'+(p.second/3600).toFixed(2)+'h · '+(p.choice||'market');node.append(title);node.onclick=()=>select(pathIndex,path.points.indexOf(p));node.onkeydown=e=>{if(e.key==='Enter')node.onclick()};drawing.append(node);if(p.events?.length&&span<=24){const event=svg('text',{x,y:y+25+(index%2)*17,'text-anchor':'middle'});event.textContent=(p.events[0].kind||p.events[0].id||'event').slice(0,22);drawing.append(event)}})});get('timeline').replaceChildren(drawing);
if(!point){get('detail').textContent='No complete boundary has been settled yet.';return}const stats=get('stats');stats.replaceChildren();[['Market cap',money(point.mc_usd)],['Real venue cash',money(point.venue_cash_usd)],['6H volume',money(point.volume_6h_usd)],[data.actor==='analyst'?'Founder net cash':'Own cash',data.actor==='analyst'?money(point.founder_net_cash_usd):money(point.cash_cents/100)]].forEach(([label,value])=>{const box=element('div');box.append(element('strong',value),element('small',label));stats.append(box)});
const detail=get('detail');detail.replaceChildren(element('h2','+'+(point.second/3600).toFixed(2)+'h · '+selectedPath.policy+' · '+(point.choice||'public market state')));detail.append(element('p','Recorded boundary, not a forecast. '+(point.executions||[]).map(e=>e.status+(e.side?' '+e.side:'')+(e.reason?' / '+e.reason:'')).join('; ')));(point.events||[]).forEach(e=>detail.append(element('p',e.text||e.kind||e.id)));(point.visible_topics||[]).forEach(e=>detail.append(element('p',e.text)));(point.coordination||[]).forEach(e=>detail.append(element('p','Permitted private instruction: '+e.choice)));if(point.scores){detail.append(element('p','Provider highest-scored option: '+point.provider_choice+'. Actual sampled option: '+point.choice+'. These scores are not event probabilities and the provider supplies no free-text rationale.'))}detail.append(element('p',point.peak_fraction?'6H total volume / reference peak = '+point.peak_fraction+__POLICY_NOTE__:'The six-hour reference is warming up or has no positive denominator. Do not interpret unknown as zero risk.'));const evidence=element('details');evidence.append(element('summary','Saved state, scores and own memory'),element('pre',JSON.stringify(point,null,2)));detail.append(evidence);drawChart(paths,start,span);const reached=(selectedPath.points||[]).some(p=>p.mc_usd>=5000000);get('odds').textContent='Above $5M: '+(reached?'reached':'not reached')+' in this recorded path. Real-world probability is unknown; one matched seed is not a calibrated odds estimate.';}
function select(pathIndex,index){lane=pathIndex;get('step').value=index;render()}function drawChart(paths,start,span){const field=get('metric').value,values=paths.flatMap(p=>p.points.filter(x=>x.second/3600>=start&&x.second/3600<=start+span).map(x=>x[field])).filter(v=>v!=null),min=Math.min(0,...values),max=Math.max(1,...values),drawing=svg('svg',{viewBox:'0 0 1000 300',class:'chart',role:'img','aria-label':get('metric').selectedOptions[0].textContent});for(let tick=0;tick<4;tick++){const y=245-tick*70,line=svg('line',{x1:95,y1:y,x2:955,y2:y,stroke:'GrayText',opacity:.25});drawing.append(line);const text=svg('text',{x:85,y:y+4,'text-anchor':'end'});text.textContent=money(min+(max-min)*tick/3);drawing.append(text)}paths.forEach((path,index)=>{const points=path.points.filter(p=>p.second/3600>=start&&p.second/3600<=start+span&&p[field]!=null).map(p=>(95+(p.second/3600-start)/span*860)+','+(245-(p[field]-min)/(max-min)*210)).join(' ');drawing.append(svg('polyline',{points,fill:'none',stroke:'currentColor','stroke-width':2.5,'stroke-dasharray':index?'6 4':'none',opacity:index?.55:1}))});get('chart').replaceChildren(drawing);get('explanation').textContent='Solid: '+paths[0].policy+'. Dashed: '+(paths[1]?.policy||'none')+'. Compare the same elapsed hours and evidence mode. Changes arise from recorded fills and costs; no marketing-driven price jump is inserted. Flat or missing segments may indicate no filled trades, warmup, or an unfinished path—not a stable-price forecast. Market cap is not sale liquidity; turnover is not fresh capital. '+(get('mode').value==='native'?'These are model-conditioned native decisions.':'This is an explicit offline mechanics reference, not Jev behavior.');}
['case','window','start','metric'].forEach(id=>get(id).oninput=render);get('step').oninput=()=>{const p=data.paths.filter(p=>p.mode===get('mode').value&&p.case===get('case').value)[lane]?.points[Number(get('step').value)];if(p)get('start').value=Math.max(0,p.second/3600-Number(get('window').value)/2);render()};get('mode').onchange=cases;get('download').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=element('a');a.href=url;a.download='MACRON-'+data.actor+'-projection.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};cases();
</script></body></html>'''.replace('__DATA__', payload).replace('__POLICY_NOTE__', json.dumps(policy_note)).replace('</script></body>', enhancements + "\n})().catch(error=>{document.getElementById('scope').textContent='Unable to open this view: '+error.message;console.error(error)});\n</script></body>").replace('</style>', 'svg,svg.chart{min-width:1000px}</style>').replace('<div id="chart">', '<div id="chart" class="scroll">')


def write_pdf(data, filename, regime=None):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
    from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Explanation', fontSize=11, leading=16, spaceAfter=14))
    doc = SimpleDocTemplate(str(filename), pagesize=(595, 842), rightMargin=45, leftMargin=45,
                            topMargin=45, bottomMargin=45)
    story = [Paragraph('MACRON / ' + (regime + ' Market scenario' if regime else 'Lifecycle research'), styles['Title']),
             Paragraph('Live Jev results and a separately labeled complete offline reference', styles['Heading2'])]
    def rich_text(text):
        value = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', escape(text))
        value = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<link href="\2" color="#173F35">\1</link>', value)
        return value.replace('\n', '<br/>')
    markdown = report_markdown(data, regime)
    for section in markdown.split('\n## ')[1:]:
        heading, _, body = section.partition('\n')
        if heading.startswith('6.'):
            story.append(Paragraph(heading, styles['Heading1']))
            rows = [['Mode / regime', 'Position / cost', 'Policy', 'Hours', 'Net cash']]
            for path in data['paths']:
                if regime and path['regime'] != regime:
                    continue
                rows.append([path['mode'] + '/' + path['regime'], f"{path['position_usd']/1000:g}k / {path['upfront_usd']/1000:g}k",
                             'pause' if path['policy'] == 'pause-and-observe' else 'exit',
                             f"{path['last_hour']:.1f}" if path['last_hour'] is not None else '?',
                             f"${path['summary']['founder_net_cash_cents']/100:,.0f}"])
            table = Table(rows, colWidths=[120, 95, 65, 60, 100], repeatRows=1)
            table.setStyle(TableStyle([('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8),
                                      ('BOTTOMPADDING', (0, 0), (-1, -1), 6), ('LINEBELOW', (0, 0), (-1, 0), .7, colors.grey)]))
            story += [table, Spacer(1, 15)]
            continue
        story.append(Paragraph(escape(heading), styles['Heading1']))
        for paragraph in body.split('\n\n'):
            text = paragraph.strip()
            if text and not text.startswith('|'):
                story.append(Paragraph(rich_text(text), styles['Explanation']))
    context = data.get('market_context')
    if context and context['daily']:
        daily = context['daily']
        story.append(PageBreak())
        story.append(Paragraph('Observed six-month market context / not persona calibration', styles['Heading1']))
        chart = Drawing(490, 210)
        chart.add(String(5, 195, 'Solana tracked DEX daily volume / USD billions', fontName='Helvetica-Bold', fontSize=11))
        high = max(row[1] for row in daily)
        points = [coordinate for index, row in enumerate(daily) for coordinate in (60 + index / max(1, len(daily)-1) * 415, 35 + row[1] / high * 130)]
        chart.add(PolyLine(points, strokeColor=colors.HexColor('#173F35'), strokeWidth=1.4))
        for fraction in (0, .5, 1):
            chart.add(String(5, 35 + fraction * 130, f'${high*fraction/1000000000:.1f}bn', fontSize=8))
        chart.add(String(60, 10, '2 May 2026', fontSize=9))
        chart.add(String(400, 10, '1 Nov 2026', fontSize=9))
        story.append(chart)
        prior = sum(row[1] for row in daily[-14:-7])
        change = sum(row[1] for row in daily[-7:]) / prior - 1 if prior else None
        story.append(Paragraph(f'{len(daily)} dated daily observations from DefiLlama. ' +
            (f'The last seven-day total changes {change:+.1%} versus the preceding seven days. ' if change is not None else '') +
            'This is chain-wide DEX activity, not memecoin-only demand, distinct retail arrivals or executable exit depth. '
            'The incomplete 2 November day is excluded. The series was captured for report context after the native packages were frozen; '
            'it was not retroactively used to fit persona decisions, campaign response or BULL/BEAR classification. '
            'A changing market total alone does not establish MACRON demand or explain a particular simulated trade.', styles['Explanation']))
        story.append(Paragraph(escape(context['source_url']), styles['Explanation']))
    for mode in dict.fromkeys(path['mode'] for path in data['paths']):
        selected = [path for path in data['paths'] if path['mode'] == mode and path['regime'] == (regime or 'BULL')
                    and path['policy'] == 'staged-exit']
        for path in selected:
            paired = [item for item in data['paths'] if item['case'] == path['case'] and item['mode'] == mode]
            story.append(PageBreak())
            story.append(Paragraph(f"{path['regime']} / {mode} / ${path['position_usd']:,.0f} position, ${path['upfront_usd']:,.0f} upfront", styles['Heading2']))
            story.append(Paragraph('Paired response paths: dark solid = staged exit; sage = pause. '
                                   'Each line ends at its own actual recorded boundary. The native axis is zoomed to recorded coverage, not a fabricated fourteen-day horizon.', styles['Explanation']))
            for metric, title in (('mc_usd', 'Circulating market cap'), ('volume_6h_usd', 'Six-hour executed turnover'),
                                  ('venue_cash_usd', 'Real venue cash'),
                                  ('founder_net_cash_usd', 'Founder net cash after paid costs')):
                rows = path['rows']
                if not rows:
                    continue
                values = [row[metric] for item in paired for row in item['rows'] if row[metric] is not None]
                if not values:
                    continue
                low, high = min(0, min(values)), max(1, max(values))
                horizon = 336 if all(item['status'] == 'completed' for item in paired) else max(1, max(item['last_hour'] or 0 for item in paired))
                chart = Drawing(490, 150)
                chart.add(String(5, 136, title, fontName='Helvetica-Bold', fontSize=11))
                chart.add(Line(60, 25, 475, 25, strokeColor=colors.grey))
                for fraction in (0, .5, 1):
                    chart.add(String(5, 25 + fraction * 90, f'${low+(high-low)*fraction:,.0f}', fontSize=8))
                for item in paired:
                    points = [coordinate for row in item['rows'] if row[metric] is not None for coordinate in (60 + row['hours'] / horizon * 415, 25 + (row[metric] - low) / (high-low) * 90)]
                    if len(points) >= 4:
                        chart.add(PolyLine(points, strokeColor=colors.HexColor('#173F35' if item['policy'] == 'staged-exit' else '#A8C3A0'), strokeWidth=1.5))
                for fraction in (0, .25, .5, .75, 1):
                    chart.add(String(55 + fraction * 415, 7, '+' + f'{horizon*fraction:.1f}' + 'h', fontSize=8))
                source = 'Derived claim: conditional-outcomes / ' + path['id'] + ' / final checkpoint ' + path['rows'][-1]['checkpoint_sha256'][:20]
                story.append(KeepTogether([chart, Paragraph(escape(interpretation(path, metric)), styles['Explanation']),
                                          Paragraph(escape(source), styles['Normal'])]))
    def footer(canvas, document):
        canvas.setFont('Helvetica', 8)
        canvas.drawString(45, 25, 'MACRON / conditional scenarios, not calibrated forecasts / ' + str(document.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def view_projection(paths, roles, actor):
    projection = {'actor': actor, 'roles': {'self': roles.get(actor)}, 'paths': []}
    public_cases = {case: 'scenario-' + str(index + 1) for index, case in enumerate(dict.fromkeys(path['case'] for path in paths))}
    for path in paths:
        value = {key: path[key] for key in ('id', 'case', 'policy', 'mode', 'regime', 'position_usd', 'upfront_usd', 'status', 'last_hour')}
        value['points'] = path['rows'] if actor == 'analyst' else path['actors'][actor]
        if actor not in {'analyst', 'founder'}:
            value.update(case=public_cases[path['case']], policy='path-A' if path['policy'] == 'pause-and-observe' else 'path-B',
                         position_usd=None, upfront_usd=None)
            value['id'] = value['case'] + '/' + value['policy']
        projection['paths'].append(value)
    return projection


def build(native, reference, output, stress=None, market_context=None):
    destination = Path(output)
    destination.mkdir(mode=0o700)
    paths, roles = [], {}
    data = {'market_context': read_json(market_context) if market_context else None}
    sources = [('native', native, 'native'), ('offline_reference', reference, 'offline_reference')]
    if stress:
        sources.append(('offline_stress_4x', stress, 'offline_stress_4x'))
    for key, root, mode in sources:
        matrix, collected, actors = collect_matrix(root, mode)
        data[key] = matrix
        paths.extend(collected)
        roles.update(actors)
    data['paths'] = paths
    aggregates = [{key: value for key, value in path.items() if key not in {'actors'}} for path in paths]
    data['result_sha256'] = digest({'paths': aggregates, 'market_context': data['market_context']})
    write_artifacts([(destination / 'results.json', json_bytes({**data, 'paths': aggregates})),
                     (destination / 'REPORT.md', report_markdown(data).encode()),
                     (destination / 'BULL-Market-scenario.md', report_markdown(data, 'BULL').encode()),
                     (destination / 'BEAR-Market-scenario.md', report_markdown(data, 'BEAR').encode())])
    for actor in ['analyst'] + list(roles):
        projection = view_projection(paths, roles, actor)
        filename = 'MACRON-interactive.html' if actor == 'analyst' else 'MACRON-actor-' + actor + '.html'
        write_artifacts([(destination / filename, interactive_html(projection).encode())])
    with (destination / 'timeline.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['mode', 'case', 'policy', 'hours', 'mc_usd', 'fdv_usd', 'venue_cash_usd',
                                                   'volume_usd', 'volume_6h_usd', 'founder_net_cash_usd', 'phase', 'checkpoint_sha256'])
        writer.writeheader()
        for path in paths:
            for row in path['rows']:
                writer.writerow({key: path[key] if key in {'mode', 'case', 'policy'} else row[key] for key in writer.fieldnames})
    for regime in (None, 'BULL', 'BEAR'):
        filename = destination / ('MACRON-graph-report.pdf' if regime is None else regime + '-Market-scenario.pdf')
        write_pdf(data, filename, regime)
    modes = Counter(path['mode'] for path in paths)
    summary = ['# MACRON results — start here', '',
               'Conditional scenarios, not market forecasts. Native Jev endpoints and complete synthetic references are distinct.', '',
               '- [Interactive analyst DAG](MACRON-interactive.html)',
               '- [Graph-led report PDF](MACRON-graph-report.pdf)',
               '- [BULL Market PDF](BULL-Market-scenario.pdf)',
               '- [BEAR Market PDF](BEAR-Market-scenario.pdf)',
               '- [Full written report](REPORT.md)',
               '- [Replayed data](results.json) · [Timeline CSV](timeline.csv)', '',
               f"Native status: {data['native']['status']}. Completed calls: {data['native']['budget']['completed_calls']:,}. "
               f"Published-tariff estimate: ${data['native']['budget']['spent_estimate_micro_usd']/1000000:.6f} of the shared $2 cap.", '',
               '## Coverage', '']
    summary += [f'- {mode}: {count} paths; ' + str(sum(path['status'] == 'completed' for path in paths if path['mode'] == mode)) + ' complete to +336h.' for mode, count in modes.items()]
    summary += ['', 'The 4x stress changes synthetic activity thresholds with finite-wallet and saturation constraints; it does not promise four times the realized fills or volume. No extra live Jev budget was used.', '', '## Actor-only views', '']
    summary += [f'- [{actor}](MACRON-actor-{actor}.html)' for actor in roles]
    write_artifacts([(destination / 'README.md', '\n'.join(summary).encode())])
    return {'status': 'built', 'result_sha256': data['result_sha256'], 'paths': len(paths),
            'native_status': data['native']['status'], 'output_dir': str(destination)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', required=True)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--stress')
    parser.add_argument('--market-context')
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.native, arguments.reference, arguments.output, arguments.stress, arguments.market_context), indent=2))
