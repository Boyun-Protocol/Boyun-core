"""Fresh explanatory Presenton slides from replay-derived aggregate lifecycle results."""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from html import escape
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from build_lifecycle_reports import matched_comparisons


ROOT = Path(__file__).resolve().parents[1]
HELPER = Path(os.environ.get('BOYUN_PRESENTON_SCRIPTS', 'presenton-scripts')).expanduser() / 'presenton_artifacts.py'
FONT_URL = 'https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Manrope:wght@400;500;600;700&display=swap'


def deck(data):
    slides, charts = [], []
    native = data['native']
    paths = data['paths']
    live = [path for path in paths if path['mode'] == 'native']
    reference = [path for path in paths if path['mode'] == 'offline_reference']
    stress = [path for path in paths if path['mode'] == 'offline_stress_4x']
    pairs = matched_comparisons(paths)
    palette = ['#173F35', '#A8C3A0', '#727F69', '#C6B991']

    def paragraphs(*texts):
        return ''.join('<p class="mb-[20px] text-[20px] leading-[1.5]">' + escape(text) + '</p>' for text in texts)

    def page(title, content, kicker='MACRON / conditional lifecycle research', footer='Recorded states, not calibrated forecasts. Market cap is not executable sale liquidity.'):
        index = len(slides) + 1
        slides.append(f'<section class="relative h-[720px] w-[1280px] overflow-hidden bg-[#F8F5ED] text-[#252B29] font-[Manrope]">'
                      f'<p class="absolute left-[56px] top-[30px] text-[13px] tracking-[0.16em] uppercase text-[#173F35]">{escape(kicker)}</p>'
                      f'<h1 class="absolute left-[56px] top-[65px] max-w-[1168px] text-[45px] leading-[1.08] font-[DM_Serif_Display]">{escape(title)}</h1>'
                      f'<div class="absolute left-[56px] top-[172px] w-[1168px]">{content}</div>'
                      f'<div class="absolute left-[56px] bottom-[28px] w-[1168px] border-t border-[#A8C3A0] pt-[12px] flex justify-between gap-[24px] text-[12px]">'
                      f'<span>{escape(footer)}</span><span>MACRON / {index:02d}</span></div></section>')

    def chart(identifier, datasets, *, kind='line', labels=None, ymax=None, xmax=None):
        options = {'responsive': False, 'animation': False, 'maintainAspectRatio': False,
                   'plugins': {'legend': {'labels': {'color': '#252B29', 'font': {'family': 'Manrope', 'size': 12}}}},
                   'scales': {'y': {'beginAtZero': kind == 'bar', 'ticks': {'font': {'family': 'Manrope', 'size': 12}}},
                              'x': {'ticks': {'font': {'family': 'Manrope', 'size': 11}}}}}
        if kind == 'line':
            options['scales']['x'].update(type='linear', title={'display': True, 'text': 'Elapsed hours from launch'})
        if ymax is not None:
            options['scales']['y']['max'] = ymax
        if xmax is not None:
            options['scales']['x']['max'] = xmax
        config = {'type': kind, 'data': {'datasets': datasets}, 'options': options}
        if labels is not None:
            config['data']['labels'] = labels
        charts.append('new Chart(document.querySelector("#' + identifier + '"),' + json.dumps(config) + ');')
        return f'<canvas id="{identifier}" width="710" height="360" class="w-[710px] h-[360px]"></canvas>'

    def series(path, field, index):
        return {'label': path['policy'], 'data': [{'x': row['hours'], 'y': row[field]} for row in path['rows'] if row[field] is not None],
                'borderColor': palette[index % len(palette)], 'borderWidth': 2, 'pointRadius': 0,
                'borderDash': [6, 4] if index else [], 'spanGaps': False}

    def split(graph, *texts):
        return '<div class="grid grid-cols-[740px_396px] gap-[32px]"><div>' + graph + '</div><div>' + paragraphs(*texts) + '</div></div>'

    budget = native['budget']
    page('A deeper launch study. An honest boundary.',
         paragraphs('MACRON · 2 November 2026, 12:00 UTC+4 · fourteen-day target · six capital/cost plans · BULL and BEAR · matched response branches.') +
         '<div class="grid grid-cols-3 gap-[24px] my-[28px]">' + ''.join(
             '<div class="rounded-[12px] bg-[#E8F0E5] p-[24px]"><p class="text-[42px] font-[DM_Serif_Display] text-[#173F35]">' + value +
             '</p><p class="mt-[10px] text-[17px]">' + label + '</p></div>' for value, label in [
                 (f"{budget['completed_calls']:,}", 'completed native Jev calls'),
                 (f"${budget['spent_estimate_micro_usd']/1000000:.4f}", 'published-tariff input estimate / $2 cap'),
                 (str(sum(path['status'] == 'completed' for path in reference)), 'complete offline reference paths / not Jev')]) + '</div>' +
         paragraphs('Live unfinished paths are not fourteen-day results. Synthetic reference and artificial stress calculations are shown separately; neither substitutes for a calibrated market forecast.'))

    graph = chart('coverage', [{'label': 'Recorded hours / target 336', 'data': [path['last_hour'] or 0 for path in live], 'backgroundColor': palette[0]}],
                  kind='bar', labels=[path['regime'][0] + str(int(path['position_usd']/1000)) + '/' + str(int(path['upfront_usd']/1000)) + ('P' if path['policy'] == 'pause-and-observe' else 'E') for path in live], ymax=336)
    page('What finished—and what did not', split(graph,
         'Every completed barrier contains all actor choices, permitted observations, fills and cash/token balances. No hours are filled with invented decisions.',
         f"Native matrix: {native['status']}. The full comparison received budget; no favorite plan was silently selected.",
         'Three interrupted requests had unknown outcomes. Their reservations remain charged against the cap and affected paths are not retried.'))

    page('Capital must exist before an action can execute',
         '<div class="grid grid-cols-3 gap-[28px]">' + ''.join('<div class="border-t-2 border-[#173F35] pt-[18px]"><h2 class="font-[DM_Serif_Display] text-[29px] mb-[20px]">' + title + '</h2>' + paragraphs(*texts) + '</div>' for title, texts in [
             ('Founder', ['$50,000 capital. A separate $10,000 reserve cannot fund discretionary buys.', 'Position budgets: $5k / $10k / $15k. Split: 50% launch, 20% confirmed migration, up to 30% continuing under the funding rule.']),
             ('Paid launch plan', ['$5k / $10k upfront envelopes are spent once, including $3,000 total KOL/operator cash.', 'The 3% token grant comes from founder-purchased tokens. It is not a free mint or a team LP.']),
             ('Curve and migration', ['Virtual reserves determine an estimated quote; they are not withdrawable money.', 'Only real collected cash enters the estimated migrated pool. Static fees and immediate migration are simplifying hypotheses.'])]) + '</div>')

    page('Sixteen actors. Different information, shared consequences.',
         '<div class="grid grid-cols-2 gap-[48px]"><div>' + paragraphs('Founder and MM receive only authorized private coordination. Retail cannot read team instructions, planned exits or peer wallet balances.',
             'KOLs, the operator, ecosystem roles and retail each retain their own funds, holdings, cumulative activity, last choice and recent public history.') + '</div><div>' +
         paragraphs('The market state changes only when funded actions settle. Publishing a campaign does not insert a price jump or spawn buyers.',
             'Actor HTML exports physically exclude peer private state. The analyst file is a separate private projection, not a UI filter over a public payload.') + '</div></div>' +
         '<p class="mt-[20px] rounded-[10px] bg-[#E8F0E5] p-[22px] text-[19px] leading-[1.5]">Memory is bounded context, not omniscience: full states are saved, while decisions receive current own state plus a compact permitted history.</p>')

    page('Hourly decisions, dense launch, dated public events',
         paragraphs('The schedule retains every hourly boundary from +0 to +336h, minute launch decisions and additional response/acknowledgement times. No +24 → +48 jump is substituted for the missing day.') +
         '<div class="grid grid-cols-2 gap-[40px]">' + '<div>' + paragraphs('Executed conditional plan: launch post at root, KOL publications at +1h / +6h / +24h / +72h, token-information delivery at +12h.',
             '29 Assembly session starts come from the dated agenda. A planned session is not a known vote result or a guaranteed announcement.') + '</div><div>' +
         paragraphs('Volume-spike and liquidity-drop events are derived from the saved market state. Their detector thresholds remain disclosed assumptions.',
             'Not completed: a fitted six-to-twelve-month process for new arrivals, political surprises or campaign conversion. We do not label this missing realism as implemented.') + '</div></div>')

    for regime, field, description in [('BULL', 'mc_usd', 'Modeled circulating market cap / USD'), ('BEAR', 'volume_6h_usd', 'Trailing six-hour traded cash / USD')]:
        selected = [path for path in live if path['regime'] == regime and path['position_usd'] == 5000 and path['upfront_usd'] == 5000]
        graph = chart('native-' + regime.lower(), [series(path, field, index) for index, path in enumerate(selected)])
        page(regime + ' Market scenario · native decisions', split(graph,
             description + '. Illustration uses the $5k position / $5k upfront plan; all plans remain in the reports.',
             'Each line stops at its actual completed endpoint. A rise or decline follows recorded choices and constrained settlement, not a preset campaign multiplier.',
             'BULL/BEAR here means a qualitative risk-appetite hypothesis. This is not a declaration of today’s regime or a historical causal estimate.'))

    graph = chart('response-cash', [{'label': 'Staged exit minus pause / realized cash USD',
                   'data': [pair['exit_minus_pause_cash_usd'] for pair in pairs if pair['mode'] == 'native'], 'backgroundColor': palette[0]}], kind='bar',
                  labels=[pair['regime'][0] + ' ' + str(int(pair['position_usd']/1000)) + '/' + str(int(pair['upfront_usd']/1000)) for pair in pairs if pair['mode'] == 'native'])
    page('Compare responses at the same saved hour', split(graph,
         'Each bar uses the latest exact common timestamp for its paired branches. Different native endpoints are never ranked as if both were day fourteen.',
         'Positive means the exit branch held more realized founder cash at that time. Unsold inventory and its uncertain future value are excluded.',
         'The no-launch cash baseline is $50,000 and zero cash profit. Neither response can guarantee recovery of prepaid costs or an executable stop.'))

    ref_pairs = [pair for pair in pairs if pair['mode'] == 'offline_reference']
    graph = chart('reference-cash', [
        {'label': 'Pause net cash / USD', 'data': [pair['pause_cash_usd'] for pair in ref_pairs], 'backgroundColor': palette[0]},
        {'label': 'Exit net cash / USD', 'data': [pair['exit_cash_usd'] for pair in ref_pairs], 'backgroundColor': palette[1]}], kind='bar',
        labels=[pair['regime'][0] + ' ' + str(int(pair['position_usd']/1000)) + '/' + str(int(pair['upfront_usd']/1000)) for pair in ref_pairs])
    page('Complete fourteen-day reference · not Jev', split(graph,
         'All 24 reference paths reach +336h. These use explicit seeded synthetic rules to exercise mechanics, costs, conservation and long-horizon persistence.',
         'Negative cash profit includes prepaid launch costs and fees, but does not mark remaining inventory as worthless. The two measures must stay separate.',
         'A complete deterministic reference is not evidence that the live actor simulation finished or that real token demand follows these rules.'))

    graph = chart('stress-fills', [{'label': label, 'data': [sum(path.get('statistics', {}).get('filled_trades', 0) for path in cohort if path['regime'] == regime) for regime in ('BULL', 'BEAR')],
                                   'backgroundColor': palette[index]} for index, (label, cohort) in enumerate([('Synthetic baseline', reference), ('Artificial 4x activity thresholds', stress)])],
                  kind='bar', labels=['BULL context / dependent paths', 'BEAR context / dependent paths'])
    page('Push the engine—not the forecast', split(graph,
         'The separate offline stress arm increases synthetic trading thresholds by 4x, with explicit saturation caps and the same finite-wallet constraints.',
         'Four times the decision bias cannot guarantee four times the fills or volume: liquidity, fees, depleted cash and owned inventory constrain execution.',
         'Totals are engineering workload across dependent parameter/policy paths, not independent investors, population estimates or native Jev behavior.'))

    rejected = sum(path.get('statistics', {}).get('rejected_trades', 0) for path in live)
    attempts = sum(path.get('statistics', {}).get('trade_attempts', 0) for path in live)
    page('What the statistics can—and cannot—say',
         paragraphs(f'Native saved barriers contain {attempts:,} attempted executions and {rejected:,} rejected executions. The denominator is attempted orders, not all actor decisions; waits and publications are not trade attempts.') +
         '<div class="grid grid-cols-2 gap-[44px]"><div>' + paragraphs('Reported: filled buys/sells, rejection reason, sampled peak-to-trough drawdown, actor turnover concentration and conditional campaign windows.',
             'A six-hour before/after campaign window is descriptive. Simultaneous trades and overlapping events prevent treating it as incremental campaign ROI.') + '</div><div>' +
         paragraphs('Not supported by one matched seed: p95/CVaR, calibrated crash odds, confidence intervals for real markets or “$5M with 20% odds.”',
             'Calls are decisions inside a path, not independent world replications. Intrabarrier extremes may be missed; no attempts means an undefined rejection rate.') + '</div></div>')

    page('Expected, unusual, and genuinely unresolved',
         '<div class="grid grid-cols-3 gap-[28px]">' + ''.join('<div class="border-t-2 border-[#173F35] pt-[18px]"><h2 class="font-[DM_Serif_Display] text-[29px] mb-[20px]">' + title + '</h2>' + paragraphs(*texts) + '</div>' for title, texts in [
             ('Expected mechanics', ['Prepaid costs reduce cash immediately. Fee drag persists even when turnover increases.', 'A published KOL post can be followed by selling or waiting; paid reach is not new investor cash.']),
             ('Testable edge cases', ['Shallow liquidity rejects an attempted exit. A loss alert can fire early when upfront costs consume the loss allowance.', 'Migration may occur earlier or later than the user’s 10–15 minute hypothesis; it is not forced to meet it.']),
             ('Unresolved evidence', ['No fitted long-history arrival or attention model. No actual political outcome distribution or vendor delivery record.', 'Simplified execution excludes exact dynamic fees, MEV, chain outages and creator-fee collection.'])]) + '</div>')

    context = data.get('market_context')
    if context and context['daily']:
        daily = context['daily']
        last_week = sum(row[1] for row in daily[-7:])
        prior_week = sum(row[1] for row in daily[-14:-7])
        change = last_week / prior_week - 1 if prior_week else None
        graph = chart('observed-dex-context', [{'label': 'Observed Solana DEX volume / USD billions',
            'data': [{'x': (row[0] - daily[0][0]) / 86400, 'y': row[1] / 1000000000} for row in daily],
            'borderColor': palette[0], 'borderWidth': 2, 'pointRadius': 0}])
        charts[-1] = charts[-1].replace('Elapsed hours from launch', 'Days since 2 May 2026 / observed context')
        page('Six months of observed context—not fitted launch odds', split(graph,
             f"DefiLlama reports {len(daily)} daily Solana DEX observations from 2 May through 1 November 2026. Last seven days versus the preceding seven: {change:+.1%}." if change is not None else 'The comparison window is unavailable.',
             'This chain-wide series includes more than memecoins. It describes traded activity, not unique retail arrivals, executable depth or campaign conversion.',
             'Collected for the report after the world was frozen; not retroactively sent to personas. It cannot turn the conditional BULL/BEAR labels into a calibrated regime classifier.'),
             footer='Source: api.llama.fi/overview/dexs/solana / dailyVolume / incomplete 2 November day excluded / report context only')

    page('Choose when a regime hypothesis applies',
         '<div class="grid grid-cols-2 gap-[48px]"><div><h2 class="font-[DM_Serif_Display] text-[30px] mb-[20px]">BULL applicability checklist</h2>' +
         paragraphs('Look for a persistent BTC trend with broad participation, sustained spot activity across both exchanges and DEXs, and supportive executable depth.',
             'Record source, timestamp, lookback and metric definition. A price bounce alone is not sufficient evidence of broad risk appetite.') + '</div><div><h2 class="font-[DM_Serif_Display] text-[30px] mb-[20px]">BEAR applicability checklist</h2>' +
         paragraphs('Look for weak breadth, declining spot participation, widening spreads or deteriorating depth. Verify disruptions independently before attributing the regime to an incident.',
             'These are qualitative conditions for the user to assess—not fitted classifier thresholds, current market readings or a recommendation to trade.') + '</div></div>' +
         '<p class="text-[17px] leading-[1.5] mt-[16px]">Primary indicator definitions: CoinGecko global/exchange data · DefiLlama DEX volumes. No unverified Binance-hack explanation is inserted into the run.</p>')

    page('Guidance should explain constraints, not promise an optimum',
         paragraphs('Founder: funding needs ≥60% of the causal first-48h six-hour-volume peak. An exit trigger uses ≤25%; recovery deferral also needs one-hour price holding. Four sale attempts occur 15 minutes apart after the modeled response.') +
         '<div class="grid grid-cols-2 gap-[44px]"><div>' + paragraphs('Retail: inspect public participation, executable depth and own cash/inventory. You cannot see the private team decision; its market effects may still be visible.',
             'A rejected order calls for reviewing size/depth or waiting, not assuming that the previous quote is still executable.') + '</div><div>' +
         paragraphs('Actor guidance is a transparent risk-control explanation from permitted state, separate from the sampled Jev action scores.',
             'No model-supplied free-text rationale or “best possible result” is fabricated. Future demand and real-world event odds remain unknown.') + '</div></div>')

    page('Reproduce the path. Challenge the assumptions.',
         paragraphs('The package, evidence register, typed requests/responses, sampled choices, cost reservations, state checkpoints and engine hashes are retained privately. Zero-call replay verifies completed paths.') +
         '<div class="grid grid-cols-2 gap-[42px] text-[17px] leading-[1.7]"><div>' +
         '<p class="font-bold mb-[10px]">Primary mechanics and dated context</p><p>github.com/pump-fun/pump-public-docs</p><p>assemblee-nationale.fr / dated session agenda</p><p>fec.gov / election-date information</p><p>docs.typesafe.ai/models / Jev published tariff</p></div><div>' +
         '<p class="font-bold mb-[10px]">Research and indicator definitions</p><p>arxiv.org/html/2602.14860v1 / one-month Pump.fun cohort, not six-month calibration</p><p>docs.coingecko.com / global and exchange metrics</p><p>docs.llama.fi / DEX volume definitions</p></div></div>' +
         '<p class="mt-[22px] text-[17px]">Next evidence gate: dated long-history arrivals, observed campaign delivery/conversion and independent seeds—not more decorative certainty.</p>',
         footer='Result fingerprint: ' + data.get('result_sha256', '')[:32] + ' / fonts: DM Serif Display + Manrope / Sage Authority 14')

    head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><script src="https://cdn.tailwindcss.com"></script><script src="https://cdn.jsdelivr.net/npm/chart.js"></script><link rel="stylesheet" href="' + FONT_URL + '"></head><body class="m-0 p-0"><main id="presentation-slides-wrapper" class="m-0 w-[1280px] p-0">'
    html = head + ''.join(slides) + '</main><script>' + ''.join(charts) + '</script></body></html>'
    return html.replace('font-[DM_Serif_Display]', "font-['DM_Serif_Display']"), len(slides)


def helper(*arguments):
    result = subprocess.run([sys.executable, str(HELPER), *arguments], capture_output=True, text=True)
    if result.stderr:
        print(result.stderr, end='', flush=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout, [line.removeprefix('API message: ') for line in result.stderr.splitlines() if line.startswith('API message: ')]


def export(directory):
    root = Path(directory)
    receipt = root / 'presenton-lifecycle-receipts.json'
    if receipt.exists():
        raise ValueError('inspect existing export receipts; no automatic repeated export')
    data = json.loads((root / 'results.json').read_text())
    html, count = deck(data)
    state = {'title': 'MACRON · BULL / BEAR lifecycle research', 'slides': count, 'design_id': 14,
             'design': 'Sage Authority', 'fonts': ['DM Serif Display', 'Manrope'], 'font_source': FONT_URL,
             'exports': {}, 'messages': [], 'status': 'running', 'result_sha256': data['result_sha256']}
    with tempfile.TemporaryDirectory(prefix='presenton-') as temporary:
        (Path(temporary) / '.presenton-temp').write_text('presenton-owned\n')
        source = Path(temporary) / 'presentation.html'
        source.write_text(html)
        validation = subprocess.run([sys.executable, str(HELPER.with_name('validate_html.py')), str(source)], capture_output=True, text=True)
        if validation.returncode:
            raise ValueError(validation.stdout + validation.stderr)
        receipt.write_text(json.dumps(state, indent=2))
        try:
            def export_format(format_name):
                output, messages = helper('export', '--html', str(source), '--format', format_name,
                                          '--title', state['title'], '--design-id', '14', '--json')
                return json.loads(output), messages
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {format_name: pool.submit(export_format, format_name) for format_name in ('pptx', 'pdf')}
                for format_name, future in futures.items():
                    try:
                        value, messages = future.result()
                        if type(value.get('id')) is not int or value['id'] <= 0 or not value.get('url', '').startswith(('https://', 'http://')):
                            raise ValueError('invalid export response')
                        state['exports'][format_name] = value
                        state['messages'].extend(messages)
                        print(format_name + ': ' + value['url'], flush=True)
                    except Exception as error:
                        state['exports'][format_name] = {'error': str(error)}
                    receipt.write_text(json.dumps(state, indent=2))
            if all(value.get('url') for value in state['exports'].values()):
                output, messages = helper('create-preview', '--id', str(state['exports']['pptx']['id']))
                state['preview_url'] = output.strip()
                state['messages'].extend(messages)
                state['font_inventory'], _ = helper('list-fonts', '--html', str(source))
                state['status'] = 'completed' if state['preview_url'].startswith(('https://', 'http://')) else 'partial_or_failed'
            else:
                state['status'] = 'partial_or_failed'
        finally:
            receipt.write_text(json.dumps(state, indent=2))
    lines = ['# MACRON presentation', '', f'{count} explanatory slides · Sage Authority (14) · conditional research.', '',
             'Formats: PPTX and presentation PDF. Aggregate hypothetical results only; no raw actor observations or credentials sent.', '']
    for format_name, value in state['exports'].items():
        lines.append(f'- [{format_name.upper()} download]({value["url"]})' if value.get('url') else f'- {format_name.upper()}: export failed; see receipt.')
    if state.get('preview_url'):
        lines.append('- [Shareable presentation preview](' + state['preview_url'] + ') — expires after 24 hours')
    lines += ['', 'Fonts for both exports: DM Serif Display and Manrope — ' + FONT_URL, '',
              'Notes: ' + ('; '.join(state['messages']) or 'None'), '', 'Download and preview links expire after 24 hours.']
    (root / 'PRESENTATION.md').write_text('\n'.join(lines))
    print(json.dumps(state, indent=2))
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    export(parser.parse_args().directory)
