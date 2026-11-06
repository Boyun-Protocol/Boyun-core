"""Compact, actor-private lending decisions using an explicitly supplied client.

No client selection, hidden fallback, campaign conversion or model calls on import.
Menus are proposed deterministic policy; settlement stays in LendingPool.
"""
from copy import deepcopy
from fractions import Fraction as F

from .jev import validate_answers
from .lending import fingerprint


def display(value):
    """Bounded human display only; exact settlement amounts stay in the menu."""
    return f'{float(value):.4f}'


def lending_request(pool, actor, role, *, news='', profile='', step_usdc=5000, step_near=2500):
    if role not in ('supplier', 'borrower'):
        raise ValueError('explicit supplier or borrower role required')
    if type(news) is not str or len(news) > 240:
        raise ValueError('bounded public news required')
    if type(profile) is not str or len(profile) > 160:
        raise ValueError('bounded actor-private profile required')
    if type(step_usdc) is not int or not 1 <= step_usdc <= 100000:
        raise ValueError('bounded positive USDC menu step required')
    if type(step_near) is not int or not 1 <= step_near <= 100000:
        raise ValueError('bounded positive NEAR menu step required')
    if actor not in pool.state['wallets']:
        raise ValueError('unknown actor')
    s, w = pool.state, pool.state['wallets'][actor]
    loan = s['loans'][actor]
    # State is explicitly assembled from this actor's own resources and public
    # pool totals; no other wallets, private partner terms or future events.
    state = {'hour':display(F(s['second'],3600)), 'role':role,
        'own_usdc':display(w['usdc']), 'own_near':display(w['near']),
        'own_supply_claim':display(s['suppliers'][actor]),
        'own_queued_withdrawal':display(pool.queued(actor)),
        'own_collateral_near':display(loan['collateral']),
        'own_total_debt_usdc':display(pool.debt(loan)),
        'own_points':display(s['points'][actor]),
        'pool_available_usdc':display(s['cash']),
        'pool_principal_usdc':display(pool.principal()),
        'borrow_apr':display(pool.apr()),
        'points_terms':'1 point per allocated borrowed USDC-day; idle and queued balances earn none. No cash redemption or guaranteed token.',
        'news':news}
    if profile:
        state['profile'] = profile
    try:
        near, usdc = pool._prices()
        state.update(near_usd=display(near),usdc_usd=display(usdc),oracle='fresh')
    except ValueError:
        near = usdc = None
        state['oracle'] = 'missing_or_stale; borrow and collateral withdrawal unavailable'
    candidates = []

    def offer(ident, kind, key, quantity, unit):
        # Menu uses bounded whole base units. Fractional settlement can still
        # accrue in the kernel; this intentionally limits actor action granularity.
        n = int(quantity)
        if n <= 0:
            return
        payload = {'actor':actor, key:n}
        probe = deepcopy(pool)
        try:
            probe.apply(f'menu-{ident}',kind,**payload)
        except ValueError:
            return
        candidates.append((ident,kind,payload,f'{kind.replace("_"," ")} {n} {unit}'))

    if role == 'supplier':
        offer('supply','supply','usdc',min(step_usdc,w['usdc']),'USDC')
        offer('withdraw','withdraw','usdc',min(step_usdc,s['suppliers'][actor]-pool.queued(actor)),'USDC claim')
    else:
        offer('post','post_collateral','near',min(step_near,w['near']),'NEAR collateral')
        if near is not None:
            capacity = max(F(0),loan['collateral']*near*pool.ltv/usdc-pool.debt(loan))
            offer('borrow','borrow','usdc',min(step_usdc,s['cash'],capacity,
                pool.actor_cap-loan['principal'],pool.pool_cap-pool.principal()),'USDC')
            if not pool.debt(loan):
                offer('remove','remove_collateral','near',min(step_near,loan['collateral']),'NEAR collateral')
        offer('repay','repay','usdc',min(step_usdc,w['usdc'],pool.debt(loan)),'USDC debt')
    options = {'wait':'Wait; do not change balances.'}
    actions = {'wait':None}
    for ident,kind,payload,label in candidates:
        options[ident] = label
        actions[ident] = {'kind':kind,'payload':payload}
    if len(options) == 1:
        return {'actor':actor,'state':state,'questions':None,'actions':actions,
                'kernel_state_sha256':fingerprint(s),'policy':'forced_wait_no_feasible_whole_unit_action'}
    goal = ('Choose whether to supply or withdraw using interest, risk, points and cash needs.' if role == 'supplier'
            else 'Choose whether to post collateral, borrow, repay or wait given debt risk and liquidity needs.')
    return {'actor':actor,'state':state,'actions':actions,
        'kernel_state_sha256':fingerprint(s),'policy':'bounded_whole_unit_menu_v1',
        'questions':{'action':{'type':'choice','instructions':goal,'criteria':options}}}


def decide_lending(pool, request, client):
    """Evaluate one bounded request without settling; caller retains the receipt."""
    if request['kernel_state_sha256'] != fingerprint(pool.state):
        raise ValueError('request belongs to a different lending state')
    if request['questions'] is None:
        return {'request':deepcopy(request),'request_sha256':fingerprint(request),
                'choice':'wait','model_used':False,'response':None}
    response = client.evaluate(state=request['state'],questions=request['questions'])
    answers = validate_answers(response['answers'],request['questions'])
    return {'request':deepcopy(request),'request_sha256':fingerprint(request),
            'choice':answers['action']['choice'],'model_used':True,'response':deepcopy(response)}


def settle_lending_choice(pool, record, event_id):
    request = record['request']
    if fingerprint(request) != record['request_sha256'] or request['kernel_state_sha256'] != fingerprint(pool.state):
        raise ValueError('altered request or stale lending state')
    choice = record['choice']
    if choice not in request['actions']:
        raise ValueError('unknown lending option')
    if record['model_used']:
        answers = validate_answers(record['response']['answers'],request['questions'])
        if choice != answers['action']['choice']:
            raise ValueError('choice differs from recorded model response')
    elif choice != 'wait' or request['questions'] is not None:
        raise ValueError('nonmodel decision must be forced wait')
    action = request['actions'][choice]
    if action is None:
        return {'event_id':event_id,'action':'wait','state_sha256':fingerprint(pool.state)}
    return pool.apply(event_id,action['kind'],**action['payload'])
