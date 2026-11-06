"""Deterministic, bounded decision memo; no model-written financial conclusions."""
from html import escape
import json
import re

from .agent_orchestration import validate_brief
from .decision_evidence import brief_evidence

MAX_INPUT_BYTES = 524288
MAX_REPORT_BYTES = 131072


def _text(value, limit=1600):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise ValueError('invalid bounded report text')
    return value


def _safe(value):
    raw = _text(value, 8000)
    raw = ''.join(' ' if ord(char) < 32 or 127 <= ord(char) <= 159 or char in '\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069' else char for char in raw)
    # Escape once per original character, so '#' in emitted entities is not
    # accidentally escaped a second time (and quote entities stay intact).
    return ''.join(f'&#{ord(char)};' if char in '\\`*_{}[]()#+!|' else escape(char, quote=True)
                   for char in ' '.join(raw.split()))


def _int(value, *, signed=False, maximum=10**18):
    if type(value) is not int or not (-maximum if signed else 0) <= value <= maximum:
        raise ValueError('invalid bounded report integer')
    return value


def _money(value):
    _int(value, signed=True)
    amount = abs(value)
    return f"{'-' if value < 0 else ''}${amount // 100:,}.{amount % 100:02d}"


def _strings(values, limit=64):
    if type(values) is not list or len(values) > limit:
        raise ValueError('invalid bounded report text list')
    for value in values:
        _text(value)
    return values


def _hash(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('invalid artifact hash')
    return value


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('invalid decision analysis shape')


def _validate_analysis(analysis):
    if type(analysis) is not dict or analysis.get('schema_version') != 'decision-financial-analysis.v1':
        raise ValueError('invalid financial analysis schema')
    _shape(analysis, {'schema_version', 'identity', 'no_launch', 'actual', 'hypothetical_exit',
                      'demand_stress', 'break_even', 'assumptions', 'limitations'})
    _shape(analysis['identity'], {'world_sha256', 'engine_sha256', 'report_sha256', 'analysis_engine_sha256'})
    _shape(analysis['no_launch'], {'ending_cash_cents', 'profit_cents'})
    for value in analysis['no_launch'].values():
        _int(value)
    for value in analysis['identity'].values():
        _hash(value)
    for key in ('world_sha256', 'engine_sha256', 'report_sha256', 'analysis_engine_sha256'):
        _hash(analysis['identity'][key])
    actual, exit_quote = analysis['actual'], analysis['hypothetical_exit']
    _shape(actual, {'initial_capital_cents', 'ending_cash_cents', 'paid_costs_cents',
                    'locked_lp_cash_deposit_cents', 'locked_lp_shares', 'unsold_token_units',
                    'cash_profit_cents'})
    _shape(exit_quote, {'exit_token_units', 'cash_proceeds_cents', 'ending_cash_cents',
                        'profit_cents', 'fee_token_units', 'remaining_token_units'})
    for key, value in actual.items():
        _int(value, signed=key == 'cash_profit_cents')
    for key, value in exit_quote.items():
        _int(value, signed=key == 'profit_cents')
    capital, ending = actual['initial_capital_cents'], actual['ending_cash_cents']
    if (actual['cash_profit_cents'] != ending - capital
        or analysis['no_launch'] != {'ending_cash_cents': capital, 'profit_cents': 0}
        or exit_quote['ending_cash_cents'] != ending + exit_quote['cash_proceeds_cents']
        or exit_quote['profit_cents'] != exit_quote['ending_cash_cents'] - capital
        or exit_quote['exit_token_units'] + exit_quote['remaining_token_units'] != actual['unsold_token_units']
        or exit_quote['fee_token_units'] > exit_quote['exit_token_units']):
        raise ValueError('inconsistent financial analysis arithmetic')
    rows = analysis['demand_stress']
    if type(rows) is not list or len(rows) > 32:
        raise ValueError('invalid demand stress rows')
    previous = -1
    for row in rows:
        _shape(row, {'external_buy_cents', 'bought_token_units', 'buy_fee_cash_cents',
                     'exit_cash_proceeds_cents', 'ending_project_cash_cents', 'profit_cents',
                     'exit_fee_token_units'})
        for key, value in row.items():
            _int(value, signed=key == 'profit_cents')
        if (row['external_buy_cents'] <= previous
            or row['ending_project_cash_cents'] != ending + row['exit_cash_proceeds_cents']
            or row['profit_cents'] != row['ending_project_cash_cents'] - capital
            or row['buy_fee_cash_cents'] > row['external_buy_cents']
            or row['exit_fee_token_units'] > exit_quote['exit_token_units']):
            raise ValueError('inconsistent demand stress arithmetic')
        previous = row['external_buy_cents']
    boundary = analysis['break_even']
    _shape(boundary, {'status', 'minimum_additional_buy_cents', 'search_bound_cents',
                      'previous_cent_profit_cents'})
    bound = _int(boundary['search_bound_cents'], maximum=10**12)
    if previous > bound:
        raise ValueError('demand exceeds search bound')
    status, minimum = boundary['status'], boundary['minimum_additional_buy_cents']
    if minimum is not None:
        _int(minimum, maximum=bound)
    if boundary['previous_cent_profit_cents'] is not None:
        _int(boundary['previous_cent_profit_cents'], signed=True)
    if status == 'already_break_even':
        valid = minimum == 0 and exit_quote['profit_cents'] >= 0 and boundary['previous_cent_profit_cents'] is None
    elif status == 'reachable':
        valid = (minimum is not None and minimum > 0 and exit_quote['profit_cents'] < 0
                 and boundary['previous_cent_profit_cents'] is not None and boundary['previous_cent_profit_cents'] < 0)
    elif status == 'no_exit_tokens':
        valid = (minimum is None and exit_quote['exit_token_units'] == 0 and exit_quote['profit_cents'] < 0
                 and boundary['previous_cent_profit_cents'] is None)
    elif status == 'not_reached_within_bound':
        valid = (minimum is None and exit_quote['profit_cents'] < 0 and exit_quote['exit_token_units'] > 0
                 and boundary['previous_cent_profit_cents'] is None)
    else:
        valid = False
    if not valid:
        raise ValueError('inconsistent break-even analysis')
    _strings(analysis['assumptions'], 32)
    _strings(analysis['limitations'])


def _render_sources(context):
    lines = [f"Primary network: {_safe(context['primary_network'])}. Evidence cutoff: {_safe(context['as_of']) if context['as_of'] else 'not supplied'}.",
             '', 'Coverage is partial; continuity is unverified. Overlapping sources remain separate: do not sum their counts into a population.', '']
    if not context['primary']:
        lines += ['No primary-network observations were supplied. Persona resources and behavior remain assumptions.', '']
    for title, sources in (('Primary sources', context['primary']), ('Comparison sources — separate network only', context['comparisons'])):
        lines += [f'### {title}', '']
        if not sources:
            lines += ['None supplied.', '']
        for row in sources:
            summary, observed = row['summary'], row['observed_window']
            trades, wallets = _int(summary['accepted_trades']), _int(summary['observed_wallets'])
            start, end = observed['start'], observed['end']
            lines += [f"- Network {_safe(row['network'])}: {trades:,} accepted sampled trades; {wallets:,} observed wallets. Window: {_safe(start) if start else 'unknown'} → {_safe(end) if end else 'unknown'}.",
                      f"  Source: {_safe(row['source_ref'])}. Captured: {_safe(row['captured_at'])}. Provider retrieval: {_safe(row['latest_provider_retrieved_at'])}.",
                      f"  Source hash: {_hash(row['sha256'])}. Verification: {_safe(row['verification'])}. Complete target window: no."]
            if row['omitted_cohorts']['cohort_count']:
                lines += [f"  Bounded context omits {_int(row['omitted_cohorts']['cohort_count']):,} detailed cohort rows; their receipt totals remain in the evidence artifact."]
        lines.append('')
    lines += ['Observed turnover is not available capital, profit, wallet ownership, KOL identity or future willingness to buy. Comparison data does not calibrate primary-network behavior.', '']
    return lines


def render_decision_report(*, question, proposal, evidence_context, manifest, analysis):
    """Render validated workflow artifacts as inert Markdown, never new forecasts.

    The caller supplies a replay-derived analysis. Internal arithmetic and run
    binding are checked here; content hashes are identities, not signatures.
    """
    try:
        encoded = json.dumps([question, proposal, evidence_context, manifest, analysis],
                             ensure_ascii=True, allow_nan=False).encode('ascii')
        if len(encoded) > MAX_INPUT_BYTES:
            raise ValueError('decision report input exceeds size budget')
        _text(question, 8000)
        _text(proposal['summary'], 4000)
        _strings(proposal['assumptions'], 32)
        _strings(proposal['limitations'], 32)
        brief = validate_brief(proposal['brief'])
        brief_evidence(evidence_context)
        if evidence_context['primary_network'] != brief['network']:
            raise ValueError('evidence and brief networks differ')
        if manifest.get('schema_version') != 'agent-live-run.v1' or manifest.get('status') != 'completed':
            raise ValueError('a completed live-run manifest is required')
        _validate_analysis(analysis)
        binding = manifest.get('world_sha256')
        if binding is not None and _hash(binding) != analysis['identity']['world_sha256']:
            raise ValueError('manifest and analysis world hashes differ')
        actual = analysis['actual']
        market = brief['market']
        if (actual['initial_capital_cents'] != market['project_capital_cents']
            or actual['paid_costs_cents'] != market['launch_cost_cents']
            or actual['locked_lp_cash_deposit_cents'] != market['lp_cash_cents']
            or actual['unsold_token_units'] != market['project_token_units'] - market['lp_token_units']):
            raise ValueError('brief and financial analysis differ')
        completed_calls = manifest.get('completed_calls')
        completed_rounds = manifest.get('completed_rounds')
        if completed_calls is not None:
            _int(completed_calls, maximum=129)
        if completed_rounds is not None and _int(completed_rounds, maximum=16) != brief['rounds']:
            raise ValueError('manifest rounds differ from reviewed brief')
        sources = _render_sources(evidence_context)
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        raise ValueError('invalid decision report artifacts') from error
    exit_quote, boundary = analysis['hypothetical_exit'], analysis['break_even']
    lines = ['# Decision worksheet', '', f"Question: {_safe(question)}", '',
             f"Reviewed proposal: {_safe(proposal['summary'])}", '',
             '**Real-world outcome probabilities are unknown.** This run is one conditional synthetic trajectory, not a forecast.', '',
             '## Cash comparison', '', '| Position | Cash | Profit versus initial capital |', '| --- | ---: | ---: |',
             f"| No launch — keep capital | {_money(analysis['no_launch']['ending_cash_cents'])} | {_money(0)} |",
             f"| Actual ending project cash in recorded world | {_money(actual['ending_cash_cents'])} | {_money(actual['cash_profit_cents'])} |",
             '', f"Modeled costs already paid: {_money(actual['paid_costs_cents'])}. Initial cash deposited into locked LP: {_money(actual['locked_lp_cash_deposit_cents'])}; synthetic LP shares: {actual['locked_lp_shares']:,}.",
             f"Unpooled project tokens: {actual['unsold_token_units']:,}. Neither unsold tokens nor locked LP are counted as withdrawable cash profit.",
             'Only supplied modeled costs are included. Verify every actual expense before interpreting net profit; omitted expenses are not zero.', '',
             '## Hypothetical project exit — separate from actual history', '',
             f"Selling {exit_quote['exit_token_units']:,} unpooled tokens immediately into the ending synthetic pool quotes {_money(exit_quote['cash_proceeds_cents'])} cash, with {exit_quote['fee_token_units']:,} token units retained as fee.",
             f"Hypothetical ending project cash: {_money(exit_quote['ending_cash_cents'])}; profit after modeled costs: {_money(exit_quote['profit_cents'])}. Remaining unpooled tokens: {exit_quote['remaining_token_units']:,}.",
             'This sale did not happen in the recorded world. LP stays locked; quoted proceeds depend on modeled reserves and settlement assumptions.', '',
             '## Conditional additional-demand worksheet', '',
             'Each row resets to the actual ending balances, adds one externally funded aggregate buy, then sells the selected project tokens. It is not a prediction of real buyers or their budgets.', '',
             '| Added buy cash | Tokens bought | Buy fee | Hypothetical exit cash | Ending project cash | Profit |',
             '| ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in analysis['demand_stress']:
        lines.append(f"| {_money(row['external_buy_cents'])} | {row['bought_token_units']:,} | {_money(row['buy_fee_cash_cents'])} | {_money(row['exit_cash_proceeds_cents'])} | {_money(row['ending_project_cash_cents'])} | {_money(row['profit_cents'])} |")
    lines.append('')
    if boundary['status'] == 'already_break_even':
        lines.append('Hypothetical immediate exit already reaches the initial capital with additional demand of $0.00. This does not mean actual cash profit is positive.')
    elif boundary['status'] == 'reachable':
        lines.append(f"Minimum additional aggregate buy for hypothetical cash break-even: {_money(boundary['minimum_additional_buy_cents'])}. One cent less leaves profit of {_money(boundary['previous_cent_profit_cents'])}. This is an integer AMM feasibility threshold, not a probability.")
    elif boundary['status'] == 'no_exit_tokens':
        lines.append('No project tokens were selected for exit; added demand cannot recover project cash through this exit calculation.')
    else:
        lines.append(f"Break-even was not reached within the tested additional-buy bound of {_money(boundary['search_bound_cents'])}. No conclusion is made beyond that bound.")
    lines += ['', '## Evidence and coverage', '', *sources, '## Reviewed assumptions and limits', '']
    for item in dict.fromkeys(proposal['assumptions'] + analysis['assumptions']):
        lines.append('- ' + _safe(item))
    for item in dict.fromkeys(proposal['limitations'] + analysis['limitations']):
        lines.append('- ' + _safe(item))
    lines += ['', '## Next checks before acting', '',
              '1. Replace assumed liquidity, token allocation, lock conditions and fee schedule with the intended venue’s verified rules.',
              '2. List all launch, marketing, operating, tax and exit expenses; rerun the reviewed capital plan when any input changes.',
              '3. Verify the specific real-world event, rights to names/images and source timestamps. Do not treat agent messages as authenticated news.',
              '4. Establish actual audience interest and available exit liquidity. Historical observation and held-out validation are needed before publishing calibrated odds.',
              '5. Compare the same cash accounting against not launching and smaller commitments. This worksheet does not choose for the user.', '',
              '## Execution identity', '',
              f"Model calls completed: {completed_calls if completed_calls is not None else 'not supplied'}. Completed rounds: {completed_rounds if completed_rounds is not None else 'not supplied'}. Provider cost: unknown unless separately verified from provider receipts.",
              'Manifest world binding checked.' if binding is not None else 'Manifest world binding unavailable; no manifest-to-world verification claimed.',
              f"World hash: {analysis['identity']['world_sha256']}", f"Recorded result hash: {analysis['identity']['report_sha256']}",
              f"Simulation engine hash: {analysis['identity']['engine_sha256']}", f"Analysis engine hash: {analysis['identity']['analysis_engine_sha256']}",
              'Content hashes identify artifacts; they do not authenticate provider observations or prove historical ownership.', '']
    rendered = '\n'.join(lines)
    if len(rendered.encode('utf-8')) > MAX_REPORT_BYTES:
        raise ValueError('decision report exceeds output size budget')
    return rendered
