"""Replay-derived cash accounting and bounded conditional AMM feasibility.

This worksheet does not predict demand or attach odds to one model trajectory.
Actual balances are immutable; each counterfactual starts from its own copy.
"""
from hashlib import sha256
from pathlib import Path

from .agent_worlds import digest, replay_agent_world
from .finance import Balance, ConstantProductMarket, Ledger

MAX_EXTERNAL_CASH_CENTS = 10**12
MAX_STRESS_ROWS = 32
ANALYSIS_ENGINE_SHA256 = sha256(Path(__file__).read_bytes()).hexdigest()
_EXTERNAL_BUYER = '__decision_external_buyer__'


def _integer(value, name, maximum=MAX_EXTERNAL_CASH_CENTS):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be an integer between 0 and {maximum}')
    return value


def _validated_report(report):
    try:
        replayed = replay_agent_world(report)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
        raise ValueError('a replay-valid agent-world-results.v1 report is required') from exc
    if replayed['status'] != 'completed':
        raise ValueError('financial decision analysis requires a completed world')
    return replayed


def analyze_launch_result(report, *, exit_token_units=None, demand_cents=None,
                          max_external_cash_cents=100_000_000):
    """Analyze supplied exit quantity under independent aggregate-buy stresses.

    ``demand_cents`` is a bounded list of externally supplied hypothetical cash
    inputs, not forecast demand. Defaults are fractions/multiples of project
    capital, capped at ``max_external_cash_cents``. The binary search finds the
    smallest additional aggregate buy within that bound for which *immediate
    hypothetical exit* recovers initial cash, after modeled costs and fees.

    Monotonicity is exact despite floors: as buy cash increases, cash reserves
    increase and remaining pool tokens cannot increase. For fixed founder token
    input, floored sell output therefore cannot decrease. At most 40 midpoint
    checks are needed for the 10**12-cent public bound.
    """
    bound = _integer(max_external_cash_cents, 'max_external_cash_cents')
    if exit_token_units is not None:
        _integer(exit_token_units, 'exit_token_units')
    if demand_cents is not None:
        if type(demand_cents) is not list or len(demand_cents) > MAX_STRESS_ROWS:
            raise ValueError('demand_cents must be a list with at most 32 entries')
        for amount in demand_cents:
            _integer(amount, 'demand_cents entry', bound)
    actual_report = _validated_report(report)
    world = actual_report['world']
    market_parameters = world['market']
    balances = actual_report['balances']
    project = balances['project']
    capital = market_parameters['project_capital_cents']
    owned_tokens = project['token_units']
    quantity = owned_tokens if exit_token_units is None else exit_token_units
    if quantity > owned_tokens:
        raise ValueError('exit_token_units exceeds unpooled project tokens')
    stresses = (sorted(set(min(bound, amount) for amount in
                          [0, capital // 10, capital // 2, capital, 5 * capital]))
                if demand_cents is None else sorted(set(demand_cents)))

    def quote(external_cash):
        accounts = {owner: Balance(**balance) for owner, balance in balances.items()}
        accounts[_EXTERNAL_BUYER] = Balance(external_cash)
        ledger = Ledger(accounts)
        pool = ConstantProductMarket(
            ledger, fee_bps=market_parameters['fee_bps'],
            lp_shares={'project': actual_report['locked_project_lp_shares']},
        )
        bought = pool.buy(_EXTERNAL_BUYER, external_cash, 'analysis:buy') if external_cash else None
        sold = pool.sell('project', quantity, 'analysis:exit') if quantity else None
        ending_cash = ledger.accounts['project'].cash_cents
        return {
            'external_buy_cents': external_cash,
            'bought_token_units': bought.token_units if bought else 0,
            'buy_fee_cash_cents': bought.fee_cash_cents if bought else 0,
            'exit_cash_proceeds_cents': sold.cash_cents if sold else 0,
            'ending_project_cash_cents': ending_cash,
            'profit_cents': ending_cash - capital,
            'exit_fee_token_units': sold.fee_token_units if sold else 0,
        }

    immediate = quote(0)
    if immediate['profit_cents'] >= 0:
        status, minimum, previous = 'already_break_even', 0, None
    elif not quantity:
        status, minimum, previous = 'no_exit_tokens', None, None
    elif quote(bound)['profit_cents'] < 0:
        status, minimum, previous = 'not_reached_within_bound', None, None
    else:
        low, high = 1, bound
        while low < high:
            midpoint = (low + high) // 2
            if quote(midpoint)['profit_cents'] >= 0:
                high = midpoint
            else:
                low = midpoint + 1
        status, minimum = 'reachable', low
        previous = quote(low - 1)['profit_cents']
    return {
        'schema_version': 'decision-financial-analysis.v1',
        'identity': {
            'world_sha256': actual_report['world_sha256'],
            'engine_sha256': actual_report['engine_sha256'],
            'report_sha256': digest(actual_report),
            'analysis_engine_sha256': ANALYSIS_ENGINE_SHA256,
        },
        'no_launch': {'ending_cash_cents': capital, 'profit_cents': 0},
        'actual': {
            'initial_capital_cents': capital,
            'ending_cash_cents': project['cash_cents'],
            'paid_costs_cents': market_parameters['launch_cost_cents'],
            'locked_lp_cash_deposit_cents': market_parameters['lp_cash_cents'],
            'locked_lp_shares': actual_report['locked_project_lp_shares'],
            'unsold_token_units': owned_tokens,
            'cash_profit_cents': actual_report['project_cash_profit_cents'],
        },
        'hypothetical_exit': {
            'exit_token_units': quantity,
            'cash_proceeds_cents': immediate['exit_cash_proceeds_cents'],
            'ending_cash_cents': immediate['ending_project_cash_cents'],
            'profit_cents': immediate['profit_cents'],
            'fee_token_units': immediate['exit_fee_token_units'],
            'remaining_token_units': owned_tokens - quantity,
        },
        'demand_stress': [quote(amount) for amount in stresses],
        'break_even': {
            'status': status, 'minimum_additional_buy_cents': minimum,
            'search_bound_cents': bound, 'previous_cent_profit_cents': previous,
        },
        'assumptions': list(world['assumptions']),
        'limitations': [
            'Cash amounts are synthetic cents; tokens have no guaranteed redemption or fair value.',
            'Actual cash profit subtracts initial capital after paid modeled costs; locked LP and unsold tokens are excluded.',
            'Only supplied launch costs and modeled trading fees are included. Taxes, venue costs, salaries and other unmodeled expenses are excluded.',
            'No-launch baseline keeps initial capital with zero modeled return, cost or opportunity return.',
            'Each demand row independently adds one externally funded aggregate buyer, then immediately sells the selected project tokens; this changes neither actual history nor other rows.',
            'Aggregate demand is a counterfactual input, not a forecast, affordability estimate or probability. Buyer position limits and existing actor budgets are not enforced for this added account.',
            'AMM fees, price impact and integer rounding apply. Quotes assume immediate settlement with no intervening orders; configured live-round slippage limits are not a demand or execution guarantee.',
            'LP shares remain locked in every counterfactual. Their initial cash deposit is shown separately, not valued as withdrawable cash.',
            'Break-even means hypothetical cash after the selected exit reaches initial project capital; not_reached_within_bound makes no claim beyond the stated bound.',
            *actual_report['limitations'],
        ],
    }
