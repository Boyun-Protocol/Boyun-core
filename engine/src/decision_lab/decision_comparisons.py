"""Offline descriptive comparisons of matched, completed decision trajectories.

Fresh model responses remain nondeterministic even with a shared engine seed.
No result is ranked or assigned a real-world outcome probability here.
"""
from copy import deepcopy
from math import isqrt

from .agent_orchestration import validate_brief
from .agent_worlds import canonical, digest, replay_agent_world, ENGINE_SHA256
from .decision_analysis import analyze_launch_result, ANALYSIS_ENGINE_SHA256
from .decision_evidence import brief_evidence
from .decision_report import _safe, _money, _hash, _int, _validate_analysis, _render_sources
from .providers import _endpoint_origin

MAX_MEMBER_BYTES = 10 * 1024 * 1024
MAX_COMPARISON_BYTES = 262144
MAX_REPORT_BYTES = 131072
ALLOWED_MARKET_FIELDS = ('launch_cost_cents', 'lp_cash_cents', 'lp_token_units',
                         'fee_bps', 'max_slippage_bps')
INPUT_FIELDS = ALLOWED_MARKET_FIELDS + ('exit_token_units',)
_LIMITATIONS = [
    'Real-world outcome probabilities are unknown; each row is one conditional synthetic trajectory.',
    'A shared engine seed controls ordering and information delivery, not fresh model outputs. This is not a causal ablation or a statistical significance test.',
    'Cash deltas describe these recorded outcomes, not guaranteed gains, optimized strategies, a ranking or a recommendation to launch.',
    'LP cash deposits are locked commitments, not claimed permanent economic losses. Unsold tokens and locked LP are excluded from actual cash profit.',
    'Hypothetical exits and aggregate-buy stresses are independent counterfactuals, not actual sales, actor budgets or forecasts of demand.',
    'Only supplied modeled expenses and AMM fees are included; provider cost and omitted real expenses remain unknown.',
    'Frozen provider-declared evidence is partial and unverified; comparison networks do not calibrate primary-network behavior.',
    'Artifact hashes establish content consistency, not signatures, authentic historical ownership or verified model identity.',
]


def _text(value, limit=160):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise ValueError('nonempty bounded comparison text required')
    return value


def _checksum(value, key, schema=None):
    if type(value) is not dict or (schema and value.get('schema_version') != schema):
        raise ValueError('invalid comparison source schema')
    copy = deepcopy(value)
    declared = copy.pop(key, None)
    if _hash(declared) != digest(copy):
        raise ValueError('comparison source checksum mismatch')
    return declared


def _route(value):
    if type(value) is not dict or not {'model', 'adapter'} <= set(value) <= {
        'model', 'adapter', 'endpoint', 'protocol', 'timeout', 'max_output_tokens', 'binary'
    }:
        raise ValueError('invalid declared model route')
    for key in ('model', 'adapter'):
        _text(value[key])
    for key in ('endpoint', 'binary'):
        if key in value:
            _text(value[key], 4096)
    if 'endpoint' in value:
        _endpoint_origin(value['endpoint'])
    if 'protocol' in value and value['protocol'] not in {'openai', 'gemini'}:
        raise ValueError('invalid model protocol')
    for key, maximum in (('timeout', 300), ('max_output_tokens', 16384)):
        if key in value and not 1 <= _int(value[key], maximum=maximum):
            raise ValueError('invalid model route budget')
    return deepcopy(value)


def _control_values(world, review, evidence):
    market = world['market']
    return {
        'evidence_sha256': evidence['context_sha256'],
        'actors_sha256': digest(world['agents']), 'network': world['network'], 'world_id': world['id'],
        'event_description_sha256': digest(world['event_description']),
        'events_sha256': digest(world['events']), 'rounds': world['rounds'],
        'initial_capital_cents': market['project_capital_cents'],
        'total_token_units': market['project_token_units'],
        'route': _route(review['route']), 'seed': _int(review['seed'], maximum=10**9),
        'analysis_search_bound_cents': _int(review['max_external_cash_cents'], maximum=10**12),
    }


def _validate_member(member):
    if type(member) is not dict or set(member) != {'label', 'state', 'manifest', 'result'}:
        raise ValueError('comparison members require label, state, manifest and result')
    _text(member['label'])
    if len(canonical(member)) > MAX_MEMBER_BYTES:
        raise ValueError('comparison member exceeds size budget')
    state, manifest = member['state'], member['manifest']
    state_hash = _checksum(state, 'state_sha256', 'decision-session.v1')
    if state['status'] != 'completed' or state.get('error') is not None:
        raise ValueError('comparison requires completed sessions')
    review = state['execution_review']
    review_hash = _checksum(review, 'review_sha256', 'decision-review.v1')
    proposal = state['proposal']
    if type(proposal) is not dict or type(proposal.get('questions')) is not list or len(proposal['questions']) > 3:
        raise ValueError('invalid reviewed launch proposal questions')
    question_ids = set()
    for question in proposal['questions']:
        if (type(question) is not dict or set(question) != {'id', 'prompt', 'choices', 'required'}
            or type(question['required']) is not bool or question['required']):
            raise ValueError('required questions remain unresolved or malformed')
        _text(question['id'], 40);_text(question['prompt'], 1000)
        if question['id'] in question_ids:
            raise ValueError('duplicate proposal question')
        question_ids.add(question['id'])
        if type(question['choices']) is not list or len(question['choices']) not in (0, 2, 3):
            raise ValueError('invalid bounded proposal question choices')
        for choice in question['choices']:
            _text(choice, 200)
    _text(proposal['summary'], 1600);_hash(proposal['context_sha256'])
    for key in ('assumptions', 'limitations'):
        if type(proposal[key]) is not list or len(proposal[key]) > 16:
            raise ValueError('invalid bounded proposal assumptions or limitations')
        for item in proposal[key]:
            _text(item, 1600)
    _int(state['revision'], maximum=1000000);_int(review['revision'], maximum=1000000)
    if (proposal.get('schema_version') != 'decision-proposal.v1'
        or proposal.get('decision_type') != 'launch'
        or review['proposal_sha256'] != digest(proposal)
        or review['revision'] != state['revision']):
        raise ValueError('review does not bind completed launch proposal')
    brief = validate_brief(proposal['brief'])
    evidence = state['evidence_context']
    attached_evidence = brief_evidence(evidence)
    if brief['evidence'] != attached_evidence:
        raise ValueError('reviewed construction brief differs from frozen evidence attachment')
    if (review['brief'] != brief or review['evidence_sha256'] != evidence['context_sha256']
        or state['network'] != brief['network'] or evidence['primary_network'] != brief['network']
        or review['exit_token_units'] != proposal['exit_token_units']):
        raise ValueError('reviewed brief, evidence or exit differs from session')
    _int(proposal['exit_token_units'], maximum=10**12)
    if (review['engine_sha256'] != ENGINE_SHA256
        or review['analysis_engine_sha256'] != ANALYSIS_ENGINE_SHA256):
        raise ValueError('review engine identity differs from current replay/analysis')
    result = replay_agent_world(member['result'])
    world = result['world']
    if result['status'] != 'completed':
        raise ValueError('comparison requires completed world results')
    for key in ('id', 'network', 'event_description', 'events', 'rounds', 'market'):
        if world[key] != brief[key]:
            raise ValueError('recorded world differs from reviewed brief')
    if len(world['agents']) != len(brief['slots']):
        raise ValueError('recorded actor coverage differs from review')
    for actor, slot in zip(world['agents'], brief['slots']):
        for key in ('id', 'role', 'initial_cash_cents', 'position_limit_cents', 'allowed_actions', 'attention_capacity'):
            if actor[key] != slot[key]:
                raise ValueError('recorded resources differ from reviewed slots')
        if not set(slot['required_sources']) <= set(actor['subscriptions']):
            raise ValueError('recorded subscriptions dropped reviewed sources')
    controls = _control_values(world, review, evidence)
    mode = review.get('construction_mode')
    if mode not in (None, 'reuse_reviewed_cast'):
        raise ValueError('unsupported reviewed construction mode')
    if mode is None and 'prepared_world_sha256' in review:
        raise ValueError('prepared world hash requires reviewed reuse mode')
    if state.get('comparison_parent') is not None and mode != 'reuse_reviewed_cast':
        raise ValueError('branch result lacks reviewed cast reuse binding')
    if mode == 'reuse_reviewed_cast' and review.get('prepared_world_sha256') != result['world_sha256']:
        raise ValueError('recorded world differs from reviewed prepared world')
    required = len(world['agents']) * world['rounds'] + (mode is None)
    if (type(manifest) is not dict or manifest.get('schema_version') != 'agent-live-run.v1'
        or manifest.get('status') != 'completed' or manifest.get('world_sha256') != result['world_sha256']
        or type(manifest.get('seed')) is not int or manifest['seed'] != controls['seed']
        or result['seed'] != controls['seed'] or manifest.get('error') is not None):
        raise ValueError('completed manifest does not bind recorded world and seed')
    _int(review['required_model_calls'], maximum=129)
    _int(review['project_capital_cents'], maximum=10**12)
    _int(review['outside_actor_cash_cents'], maximum=16 * 10**12)
    if (review['required_model_calls'] != required
        or _int(review['max_calls'], maximum=129) < required
        or review['project_capital_cents'] != world['market']['project_capital_cents']
        or review['outside_actor_cash_cents'] != sum(a['initial_cash_cents'] for a in world['agents'])):
        raise ValueError('review budgets differ from executed world')
    for key in ('required_calls', 'attempted_calls', 'completed_calls'):
        if type(manifest.get(key)) is not int or manifest[key] != required:
            raise ValueError('manifest call counts differ from reviewed execution')
    if (manifest.get('max_calls') != review['max_calls']
        or type(manifest.get('completed_rounds')) is not int
        or manifest['completed_rounds'] != world['rounds']):
        raise ValueError('manifest budgets or rounds differ from review')
    if type(manifest.get('calls')) is not list or len(manifest['calls']) != required:
        raise ValueError('complete model call receipts required')
    for index, call in enumerate(manifest['calls'], 1):
        if (type(call.get('index')) is not int or call['index'] != index or call.get('status') != 'response_received'
            or call.get('receipt', {}).get('model_declared') != controls['route']['model']):
            raise ValueError('call receipt does not match declared execution route')
    analysis = analyze_launch_result(result, exit_token_units=review['exit_token_units'],
                                     max_external_cash_cents=controls['analysis_search_bound_cents'])
    source = {'state_sha256': state_hash, 'review_sha256': review_hash,
              'manifest_sha256': digest(manifest), 'result_sha256': digest(result),
              'world_sha256': result['world_sha256']}
    for key in ('manifest_sha256', 'result_sha256'):
        if key in state and state[key] != source[key]:
            raise ValueError('session run artifact hash differs')
    inputs = {key: world['market'][key] for key in ALLOWED_MARKET_FIELDS}
    inputs['exit_token_units'] = review['exit_token_units']
    return {'label': member['label'], 'source': source, 'inputs': inputs,
            'analyzed_market': deepcopy(world['market']), 'analysis': analysis}, controls, deepcopy(evidence)


def _deltas(analysis, baseline):
    current_break_even = analysis['break_even']['minimum_additional_buy_cents']
    baseline_break_even = baseline['break_even']['minimum_additional_buy_cents']
    return {
        'actual_cash_profit_cents': analysis['actual']['cash_profit_cents'] - baseline['actual']['cash_profit_cents'],
        'hypothetical_exit_profit_cents': analysis['hypothetical_exit']['profit_cents'] - baseline['hypothetical_exit']['profit_cents'],
        'locked_lp_cash_deposit_cents': analysis['actual']['locked_lp_cash_deposit_cents'] - baseline['actual']['locked_lp_cash_deposit_cents'],
        'break_even_additional_buy_cents': (current_break_even - baseline_break_even
            if current_break_even is not None and baseline_break_even is not None else None),
    }


def _changes(inputs, baseline):
    return [{'field': key, 'baseline': baseline[key], 'value': inputs[key]}
            for key in INPUT_FIELDS if inputs[key] != baseline[key]]


def compare_decisions(members):
    """Recompute and compare 2–8 matched, completed decision session artifacts."""
    if type(members) is not list or not 2 <= len(members) <= 8:
        raise ValueError('comparison requires two to eight members')
    rows, controls, evidence = [], None, None
    seen_results, seen_labels = set(), set()
    try:
        for member in members:
            row, selected_controls, selected_evidence = _validate_member(member)
            if row['source']['result_sha256'] in seen_results:
                raise ValueError('duplicate result trajectory in comparison')
            if row['label'] in seen_labels:
                raise ValueError('duplicate comparison label')
            seen_results.add(row['source']['result_sha256']);seen_labels.add(row['label'])
            if controls is None:
                controls, evidence = selected_controls, selected_evidence
            elif selected_controls != controls or selected_evidence != evidence:
                raise ValueError('matched decision controls differ')
            rows.append(row)
        for row in rows:
            row['input_changes'] = _changes(row['inputs'], rows[0]['inputs'])
            row['deltas'] = _deltas(row['analysis'], rows[0]['analysis'])
        result = {'schema_version': 'decision-comparison.v1', 'baseline_label': rows[0]['label'],
                  'controls': controls, 'evidence_context': evidence, 'rows': rows,
                  'probability_status': 'unknown', 'provider_cost_status': 'unknown',
                  'limitations': list(_LIMITATIONS)}
        result['comparison_sha256'] = digest(result)
        if len(canonical(result)) > MAX_COMPARISON_BYTES:
            raise ValueError('comparison exceeds artifact size budget')
        return result
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        raise ValueError('invalid matched comparison artifacts') from error


def _validate_analyzed_market(row, controls):
    """Tie rendered inputs to the analyzed funded market and fee arithmetic.

    These are the existing agent-world.v1 funded-market invariants. Source
    origin still requires the replayed original world/result; a rehashable
    comparison summary is not an authenticated substitute for those artifacts.
    """
    market = row['analyzed_market']
    if type(market) is not dict or set(market) != {
        'project_capital_cents', 'launch_cost_cents', 'lp_cash_cents',
        'project_token_units', 'lp_token_units', 'fee_bps', 'max_slippage_bps'
    }:
        raise ValueError('invalid analyzed market shape')
    for value in market.values():
        _int(value, maximum=10**12)
    capital, cost = market['project_capital_cents'], market['launch_cost_cents']
    pool_cash, pool_tokens = market['lp_cash_cents'], market['lp_token_units']
    supply, fee = market['project_token_units'], market['fee_bps']
    if (not pool_cash or not pool_tokens or cost + pool_cash > capital
        or pool_tokens > supply or fee >= 10000 or market['max_slippage_bps'] > 10000):
        raise ValueError('invalid analyzed funded market')
    if (capital != controls['initial_capital_cents'] or supply != controls['total_token_units']
        or any(row['inputs'][key] != market[key] for key in ALLOWED_MARKET_FIELDS)):
        raise ValueError('rendered inputs differ from analyzed market or fixed controls')
    actual, exit_quote = row['analysis']['actual'], row['analysis']['hypothetical_exit']
    quantity = row['inputs']['exit_token_units']
    sell_fee = quantity - quantity * (10000 - fee) // 10000
    if (actual['paid_costs_cents'] != cost or actual['locked_lp_cash_deposit_cents'] != pool_cash
        or actual['unsold_token_units'] != supply - pool_tokens
        or actual['ending_cash_cents'] != capital - cost - pool_cash
        or actual['locked_lp_shares'] != isqrt(pool_cash * pool_tokens)
        or quantity != exit_quote['exit_token_units'] or quantity > supply - pool_tokens
        or exit_quote['fee_token_units'] != sell_fee):
        raise ValueError('analysis differs from funded market accounting or fee')
    for stress in row['analysis']['demand_stress']:
        buy_cash = stress['external_buy_cents']
        buy_fee = buy_cash - buy_cash * (10000 - fee) // 10000
        if stress['buy_fee_cash_cents'] != buy_fee or stress['exit_fee_token_units'] != sell_fee:
            raise ValueError('stress fees differ from analyzed market fee')


def _validated_comparison(comparison):
    if len(canonical(comparison)) > MAX_COMPARISON_BYTES:
        raise ValueError('comparison exceeds artifact size budget')
    _checksum(comparison, 'comparison_sha256', 'decision-comparison.v1')
    rows, controls = comparison['rows'], comparison['controls']
    if type(rows) is not list or not 2 <= len(rows) <= 8:
        raise ValueError('invalid comparison row count')
    if comparison['baseline_label'] != rows[0]['label']:
        raise ValueError('comparison baseline differs from first row')
    if comparison['probability_status'] != 'unknown' or comparison['provider_cost_status'] != 'unknown':
        raise ValueError('comparison cannot assert known probability or cost')
    brief_evidence(comparison['evidence_context'])
    if comparison['evidence_context']['context_sha256'] != controls['evidence_sha256']:
        raise ValueError('comparison evidence identity differs')
    _route(controls['route'])
    for key in ('evidence_sha256', 'actors_sha256', 'event_description_sha256', 'events_sha256'):
        _hash(controls[key])
    _int(controls['seed'], maximum=10**9);_int(controls['analysis_search_bound_cents'], maximum=10**12)
    _int(controls['initial_capital_cents'], maximum=10**12);_int(controls['total_token_units'], maximum=10**12)
    _text(controls['network'], 32);_text(controls['world_id'], 48)
    if _int(controls['rounds'], maximum=16) < 1:
        raise ValueError('invalid comparison rounds')
    if comparison['evidence_context']['primary_network'] != controls['network']:
        raise ValueError('comparison evidence network differs')
    result_hashes, labels = set(), set()
    for row in rows:
        _text(row['label'])
        if row['label'] in labels:
            raise ValueError('duplicate comparison label')
        labels.add(row['label'])
        if type(row['inputs']) is not dict or set(row['inputs']) != set(INPUT_FIELDS):
            raise ValueError('invalid comparison input fields')
        for value in row['inputs'].values():
            _int(value, maximum=10**12)
        _validate_analysis(row['analysis'])
        _validate_analyzed_market(row, controls)
        for value in row['source'].values():
            _hash(value)
        if (row['source']['result_sha256'] in result_hashes
            or row['source']['world_sha256'] != row['analysis']['identity']['world_sha256']
            or row['source']['result_sha256'] != row['analysis']['identity']['report_sha256']
            or row['analysis']['actual']['initial_capital_cents'] != controls['initial_capital_cents']
            or row['analysis']['break_even']['search_bound_cents'] != controls['analysis_search_bound_cents']
            or row['inputs']['exit_token_units'] != row['analysis']['hypothetical_exit']['exit_token_units']
            or row['deltas'] != _deltas(row['analysis'], rows[0]['analysis'])
            or row['input_changes'] != _changes(row['inputs'], rows[0]['inputs'])):
            raise ValueError('inconsistent comparison row arithmetic or identity')
        result_hashes.add(row['source']['result_sha256'])
    if type(comparison['limitations']) is not list or len(comparison['limitations']) > 32:
        raise ValueError('invalid comparison limitations')
    for limitation in comparison['limitations']:
        _text(limitation, 1600)
    return comparison


def _threshold(analysis):
    boundary = analysis['break_even']
    if boundary['minimum_additional_buy_cents'] is not None:
        return _money(boundary['minimum_additional_buy_cents'])
    if boundary['status'] == 'no_exit_tokens':
        return 'No selected exit tokens'
    return 'Not reached within ' + _money(boundary['search_bound_cents'])


def render_comparison_report(comparison):
    """Render checksum-bound descriptive results with all source text inert."""
    try:
        comparison = _validated_comparison(comparison)
        controls, rows = comparison['controls'], comparison['rows']
        lines = ['# Matched launch-plan comparison', '',
            f"Baseline: {_safe(comparison['baseline_label'])}. Rows retain input order; they are not ranked.", '',
            '**Real-world outcome probabilities are unknown.** One fresh model trajectory per plan is not a causal ablation, a calibrated probability sample or a significance test.', '',
            '## Cash outcomes', '',
            '| Plan | Actual ending cash | Actual cash profit | Locked LP deposit | Hypothetical exit cash | Hypothetical exit profit | Additional buy for cash break-even |',
            '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
        capital = controls['initial_capital_cents']
        lines.append(f'| No launch — retain capital | {_money(capital)} | {_money(0)} | {_money(0)} | Not applicable | Not applicable | Not applicable |')
        for row in rows:
            actual, exit_quote = row['analysis']['actual'], row['analysis']['hypothetical_exit']
            lines.append(f"| {_safe(row['label'])} | {_money(actual['ending_cash_cents'])} | {_money(actual['cash_profit_cents'])} | {_money(actual['locked_lp_cash_deposit_cents'])} | {_money(exit_quote['ending_cash_cents'])} | {_money(exit_quote['profit_cents'])} | {_threshold(row['analysis'])} |")
        lines += ['', 'Actual cash excludes locked LP and unsold tokens. Hypothetical exit cash is project cash after a sale that did not occur in actual history. Locked LP deposits are commitments, not claimed permanent losses.', '',
            'Provider cost and omitted real expenses are unknown. Only reviewed modeled costs and fees are included.', '',
            '## Descriptive deltas versus baseline', '',
            '| Plan | Actual cash profit delta | Hypothetical exit profit delta | Locked LP deposit delta | Break-even demand delta |',
            '| --- | ---: | ---: | ---: | ---: |']
        for row in rows:
            delta = row['deltas'];threshold_delta = delta['break_even_additional_buy_cents']
            lines.append(f"| {_safe(row['label'])} | {_money(delta['actual_cash_profit_cents'])} | {_money(delta['hypothetical_exit_profit_cents'])} | {_money(delta['locked_lp_cash_deposit_cents'])} | {_money(threshold_delta) if threshold_delta is not None else 'Not comparable within bounds'} |")
        lines += ['', 'Positive and negative deltas are accounting differences in these trajectories, not a recommendation or an estimate of a causal effect.', '',
                  '## Reviewed input differences', '', '| Plan | Input | Baseline | Plan value |', '| --- | --- | ---: | ---: |']
        for row in rows[1:]:
            if not row['input_changes']:
                lines.append(f"| {_safe(row['label'])} | No allowed financial input change; fresh decisions only | — | — |")
            for change in row['input_changes']:
                field = change['field'];formatter = _money if field.endswith('_cents') else lambda value: f'{value:,}'
                lines.append(f"| {_safe(row['label'])} | {_safe(field)} | {formatter(change['baseline'])} | {formatter(change['value'])} |")
        lines += ['', '## Initial pool settings', '',
                  '| Plan | LP cash | LP token units | Fee (bps) | Slippage limit (bps) |',
                  '| --- | ---: | ---: | ---: | ---: |']
        for row in rows:
            market=row['analyzed_market']
            lines.append(f"| {_safe(row['label'])} | {_money(market['lp_cash_cents'])} | {market['lp_token_units']:,} | {market['fee_bps']:,} | {market['max_slippage_bps']:,} |")
        lines += ['', 'Initial price is pool cash divided by pooled token units; changing one reserve changes the starting price unless both reserves scale proportionally.',
                  'Token quantities are raw synthetic units; fee and slippage inputs are basis points.', '',
                  '## Fixed controls', '',
                  f"Network: {_safe(controls['network'])}. Rounds: {controls['rounds']}. Engine seed: {controls['seed']}. Initial project capital: {_money(capital)}. Total token supply: {controls['total_token_units']:,}.",
                  f"Declared model: {_safe(controls['route']['model'])}; adapter: {_safe(controls['route']['adapter'])}. Fresh model outputs remain nondeterministic.",
                  f"Evidence hash: {controls['evidence_sha256']}", f"Actual cast hash: {controls['actors_sha256']}",
                  f"Event text hash: {controls['event_description_sha256']}", f"Scheduled event hash: {controls['events_sha256']}", '',
                  '## Frozen evidence and coverage', '', *_render_sources(comparison['evidence_context']),
                  '## Independent demand stress worksheets', '',
                  'Every row adds one hypothetical external aggregate buy to a fresh copy of that plan’s actual ending balances, then sells the reviewed project quantity. These rows are not forecast buyers or actual actor budgets.', '']
        for row in rows:
            lines += ['### ' + _safe(row['label']), '',
                      f"Selected exit: {row['inputs']['exit_token_units']:,} tokens. Modeled paid costs: {_money(row['analysis']['actual']['paid_costs_cents'])}.", '',
                      '| Added aggregate buy | Hypothetical ending project cash | Profit after modeled costs |', '| ---: | ---: | ---: |']
            for stress in row['analysis']['demand_stress']:
                lines.append(f"| {_money(stress['external_buy_cents'])} | {_money(stress['ending_project_cash_cents'])} | {_money(stress['profit_cents'])} |")
            lines.append('')
        lines += ['## Source identities', '', '| Plan | Session state | Review | Manifest | Result | World |', '| --- | --- | --- | --- | --- | --- |']
        for row in rows:
            source = row['source']
            lines.append('| ' + _safe(row['label']) + ' | ' + ' | '.join(source[key] for key in ('state_sha256', 'review_sha256', 'manifest_sha256', 'result_sha256', 'world_sha256')) + ' |')
        lines += ['', f"Comparison hash: {comparison['comparison_sha256']}", '', '## Limits and next checks', '']
        lines += ['- ' + _safe(limitation) for limitation in comparison['limitations']]
        lines += ['- Verify actual venue fees, LP locks, all expenses and specific event sources before acting. Validate behavior against held-out observations before treating any frequency as predictive.', '']
        text = '\n'.join(lines)
        if len(text.encode('utf-8')) > MAX_REPORT_BYTES:
            raise ValueError('comparison report exceeds output budget')
        return text
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        raise ValueError('invalid comparison report artifact') from error
