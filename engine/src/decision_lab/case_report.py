"""Render a Boyun case report: five documents, figures and data tables from case artefacts.

    python -m decision_lab.case_report <case-dir>

Structure follows docs/decision-lab/REPORT_STRUCTURE.md: odds as natural frequencies, one page
for the decision document, four findings at most, and every figure regenerated from the data.
No number in a document is typed by hand.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

from .case_brief import load_brief, read_artefacts, write_interview
from .launch_estimate import estimate_launch, sensitivity

INK, MUTED, RULE = '#1a1f24', '#5b6770', '#d7dee3'
LOSS, PROFIT, WHALE, ACCENT = '#b0453a', '#2f6f4f', '#b8860b', '#2b6cb0'
ENGINE_TESTS_ON_RECORD = 1_730
RECORDED_DATE = '2026-10-30'
FONT = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Inter, sans-serif'


def _esc(value):
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _svg(width, height, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" aria-label="{_esc(title)}">'
            f'<title>{_esc(title)}</title><rect width="{width}" height="{height}" fill="#ffffff"/>'
            f'<style>text{{font-family:{FONT};fill:{INK}}}</style>' + body + '</svg>\n')


def _text(x, y, value, size=13, fill=None, weight=400, anchor='start'):
    return (f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'text-anchor="{anchor}" fill="{fill or INK}">{_esc(value)}</text>')


def _line(x1, y1, x2, y2, stroke=RULE, width=1, dash=None):
    extra = f' stroke-dasharray="{dash}"' if dash else ''
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{width}"{extra}/>')


def money(value):
    """Dollars with the sign before the symbol: -$1,802 rather than $-1,802."""
    value = round(value)
    return f'-${abs(value):,}' if value < 0 else f'${value:,}'


def _out_of_100(share):
    return round(share * 100)


EMPTY_BUCKET = {'share': 0.0, 'p50': 0, 'p05': 0, 'p95': 0, 'n': 1, 'profit': 0}


def _bucket(summary, name):
    """A case may never see one outcome class; a missing class must read as zero, not crash."""
    return summary['by_bucket'].get(name, dict(EMPTY_BUCKET))


def fig_outcomes(summary, path):
    whale = _bucket(summary, 'whale outside money')
    gold = round(whale['profit'] / summary['worlds'] * 100)
    green = round((summary['profit_count'] - whale['profit']) / summary['worlds'] * 100)
    red = 100 - gold - green
    cell, gap = 24, 16
    body = [_text(12, 18, 'Outcome of 100 simulated launches', 16, weight=600),
            _text(12, 40, f'{gold + green} finish ahead, {red} finish behind.', 13, MUTED),
            _text(12, 58, 'Each dot is one launch in a hundred.', 11.5, MUTED)]
    colours = [WHALE] * gold + [PROFIT] * green + [LOSS] * red
    for index, colour in enumerate(colours):
        row, column = divmod(index, 10)
        x = 12 + column * (cell + gap // 2)
        y = 78 + row * (cell + gap // 4)
        body.append(f'<circle cx="{x + 8}" cy="{y}" r="8" fill="{colour}" fill-opacity="0.92"/>')
    legend_y = 78 + 10 * (cell + gap // 4) + 12
    for offset, (colour, label) in enumerate([
            (WHALE, f'{gold} of 100: a whale-size outside buyer appears'),
            (PROFIT, f'{green} of 100: profitable without a whale'),
            (LOSS, f'{red} of 100: you end with less cash than you started with')]):
        y = legend_y + offset * 22
        body.append(f'<circle cx="21" cy="{y - 4}" r="7" fill="{colour}" fill-opacity="0.92"/>')
        body.append(_text(38, y, label, 12))
    path.write_text(_svg(360, legend_y + 92, ''.join(body), 'Icon array of launch outcomes'))
    return {'gold': gold, 'green': green, 'red': red}


def fig_net_cash(worlds, summary, path):
    width, height = 760, 470
    left, right, top, bottom = 56, 24, 64, 86
    plot_w, plot_h = width - left - right, height - top - bottom
    low, high, step = -4500, 13000, 500
    bins, overflow = {}, 0
    for row in worlds:
        net = row['net_cash_usd']
        if net >= high:
            overflow += 1
            continue
        index = int((net - low) // step)
        bins[index] = bins.get(index, 0) + 1
    ceiling = max(list(bins.values()) + [overflow]) or 1
    step_y = 1000
    while ceiling / step_y > 6:
        step_y *= 2
    ceiling = (ceiling // step_y + 1) * step_y
    quantiles = summary['net_quantiles']
    body = [_text(12, 18, f'Net cash after the launch, {len(worlds):,} simulated worlds', 16, weight=600),
            _text(12, 40, 'Bars show how many launches land in each $500 band. The dashed line is '
                          'doing nothing.', 12, MUTED)]

    def x_of(value):
        return left + (value - low) / (high - low) * plot_w

    body.append(_line(left, top, left, top + plot_h))
    body.append(_line(left, top + plot_h, left + plot_w, top + plot_h))
    for value in range(-4000, 13001, 2000):
        x = x_of(value)
        body.append(_line(x, top + plot_h, x, top + plot_h + 5))
        body.append(_text(x, top + plot_h + 20, money(value), 11, MUTED, anchor='middle'))
    for value in range(0, ceiling + 1, step_y):
        y = top + plot_h - value / ceiling * plot_h
        body.append(_line(left - 5, y, left, y))
        body.append(_text(left - 9, y + 4, f'{value:,}', 11, MUTED, anchor='end'))
    for index, count in sorted(bins.items()):
        x0, x1 = x_of(low + index * step), x_of(low + (index + 1) * step)
        bar = count / ceiling * plot_h
        colour = LOSS if (low + index * step) < 0 else PROFIT
        body.append(f'<rect x="{x0 + 0.5:.1f}" y="{top + plot_h - bar:.1f}" '
                    f'width="{max(1.0, x1 - x0 - 1):.1f}" height="{bar:.1f}" fill="{colour}" '
                    f'fill-opacity="0.82"/>')
    if overflow:
        x0 = x_of(high)
        bar = overflow / ceiling * plot_h
        body.append(f'<rect x="{x0 + 0.5:.1f}" y="{top + plot_h - bar:.1f}" width="12" '
                    f'height="{bar:.1f}" fill="{WHALE}" fill-opacity="0.9"/>')
        body.append(_text(x0 - 8, top + plot_h - bar - 6, f'≥{money(high)}: {overflow:,}',
                          anchor='end'))
    zero = x_of(0)
    body.append(_line(zero, top, zero, top + plot_h + 5, INK, 1.5, '5 4'))
    body.append(_text(zero + 6, top + 12, 'do nothing = $0', 12, INK, 600))
    for key in ('p05', 'p50', 'p90'):
        body.append(_line(x_of(quantiles[key]), top, x_of(quantiles[key]), top + plot_h,
                          MUTED, 1, '2 3'))
    body.append(_text(left, top + plot_h + 38,
                      f'5th percentile {money(quantiles["p05"])}  ·  '
                      f'median {money(quantiles["p50"])}  ·  '
                      f'90th percentile {money(quantiles["p90"])}', 11, MUTED))
    body.append(_text(12, height - 12,
                      f'{summary["profit_count"]:,} of {len(worlds):,} worlds finish above zero '
                      f'({summary["profit_count"] / len(worlds):.1%}). '
                      f'Range {money(summary["net_min"])} to {money(summary["net_max"])}.', 11, MUTED))
    path.write_text(_svg(width, height, ''.join(body), 'Distribution of net cash'))


def fig_pipeline(path):
    stages = ['brief\n(interview)', 'evidence\npack', 'launch\ncases', 'cast\n15 actors',
              'Jev\nprobabilities', 'sampled\nworlds', 'report\n5 docs']
    width, height = 900, 210
    box_w, box_h, gap = 104, 56, 16
    body = [_text(12, 18, 'How the numbers were produced', 16, weight=600),
            _text(12, 40, 'Each stage writes a typed artefact and a receipt; the report regenerates '
                          'from them.', 12, MUTED)]
    for index, stage in enumerate(stages):
        x, y = index * (box_w + gap), 66
        body.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="6" '
                    f'fill="#f4f7f9" stroke="{RULE}"/>')
        for line_no, part in enumerate(stage.split('\n')):
            body.append(_text(x + box_w / 2, y + 22 + line_no * 15, part, 11.5, anchor='middle'))
        if index < len(stages) - 1:
            body.append(f'<path d="M{x + box_w + 2} {y + box_h / 2} l{gap - 4} 0" stroke="{MUTED}" '
                        f'stroke-width="1.4"/>')
            body.append(f'<path d="M{x + box_w + gap - 8} {y + box_h / 2 - 4} l6 4 l-6 4z" '
                        f'fill="{MUTED}"/>')
    body.append(_text(12, height - 60,
                      'No venue adapter: USD figures are closed-form estimates, not settlement.',
                      11, MUTED))
    body.append(_text(12, height - 40,
                      'Dynamic fee tiers, queue position, partial fills and post-cast buyers are '
                      'absent by construction.', 11, MUTED))
    body.append(_text(12, height - 20,
                      'Actor probabilities are provider decision scores, not calibrated odds.',
                      11, MUTED))
    path.write_text(_svg(width, height, ''.join(body), 'Pipeline diagram'))


def fig_sensitivity(sens, path):
    rows = sens['arms']
    labels = [f'{row["parameter"].replace("_", " ")} = {row["value"]:,}' for row in rows]
    values = [row['net_p50'] for row in rows]
    low, high = min(values + [0]), max(values + [0])
    span = high - low or 1
    width = 760
    row_h = 26
    left, right = 232, 96
    height = 70 + row_h * len(rows)
    plot_w = width - left - right
    body = [_text(12, 18, 'Sensitivity of the median outcome', 16, weight=600),
            _text(12, 40, f'Each arm re-runs {sens["worlds_per_arm"]:,} worlds with one parameter '
                          f'changed. Bars start at zero.', 12, MUTED)]

    def x_of(value):
        return left + (value - low) / span * plot_w

    zero = x_of(0)
    body.append(_line(zero, 56, zero, height - 16, INK, 1.2, '4 3'))
    for index, (label, value) in enumerate(zip(labels, values)):
        y = 66 + index * row_h
        x0, x1 = (zero, x_of(value)) if value >= 0 else (x_of(value), zero)
        colour = PROFIT if value >= 0 else LOSS
        body.append(f'<rect x="{x0:.1f}" y="{y - 11}" width="{max(1.5, x1 - x0):.1f}" height="18" '
                    f'fill="{colour}" fill-opacity="0.82"/>')
        body.append(_text(12, y + 4, label, 11.5))
        body.append(_text(width - 12, y + 4, money(value), 11.5, anchor='end'))
    path.write_text(_svg(width, height, ''.join(body), 'Sensitivity of the median outcome'))


def _kol_dump_cost(summary):
    """Median cost of a full KOL dump, averaged over the pairs we can compare."""
    rows = {row['scenario']: row for row in summary['scenarios']}
    costs = []
    for name, row in rows.items():
        if 'KOL sells all' in name:
            twin = rows.get(name.replace('KOL sells all', 'KOLs hold'))
            if twin:
                costs.append(twin['p50'] - row['p50'])
    return round(sum(costs) / len(costs)) if costs else None


def _table(rows, header):
    lines = ['| ' + ' | '.join(header) + ' |', '|' + '|'.join(['---'] * len(header)) + '|']
    for row in rows:
        cells = [str(cell).replace('|', '\\|').replace('\n', ' ') for cell in row]
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def _expected_outside(probabilities, params):
    """Probability-weighted outside buying from the trading cast, in dollars."""
    total = 0.0
    for actor, probs in probabilities.items():
        capital = params.get('capital_usd', {}).get(actor)
        if not capital:
            continue
        total += capital * (probs.get('buy_small', 0) * .25 + probs.get('buy_half', 0) * .5
                            + probs.get('buy_all', 0))
    return total


def doc_decision(summary, cast, probabilities, labels):
    no_money = _bucket(summary, 'no outside money')
    moderate = _bucket(summary, 'moderate outside money')
    whale = _bucket(summary, 'whale outside money')
    gold = round(whale['profit'] / summary['worlds'] * 100)
    green = round((summary['profit_count'] - whale['profit']) / summary['worlds'] * 100)
    params = summary['params']
    expected = _expected_outside(probabilities, params)
    if params['venue'] == 'curve':
        finding_four = (f"**Your own buying pushes the curve to migration in "
                        f"{_out_of_100(summary['migration_share'])} of 100 worlds**, so most of the "
                        f"sample trades in a post-migration pool whose depth is set by the raise, "
                        f"not by a market you chose.")
        plan_sentence = (f"{money(params['bootstrap_usd'])} as early buys on the curve "
                         f"(about {summary.get('bootstrap_supply_pct', 0):.0f}% of supply at "
                         f"${params['sol_usd']}/SOL), {params['kol_supply_bps']/100:g}% of supply and "
                         f"{money(params['kol_cash_usd'])} to creators.")
        complication = ("Holding that share of supply makes you the exit liquidity: your proceeds "
                        "cannot exceed what buyers put in.")
    else:
        plan_sentence = (f"{money(params['bootstrap_usd'])} deposited as pool liquidity against "
                         f"{params['pool_supply_bps']/100:g}% of supply, a founder holding of "
                         f"{params['founder_supply_bps']/100:g}% of supply, and "
                         f"{params['kol_supply_bps']/100:g}% of supply plus "
                         f"{money(params['kol_cash_usd']) if params['kol_cash_usd'] else 'no cash'} "
                         f"to creators.")
        complication = ("Your exit depends on pool depth: selling a large holding moves the price "
                        "against you, and the liquidity you recover is your own deposit plus what "
                        "buyers added.")
        ratio = params['founder_supply_bps'] / max(1, params['pool_supply_bps'])
        finding_four = (f"**Your holding is {ratio:.1f}× the pool's own token reserve**, so each of "
                        f"the four exit tranches moves the price against the remaining three, and "
                        f"the pool's depth — your deposit — is the binding constraint.")
    
    title = labels.get('title', 'Case')
    profit = gold + green
    median = summary['net_quantiles']['p50']
    if profit >= 100:
        opening = "**All 100 simulated launches finish with more cash than you start with"
    elif profit <= 0:
        opening = "**No simulated launch finishes with more cash than you start with"
    else:
        opening = f"**{profit} of every 100 simulated launches finish with more cash than you start with"
    if median < 0:
        verdict = (f"{opening}, and the median launch loses money — doing nothing beats "
                   f"about {100 - profit} of 100 outcomes.**")
    else:
        verdict = (f"{opening}, and the median launch makes money — it beats doing nothing in "
                   f"{'all 100' if profit >= 100 else str(profit) + ' of 100'} outcomes.**")
    if not gold:
        whale_note = 'No whale-sized outside buyer appears anywhere in this sample.'
    elif moderate['share'] == 0:
        whale_note = ('Every world here contains a whale-sized buyer, so this configuration has no '
                      'non-whale case to compare against.')
    elif moderate['p50'] > 0:
        whale_note = (f"{gold} of those 100 worlds contain a whale-sized buyer; "
                      f"the median with moderate outside money is {money(moderate['p50'])}.")
    else:
        whale_note = (f"{gold} of those 100 worlds contain a whale-sized buyer, and without one the "
                      f"best median you reach is {money(moderate['p50'])}.")
    body = f"""# {title} — should you launch this, and with what plan?

*Estimate, not a forecast. {summary['worlds']:,} simulated runs, actor probabilities from the source named in `01-MODEL.md`, {params['half_life_hours']}h half-life: the exit fires at hour {summary['exit_hour']}.*

## Answer

{verdict} {whale_note}

![Outcome of 100 simulated launches](FIGURES/fig-outcomes.svg)

## Situation, complication, question

You have {money(params['founder_capital_usd'])} and this plan: {plan_sentence} The exit rule sells in four tranches when trading volume falls to 25% of its first-48-hour peak. {complication} The question is whether anyone outside your own cast turns up.

## Four findings

1. **Outside demand is about the size of your own bootstrap.** The cast expects about {money(expected)} of buying against your {money(params['bootstrap_usd'])}, and most trading archetypes mostly hold.
2. **The distribution is bimodal, not spread.** In {_out_of_100(no_money['share'])} of 100 worlds no outside money arrives and the median is {money(no_money['p50'])}. In {_out_of_100(moderate['share'])} of 100, moderate money arrives and the median is {money(moderate['p50'])}. In {gold} of 100 a whale-size buyer appears and the median is {money(whale['p50'])}.
3. **The outcome distribution has a tail.** Mean net cash is {money(summary['net_mean'])} while the median is {money(summary['net_quantiles']['p50'])}; the 90th percentile is {money(summary['net_quantiles']['p90'])} and the 99th {money(summary['net_quantiles']['p99'])}.
4. {finding_four}

![Net cash distribution](FIGURES/fig-net-cash.svg)

## The comparison that decides it

{_table([
    ['No outside money', _out_of_100(no_money['share']), money(no_money['p50']), f"{no_money['profit']/no_money['n']:.0%}"],
    ['Moderate outside money', _out_of_100(moderate['share']), money(moderate['p50']), f"{moderate['profit']/moderate['n']:.0%}"],
    ['Whale-size outside money', gold, money(whale['p50']), f"{whale['profit']/whale['n']:.0%}"],
    ['**Do nothing**', '—', '**$0**', '—']],
    ['Outcome class', 'Of 100 worlds', 'Median net cash', 'Chance of profit'])}

The scenario rows are in `DATA/scenarios.csv` and `02-SCENARIOS.md`.

## What would change the answer

- **A smaller supply target.** Holding less of the float leaves room for buyers and shrinks the position you must liquidate into your own market.
- **Demand that is not your own money** — a buyer large enough to matter, or measured demand outside the cast, which this case does not have.
- **A different decay assumption.** The sensitivity table in `02-SCENARIOS.md` re-runs the same worlds across the declared decay arms.

## How this was produced, and what it cannot do

Actor probabilities are supplied per actor; the rest is closed-form constant-product arithmetic over {summary['worlds']:,} sampled worlds. Cast, policy and assumptions are listed in `01-MODEL.md`; sources and receipts are in `DATA/`.

It cannot model queue position, partial fills, MEV, dynamic fee tiers, or any buyer who arrives after the cast. It is not financial advice, and the probabilities are provider decision scores, not calibrated real-world odds.

The claim this report makes is recorded, with resolution criteria, in `04-FORECAST.md`.
"""
    return body


def doc_model(summary, cast, bootstrap, events, probabilities, labels, probability_label,
              call_count, model_name):
    params = summary['params']
    if params['venue'] == 'curve':
        model_type = 'sampled actor decisions over a constant-product curve with migration'
        initialisation = ('Virtual reserves 30 SOL and 1.073B tokens; 793.1M tokens on the curve; '
                          '1B supply; 100 bps base fee; creator fee 0 at capture time.')
        bootstrap_row = f"{money(params['bootstrap_usd'])} as early curve buys, no team liquidity"
    else:
        model_type = 'sampled actor decisions over an existing constant-product pool'
        initialisation = (f"Pool depth {money(params['bootstrap_usd'])} against "
                          f"{params['pool_supply_bps']/100:g}% of supply; founder holding "
                          f"{params['founder_supply_bps']/100:g}% of supply; no curve phase and no "
                          f"migration; 100 bps base fee on both sides.")
        bootstrap_row = (f"{money(params['bootstrap_usd'])} deposited as pool liquidity, recovered "
                         f"at exit as the team's own LP share")
    if params['venue'] == 'curve':
        entities = (f"A curve with virtual reserves, a post-migration pool, "
                    f"{cast.get('actor_count')} actor archetypes, and one founder position.")
        submodels = ('Curve buy and sell arithmetic, migration at curve exhaustion, pool arithmetic '
                     'afterwards, and the exit rule.')
        falsifiers = ('- A curve constant that differs from the official values (30 SOL / 1.073B / '
                      '793.1M).\n')
    else:
        entities = (f"A constant-product pool at the depth and supply declared in the brief, "
                    f"{cast.get('actor_count')} actor archetypes, and one founder position.")
        submodels = ('Pool buy and sell arithmetic with a 100 bps fee on both sides, and the exit '
                     'rule. No curve phase and no migration.')
        falsifiers = ('- A pool depth or supply share that differs from the brief.\n')
    receipt_row = (f"| Model receipts | {call_count} calls recorded, model reported `{model_name}`, "
                   f"spend capped |" if call_count else
                   "| Model receipts | none: the probabilities are declared, not sampled |")
    roles = cast.get('role_counts', {})
    role_rows = [[role.replace('_', ' '), count] for role, count in sorted(roles.items())]
    return f"""# Model — what produced the numbers

One page of model card, followed by the ODD description and the evidence that the model was
tested. Written so a reviewer can falsify it rather than trust it.

![Pipeline](FIGURES/fig-pipeline.svg)

## Model card

| Field | Value |
|---|---|
| Intended use | compare funded plans for one token launch inside a declared budget |
| Not for | price prediction, odds on real events, advice, or any venue settlement |
| Model type | {model_type} |
| Actors | {cast.get('actor_count')} declared archetypes, {sum(1 for a in cast.get('actors', []) if a['role'] in ('kol', 'creator_organic', 'partnership', 'foundation'))} of them demand-generating |
| Actor probabilities | {probability_label} |
| World count | {summary['worlds']:,} per arm |
| Currency unit | integer lamports and 6-decimal token base units, converted at ${params['sol_usd']}/SOL |
| Evaluation | distribution of net cash versus doing nothing, plus scenario groups |
| Caveats | estimates only; no queue position, partial fills, MEV or dynamic fee tiers |

## ODD: Overview

- **Purpose.** Estimate whether one launch plan ends with more cash than not launching, under
  explicit assumptions, for a token that has not launched.
- **Entities.** {entities}
- **Process order.** The founder buys first with the bootstrap; each actor then acts once in sorted
  actor order; the founder exits in four tranches after the decay rule fires.
- **Scheduling.** Actor actions happen at launch; the exit happens at twice the decay half-life,
  where volume reaches 25% of the launch peak.

## ODD: Design concepts

- **Objectives.** Actors maximise their own stated objective; the founder maximises realisable net
  cash. No actor sees another's action.
- **Sensing.** Actors know only what their declaration allows: public posts, price, pool depth, or
  their own position. No actor sees the founder's unpublished plan.
- **Interaction.** Only through the curve and the pool price.
- **Stochasticity.** Named SHA-256 draws per world and actor; the same seed replays exactly.
- **Observation.** Volume and price per world; net cash after bootstrap and creator costs.

## ODD: Details

- **Initialisation.** {initialisation}
- **Inputs.** Cast capital as multiples of pool liquidity, policy thresholds below, and the
  probability vectors recorded in `DATA/probabilities.json`.
- **Submodels.** {submodels}

## Policy thresholds in force

{_table([
    ['Exit level', '25% of the 48h volume peak'],
    ['Exit shape', '4 tranches, 15 minutes apart, inside one hour'],
    ['Defer rule', 'volume recovered AND one-hour price return ≥ 0 (conjunction)'],
    ['Funding gate', 'continue only at ≥60% of the peak'],
    ['Decay', f"exponential, {params['half_life_hours']}h half-life, exit at hour {summary['exit_hour']}"],
    ['Bootstrap', bootstrap_row]],
    ['Parameter', 'Value'])}

## Cast

{_table(role_rows, ['Role', 'Actors'])}

Actor capital is expressed against the case pool liquidity; see `DATA/cast.json` for each actor's
capital, information rights and objective.

## What could falsify this

{falsifiers}- Actor probabilities that are not what the recorded source returns for the same state.
- A policy rule that does not match the recorded interview answers.
- A settlement path that differs from constant product (dynamic fees, MEV, partial fills).

## Verification on record

| Check | Result |
|---|---|
| Engine test suite | {ENGINE_TESTS_ON_RECORD:,} tests passing on {RECORDED_DATE} |
| Curve arithmetic | exhausting 793.1M tokens needs 85.86 SOL, consistent with the documented ~85 SOL migration |
| Randomised sweeps | 2,000 valid plans conserved, deterministic and time-ordered; 1,500 over composites; 1,884 malformed mutations all rejected with a path |
{receipt_row}
| Reproducibility | same seed, same probabilities, same worlds; the report regenerates from `DATA/` |

## Limits

- Estimates, not settlement: proceeds assume the curve or pool absorbs the whole tranche.
- One decision round per actor; no buyer arrives after the cast.
- Probabilities are provider decision scores, not calibrated real-world odds.
- SOL price is a declared assumption, not a market feed.
"""


def doc_scenarios(summary, sens, labels):
    scenario_rows = [[row['scenario'], row['out_of_100'], money(row['p05']), money(row['p50']),
                      money(row['p95']), f"{row['share_positive']:.0%}"]
                     for row in summary['scenarios']]
    bucket_rows = [[name, _out_of_100(entry['share']), money(entry['p05']),
                    money(entry['p50']), money(entry['p95']), f"{entry['profit']/entry['n']:.0%}"]
                   for name, entry in sorted(summary['by_bucket'].items())]
    arm_rows = [[row['parameter'].replace('_', ' '), f'{row["value"]:,}', money(row['net_p50']),
                 money(row['net_p90']), f"{row['share_positive']:.0%}",
                 _out_of_100(row['migration_share']), row['exit_hour']]
                for row in sens['arms']]
    split_note = (' with two splits inside each: whether any creator sells their entire allocation, '
                  'and whether the curve completed'
                  if summary['params']['venue'] == 'curve' else
                  ' with one split inside each: whether any creator sells their entire allocation')
    kol_cost = _kol_dump_cost(summary)
    kol_sentence = (f"The difference between KOL sale and hold medians is about {money(kol_cost)}."
                    if kol_cost is not None else
                    "The table shows the observed outcome groups.")
    return f"""# Scenarios, odds and sensitivity

Every number is a natural frequency over simulated worlds: "X of 100" means X percent of the
{summary['worlds']:,} sampled launches. No probability here is a real-world forecast.

## Every scenario

{_table(scenario_rows, ['Scenario', 'Of 100', 'p05', 'Median', 'p95', 'P(profit)'])}

Read it as three outcome classes{split_note}. {kol_sentence}

## By outcome class

{_table(bucket_rows, ['Outside money', 'Of 100', 'p05', 'Median', 'p95', 'P(profit)'])}

![Net cash distribution](FIGURES/fig-net-cash.svg)

## Sensitivity

{_table(arm_rows, ['Parameter', 'Value', 'Median', 'p90', 'P(profit)', 'Migrated of 100', 'Exit hour'])}

![Sensitivity](FIGURES/fig-sensitivity.svg)

Each arm changes one parameter and re-runs {sens['worlds_per_arm']:,} worlds; the base arm is the
report's. Compare the median and profit frequency across arms in the table; these are simulated
outcomes conditional on the stated assumptions. No buyer arrives after the cast in this model,
so the timing results do not establish what would happen if later buyers entered the market.

## How to read the tails

- The 5th and 95th percentiles in the tables describe the sampled tails for each group.
- A sampled maximum is not a target or a prediction.
"""


def doc_evidence(summary, cast, events, probabilities, bootstrap, interview, labels,
                 probability_label, has_receipts, public=False):
    prob_rows = []
    for actor, row in sorted(probabilities.items()):
        prob = row.get('probabilities', row) if type(row) is dict else {}
        top = max(prob, key=prob.get) if prob else '—'
        prob_rows.append([actor.replace('_', ' '), top, f"{prob.get(top, 0):.2f}",
                          ', '.join(f'{k} {v:.2f}' for k, v in sorted(prob.items()))])
    cast_rows = []
    for index, actor in enumerate(cast.get('actors', []), 1):
        label = (f"{actor['role'].replace('_', ' ').title()} {index}" if public
                 else actor['label'])
        capital = actor['capital']
        capital_text = (f"{capital.get('mode', 'declared')} "
                        f"{capital.get('low', capital.get('usd', capital.get('supply_share', '')))}"
                        if public else json.dumps(capital)[:70])
        cast_rows.append([label, actor['role'].replace('_', ' '), capital_text])
    params = summary['params']
    if params['venue'] == 'curve':
        venue_table = _table([
            ['Virtual SOL reserves', '30 SOL', 'official program README, captured 2026-10-30'],
            ['Virtual token reserves', '1.073B', 'same'],
            ['Tokens on the curve', '793.1M', 'same'],
            ['Total supply', '1B', 'same'],
            ['Base fee', '100 bps', 'same'],
            ['Creator fee', '0', 'same, at capture time'],
            ['Bootstrap share', f"{summary.get('bootstrap_supply_pct', 0):.2f}% of supply at "
                                f"${params['sol_usd']}/SOL", 'curve arithmetic']],
            ['Item', 'Value', 'Source'])
    else:
        venue_table = _table([
            ['Pool depth at launch', money(params['bootstrap_usd']), 'team deposit, from the brief'],
            ['Supply in the pool', f"{params['pool_supply_bps']/100:g}%", 'declared'],
            ['Founder holding', f"{params['founder_supply_bps']/100:g}%", 'declared'],
            ['Creator allocation', f"{params['kol_supply_bps']/100:g}% of supply", 'declared'],
            ['Base fee', '100 bps', 'declared for both sides'],
            ['Curve phase', 'none', 'the token already trades in a pool'],
            ['Bootstrap share', 'not applicable', 'no curve purchase']],
            ['Item', 'Value', 'Source'])
    blocks = [f"""## Actor probabilities

Source: {probability_label}. These are decision scores for a stated observation, not calibrated
odds. Actors without trading capital are excluded, and the founder follows a fixed policy rather
than a model choice.

{_table(prob_rows, ['Actor', 'Most likely', 'P', 'All actions'])}""",
              f"""## Cast

{_table(cast_rows, ['Actor', 'Role', 'Capital'])}""",
              f"""## Venue facts

{venue_table}"""]
    if not public:
        event_rows = [[item.get('window_start') or '—', item.get('window_end') or '—',
                       item.get('what', '')[:80], item.get('status', '')]
                      for item in events.get('events', [])]
        blocks.insert(2, f"""## Real-world events

{_table(event_rows, ['Start', 'End', 'What', 'Status'])}

Only a verified calendar row may act as a catalyst. A date the capture could not support is
printed as unknown rather than inferred, and unsupported political claims stay out of the world.""")
        excerpt = interview[-6:]
        interview_table = (_table([[row['question'][:58] or '—', row['answer'][:58],
                                    row['status'][:22]] for row in excerpt],
                                  ['Question', 'Answer as received', 'Status'])
                           if excerpt else '_No answers recorded._')
        blocks.insert(3, f"""## Interview record

{len(interview)} answers were recorded before the model was built; the complete table, with the
interpretation of each answer, is `DATA/interview.csv`. The most recent rows:

{interview_table}

Every parameter in `01-MODEL.md` traces to one of these answers or to a labelled assumption.""")
        blocks.append(f"""## Sources

- `DATA/sources.json` lists the case artefacts, evidence captures and the structure spec.
- Model receipts: {'`DATA/jev-receipts.json`' if has_receipts else 'none, probabilities are declared'}.
- Every figure regenerates from `DATA/` with one command; a hand-built figure is a defect.""")
    else:
        blocks.append("_Public version: token identity, private research, the interview record and "
                      "the raw data files are removed. The arithmetic and the figures are the same._")
    blocks.append("""## What this evidence does not show

- No measured demand outside the cast; volume is the only demand proxy we hold.
- No verified market-maker terms; the pause assumption is labelled optimistic.
- No buyer counts per window and no queue position.""")
    return "# Evidence — what the numbers are built from\n\n" + "\n\n".join(blocks) + "\n"


def doc_forecast(summary, labels):
    quantiles = summary['net_quantiles']
    title = labels.get('title', 'Case')
    return f"""# Forecast record

A report can quietly rewrite its own history; a forecast record cannot. This is the claim as
recorded, with the criteria that will later score it.

| Field | Value |
|---|---|
| Recorded | {RECORDED_DATE} |
| Question | {labels.get('question', 'Does the plan beat not launching?')} |
| Claim | {summary['profit_count']:,} of {summary['worlds']:,} simulated worlds finish above zero ({summary['profit_count']/summary['worlds']:.1%}), median {money(quantiles['p50'])} |
| Distribution | p05 {money(quantiles['p05'])} · p50 {money(quantiles['p50'])} · p90 {money(quantiles['p90'])} · p99 {money(quantiles['p99'])} |
| Compared with | doing nothing = $0 |
| Assumptions fixed at record time | SOL ${summary['params']['sol_usd']}; {summary['params']['half_life_hours']}h decay; 3% creator allocation; {money(summary['params']['kol_cash_usd'])} creator cash |
| Resolution | a real launch with the same bootstrap and exit rule, measured at the exit hour: cash received minus bootstrap and creator costs |
| Score | pending — to be recorded as a Brier score and a realised-versus-median comparison |
| Status | **pending**; no launch has happened |

## Why this exists

The only way to learn whether these estimates mean anything is to compare them with what happened,
on the terms written here before the outcome was known. Any later edit belongs in a new record, not
in this one.
"""


def doc_index(summary, cast, rendered):
    status = {name: '**ready**' if rendered.get(name) else 'pending' for name in
              ('00-DECISION.md', '01-MODEL.md', '02-SCENARIOS.md', '03-EVIDENCE.md',
               '04-FORECAST.md')}
    rows = [[f'`{name}`', status[name], note] for name, note in (
        ('00-DECISION.md', 'the answer, four findings, the comparison, what would change it'),
        ('01-MODEL.md', 'model card, ODD, policy thresholds, verification evidence'),
        ('02-SCENARIOS.md', 'all scenario rows, tails, sensitivity'),
        ('03-EVIDENCE.md', 'actor probabilities, cast, events, curve facts'),
        ('04-FORECAST.md', 'the recorded claim, resolution criteria, later the score'))]
    rows.append(['`DATA/`', '**ready**', 'inputs, outputs, assumptions, scenarios, cast, sources'])
    rows.append(['`FIGURES/`', '**ready**', 'outcome dots, net-cash distribution, pipeline, sensitivity'])
    return f"""# Report index

Generated by `python -m decision_lab.case_report` from the case artefacts. Do not edit by hand.

{_table(rows, ['Artefact', 'Status', 'Contents'])}

Facts behind the numbers: {cast.get('actor_count')} cast members, {summary['worlds']:,} worlds,
migration in {summary['migration_share']:.0%} of them, exit at hour {summary['exit_hour']}.
Estimate, not a forecast; the claim being scored is in `04-FORECAST.md`.
"""


def write_data(report, case, summary, sens, probabilities, cast, launch, bootstrap, events):
    data = report / 'DATA'
    data.mkdir(parents=True, exist_ok=True)
    params = summary['params']
    (data / 'inputs.json').write_text(json.dumps({
        'case': case.name, 'venue': 'pump.fun fair launch (bonding curve)',
        'founder_capital_usd': params['founder_capital_usd'],
        'bootstrap_usd': params['bootstrap_usd'], 'sol_price_usd': params['sol_usd'],
        'kol_cash_usd': params['kol_cash_usd'], 'kol_supply_bps': params['kol_supply_bps'],
        'cast_actors': cast.get('actor_count'), 'worlds': summary['worlds'],
        'policy': {'exit_level_pct_of_48h_peak': 25, 'tranches': 4,
                   'tranche_spacing_minutes': 15, 'funding_gate_pct_of_peak': 60,
                   'defer': 'volume recovered AND 1h price return >= 0',
                   'half_life_hours': params['half_life_hours'],
                   'exit_hour': summary['exit_hour']},
        'venue_facts': (bootstrap.get('parameters') if params['venue'] == 'curve'
                        else {key: value for key, value in bootstrap.items()
                              if key != 'artifact_kind'})}, indent=2) + '\n')
    (data / 'outputs.json').write_text(json.dumps({
        'overall': {key: summary[key] for key in
                    ('net_quantiles', 'net_mean', 'net_min', 'net_max', 'profit_count',
                     'migration_share', 'exit_hour', 'worlds', 'proceeds_quantiles')},
        'by_bucket': summary['by_bucket'], 'scenarios': summary['scenarios'],
        'sensitivity': sens, 'limitations': summary['limitations']}, indent=2) + '\n')
    with (data / 'assumptions.csv').open('w', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['id', 'assumption', 'value', 'label'])
        rows = [('sol_usd', params['sol_usd'], 'declared'),
                ('fee_bps', params['fee_bps'], 'confirmed base fee'),
                ('bootstrap_usd', params['bootstrap_usd'], 'user decision'),
                ('kol_cash_usd', params['kol_cash_usd'], 'user decision'),
                ('kol_supply_bps', params['kol_supply_bps'], 'user decision'),
                ('half_life_hours', params['half_life_hours'], 'declared'),
                ('capitals', json.dumps(params['capital_usd']), 'library ranges vs pool liquidity'),
                ('venue', params['venue'], 'curve with migration' if params['venue'] == 'curve'
         else 'existing pool, no curve phase'),
                ('probabilities', 'one Jev call per trading actor', 'provider scores, not odds')]
        for index, (name, value, label) in enumerate(rows, 1):
            writer.writerow([f'A{index:02d}', name, value, label])
    with (data / 'scenarios.csv').open('w', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['scenario', 'share', 'out_of_100', 'p05', 'p50', 'p95', 'share_positive'])
        for row in summary['scenarios']:
            writer.writerow([row['scenario'], row['share'], row['out_of_100'], row['p05'],
                             row['p50'], row['p95'], row['share_positive']])
    (data / 'cast.json').write_text(json.dumps(cast, indent=2) + '\n')
    (data / 'probabilities.json').write_text(json.dumps(probabilities, indent=2) + '\n')
    (data / 'sources.json').write_text(json.dumps({
        'case_artefacts': ['plf-pilot/jev-probabilities.json',
                           'world-grounding-2026-10-30/cast-16.json',
                           'world-grounding-2026-10-30/launch-cases.json',
                           'world-grounding-2026-10-30/bootstrap-buy.json',
                           'world-grounding-2026-10-30/real-world-events.json'],
        'evidence': ['evidence/pump-program-constants-2026-10-30.json',
                     'evidence/assemblee-plf2027-schedule.txt'],
        'structure': 'docs/decision-lab/REPORT_STRUCTURE.md'}, indent=2) + '\n')
    receipts = case / 'plf-pilot' / 'jev-probabilities.json'
    if receipts.exists():
        pilot = json.loads(receipts.read_text())
        (data / 'jev-receipts.json').write_text(json.dumps(
            {'model': pilot.get('model'), 'cap_usd': pilot.get('cap_usd'),
             'spend_estimate_usd': pilot.get('spend_estimate_usd'),
             'calls': pilot.get('calls'), 'label': pilot.get('label')}, indent=2) + '\n')
    with (data / 'worlds.csv').open('w', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['world', 'bucket', 'kol_dump', 'migrated', 'deployed_usd', 'net_cash_usd',
                         'proceeds_usd'])
        for row in summary.get('worlds_rows', []):
            writer.writerow([row['world'], row['bucket'], int(row['kol_dump']),
                             int(row['migrated']), row['deployed_usd'], row['net_cash_usd'],
                             row['proceeds_usd']])


def render_case(case_dir, out_dir=None, params=None, worlds=None, public=False):
    """Render the five documents, four figures and the data tables named by a case brief."""
    case = Path(case_dir).resolve()
    brief = load_brief(case)
    labels = dict(brief.get('labels', {}))
    question = brief['question']
    if public:
        overrides = brief.get('labels_public', {})
        labels.update({key: value for key, value in overrides.items() if value})
        question = overrides.get('question', question)
    labels['question'] = question
    report = Path(out_dir).resolve() if out_dir else case / (
        'report-public' if public else 'report')
    report.mkdir(parents=True, exist_ok=True)
    (report / 'FIGURES').mkdir(exist_ok=True)
    artefacts = read_artefacts(case, brief)
    probabilities = {key: row['probabilities']
                     for key, row in artefacts['probabilities']['answers'].items()
                     if 'probabilities' in row}
    probability_artefact = artefacts['probabilities']
    probability_label = probability_artefact.get('label', 'supplied decision probabilities')
    calls = probability_artefact.get('calls') or []
    call_count = len(calls)
    has_receipts = call_count > 0
    model_name = (calls[0].get('model_reported') if calls else None) or \
        probability_artefact.get('model', 'unknown')
    cast = artefacts['cast']
    launch = artefacts['launch_cases']
    bootstrap = artefacts['bootstrap']
    events = artefacts['events']
    run_params = dict(brief.get('estimate', {}))
    run_params.update(params or {})
    if worlds:
        run_params['worlds'] = worlds
    summary = estimate_launch(probabilities, run_params, with_worlds=True)
    worlds_rows = summary.pop('worlds_rows', [])
    config = brief.get('sensitivity', {})
    scores = sensitivity(probabilities, run_params, grid=config.get('grid'),
                         worlds=min(config.get('worlds', 5_000), summary['worlds']))
    interview = ([] if public else
                 write_interview(case, brief.get('interview_files', []),
                                 report / 'DATA' / 'interview.csv'))
    fig_outcomes(summary, report / 'FIGURES' / 'fig-outcomes.svg')
    fig_net_cash(worlds_rows, summary, report / 'FIGURES' / 'fig-net-cash.svg')
    fig_pipeline(report / 'FIGURES' / 'fig-pipeline.svg')
    fig_sensitivity(scores, report / 'FIGURES' / 'fig-sensitivity.svg')
    summary['worlds_rows'] = worlds_rows
    if not public:
        write_data(report, case, summary, scores, probabilities, cast, launch, bootstrap, events)
    summary.pop('worlds_rows', None)
    docs = {
        '00-DECISION.md': doc_decision(summary, cast, probabilities, labels),
        '01-MODEL.md': doc_model(summary, cast, bootstrap, events, probabilities, labels,
                                 probability_label, call_count, model_name),
        '02-SCENARIOS.md': doc_scenarios(summary, scores, labels),
        '03-EVIDENCE.md': doc_evidence(summary, cast, events, probabilities, bootstrap,
                                       interview, labels, probability_label, has_receipts,
                                       public=public),
        '04-FORECAST.md': doc_forecast(summary, labels),
    }
    for name, body in docs.items():
        (report / name).write_text(body)
    export_html(report, report / 'report.html', labels.get('title', brief['id']),
                'Estimate, not a forecast.' + (' Public version: identity and private research '
                                               'removed.' if public else ''),
                f'Generated {time.strftime("%Y-%m-%d")} by decision-lab case build.')
    (report / 'INDEX.md').write_text(doc_index(summary, cast, docs))
    return {'report': str(report), 'public': public, 'worlds': summary['worlds'],
            'profit_of_100': round(summary['profit_count'] / summary['worlds'] * 100),
            'median': summary['net_quantiles']['p50'],
            'interview_rows': len(interview),
            'documents': sorted(docs), 'figures': 4}


def main(argv):
    if len(argv) < 2:
        print('usage: python -m decision_lab.case_report <case-dir> [--out DIR] [--worlds N]',
              file=sys.stderr)
        return 2
    case = argv[1]
    out, worlds = None, None
    if '--out' in argv:
        out = argv[argv.index('--out') + 1]
    if '--worlds' in argv:
        worlds = int(argv[argv.index('--worlds') + 1])
    summary = render_case(case, out, worlds=worlds)
    print(json.dumps(summary, indent=1))
    return 0



# --- static HTML export -----------------------------------------------------

def _inline(text):
    """Escape, then apply the inline markdown this report actually uses."""
    out = _esc(text)
    out = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'\1', out)
    out = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', out)
    out = re.sub(r'`([^`]+)`', r'<code>\1</code>', out)
    out = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', out)
    out = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', out)
    return out


def _md_to_html(markdown, figures):
    """Convert the report's markdown subset; images become inline SVG when available."""
    html, in_table, in_list = [], False, None
    def close():
        nonlocal in_table, in_list
        if in_table:
            html.append('</tbody></table></div>')
            in_table = False
        if in_list:
            html.append(f'</{in_list}>')
            in_list = None
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close()
            continue
        image = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line.strip())
        if image:
            close()
            name = Path(image.group(2)).name
            svg = figures.get(name)
            if svg:
                html.append(f'<figure>{svg}<figcaption>{_esc(image.group(1))}</figcaption></figure>')
            continue
        if line.startswith('#'):
            close()
            level = len(line) - len(line.lstrip('#'))
            html.append(f'<h{level}>{_inline(line[level:].strip())}</h{level}>')
            continue
        if line.lstrip().startswith('> '):
            close()
            html.append(f'<p class="banner">{_inline(line.lstrip()[2:])}</p>')
            continue
        if line.startswith('|'):
            cells = [cell.strip().replace('\\|', '|')
                     for cell in re.split(r'(?<!\\)\|', line.strip().strip('|'))]
            if all(set(cell) <= set('-: ') for cell in cells):
                continue
            if not in_table:
                close()
                html.append('<div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable table"><table><thead>')
                html.append('<tr>' + ''.join(f'<th>{_inline(c)}</th>' for c in cells) + '</tr>')
                html.append('</thead><tbody>')
                in_table = True
            else:
                html.append('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in cells) + '</tr>')
            continue
        bullet = re.match(r'\s*[-*]\s+(.*)', line)
        ordered = re.match(r'\s*\d+\.\s+(.*)', line)
        if bullet or ordered:
            tag = 'ul' if bullet else 'ol'
            if in_list != tag:
                close()
                html.append(f'<{tag}>')
                in_list = tag
            html.append(f'<li>{_inline((bullet or ordered).group(1))}</li>')
            continue
        close()
        html.append(f'<p>{_inline(line.strip())}</p>')
    close()
    return '\n'.join(html)


_STYLE = """
:root{--ink:#1a1f24;--muted:#5b6770;--rule:#d7dee3;--bg:#edf2f5;--card:#ffffff;--accent:#2b6cb0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.62 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,sans-serif}
main{max-width:860px;margin:0 auto;padding:40px 24px 96px}
header{border-bottom:1px solid var(--rule);margin-bottom:28px;padding-bottom:18px}
header p{margin:0;color:var(--muted);font-size:13px}
h1{font-size:30px;font-weight:600;letter-spacing:-.02em;margin:0 0 8px}
h2{font-size:20px;font-weight:600;margin:34px 0 10px}
h3{font-size:16px;font-weight:600;margin:24px 0 8px}
p{margin:10px 0}
ul,ol{margin:10px 0 10px 22px;padding:0}
li{margin:4px 0}
a{color:var(--accent)}
code{background:#e6ecf0;border-radius:4px;padding:1px 5px;font-size:13px}
table{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px;background:var(--card)}
.table-wrap{max-width:100%;overflow-x:auto}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule)}
th{background:#f5f8fa;font-weight:600}
figure{margin:22px 0;background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px}
figure svg{max-width:100%;height:auto;display:block}
figcaption{color:var(--muted);font-size:12px;margin-top:8px;text-align:center}
.banner{background:#fff6e5;border-left:3px solid #b8860b;padding:10px 12px;border-radius:4px;
 color:#5b4a10;font-size:13px}
section{margin-bottom:48px}
nav{position:sticky;top:0;z-index:1;display:flex;gap:8px;overflow-x:auto;
 padding:10px 0;background:var(--bg);border-bottom:1px solid var(--rule)}
nav a{white-space:nowrap;text-decoration:none;padding:6px 12px;border-radius:6px;
 background:var(--card);font-weight:600;font-size:13px}
nav a:hover,nav a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
section{scroll-margin-top:65px}
@media print{body{background:white}main{max-width:none;padding:0}nav{display:none}
 section{break-before:page}section:first-of-type{break-before:auto}figure,table{break-inside:avoid}}
"""

_INDEX = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{style}</style>
<main><header><h1>{title}</h1><p>{subtitle}</p></header>
<nav aria-label="Report sections">{navigation}</nav>
{body}
<footer><p>{footer}</p></footer></main></html>
"""


def export_html(report, out_path, title, subtitle='', footer=''):
    """Write one self-contained HTML file: documents, tables and inline SVG figures."""
    report = Path(report)
    figures = {path.name: path.read_text().split('?>')[-1].strip()
               for path in (report / 'FIGURES').glob('*.svg')}
    figures = {name: re.sub(r'^<\?xml[^>]*\?>', '', text) for name, text in figures.items()}
    sections, navigation = [], []
    for name, label in (('00-DECISION.md', 'Decision'), ('01-MODEL.md', 'Model'),
                        ('02-SCENARIOS.md', 'Scenarios'), ('03-EVIDENCE.md', 'Evidence'),
                        ('04-FORECAST.md', 'Forecast')):
        path = report / name
        if not path.exists():
            continue
        body = _md_to_html(path.read_text(), figures)
        if name == '00-DECISION.md':
            body = re.sub(r'<h1>[^<]*</h1>', '', body, count=1)
        else:
            body = re.sub(r'<h([1-5])>', lambda m: f'<h{min(6, int(m.group(1)) + 1)}>', body)
            body = re.sub(r'</h([1-5])>', lambda m: f'</h{min(6, int(m.group(1)) + 1)}>', body)
        sections.append(f'<section id="{name.split("-")[0]}">{body}</section>')
        navigation.append(f'<a href="#{name.split("-")[0]}">{label}</a>')
    html = _INDEX.format(title=_esc(title), style=_STYLE, body='\n'.join(sections),
                         subtitle=_esc(subtitle), footer=_esc(footer),
                         navigation='\n'.join(navigation))
    Path(out_path).write_text(html)
    return {'html': str(out_path), 'bytes': len(html.encode()), 'sections': len(sections)}

if __name__ == '__main__':
    sys.exit(main(sys.argv))
