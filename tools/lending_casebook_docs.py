"""Reader-facing NEAR lending documents: World Creation, Choppy, Bear and Bull cases.

All numbers are computed from lending_casebook_data; no figure is typed by hand except
external snapshot values, which cite their captured evidence file.
"""
from collections import Counter

from build_financial_casebook import chart, paragraph, section, table
from lending_casebook_data import at_day, family
from lending_casebook_records import decision_record, technical  # noqa: F401  (re-exported)

DAYS = list(range(1, 91))
RHEA = {'supplied': 13.09e6, 'borrowed': 11.10e6, 'supply_apy': .0988, 'borrow_apy': .1529, 'near': 4.0375}
RHEA_SRC = 'Rhea lending page captured 2026-11-05 08:14 UTC (engine/examples/near-lending/evidence/rhea-live-lending.txt).'
CHOICES = [('Wait', {'wait', 'no_action', 'delay'}), ('Add (supply / post / accept)', {'supply', 'post', 'accept', 'status_update', 'partner_retention', 'extra_kol'}),
           ('Borrow', {'borrow'}), ('Reduce (withdraw / repay / decline)', {'withdraw', 'repay', 'remove', 'decline'})]


def path_stats(path):
    """Drawdowns on hourly closes (what the oracle saw) versus intrahour lows (never observed by the ledger)."""
    rows = path['path']; opening = rows[0]['near_close_scaled']
    close = min(rows, key=lambda r: r['near_close_scaled']); low = min(rows, key=lambda r: r['near_low_scaled'])
    return {'close_dd': close['near_close_scaled'] / opening - 1, 'close_day': close['hour'] // 24 + 1,
            'low_dd': low['near_low_scaled'] / opening - 1, 'low_day': low['hour'] // 24 + 1,
            'end': rows[-1]['near_close_scaled'] / opening - 1}


def liq_days_text(world):
    days = [f'day {d} ({n})' for d, n in zip(DAYS, world['liq_counts']) if n]
    return ', '.join(days) if days else 'none'


def usd(v):
    return f'${v:,.0f}'


def short(v):
    return f'${v / 1e6:.2f}M' if abs(v) >= 1e6 else f'${v / 1e3:.0f}K' if abs(v) >= 1e3 else f'${v:,.0f}'


def series(world, key, scale=1.0):
    return [round(world['daily'][d - 1][key] * scale, 4) for d in DAYS]


def run_src(*worlds):
    return 'Run data: ' + '; '.join(f'engine/output/{w["dir"]}/daily.json' for w in worlds) + '.'


def label(w):
    return f'{w["name"]} ({w["code"]})'


def peak(world, key):
    day = max(DAYS, key=lambda d: at_day(world, key, d))
    return day, at_day(world, key, day)


def mix_rows(world, families):
    rows, data = [], {name: [] for name, _ in CHOICES}
    for fam in families:
        counts = Counter()
        for d in world['decisions']:
            if family(d['actor']) == fam:
                counts[d['choice']] += 1
        total = sum(counts.values())
        if not total:
            continue
        rows.append(f'{fam} (n={total})')
        for name, members in CHOICES:
            data[name].append(round(100 * sum(c for k, c in counts.items() if k in members) / total, 1))
    return rows, [{'name': name, 'values': data[name]} for name, _ in CHOICES]


def gantt(world):
    lanes, start, end = [], [], []
    for item in world['campaign']:
        hour = item.get('delivered_hour', item.get('decided_hour'))
        if item['id'].startswith('team_update'):
            continue
        lanes.append(f"{item['id'].replace('_', ' ')} ({item['status']})")
        start.append(round(hour / 24, 2)); end.append(round(hour / 24 + .8, 2))
    updates = [c['delivered_hour'] / 24 for c in world['campaign'] if c['id'].startswith('team_update')]
    if updates:
        lanes.append(f'team status updates (n={len(updates)})'); start.append(round(min(updates), 2)); end.append(round(max(updates) + .8, 2))
    moves = [t['hour'] / 24 for t in world['triggers'] if t['trigger'] == 'near_move']
    if moves:
        lanes.append(f'NEAR ±8%/24h triggers (n={len(moves)})'); start.append(round(min(moves), 2)); end.append(round(max(moves) + .8, 2))
    liq = [d for d in DAYS if world['liq_counts'][d - 1]]
    if liq:
        lanes.append(f'liquidations (n={sum(world["liq_counts"])}, {len(liq)} days)'); start.append(liq[0] - 1); end.append(liq[-1])
    return lanes, start, end


def accounting_table(worlds):
    rows = []
    for w in worlds:
        rows.append([w['name'], short(w['interest_collected'] + w['interest_owed']), usd(w['protocol_collected'] + w['protocol_owed']),
                     usd(sum(w['spending'].values())), f'{sum(w["liq_counts"])} / {short(sum(w["liq_repaid"]))}',
                     usd(w['losses']), usd(w['reserve_left']), str(w['withdraw_requests'])])
    return table(['World', 'Borrower interest (paid + owed)', 'Protocol share', 'Campaign spend', 'Liquidations / repaid',
                  'Bad debt', 'Reserve left', 'Withdraw requests'], rows,
                 'Interest = repayment and liquidation receipts plus receivables owed at day 90. Protocol share is 15% of interest. '
                 'Spend is charged only when a campaign item is delivered; $30K operations is not charged in the ledger.')


def world_creation(ctx, base):
    w = ctx['worlds']; fl = w['first-light']; cast = ctx['cast']; cal = ctx['calendar']; s = ctx['settings']
    doc = base('WORLD-CREATION', 'World Creation', 'Question, evidence, actors, rules and the six simulated worlds', ctx)
    doc['highlights'] = [
        'Question: what happens in the first 90 days if we launch NEAR-collateral USDC lending with $1M of friendly supply deposited at opening?',
        'Six native, complete 90-day worlds (2,160 hours each): four on local Laya, two on Jev. Five replay a real choppy NEAR window; one replays a real bear window.',
        'The cast, campaign and lending rules are synthetic assumptions you approved. Market prices and the Rhea outside option are real, dated observations.',
        'No no-launch arm was run. Real-world odds are unknown.']
    m = ctx['paths']['choppy-2025-08']['summary']; b = ctx['paths']['bear-2025-11']['summary']
    cs, bs = path_stats(ctx['paths']['choppy-2025-08']), path_stats(ctx['paths']['bear-2025-11'])
    doc['sections'].append(section('Experiment identity',
        paragraph('The user asked what would happen if they launched a lending protocol on NEAR. Over 41 recorded answers '
                  'the question narrowed to: native NEAR as collateral, Circle-issued native USDC as the only borrowable '
                  'asset, a 90-day evaluation, supplier points on USDC actually borrowed, no token, and a broad public launch. '
                  'The user then chose to assume $1M of friendly-partner USDC is already deposited at opening.'),
        table(['Item', 'Value'], [
            ['Run date / evidence cutoff', '5 November 2026; market snapshot captured 2026-11-05 08:14 UTC'],
            ['Horizon', '90 days = 2,160 hourly ledger steps per world; all six worlds completed it'],
            ['Actor models', 'Laya (local, convaiinnovations/laya-typed-decisions) and Jev (jev-latest, remote)'],
            ['Worlds', '6 native runs; no no-launch arm; no repeated seeds'],
            ['Result identity', ctx['identity'][:32] + '…']], 'Run identity hashes every world manifest; see the Technical Report.')))
    doc['sections'].append(section('Real-world evidence',
        paragraph(f'Outside option. On the evidence date Rhea, the largest NEAR lending venue observed, listed native USDC with '
                  f'{short(RHEA["supplied"])} supplied, {short(RHEA["borrowed"])} borrowed ({RHEA["borrowed"] / RHEA["supplied"]:.0%} utilization), '
                  f'a {RHEA["supply_apy"]:.2%} supply APY and a {RHEA["borrow_apy"]:.2%} borrow APY, with NEAR at ${RHEA["near"]}. '
                  'Actors see these Rhea rates as a fixed outside option for the whole run. ' + RHEA_SRC),
        paragraph(f'Prices. Both price paths are real Binance NEARUSDT hourly closes, multiplied by a constant so each opens at '
                  f'${RHEA["near"]}. That keeps percentage moves and timing but not the historical price level or liquidity. '
                  f'Choppy window from {m["window_start_utc"][:10]}: {cs["end"]:+.1%} net; hourly closes fall at most {cs["close_dd"]:.1%} (day {cs["close_day"]}); '
                  f'worst 24h {m["worst_24h_return"]:.1%}. Bear window from {b["window_start_utc"][:10]}: {bs["end"]:+.1%} net; hourly closes fall at most '
                  f'{bs["close_dd"]:.1%} (day {bs["close_day"]}); worst 24h {b["worst_24h_return"]:.1%}. USDC used real USDCUSDT closes; neither window contains a depeg.'),
        paragraph(f'What the ledger does not see. The oracle uses hourly closes, so moves inside an hour are invisible. On 2025-10-10 (day {cs["low_day"]}) NEAR wicked '
                  f'to {cs["low_dd"]:.1%} within one hour but closed that hour about 9% down; no liquidation could trigger on the wick. Real oracles update '
                  'far more often, so real liquidations during such a wick could exceed anything recorded here.'),
        chart('line', 'The two replayed NEAR paths', DAYS,
              [{'name': 'Choppy (Aug–Nov 2025)', 'values': series(fl, 'near_usd')},
               {'name': 'Bear (Nov 2025–Feb 2026)', 'values': series(w['long-winter'], 'near_usd')}],
              f'The choppy path falls as far as {cs["close_dd"]:.0%} (day {cs["close_day"]}) and ends {cs["end"]:+.0%}; the bear path ends {bs["end"]:+.0%}.',
              'Daily close (hour 23 UTC) of each scaled path, in USD per NEAR, days 1–90 from launch. Both start at $4.04, so '
              'the two lines are directly comparable in percentage terms.',
              'Liquidation and collateral findings in this package hold only for these two real paths; no bull path was run.',
              'Binance klines via evidence/manifest.json; price-path-choppy-2025-08.json and price-path-bear-2025-11.json.',
              unit='USD / NEAR', x_unit='d'),
        table(['Source', 'Used for', 'Limitation'],
              [[src['id'], src['url'][:70], src['limitations'][:90]] for src in ctx['evidence']['sources']
               if not src['id'].startswith(('nearusdt-1h', 'usdcusdt-1h', 'bear-'))],
              'Hourly Binance parts are listed in evidence/manifest.json with SHA-256 hashes.')))
    actors = [[a['id'], a['role'].replace('_', ' '), short(a.get('deposited_usdc', 0) + a.get('usdc', 0) + a.get('outside_usdc', 0)),
               f'{a.get("near", 0):,}' if a.get('near') else '—', (a.get('incentive') or a.get('need') or a.get('audience_hint') or '—').replace('_', ' ')[:70]]
              for a in cast['actors']]
    caps = {'Friendly supply at opening': 1_000_000, 'Independent supply capacity': 700_000,
            'Borrow capacity at 50% LTV': 355_000 * RHEA['near'] * .5, 'Aggregate borrow cap': 500_000,
            'First Light borrow ceiling (6 × $50K)': 300_000, 'Liquidator cash': 200_000}
    doc['sections'].append(section('Actors, resources and information',
        paragraph('Twenty decision-makers (27 after the borrower group was split into 8 accounts). Each actor sees only its own balances, '
                  'public pool totals, its private motive, public news on channels it follows, and the Rhea outside option. Nobody sees '
                  'other wallets, future prices or the actor model\'s outputs for others. Balances are synthetic, sized against the '
                  'user\'s premises; none is an observed wallet.'),
        table(['Actor', 'Role', 'USDC', 'NEAR', 'Private motive given to the model'], actors,
              'Source: funded-cast-proposal.json (user-approved). Split-cohort worlds replace borrower_cohort_small with borrower_small_01–08 (7,500 NEAR, $750 each).'),
        chart('bar', 'Supply is about four times what the caps let borrowers take', list(caps), [{'name': 'USD', 'values': [round(v) for v in caps.values()]}],
              'Supply capacity is $1.7M, but borrowing is capped at $500K in aggregate and $300K in First Light.',
              'Opening resources and limits in USD. Borrow capacity is the cast\'s 355,000 NEAR at $4.04 and 50% maximum loan-to-value.',
              'Utilization cannot exceed about 25% on this supply under the selected caps, whatever actors decide.',
              'funded-cast-proposal.json; proposed-settings.json.', unit='USD')))
    mk, it = s['market'], s['interest']
    rules = [['Collateral / debt', 'NEAR / native USDC'], ['Max loan-to-value; liquidation threshold', f'{mk["max_origination_ltv_bps"] / 100:.0f}%; {mk["liquidation_ltv_bps"] / 100:.0f}%'],
             ['Liquidation bonus; close factor', f'{mk["liquidation_bonus_bps"] / 100:.0f}%; {mk["ordinary_close_factor_bps"] / 100:.0f}% (full close at health ≤ 0.95)'],
             ['Caps', f'{usd(mk["initial_per_borrower_principal_cap_usdc"])} per borrower (P50) or $100,000 (P100); {usd(mk["initial_aggregate_principal_cap_usdc"])} aggregate'],
             ['Rate curve R2 (cheap)', f'{it["base_borrow_apr_bps"] / 100:.0f}% base, {it["borrow_apr_at_kink_bps"] / 100:.0f}% at {it["kink_utilization_bps"] / 100:.0f}% utilization, {it["borrow_apr_at_full_utilization_bps"] / 100:.0f}% at full'],
             ['Rate curve R8 (steep)', '8% base, 15% at 50% utilization, 60% at full'],
             ['Protocol share of interest', f'{it["protocol_share_of_collected_interest_bps"] / 100:.0f}%'],
             ['Supplier points', '1 point per borrowed USDC-day, allocated pro rata to unqueued supply; idle supply earns none; no cash value'],
             ['Withdrawals', 'Paid from idle cash, otherwise queued first-in first-out; queued funds stop earning points'],
             ['Losses', '$10K reserve pays suppliers pro rata on recognized bad debt; no top-up'],
             ['Oracle', 'Hourly scaled close; 60-second freshness; stale price blocks borrowing and liquidation'],
             ['Liquidators (assumption)', 'A: $150K cash, $250K/h NEAR exit depth, 0.5% impact; B: $50K, $80K/h, 1%; $25 cost each']]
    doc['sections'].append(section('Rules, schedule and settlement',
        paragraph('A deterministic ledger settles every hour: interest and points accrue, the oracle updates, campaign items due '
                  'that hour are delivered or declined, liquidators act on a fixed profit rule, then actors decide. Aware actors decide '
                  'daily at 12:00 UTC and on rising-edge triggers (NEAR ±8% in 24h, utilization ≥ 90%, a withdrawal queue, own health '
                  '< 1.1, a status update) with a 12-hour cooldown. The team decides weekly and on triggers. Actors choose from menus of '
                  'feasible whole-unit actions; the ledger rejects anything infeasible.'),
        table(['Rule', 'Setting'], rules, 'proposed-settings.json (user-selected baseline); variant-*-settings.json. Values are assumptions, not deployed parameters.'),
        table(['Day', 'Campaign item', 'Channel', 'Cash on delivery'],
              [[f'{i["hour"] / 24:.1f}', i['id'].replace('_', ' '), ', '.join(i['channels']), usd(i['spend']['usdc']) if i.get('spend') else '$0']
               for i in cal['items']],
              'campaign-calendar.json. Partners decide accept / delay three days / decline. Outsiders become aware only when a followed channel delivers.')))
    doc['sections'].append(section('Assumptions and how each could be falsified',
        table(['Assumption', 'Basis', 'Varied in this study?', 'What would falsify it'], [
            ['$1M friendly supply already deposited', 'User choice; partners have no negotiated terms', 'No', 'Term sheets or on-chain deposits'],
            ['Cast balances, motives and channel follows', 'Agent proposal approved by the user', 'Borrower cap and group split only', 'Signed borrower intents, wallet data'],
            ['Awareness without conversion rates', 'User-approved calendar', 'No', 'Campaign analytics and attributable deposits'],
            ['Scaled real NEAR paths', 'Binance hourly klines', 'Choppy vs bear', 'On-chain oracle and DEX data for the same hours'],
            ['Liquidator cash, depth and impact', 'Agent assumption', 'No', 'Measured NEAR/USDC depth during −19% days'],
            ['Rhea rates constant', '2026-11-05 snapshot', 'No', 'Rhea rate history across each window'],
            ['Actor choices from Laya or Jev', 'Uncalibrated actor models', 'Model swapped (Laya vs Jev)', 'Agreement with real user behavior']],
            'Every transfer from a real entity to a simulated actor is an assumption unless stated otherwise.')))
    rows = [[label(x), x['regime'], usd(x['cap']), 'R8 steep' if x['curve'] == 'steep' else 'R2 cheap', x['model'],
             str(x['manifest']['model_calls']['new'] + x['manifest']['model_calls']['cached'])] for x in w.values()]
    doc['sections'].append(section('The six worlds and the comparison design',
        paragraph('Each world has a short name and a code: regime (C = choppy, B = bear), per-borrower cap (P50 = $50K, P100 = $100K), '
                  'rate curve (R2 = 2% base, R8 = 8% base) and actor model (L = Laya, J = Jev). All other inputs are shared.'),
        table(['World', 'Regime', 'Per-borrower cap', 'Rate curve', 'Model', 'Decisions'], rows,
              'Decisions = cached + new model calls per manifest.json; forced waits with one option add no call.'),
        table(['Comparison', 'What changed', 'Confound'], [
            ['First Light → Open Gate', 'Cap $50K → $100K and borrower group split into 8 accounts', 'Two changes at once'],
            ['Open Gate → Dear Money', 'Rate curve only', 'None by design'],
            ['Dear Money → Long Winter', 'Price path only', 'None by design'],
            ['Dear Money → Cold Counter', 'Actor model only (Laya → Jev)', 'None by design'],
            ['Open Gate → Empty Desk', 'Actor model only (Laya → Jev)', 'None by design'],
            ['Empty Desk → Cold Counter', 'Rate curve under Jev', 'None by design']],
            'One world per cell, no repeated seeds: observed differences are single paths, not estimated effects. No no-launch arm was run.')))
    return doc


def case_overview(worlds):
    rows = []
    for x in worlds:
        pday, pval = peak(x, 'borrowed_usdc')
        rows.append([label(x), short(at_day(x, 'supply_usdc', 30)), short(at_day(x, 'borrowed_usdc', 30)), f'{short(pval)} (day {pday})',
                     short(at_day(x, 'borrowed_usdc', 90)), f'{at_day(x, "utilization", 30):.1%}', f'{at_day(x, "borrow_apr", 30):.1%}'])
    return table(['World', 'Supply day 30', 'Borrowed day 30', 'Peak borrowed', 'Borrowed day 90', 'Utilization day 30', 'Borrow APR day 30'], rows,
                 'Day-end values from daily.json. Rhea native USDC on 2026-11-05: 15.29% borrow, 9.88% supply.')


def choppy_case(ctx, base):
    w = ctx['worlds']; names = ['first-light', 'open-gate', 'dear-money', 'cold-counter', 'empty-desk']
    ws = [w[k] for k in names]; fl, og, dm, cc, ed = ws
    m = ctx['paths']['choppy-2025-08']['summary']
    cs = path_stats(ctx['paths']['choppy-2025-08'])
    doc = base('CHOPPY-CASE', 'Choppy Case', 'Five worlds on the real Aug–Nov 2025 NEAR path', ctx)
    doc['highlights'] = [
        f'With Laya actors, borrowing filled whatever cap applied: {short(at_day(fl, "borrowed_usdc", 30))} under $50K per borrower, '
        f'{short(at_day(og, "borrowed_usdc", 30))} under $100K. Utilization stayed at or below {max(x["daily"][d]["utilization"] for x in (fl, og, dm) for d in range(90)):.0%}.',
        f'NEAR fell as far as {cs["close_dd"]:.0%} on hourly closes (day {cs["close_day"]}). Laya worlds had {sum(fl["liq_counts"])} to {sum(dm["liq_counts"])} liquidations, mostly on days 60–85, and no bad debt.',
        f'With Jev actors in the same worlds, borrowers took {cc["borrow"]["chosen"]} and {ed["borrow"]["chosen"]} loans in about 220 chances each, all three paid partners declined, '
        f'and supply fell to {short(at_day(cc, "supply_usdc", 90))} and {short(at_day(ed, "supply_usdc", 90))}.',
        f'Protocol revenue was {usd(fl["protocol_collected"] + fl["protocol_owed"])}–{usd(dm["protocol_collected"] + dm["protocol_owed"])} '
        'against $20K of campaign spending.']
    doc['sections'].append(section('Regime and worlds',
        paragraph(f'This regime replays real hourly NEAR prices from {m["window_start_utc"][:10]}, scaled to open at $4.04. It is not a '
                  f'favorable regime: hourly closes fall as far as {cs["close_dd"]:.1%} (day {cs["close_day"]}) before it ends {cs["end"]:+.1%}, and it has '
                  f'{m["hours_with_24h_move_ge_8pct"]} hours with a 24-hour move of 8% or more. The 2025-10-10 wick to {cs["low_dd"]:.0%} (day {cs["low_day"]}) '
                  'lasted under an hour and is not seen by the hourly oracle. '
                  'The user chose it over the bear, bull and crash-day windows as the single path for the first run. Five of the six worlds use it.'),
        case_overview(ws)))
    doc['sections'].append(section('How borrowing developed',
        chart('line', 'Laya borrowers fill the cap; Jev borrowers never start', DAYS,
              [{'name': label(x), 'values': series(x, 'borrowed_usdc')} for x in ws],
              f'Laya worlds reach their caps by day 30 ({short(at_day(fl, "borrowed_usdc", 30))} and {short(at_day(og, "borrowed_usdc", 30))}); both Jev worlds stay near $0.',
              'Outstanding principal in USD at each day\'s end, five worlds on the same price path. Open Gate and Dear Money differ only in the rate '
              'curve, yet their lines nearly coincide until day 60. Cold Counter and Empty Desk differ from them only in the actor model.',
              'Borrowing in this study is set by the cap or by the actor model, not by price. It is not evidence of real borrower demand.',
              run_src(*ws), unit='USD', x_unit='d'),
        chart('bar', 'Each model has a fixed lean when borrowing is offered', [label(x) for x in ws],
              [{'name': 'Borrow chosen when offered (%)', 'values': [round(100 * x['borrow']['chosen'] / x['borrow']['offered'], 1) for x in ws]}],
              f'When "borrow" was on the menu, Laya chose it in {fl["borrow"]["chosen"]} of {fl["borrow"]["offered"]}, {og["borrow"]["chosen"]} of {og["borrow"]["offered"]} '
              f'and {dm["borrow"]["chosen"]} of {dm["borrow"]["offered"]} cases; Jev in {cc["borrow"]["chosen"]} of {cc["borrow"]["offered"]} and {ed["borrow"]["chosen"]} of {ed["borrow"]["offered"]}.',
              f'Percent of borrower decisions with a borrow option in which borrow was chosen. Jev\'s mean score for borrowing was {ed["borrow"]["mean_score"]:.3f} at the 2% rate '
              f'and {cc["borrow"]["mean_score"]:.3f} at 8%+, nearly identical.',
              'Neither model responds to the borrowing rate. Price elasticity cannot be estimated from these runs.',
              'decisions.json for each world (role = borrower, "borrow" in options).', unit='%')))
    doc['sections'].append(section('Supply and friendly money',
        chart('line', 'Supply grows under Laya and drains under Jev', DAYS,
              [{'name': label(x), 'values': series(x, 'supply_usdc')} for x in ws],
              f'Day-90 supply: {", ".join(short(at_day(x, "supply_usdc", 90)) for x in ws)} (in legend order).',
              'Total supplier principal claims in USD at each day\'s end. Under Laya, independent suppliers add $700K by day 14 and friendly partners mostly '
              f'wait. Under Jev, suppliers alternate supply and withdraw (Cold Counter: {cc["withdraw_requests"]} withdrawal requests).',
              'Whether friendly money stays is unresolved: the two models disagree, and neither is validated.',
              run_src(*ws), unit='USD', x_unit='d'),
        chart('stack', 'Laya actors mostly wait; Jev actors churn', *mix_rows(dm, ['Friendly partners', 'Independent suppliers', 'Borrowers', 'Points looper', 'Team']),
              f'In Dear Money, "wait" is the most common choice for every family except the team, whose {dm["mix"]["Team"].get("status_update", 0)} decisions were all status updates.',
              'Share of each family\'s decisions by choice group, all hours, Dear Money (Laya). Add = supply, post collateral, accept or a team action; Reduce = withdraw, repay or decline.',
              'Team behavior here is a model artifact (one choice every time), not a tested response policy.',
              f'engine/output/{dm["dir"]}/decisions.json.', unit='%')))
    lanes, start, end = gantt(fl)
    doc['sections'].append(section('Timeline and liquidations',
        chart('timeline', 'First Light: launch, amplification, updates and the one liquidation', lanes,
              [{'name': 'start', 'values': start}, {'name': 'end', 'values': end}],
              f'Launch items were delivered by day {max(c["delivered_hour"] for c in fl["campaign"] if c["id"] in ("launch_owned", "amplify_ecosystem", "amplify_defi", "direct_outreach", "kol")) // 24 + 1}; the only liquidation came on day '
              f'{next(d for d in DAYS if fl["liq_counts"][d - 1])}.',
              'Lanes show delivered campaign items (point events drawn as short bars), the span of team status updates and of ±8% NEAR triggers, and liquidation days. Time axis in days.',
              'Awareness spread within a week; after that, nothing the team did changed borrowing, which sat at the cap.',
              f'engine/output/{fl["dir"]}/campaign.json, triggers.json, kernel-report.json.', unit='days', max_value=90),
        paragraph('When liquidations happened. ' + '; '.join(f'{x["name"]}: {liq_days_text(x)}' for x in ws) + '. '
                  f'Day 60 is the 2025-10-10 crash as seen on hourly closes; days 67 and 80–85 are the slide to the path\'s lowest close (day {cs["close_day"]}). '
                  'Every liquidation was profitable for the liquidator and none left bad debt; the $10K reserve was untouched everywhere. '
                  'More debt (Open Gate, Dear Money) meant more liquidations, not losses. Jev worlds had no debt to liquidate.')))
    doc['sections'].append(section('Accounting and economics', accounting_table(ws),
        chart('bar', 'Protocol revenue is a small fraction of campaign spend', [label(x) for x in ws],
              [{'name': 'Protocol share of interest', 'values': [round(x['protocol_collected'] + x['protocol_owed']) for x in ws]},
               {'name': 'Campaign spend', 'values': [round(sum(x['spending'].values())) for x in ws]}],
              f'Best case: {usd(dm["protocol_collected"] + dm["protocol_owed"])} of protocol revenue against $20,000 spent (Dear Money).',
              'USD over 90 days. Protocol share = 15% of borrower interest, collected plus still owed. Jev worlds spent $0 because every paid partner declined.',
              'At these caps and rates the launch does not pay back its campaign within 90 days in any world.',
              'kernel-report.json final_state and receipts for each world.', unit='USD')))
    doc['sections'].append(section('Risks, alternative explanations and implications',
        paragraph('Robust: utilization is bounded by the caps (25% maximum on about $2M of supply), so supplier yield stays far below Rhea\'s '
                  '9.88% under either curve. Matching it at 25% utilization would need about a 46% borrow rate.'),
        paragraph('Not robust: everything about who shows up. The alternative explanation for every behavioral pattern here is the actor model\'s '
                  'built-in lean. Laya borrows when it can and Jev waits, whatever the rate. A cheaper test than more simulation: collect signed borrower '
                  'intents or run a capped pilot, then rerun with the observed demand as an input.'),
        paragraph('Implication: if the launch goes ahead, either raise the aggregate cap or start with less friendly supply. Otherwise suppliers are paid in points alone.')))
    return doc


def bear_case(ctx, base):
    w = ctx['worlds']; lw, dm = w['long-winter'], w['dear-money']
    b = ctx['paths']['bear-2025-11']['summary']; bs = path_stats(ctx['paths']['bear-2025-11'])
    pday, pval = peak(lw, 'borrowed_usdc')
    liq_days = [d for d in DAYS if lw['liq_counts'][d - 1]]
    busiest = max(DAYS, key=lambda d: lw['liq_counts'][d - 1])
    doc = base('BEAR-CASE', 'Bear Case', 'Long Winter: the steep-rate world on the real Nov 2025–Feb 2026 NEAR path', ctx)
    doc['highlights'] = [
        f'NEAR falls {bs["end"]:.0%} over 90 days (hourly closes down {bs["close_dd"]:.0%} at the lowest). {sum(lw["liq_counts"])} liquidations repaid '
        f'{short(sum(lw["liq_repaid"]))}; bad debt was {usd(lw["losses"])} and the $10K reserve was untouched.',
        f'Borrowing peaked at {short(pval)} on day {pday}, below the $500K cap, because falling collateral value kept shrinking what borrowers could take.',
        'One world, one path, Laya actors only: this is a mechanical stress result, not a probability of survival.',
        'The result depends on the assumed liquidator cash and NEAR exit depth.']
    doc['sections'].append(section('Regime definition',
        paragraph(f'Real Binance NEARUSDT hourly prices from {b["window_start_utc"][:10]} to {b["window_end_utc"][:10]}, scaled to open at $4.04. '
                  f'In a scan of 1,000 daily closes this was the worst 90-day window. On the hourly closes the oracle used it ends {bs["end"]:+.1%}, '
                  f'with its lowest close on day {bs["close_day"]} ({bs["close_dd"]:.1%}; intrahour low {bs["low_dd"]:.1%}), and the worst 24 hours is '
                  f'{b["worst_24h_return"]:.1%}. USDC stayed between '
                  f'${b["usdc_min"]} and ${b["usdc_max"]}. The user selected this replay after the first results; Jev was not run on it.'),
        paragraph(f'World: {label(lw)}. Matched comparison: {label(dm)} has identical inputs except the price path, so differences between them come from the path within this single pair.'),
        case_overview([lw, dm])))
    doc['sections'].append(section('How the world progressed',
        chart('multi', 'Long Winter: price, borrowing and supply', DAYS,
              [{'name': 'NEAR (USD)', 'values': series(lw, 'near_usd')}, {'name': 'Borrowed (USD)', 'values': series(lw, 'borrowed_usdc')},
               {'name': 'Supply (USD)', 'values': series(lw, 'supply_usdc')}],
              f'Borrowing rises to {short(pval)} by day {pday}, then falls to {short(at_day(lw, "borrowed_usdc", 90))} as liquidations and repayments follow the price down; '
              f'supply holds near {short(at_day(lw, "supply_usdc", 90))}.',
              'Day-end values, each panel on its own scale starting at zero. Supply barely moves because Laya suppliers mostly wait and no withdrawal had to queue.',
              'Even in a −63% market the binding risk was collateral value, not supplier flight, in this world.',
              run_src(lw), x_unit='d'),
        chart('line', 'The same rules carry less debt on a falling path', DAYS,
              [{'name': label(lw), 'values': series(lw, 'borrowed_usdc')}, {'name': label(dm), 'values': series(dm, 'borrowed_usdc')}],
              f'On day 30, Long Winter has {short(at_day(lw, "borrowed_usdc", 30))} outstanding versus {short(at_day(dm, "borrowed_usdc", 30))} in Dear Money.',
              'Outstanding principal in USD, aligned by day. The pair differs only in the price path.',
              'In a falling market the 50% loan-to-value cap limits exposure on its own; caps matter less.',
              run_src(lw, dm), unit='USD', x_unit='d')))
    lanes, start, end = gantt(lw)
    doc['sections'].append(section('Liquidations and events',
        chart('bar', 'Liquidations cluster on a few sharp days', [f'Day {d}' for d in liq_days],
              [{'name': 'Repaid (USD)', 'values': [round(lw['liq_repaid'][d - 1]) for d in liq_days]}],
              f'{sum(lw["liq_counts"])} liquidations on {len(liq_days)} days; day {busiest} alone had {lw["liq_counts"][busiest - 1]}.',
              'USD of debt repaid by liquidators on each day that had any liquidation. Each was profitable under the assumed 5% bonus and 0.5–1% impact.',
              'Liquidator capacity was not exhausted here; a real test needs measured NEAR depth on those days.',
              f'engine/output/{lw["dir"]}/kernel-report.json (liquidate receipts).', unit='USD'),
        chart('timeline', 'Long Winter event timeline', lanes, [{'name': 'start', 'values': start}, {'name': 'end', 'values': end}],
              f'Campaign items delivered in the first week; ±8% triggers fired across {len([t for t in lw["triggers"] if t["trigger"] == "near_move"])} hours.',
              'Lanes as in the Choppy Case timeline. Time axis in days.',
              'The team\'s only response all run was status updates; no other lever was tested.',
              f'engine/output/{lw["dir"]}/campaign.json, triggers.json.', unit='days', max_value=90),
        chart('stack', 'Borrowers kept borrowing as collateral fell', *mix_rows(lw, ['Friendly partners', 'Independent suppliers', 'Borrowers', 'Points looper', 'Team']),
              f'Borrow was chosen in {lw["borrow"]["chosen"]} of {lw["borrow"]["offered"]} borrower decisions where it was offered.',
              'Share of each family\'s decisions by choice group, all hours.',
              'Laya borrowers re-borrowed after each drop, which raises liquidation counts. Real borrowers might deleverage instead (untested).',
              f'engine/output/{lw["dir"]}/decisions.json.', unit='%')))
    doc['sections'].append(section('Accounting', accounting_table([lw, dm]),
        paragraph(f'The protocol share in Long Winter was {usd(lw["protocol_collected"] + lw["protocol_owed"])}, compared with '
                  f'{usd(dm["protocol_collected"] + dm["protocol_owed"])} in Dear Money: less debt on a falling path means less interest. '
                  f'Liquidators earned {usd(lw["liq_profit"])} in Long Winter and {usd(dm["liq_profit"])} in Dear Money.')))
    doc['sections'].append(section('Risks, alternative explanations and implications',
        paragraph(f'What holds: with 50% / 65% loan-to-value, a 5% bonus and the assumed $200K of liquidator cash, a path whose hourly closes fell {bs["close_dd"]:.0%} produced no bad debt.'),
        paragraph('What could overturn it: thinner real NEAR liquidity, oracle lag beyond one hour, or liquidators withdrawing in a crash. None was measured. '
                  'A Jev run on this path would test whether different borrower behavior (less re-borrowing) changes the liquidation count. It was not run.'),
        paragraph('Implication: the risk settings look adequate for this path; the priority evidence is measured exit depth, not more price paths.')))
    return doc


def bull_case(ctx, base):
    doc = base('BULL-CASE', 'Bull Case', 'Not simulated: the open question and how to run it', ctx)
    doc['highlights'] = ['No bull world was run. The bull replay (from 2026-07-13, NEAR +207% over 90 days, −17% worst drawdown on daily closes) '
                         'was offered and not selected.',
                         'Nothing in this document is a simulated outcome.']
    doc['sections'].append(section('Status',
        paragraph('The user picked the choppy window for the first run, then the bear window as a follow-up. The bull window was offered both times and not '
                  'chosen. This volume records the open question so that no reader mistakes the choppy regime for a favorable one.'),
        table(['Item', 'Status'], [['Bull window', '2026-07-13 start, +207% / −17% on Binance daily closes (screening scan, not a run)'],
                                   ['Worlds run', '0'], ['Model calls', '0'], ['Evidence captured', 'evidence/binance-nearusdt-1d.json']],
              'The +207% figure comes from the daily-close scan used to offer windows; hourly data for it was not fetched.')))
    doc['sections'].append(section('What a bull run would test, and what the rules already imply',
        paragraph('Rule-based expectation, not observed: rising NEAR raises each borrower\'s collateral value, so borrow capacity grows, but the $500K aggregate '
                  'cap still binds. Utilization would therefore stay at or below about 25% on $2M of supply, and supplier yield below Rhea\'s, under either curve. '
                  'The bull path would test what the choppy runs cannot: whether rising prices draw more supply (diluting points further) and whether '
                  'borrowers repay early.'),
        paragraph('How to run it at no inference cost: fetch the hourly window into price-path-bull-2026-07.json as was done for the other paths, then run '
                  'engine/.venv/bin/python tools/run_near_lending_case.py --settings variant-cap100k-steep-settings.json --cast variant-split-cohort-cast.json '
                  '--calendar variant-split-cohort-calendar.json --path price-path-bull-2026-07.json --out engine/output/<new-dir>. '
                  'About 13 minutes on local Laya.')))
    return doc
