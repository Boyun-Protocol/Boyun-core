"""Build private, replay-verified market-regime reports from recorded experiments."""
import argparse
import csv
from fractions import Fraction
from html import escape
import json
from pathlib import Path
from statistics import median

from decision_lab.campaign_orchestration import summarize_campaign_experiment
from decision_lab.campaign_analysis import analyze_world, analyze_worlds


REGIMES = [
    ('Bitcoin trend', 'BTC above a rising 200-day average; 50-day average rising; positive 30/90-day returns.',
     'BTC below a falling 200-day average; 50-day average falling; negative 30/90-day returns.',
     'Use daily UTC closes from one consistent spot index. Moving averages lag and are not sufficient alone.'),
    ('Centralized exchange spot volume', '7-day average USD spot turnover above its 90-day median, accompanying rising prices across several reputable venues.',
     'Weak participation on rebounds, or elevated turnover accompanying falling prices and forced exits.',
     'Compare like-for-like spot pairs and venues. Derivatives, incentives and wash activity can inflate totals.'),
    ('DEX spot volume', '7-day average above its 90-day median across several chains and venues; activity sustained beyond one token.',
     'Broadly shrinking turnover and participation; occasional high-volume selloffs do not imply bullish demand.',
     'Separate spot from perpetuals and aggregators. Do not add aggregator routing to underlying DEX volume.'),
    ('Breadth and BTC dominance', 'Many liquid non-stablecoin assets above their 50-day averages; participation broadens beyond BTC.',
     'Few assets participating; speculative assets weaken against BTC. Rising BTC dominance can accompany defensive rotation.',
     'Dominance alone cannot classify the regime: BTC can lead a bull market while dominance rises.'),
    ('Liquidity and funding conditions', 'Stablecoin supply and usable market depth expanding over 30/90 days; spreads contained.',
     'Stablecoin supply or accessible depth contracting; spreads widening and slippage worsening.',
     'Supply is not deployable buying power by itself. Inspect venue depth and withdrawals, not TVL alone.'),
    ('Sentiment and disruption', 'Sentiment improves alongside breadth and spot demand; no unresolved venue/chain disruption.',
     'Persistent fear plus weak price/breadth, or verified security events interrupting market access.',
     'Fear & Greed is Bitcoin-oriented and partly overlaps price/volume. Verify incident timelines separately; this report does not establish a Binance-hack explanation.')
]
SOURCES = [
    ('CoinGecko global market data: market cap, volume and BTC dominance fields', 'https://docs.coingecko.com/reference/crypto-global'),
    ('CoinGecko exchange data: turnover, trust and spread fields', 'https://docs.coingecko.com/reference/exchanges-id'),
    ('DefiLlama methodology: separate DEX/perpetual/aggregator volume and stablecoin metrics', 'https://docs.llama.fi/'),
    ('Alternative.me: Bitcoin-oriented sentiment methodology', 'https://alternative.me/crypto/fear-and-greed-index/')
]


def dollars(cents):
    return f'${cents / 100:,.2f}'


def collect(directory, label):
    root = Path(directory)
    summary = summarize_campaign_experiment(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    rows, nodes, worlds, actors, risk_worlds = [], [], [], [], []
    for world in range(manifest['worlds']):
        checkpoints = [json.loads((root / f'world-{world:04d}-step-{step:05d}.checkpoint.json').read_text())
                       for step in range(manifest['steps'])]
        risk_worlds.append({**analyze_world(checkpoints), 'world': world, 'seed': manifest['base_seed'] + world})
        volume = buys = sells = rejected = spend = 0
        for checkpoint in checkpoints:
            spend += sum(item['cost_cents'] for item in checkpoint.get('committed_plan_execution', []))
            trades = [item for item in checkpoint['settlements'] if item['status'] == 'executed']
            step_volume = sum(item['fill']['cash_cents'] for item in trades)
            volume += step_volume
            buys += sum(item['action']['kind'] == 'buy' for item in trades)
            sells += sum(item['action']['kind'] == 'sell' for item in trades)
            rejected += sum(item['status'] == 'rejected_at_execution' for item in checkpoint['settlements'])
            spend += sum(item['action'].get('cost_cents', 0) for item in checkpoint['settlements'] if item['status'] == 'paid')
            market = checkpoint['market_after']
            row = {'scenario': label, 'world': world, 'seed': manifest['base_seed'] + world,
                   'step': checkpoint['step'], 'hours': checkpoint['second'] / 3600,
                   'market_cap_usd': float(Fraction(market['market_cap_usd_exact'])),
                   'pool_cash_usd': market['cash_reserve_cents'] / 100,
                   'step_volume_usd': step_volume / 100, 'cumulative_volume_usd': volume / 100,
                   'founder_cash_usd': checkpoint['balances_after']['founder']['cash_cents'] / 100,
                   'controlled_liquid_cash_usd': sum(checkpoint['balances_after'][actor]['cash_cents']
                                                     for actor in ('founder', 'marketing-partner')
                                                     if actor in checkpoint['balances_after']) / 100,
                   'checkpoint_sha256': checkpoint['checkpoint_sha256']}
            rows.append(row)
            for actor, observation in checkpoint['observations'].items():
                response = None
                for offset in range(manifest['actors']):
                    candidate = json.loads((root / f'call-{world * manifest["steps"] * manifest["actors"] + checkpoint["step"] * manifest["actors"] + offset + 1:06d}.response.json').read_text())
                    if candidate['decision']['actor_id'] == actor:
                        response = candidate
                        break
                own = next(item for item in checkpoint['settlements'] if item['actor_id'] == actor)
                nodes.append({'scenario': label, 'world': world, 'actor': actor, 'step': checkpoint['step'],
                              'hours': row['hours'], 'observation': observation,
                              'decision': checkpoint['decisions'][actor], 'settlement': own,
                              'own_balance_after': checkpoint['balances_after'][actor],
                              'market_after': market, 'answers': response['answers'],
                              'stress_policy': response.get('stress_policy'), 'checkpoint_sha256': checkpoint['checkpoint_sha256']})
        final = checkpoints[-1]
        first = checkpoints[0]
        founder_delta = final['balances_after']['founder']['cash_cents'] - first['balances_before']['founder']['cash_cents']
        worlds.append({'scenario': label, 'world': world, 'seed': manifest['base_seed'] + world,
                       'buys': buys, 'sells': sells, 'rejected': rejected, 'volume_cents': volume,
                       'campaign_spend_cents': spend, 'founder_cash_change_cents': founder_delta,
                       'founder_final_cash_cents': final['balances_after']['founder']['cash_cents'],
                       'founder_tokens_remaining': final['balances_after']['founder']['token_units'],
                       'initial_market_cap_usd': float(Fraction(first['market_before']['market_cap_usd_exact'])),
                       'final_market_cap_usd': float(Fraction(final['market_after']['market_cap_usd_exact'])),
                       'campaign_orders': len(final['campaigns']),
                       'delivered_campaigns': sum(item['status'] in ('active', 'expired') for item in final['campaigns']),
                       'failed_campaigns': sum(item['status'] == 'failed' for item in final['campaigns'])})
        for actor in final['balances_after']:
            if actor in ('pool', 'services'):
                continue
            own = [item for checkpoint in checkpoints for item in checkpoint['settlements'] if item['actor_id'] == actor]
            initial_cash = first['balances_before'][actor]['cash_cents'] + sum(
                item['cost_cents'] for item in first.get('committed_plan_execution', []) if item['payer'] == actor)
            actors.append({'scenario': label, 'world': world, 'actor': actor,
                           'cash_change_cents': final['balances_after'][actor]['cash_cents'] - initial_cash,
                           'remaining_tokens': final['balances_after'][actor]['token_units'],
                           'filled_buys': sum(item['status'] == 'executed' and item['action']['kind'] == 'buy' for item in own),
                           'filled_sells': sum(item['status'] == 'executed' and item['action']['kind'] == 'sell' for item in own)})
    retail_answers = [node['answers']['action'] for node in nodes
                      if node['actor'].startswith('retail-') and 'action' in node['answers']]
    selection_stats = {'retail_scored_decisions': len(retail_answers),
                       'mean_retail_buy_score': sum(sum(value for key, value in answer['probabilities'].items() if key.startswith('buy_'))
                                                    for answer in retail_answers) / max(1, len(retail_answers)),
                       'mean_retail_wait_score': sum(answer['probabilities'].get('wait', 0) for answer in retail_answers) / max(1, len(retail_answers))}
    return {'label': label, 'run': str(root), 'summary': summary, 'manifest': manifest,
            'depth_analysis': analyze_worlds(risk_worlds),
            'selection_stats': selection_stats,
            'committed_plan': manifest.get('committed_plan'),
            'rows': rows, 'nodes': nodes, 'worlds': worlds, 'actors': actors}


def chart(rows, field, title):
    width, height = 720, 250
    values = [row[field] for row in rows]
    low, high = min(values), max(values)
    span = high - low or max(abs(high) * .1, 1)
    low -= span * .08
    high += span * .08
    colors = ['#196d61', '#4766a5', '#a56b31', '#7d5585']
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    for fraction in (0, .5, 1):
        y = 205 - fraction * 175
        parts.append(f'<path d="M85 {y}H700" stroke="#d9e0df"/><text x="5" y="{y + 4}">${low + fraction*(high-low):,.0f}</text>')
    for world in range(4):
        own = [row for row in rows if row['world'] == world]
        path = ' '.join(f'{"M" if index == 0 else "L"}{85+row["hours"]/48*610:.2f},{205-(row[field]-low)/(high-low)*175:.2f}' for index, row in enumerate(own))
        parts.append(f'<path d="{path}" stroke="{colors[world]}" fill="none" stroke-width="2.4"/>')
    for hour in (0, 12, 24, 36, 48):
        parts.append(f'<text x="{85+hour/48*610}" y="237" text-anchor="middle">+{hour}h</text>')
    return ''.join(parts) + '</svg><p class="caption">Four recorded worlds, seeds 31–34. Lines show saved post-settlement states, not market observations.</p>'


def sections(data):
    summary, worlds = data['summary'], data['worlds']
    bullish = data['label'].startswith('BULL')
    trades = sum(world['buys'] + world['sells'] for world in worlds)
    committed = bool(data.get('committed_plan'))
    initial_cap = worlds[0].get('initial_market_cap_usd', 9090.90909090909)
    below_start = sum(world['final_market_cap_usd'] < world.get('initial_market_cap_usd', initial_cap) for world in worlds)
    plan_text = (' The scenario executes the same funded launch-post, Token Info and KOL order plan in both arms before actor decisions. Each world commits $899 from the marketing sleeve; actual delivery follows the saved delays and success draws. '
                 if committed else ' Campaign purchases in this run are optional actor choices, not guaranteed executed launch commitments. ')
    depth = data.get('depth_analysis')
    reconciliation = (f' After consolidating founder and marketing liquid cash, the median change is {dollars(depth["controlled_cash_change_cents"]["median"])}; {depth["worlds_with_controlled_cash_loss"]} of {depth["n_worlds"]} worlds lose liquid cash on that scope. This is still not total economic profit because inventory and LP claims remain excluded. '
                      if depth else '')
    return [
        ('1. Decision and headline',
         f'{data["label"]} contains {summary["completed_actor_calls"]:,} completed native Jev actor calls, four 48-hour worlds and 256 replay-verified checkpoints. '
         f'The recorded paths contain {trades:,} filled trades and {dollars(summary["executed_volume_cents"])} cumulative simulated turnover across all four worlds. '
         + plan_text +
         'Turnover is repeated cash exchanged through the same finite pool, not new outside capital, revenue or profit. '
         + ('This is the requested activity-stress arm: buy and sell action weights are multiplied by four, and buy-ticket caps by two. The label BULL is a user-facing scenario name, not proof that the paths represent a real bull market or rising prices.' if bullish else
            'This is the unmodified action-policy arm. Actor responses are measured after the recorded information is delivered; no action is forced. The label BEAR is a scenario name, not evidence that a real bear market or a specific incident caused the result.')),
        ('2. Price, market cap and liquidity',
         f'Final market caps range from ${min(world["final_market_cap_usd"] for world in worlds):,.2f} to ${max(world["final_market_cap_usd"] for world in worlds):,.2f}, versus an initial ${initial_cap:,.2f}. '
         + f'{below_start} of four worlds finish below that starting mark. Greater turnover does not imply appreciation. '
         + 'Market cap is computed from the hypothetical declared circulating supply and the current AMM reserve ratio. It is not cash available to the founder: selling inventory changes the ratio and incurs fees and slippage. '
         'Compare the four lines rather than treating one visually attractive path as typical. A flat line in the BEAR arm follows zero trades, not a stable-price forecast. Divergence in the BULL arm can arise from order sequencing, random policy selection and subsequent actor responses. '
         'The pool starts with $5,000 and hypothetical 550 million token units. The model starts directly in that pool; the planned 10–15 minute bonding-curve window is contextual, not an implemented graduation process.'),
        ('3. Activity and turnover',
         f'Recorded filled buys total {sum(world["buys"] for world in worlds):,}; filled sells total {sum(world["sells"] for world in worlds):,}. '
         f'There are {sum(world["rejected"] for world in worlds):,} execution rejections, and campaign payments total {dollars(summary["campaign_spend_cents"])} across the four worlds. '
         'The cumulative-turnover chart rises only when a trade actually fills. Campaign purchases transfer cash to services; they do not directly create a price jump or traded volume. '
         f'At the end of the four worlds, {sum(world.get("delivered_campaigns", 0) for world in worlds)} campaign orders had delivered and {sum(world.get("failed_campaigns", 0) for world in worlds)} had failed delivery. '
         'The stress multiplier changes relative sampling weights, not guaranteed trading frequency. Both buys and sells are increased, so a BULL label does not impose a positive price drift. Wallet exhaustion, inventory limits and slippage still constrain outcomes.'),
        ('4. Founder cash and inventory',
         f'Final founder cash ranges from {dollars(min(world["founder_final_cash_cents"] for world in worlds))} to {dollars(max(world["founder_final_cash_cents"] for world in worlds))}; '
         f'median change in the founder cash sleeve is {dollars(median(world["founder_cash_change_cents"] for world in worlds))}. '
         + reconciliation +
         'The founder starts with $43,000 liquid cash and 300 million hypothetical token units. A separate $2,000 marketing sleeve and $5,000 initial pool cash bring founder-controlled starting capital to $50,000 under the package assumptions. '
         'Cash change is not total economic profit: the result does not value remaining token inventory, recover LP claims, reconcile inventory cost basis, or attribute all marketing-partner costs to the founder cash sleeve. Do not rank a strategy as optimal from this cash chart.'),
        ('5. What is common, special and unresolved?',
         'Only four worlds are available per arm. Their range and median describe these paths, not a population confidence interval or a calibrated tail distribution. '
         + (f'Across {data["selection_stats"]["retail_scored_decisions"]} scored retail decisions, the mean total buy score is {data["selection_stats"]["mean_retail_buy_score"]:.1%} and the mean wait score is {data["selection_stats"]["mean_retail_wait_score"]:.1%}. These are provider decision scores, not observed trade frequencies or real-world probabilities. The unbuffed policy chooses a maximum-score action subject to its confidence gate rather than sampling these scores; repeated wait does not imply zero assigned buy weight. '
            if data.get('selection_stats') else '') +
         'The common starting resources and clock make the arms readable side by side, but the comparison combines weighted sampling, a larger buy cap and bypass of the action confidence gate. It does not identify the causal effect of a real market regime. '
         'Saved actor detail shows the current information, own state, provider scores, policy-selected action and execution receipt. Private founder/MM messages are excluded from retail views, although the full analyst artifact itself contains private research and must not be distributed as a retail-access-controlled service.'),
        ('6. When a reader might apply the scenario',
         'Use the market-regime checklist below to decide which scenario is relevant. Review Bitcoin trend, broad participation, centralized-exchange spot turnover, DEX spot activity, liquidity and disruptions together. '
         'Suggested comparisons such as 7-day turnover versus its 90-day median are exploratory screening rules, not validated regime classifiers. Require consistency over a user-chosen window rather than one headline or one high-volume day. '
         'Mixed indicators should be labeled mixed or transitional; neither scenario must be selected. No current indicator readings, market-regime determination or causal claim about a Binance incident is made here.'),
        ('7. Limits and next evidence',
         'The finite cast has eight illustrative actors and no new-wallet arrivals. There is no fitted six-to-twelve-month demand cohort, real political announcement calendar, bonding-curve settlement, graduation, MEV, LP withdrawal or calibrated promotion conversion. '
         'All prices, volumes and cash paths are simulated. Fees and integer accounting are enforced, but that does not validate behavioral realism. Choice scores are provider decision scores, not the odds of a $5M token or a future market event. '
         'Next research should compare matched narrative arms and historical arrival/liquidity cohorts without changing the frozen BULL/BEAR results. A recommendation to buy or sell requires evidence and risk limits beyond this load test.')
    ] + ([] if not depth else [
        ('8. Risk and execution diagnostics',
         f'The sampled maximum drawdown across worlds ranges from {depth["sampled_max_drawdown_fraction"]["minimum"]:.1%} to {depth["sampled_max_drawdown_fraction"]["maximum"]:.1%}. Minimum sampled pool cash ranges from {dollars(depth["minimum_sampled_pool_cash_cents"]["minimum"])} to {dollars(depth["minimum_sampled_pool_cash_cents"]["maximum"])}. '
         f'There are {depth["rejected_trades"]} rejected executions among {depth["trade_attempts"]} attempted trades. Zero attempts means the rejection rate is undefined, not zero execution risk. '
         'Drawdowns use saved pre/post barrier states and can miss within-barrier extremes. Worlds, not actor calls, are the statistical units. Four worlds justify descriptive medians and ranges, not p95/p99 loss estimates, calibrated crash probabilities or a forecast fan chart.'),
        ('9. Edge cases and falsification',
         'Measured edge-case coverage: ' + '; '.join(f'{item["case"]}: {item["status"]}' + (f' in {item["world_count"]} of {depth["n_worlds"]} worlds' if item['world_count'] is not None else '') for item in depth['edge_case_coverage']) + '. '
         'Untested or unsupported stress branches remain explicit: simultaneous venue outage and forced exit; liquidity withdrawal; late arrival surges; correlated KOL failures; campaign cancellation/refund; oracle/price-feed delay; bonding-curve migration; chain reorganization and MEV. They are a coverage backlog, not simulated outcomes. '
         'A claimed campaign-demand mechanism would be weakened if matched campaign-on/off worlds with identical policy and shocks show no reproducible difference. Those ablations have not been run. Neither turnover after publication nor the current BULL/BEAR difference establishes campaign causality.')])


CSS = '''body{margin:0;background:#f5f5ef;color:#18382f;font:16px/1.65 system-ui,sans-serif}main{max-width:1060px;margin:auto;padding:28px}h1{font:clamp(30px,5vw,54px)/1.12 Georgia,serif}h2{font:28px/1.2 Georgia,serif}h3{font-size:18px}section{background:white;padding:28px;margin:22px 0;border:1px solid #dce1d9;border-radius:10px}p{max-width:90ch}.caption,small{font-size:13px;color:#53675f}svg{width:100%;height:auto}svg text{font:12px system-ui;fill:#53675f}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #dae0d9;vertical-align:top}button,select,input{font:inherit;padding:9px;max-width:100%;border:1px solid #9bad9f;border-radius:5px;background:white;color:#18382f}button{cursor:pointer}nav{display:flex;gap:12px;flex-wrap:wrap}a{color:#196d61}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.notice{border-left:5px solid #ae7d32;padding-left:16px}#dag{overflow:auto}#dag svg{min-width:900px}.stat{font-size:30px;font-weight:600}.regime-row{padding:12px 0;border-bottom:1px solid #ddd}@media(max-width:650px){main{padding:12px}section{padding:17px}.grid{grid-template-columns:1fr}table{font-size:12px}td,th{padding:6px}}@media print{body{background:white}main{padding:0}section{break-inside:avoid}button,select,input{display:none}}'''


def regime_html():
    return ''.join(f'<div class="regime-row"><h3>{escape(name)}</h3><p><b>BULL:</b> {escape(bull)}</p><p><b>BEAR:</b> {escape(bear)}</p><small>{escape(note)}</small></div>' for name, bull, bear, note in REGIMES)


def write_report(data, destination):
    slug = 'BULL' if data['label'].startswith('BULL') else 'BEAR'
    parts = [f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MACRON {data["label"]}</title><style>{CSS}</style><main><p>MACRON / 2 NOVEMBER 2026 / REPLAY-VERIFIED RESEARCH</p><h1>{data["label"]}</h1><p class="notice">Synthetic scenario label, not an observed market regime. Four worlds; no calibrated market odds.</p>']
    markdown = [f'# MACRON — {data["label"]}', '', 'Recorded 2 November 2026. Completed native inference; replay verified. Synthetic regime label, not a current-market diagnosis.', '']
    for index, (title, text) in enumerate(sections(data)):
        parts.append(f'<section><h2>{title}</h2>')
        if index in (1, 2, 3):
            field = {1: 'market_cap_usd', 2: 'cumulative_volume_usd', 3: 'founder_cash_usd'}[index]
            parts.append(chart(data['rows'], field, title))
            if index == 3 and data.get('depth_analysis'):
                parts.append('<h3>Founder plus marketing: consolidated liquid cash</h3>' + chart(data['rows'], 'controlled_liquid_cash_usd', 'Consolidated liquid cash'))
        parts.append(f'<p>{escape(text)}</p></section>')
        markdown.extend([f'## {title}', '', text, ''])
    table = '| World | Filled buys | Filled sells | Turnover USD | Founder cash change USD | Remaining founder tokens |\n|---|---:|---:|---:|---:|---:|\n'
    for world in data['worlds']:
        table += f'| {world["world"] + 1} | {world["buys"]} | {world["sells"]} | {world["volume_cents"]/100:,.2f} | {world["founder_cash_change_cents"]/100:,.2f} | {world["founder_tokens_remaining"]:,} |\n'
    markdown.extend(['## Recorded worlds', '', table, '', '## Market-regime applicability: user decides', ''])
    parts.append('<section><h2>Recorded worlds</h2><table><tr><th>World</th><th>Buys / sells</th><th>Turnover</th><th>Founder cash change</th></tr>' + ''.join(
        f'<tr><td>{world["world"]+1}</td><td>{world["buys"]} / {world["sells"]}</td><td>{dollars(world["volume_cents"])}</td><td>{dollars(world["founder_cash_change_cents"])}</td></tr>' for world in data['worlds']) + '</table><p>Cash change is not total economic profit.</p></section>')
    for name, bull, bear, note in REGIMES:
        markdown.extend([f'### {name}', f'- BULL: {bull}', f'- BEAR: {bear}', f'- Caution: {note}', ''])
    markdown.extend(['## Sources and audit', '', f'Private run: `{data["run"]}`.', 'Sources support indicator definitions, not current readings or validated thresholds.', ''])
    parts.append('<section><h2>Market-regime checklist</h2>' + regime_html() + '</section><section><h2>Sources and audit</h2><ul>')
    for title, url in SOURCES:
        markdown.append(f'- [{title}]({url})')
        parts.append(f'<li><a href="{url}">{escape(title)}</a></li>')
    parts.append(f'</ul><p>{escape(data["run"])}</p></section></main></html>')
    (destination / f'{slug}-Market-scenario.html').write_text(''.join(parts))
    (destination / f'{slug}-Market-scenario.md').write_text('\n'.join(markdown))
    write_pdf(data, destination / f'{slug}-Market-scenario.pdf')


def write_pdf(data, filename):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.graphics.shapes import Drawing, Line, String, PolyLine
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Caption',fontSize=9,leading=13,textColor=colors.HexColor('#53675f')))
    styles.add(ParagraphStyle(name='Readable', fontSize=11, leading=16, spaceAfter=13, alignment=TA_LEFT))
    document = SimpleDocTemplate(str(filename), pagesize=(595,842), rightMargin=48,leftMargin=48,topMargin=48,bottomMargin=48,
                                title='MACRON '+data['label'], author='Boyun scenario lab')
    story = []
    for index, (title, text) in enumerate(sections(data)):
        if index:
            story.append(PageBreak())
        story.extend([Paragraph(escape(data['label']), styles['Title']), Paragraph(escape(title), styles['Heading1']),
                      Paragraph('Recorded 2 November 2026 | Four synthetic worlds | 2,048 native calls | Exact replay verified', styles['Caption']), Spacer(1,18)])
        if index in (1,2,3):
            field = {1:'market_cap_usd',2:'cumulative_volume_usd',3:'founder_cash_usd'}[index]
            drawing = Drawing(490,230)
            values = [row[field] for row in data['rows']]
            low, high = min(values), max(values)
            span = high-low or max(abs(high)*.1,1)
            low -= span*.08
            high += span*.08
            for fraction in (0,.5,1):
                y = 35+fraction*160
                drawing.add(Line(70,y,480,y,strokeColor=colors.HexColor('#d9e0df')))
                drawing.add(String(0,y,f'${low+fraction*(high-low):,.0f}',fontSize=9))
            for world, color in enumerate(('#196d61','#4766a5','#a56b31','#7d5585')):
                points = [coordinate for row in data['rows'] if row['world']==world
                          for coordinate in (70+row['hours']/48*410,35+(row[field]-low)/(high-low)*160)]
                drawing.add(PolyLine(points,strokeColor=colors.HexColor(color),strokeWidth=1.7))
                drawing.add(String(70+world*100,217,f'World {world+1}',fillColor=colors.HexColor(color),fontSize=10))
            for hour in (0,12,24,36,48):
                drawing.add(String(65+hour/48*410,10,f'+{hour}h',fontSize=9))
            story.extend([drawing, Spacer(1,18)])
        for sentence_group in text.split('. '):
            story.append(Paragraph(escape(sentence_group + ('.' if not sentence_group.endswith('.') else '')), styles['Readable']))
    story.extend([PageBreak(),Paragraph('Recorded worlds',styles['Heading1'])])
    table = [['World','Buys','Sells','Turnover USD','Founder cash change']]
    table += [[str(world['world']+1),str(world['buys']),str(world['sells']),dollars(world['volume_cents']),dollars(world['founder_cash_change_cents'])] for world in data['worlds']]
    grid = Table(table,colWidths=[45,45,45,125,140])
    grid.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f0e5')),('FONTSIZE',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
    story.extend([grid,Spacer(1,18),Paragraph('Cash change excludes remaining token value and recoverable LP claims. It is not total founder profit.',styles['Readable']),PageBreak(),Paragraph('Market regime: user decision checklist',styles['Heading1'])])
    for name,bull,bear,note in REGIMES:
        story.extend([Paragraph(escape(name),styles['Heading2']),Paragraph('<b>BULL:</b> '+escape(bull),styles['Readable']),Paragraph('<b>BEAR:</b> '+escape(bear),styles['Readable']),Paragraph(escape(note),styles['Caption']),Spacer(1,12)])
    story.extend([PageBreak(),Paragraph('Sources and audit',styles['Heading1'])])
    for title,url in SOURCES:
        story.extend([Paragraph(escape(title),styles['Readable']),Paragraph(f'<link href="{url}">{url}</link>',styles['Readable'])])
    story.append(Paragraph('No current market readings or historical calibration are claimed. General indicator definitions were checked against these primary sources on 2 November 2026. The run directory and exact summary are in the accompanying JSON/CSV files.',styles['Readable']))
    def footer(canvas, document):
        canvas.setFont('Helvetica',9)
        canvas.drawString(48,28,'MACRON | Synthetic scenario research | Not a market forecast')
        canvas.drawRightString(547,28,str(document.page))
    document.build(story,onFirstPage=footer,onLaterPages=footer)


def write_dashboard(datasets, destination):
    content = json.dumps([{key:value for key,value in data.items() if key not in ('manifest',)} for data in datasets],separators=(',',':')).replace('<','\\u003c')
    template = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MACRON BULL / BEAR evidence explorer</title><style>__CSS__</style><main><p>MACRON / COMPLETE RECORDED RUNS / PRIVATE ANALYST EXPLORER</p><h1>BULL / BEAR Market scenarios</h1><p class="notice">BULL is artificial activity stress. BEAR is unmodified low activity. Neither label diagnoses today's market. This file contains private research. Actor selection filters the view, not file access.</p><nav><label>Scenario <select id="scenario"><option value="0">BULL Market scenario</option><option value="1">BEAR Market scenario</option></select></label><label>World <select id="world"><option value="0">1 · seed 31</option><option value="1">2 · seed 32</option><option value="2">3 · seed 33</option><option value="3">4 · seed 34</option></select></label><label>Actor <select id="actor"></select></label></nav><section><h2 id="finding"></h2><div id="overview"></div><p id="interpretation"></p></section><section><h2>Recorded decision timeline</h2><p>Root: 2 Nov 2026, 12:00 UTC+4. Horizontal spacing is elapsed time; zoom the first hour to inspect minute-by-minute launch decisions. Click any node or edge. Each world is one realized path, not a tree of unexecuted outcomes.</p><label>Window <select id="window"><option value="48">Full 48 hours</option><option value="1">First hour</option></select></label><div id="dag"></div><label>Decision <input id="step" type="range" min="0" max="63" value="0"></label><div id="detail"></div></section><section><h2>Choose regime applicability yourself</h2><p>These are screening ideas, not fitted thresholds. Mark mixed evidence rather than force a BULL/BEAR classification. Enter your own as-of readings and save a decision note locally; no data is sent.</p>__REGIMES__<label>Your as-of date and evidence <textarea id="note" rows="5" style="width:95%;font:inherit"></textarea></label><p><button id="save">Download regime decision note</button></p></section><section><h2>Sources</h2>__SOURCES__</section></main><script id="data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id),cash=value=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(value),ratio=text=>{const [n,d='1']=String(text).split('/');return Number(n)/Number(d)},node=(tag,text)=>{const element=document.createElement(tag);if(text!==undefined)element.textContent=text;return element},svg=(tag,attributes)=>{const element=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attributes).forEach(([key,value])=>element.setAttribute(key,value));return element};
const actors=[...new Set(data[0].nodes.map(item=>item.actor))];actors.forEach(actor=>{const option=node('option',actor);option.value=actor;$('actor').append(option)});
function render(){const scenario=data[Number($('scenario').value)],world=Number($('world').value),actor=$('actor').value,path=scenario.nodes.filter(item=>item.world===world&&item.actor===actor),selected=path[Number($('step').value)],summary=scenario.worlds[world];$('finding').textContent=scenario.label+' · world '+(world+1);$('overview').textContent=`${summary.buys} filled buys / ${summary.sells} filled sells / ${cash(summary.volume_cents/100)} turnover / ${summary.rejected} rejected executions.`;$('interpretation').textContent='Turnover counts repeated simulated exchange, not new money or profit. Founder cash change '+cash(summary.founder_cash_change_cents/100)+' excludes remaining inventory and LP claims.';
const limit=Number($('window').value),visible=path.filter(item=>item.hours<=limit),drawing=svg('svg',{viewBox:'0 0 1200 180',role:'group','aria-label':'Clickable actor decision trajectory'});for(let index=0;index<visible.length;index++){const point=visible[index],x=35+point.hours/limit*1120;if(index){const previous=visible[index-1],edge=svg('line',{x1:35+previous.hours/limit*1120,y1:80,x2:x,y2:80,stroke:'#94aaa0','stroke-width':5,tabindex:0,role:'button','aria-label':'Inspect action '+previous.decision.action_id});edge.onclick=()=>{$('step').value=previous.step;render()};edge.onkeydown=event=>{if(event.key==='Enter')edge.onclick()};drawing.append(edge)}const circle=svg('circle',{cx:x,cy:80,r:point.step===selected.step?10:6,fill:point.settlement.status==='executed'?'#196d61':'#aeb7b0',tabindex:0,role:'button','aria-label':`Inspect +${point.hours.toFixed(2)}h ${point.decision.action_id}`});circle.onclick=()=>{$('step').value=point.step;render()};circle.onkeydown=event=>{if(event.key==='Enter')circle.onclick()};drawing.append(circle);if(limit===1||index%8===0||index===visible.length-1){const label=svg('text',{x,y:index%2?125:150,'text-anchor':'middle'});label.textContent=point.hours<1?Math.round(point.hours*60)+'m':'+'+point.hours+'h';drawing.append(label)}}$('dag').replaceChildren(drawing);
const details=$('detail');details.replaceChildren(node('h2',`+${selected.hours.toFixed(2)}h · ${actor} · ${selected.decision.action_id}`));details.append(node('p',`Execution: ${selected.settlement.status}. Own cash after: ${cash(selected.own_balance_after.cash_cents/100)}; tokens: ${selected.own_balance_after.token_units.toLocaleString()}. Public market cap: ${cash(ratio(selected.market_after.market_cap_usd_exact))}; pool cash: ${cash(selected.market_after.cash_reserve_cents/100)}.`));details.append(node('h3','Information available to this actor'));selected.observation.visible_events.forEach(event=>details.append(node('p',event.text)));selected.observation.coordination.forEach(message=>details.append(node('p',message.sender+': '+message.text)));selected.observation.visible_campaigns.forEach(campaign=>details.append(node('p',campaign.status+': '+campaign.text)));details.append(node('h3','Provider scores and stress-policy choice'));details.append(node('p','Scores are not event odds. Stress sampling overrides the provider action choice; it is not a model explanation or evidence a recommendation is optimal.'));const pre=node('pre',JSON.stringify({answers:selected.answers,stress_policy:selected.stress_policy},null,2));details.append(pre);const memory=node('details');memory.append(node('summary','Saved own memory and current state'),node('pre',JSON.stringify(selected.observation,null,2)));details.append(memory);}
['scenario','world','actor','window','step'].forEach(id=>$(id).oninput=render);$('save').onclick=()=>{const text='MACRON market-regime decision note\\nUser judgment; not a calibrated classifier.\\n'+$('note').value,url=URL.createObjectURL(new Blob([text],{type:'text/plain'})),link=node('a');link.href=url;link.download='market-regime-decision.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),500)};render();
</script></html>'''
    sources=''.join(f'<p><a href="{url}">{escape(title)}</a></p>' for title,url in SOURCES)
    (destination/'MACRON-BULL-BEAR-interactive.html').write_text(template.replace('__CSS__',CSS).replace('__DATA__',content).replace('__REGIMES__',regime_html()).replace('__SOURCES__',sources))


def build(bull, bear, output, docs):
    destination=Path(output)
    destination.mkdir(parents=True,exist_ok=False)
    datasets=[collect(bull,'BULL Market scenario — activity stress'),collect(bear,'BEAR Market scenario — low activity')]
    for data in datasets:
        write_report(data,destination)
    write_dashboard(datasets,destination)
    for name,key in (('worlds','worlds'),('timeline','rows'),('actors','actors')):
        records=[record for data in datasets for record in data[key]]
        with (destination/f'{name}.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    score_rows=[]
    for data in datasets:
        for node in data['nodes']:
            answer=node['answers'].get('action')
            if answer is None:
                continue
            score_rows.append({'scenario':data['label'],'world':node['world'],'step':node['step'],'hours':node['hours'],
                               'actor':node['actor'],'provider_choice':answer['choice'],'provider_confidence':answer['confidence'],
                               'buy_score':sum(value for key,value in answer['probabilities'].items() if key.startswith('buy_')),
                               'sell_score':sum(value for key,value in answer['probabilities'].items() if key.startswith('sell_')),
                               'wait_score':answer['probabilities'].get('wait',0),'policy_action':node['decision']['action_id'],
                               'execution_status':node['settlement']['status']})
    with (destination/'actor-scores.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(score_rows[0]));writer.writeheader();writer.writerows(score_rows)
    aggregate=[{key:value for key,value in data.items() if key not in ('nodes','manifest','actors')} for data in datasets]
    (destination/'results.json').write_text(json.dumps(aggregate,indent=2))
    (destination/'risk-analysis.json').write_text(json.dumps([{'scenario':data['label'], **data['depth_analysis']} for data in datasets],indent=2))
    claims=[]
    for data in datasets:
        depth=data['depth_analysis']
        evidence=[{'world':world['world'],'seed':world['seed'],'initial_checkpoint':world['initial_checkpoint'],
                   'final_checkpoint':world['final_checkpoint']} for world in depth['worlds']]
        for suffix,metric,implication in (
                ('controlled-cash','controlled_cash_change_cents','Founder-only cash is insufficient to judge the funded plan; inventory and LP claims remain unvalued.'),
                ('sampled-drawdown','sampled_max_drawdown_fraction','Path risk can differ from terminal return; saved barriers may miss within-barrier extremes.'),
                ('execution-rejections','rejected_trades','A proposed action is not a guaranteed fill; report attempted trades as its denominator.')):
            claims.append({'id':('bull' if data['label'].startswith('BULL') else 'bear')+'-'+suffix,
                           'scenario':data['label'],'evidence_type':'recorded_simulation_fact','metric':metric,
                           'value':depth[metric],'n_worlds':depth['n_worlds'],'run_directory':data['run'],
                           'evidence':evidence,'implication':implication,
                           'falsification_check':'Recompute from replay-verified checkpoint balances/settlements; a mismatch invalidates this claim.',
                           'causal_status':'descriptive; no empirical market or campaign attribution'})
    (destination/'claims.json').write_text(json.dumps(claims,indent=2))
    index=['# MACRON — BULL and BEAR Market scenario results','',
           'Both arms completed 2,048 native Jev calls, four worlds, 64 decisions per actor and exact replay. Labels describe scenario assumptions; they do not classify the current market.','',
           '| Scenario | Filled buys | Filled sells | Simulated turnover | Campaign spend |','|---|---:|---:|---:|---:|']
    for data in datasets:
        index.append(f'| {data["label"]} | {sum(world["buys"] for world in data["worlds"])} | {sum(world["sells"] for world in data["worlds"])} | {dollars(data["summary"]["executed_volume_cents"])} | {dollars(data["summary"]["campaign_spend_cents"])} |')
    index.extend(['','## Deliverables','',f'Output directory: `{destination.resolve()}`.','',
                  '- BULL-Market-scenario.md / .html / .pdf: nine analytical sections, market/cash graphs, consolidated accounting, risk and edge-case coverage, applicability checklist and sources.',
                  '- BEAR-Market-scenario.md / .html / .pdf: the same structure, retaining recorded actor responses rather than inventing activity.',
                  '- MACRON-BULL-BEAR-interactive.html: self-contained world/actor timeline explorer, clickable states/actions, provider scores and stress policy, permitted actor memory and a regime decision note.',
                  '- results.json, risk-analysis.json, claims.json, worlds.csv, timeline.csv, actors.csv and actor-scores.csv: source tables, risk diagnostics and evidence-linked claims.',
                  '- Presenton deck export links, when available, are recorded in PRESENTATION-EXPORTS.md.','',
                  '## Interpretation','',
                  'BULL is a fourfold buy/sell score-weight intervention with doubled buy caps and action-confidence bypass. BEAR uses the original provider maximum-score choice and confidence gate. This is not a clean causal market-regime comparison. Both use the same MACRON narrative, hypothetical resources and finite cast.',
                  'No live Bitcoin, exchange or DEX readings were imported. The reader decides regime applicability using the following exploratory checklist. Mixed conditions need not fit either scenario.',''])
    for name,bull_text,bear_text,note in REGIMES:
        index.extend([f'### {name}',f'- BULL applicability: {bull_text}',f'- BEAR applicability: {bear_text}',f'- Caution: {note}',''])
    index.append('## Sources')
    if datasets[0].get('committed_plan'):
        index.extend(['','## Executed launch and marketing plan','',
                      'Both arms execute the same three funded orders at root: launch post ($100 assumed production/publication cost), Token Info ($299) and KOL publication ($500 assumed). Each world commits $899 of the existing $2,000 marketing sleeve; no extra money is created.',
                      'The launch post is immediately public for 6h. Token Info becomes visible after 12h. KOL publication is due after 1h, lasts 6h and has an explicitly assumed 80% delivery success probability. An order is not a guaranteed publication. Check the saved campaign delivery states.',
                      'This simulates publication and finite-actor exposure; it does not execute real purchases, fit audience reach, or create new-wallet arrivals. The BEAR arm uses independent unbuffed actor actions; BULL retains the disclosed activity stress policy.',''])
    index += [f'- [{title}]({url})' for title,url in SOURCES]
    text='\n'.join(index)+'\n'
    (destination/'INDEX.md').write_text(text)
    Path(docs).write_text(text)
    return datasets


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--bull',required=True);parser.add_argument('--bear',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--docs',required=True)
    args=parser.parse_args()
    result=build(args.bull,args.bear,args.output,args.docs)
    print(json.dumps([{'scenario':data['label'],**data['summary']} for data in result],indent=2))
