"""Experimental exact-rational lending settlement, isolated from launch/AMM worlds.

This kernel implements synthetic accounting, not a deployed NEAR contract. Transfers
use rational units (no contract decimal rounding); execution quotes are explicit
scenario inputs, not a DEX estimator. No actor policy or external-event odds live here.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import re

YEAR = 365 * 86400
GRID = 10**12  # accrual precision in base units; matches amount()'s 12 decimals


def floor_grid(value):
    """Round down to the accrual grid so hourly accrual cannot grow denominators unboundedly."""
    return F(value.numerator * GRID // value.denominator, GRID)
ENGINE_SHA256 = sha256(Path(__file__).read_bytes()).hexdigest()


def encoded(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {key: encoded(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encoded(item) for item in value]
    return value


def fingerprint(value):
    raw = json.dumps(encoded(value), sort_keys=True, separators=(',', ':'), allow_nan=False)
    return sha256(raw.encode()).hexdigest()


def amount(value, *, positive=False):
    if type(value) is int:
        result = F(value)
    elif type(value) is str and re.fullmatch(r'\d{1,18}(?:\.\d{1,12})?', value):
        result = F(value)
    else:
        raise ValueError('nonnegative integer or bounded decimal string required')
    if result < 0 or (positive and result == 0) or result > 10**15:
        raise ValueError('amount outside bounds')
    return result


def integer(value, low=0, high=10**12):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer outside bounds')
    return value


def exact_shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('invalid event shape')


class LendingPool:
    """Atomic, idempotent event settlement with replay and conservation checks.

    Supplier interest is accrued as a loan-specific receivable and paid directly
    to its owners on collection. It is not automatically redeposited/compounded.
    Principal claims remain in the pool until withdrawn or written off.
    """
    SCHEMAS = {
        'advance': {'second'}, 'oracle': {'near_usd', 'usdc_usd', 'observed_second'},
        'supply': {'actor', 'usdc'}, 'withdraw': {'actor', 'usdc'},
        'post_collateral': {'actor', 'near'}, 'remove_collateral': {'actor', 'near'},
        'borrow': {'actor', 'usdc'}, 'repay': {'actor', 'usdc'},
        'liquidate': {'actor', 'borrower', 'max_repay_usdc', 'market_near_usd',
                      'impact_bps', 'execution_cost_usdc'},
        'writeoff': {'borrower'}, 'spend': {'category', 'usdc'},
    }

    def __init__(self, settings, actors, *, market_usdc, market_near=0):
        settings = deepcopy(settings)
        m, r = settings['market'], settings['interest']
        for key in ('max_origination_ltv_bps', 'liquidation_ltv_bps', 'liquidation_bonus_bps',
                    'ordinary_close_factor_bps'):
            integer(m[key], 1, 9999)
        if not 0 < m['max_origination_ltv_bps'] < m['liquidation_ltv_bps'] < 10000:
            raise ValueError('LTV must be below liquidation threshold')
        if F(m['liquidation_ltv_bps'], 10000) * (1+F(m['liquidation_bonus_bps'], 10000)) >= 1:
            raise ValueError('threshold and bonus are inconsistent')
        self.ltv, self.threshold = F(m['max_origination_ltv_bps'],10000), F(m['liquidation_ltv_bps'],10000)
        self.bonus, self.close = F(m['liquidation_bonus_bps'],10000), F(m['ordinary_close_factor_bps'],10000)
        self.full_close = amount(m['full_close_when_health_factor_at_or_below'], positive=True)
        if not 0 < self.full_close < 1:
            raise ValueError('invalid full-close health factor')
        self.actor_cap = amount(m['initial_per_borrower_principal_cap_usdc'], positive=True)
        self.pool_cap = amount(m['initial_aggregate_principal_cap_usdc'], positive=True)
        if self.actor_cap > self.pool_cap or m['origination_fee_bps'] != 0:
            raise ValueError('unsupported loan cap or origination fee')
        for key in ('base_borrow_apr_bps','kink_utilization_bps','borrow_apr_at_kink_bps',
                    'borrow_apr_at_full_utilization_bps','protocol_share_of_collected_interest_bps'):
            integer(r[key], 0, 10000)
        self.base = F(r['base_borrow_apr_bps'],10000)
        self.kink = F(r['kink_utilization_bps'],10000)
        self.kink_apr = F(r['borrow_apr_at_kink_bps'],10000)
        self.full_apr = F(r['borrow_apr_at_full_utilization_bps'],10000)
        self.fee_share = F(r['protocol_share_of_collected_interest_bps'],10000)
        if not (0 < self.kink < 1 and self.base <= self.kink_apr <= self.full_apr):
            raise ValueError('invalid rate curve')
        self.max_age = integer(settings['oracle_and_execution']['max_price_age_seconds'],1,86400)
        self.points_rate = amount(settings['supplier_points']['proposed_rate_points_per_allocated_usdc_day'])
        # Other policy variants must not be silently interpreted as this kernel.
        if (r['curve'] != 'piecewise_linear_in_utilization'
            or r['accrual'] != 'simple_interest_on_performing_principal_actual_elapsed_seconds_over_365_days_no_interest_on_interest'
            or r['repayment_allocation'] != 'accrued_interest_then_principal'
            or settings['supplier_points']['selected_basis'] != 'liquidity_actually_borrowed'):
            raise ValueError('unsupported interest or points policy')
        policies = {
            ('withdrawal','policy'):'pay_from_available_lendable_cash_only_queue_unpaid_claims_fifo',
            ('withdrawal','cash_priority'):'service_queued_withdrawals_before_new_loans',
            ('withdrawal','queued_balance_interest'):'remains_a_supplier_claim_until_paid_subject_to_pool_interest_and_losses',
            ('withdrawal','queued_balance_points'):'no_new_points_while_queued_remaining_eligible_suppliers_share_only_their_fraction_of_pool_principal',
            ('supplier_points','allocation'):'performing_principal_times_supplier_eligible_unqueued_principal_claim_over_total_supplier_principal_claims_including_queued_claims',
            ('supplier_points','eligible_base'):'funded_supplier_principal_claims_after_realized_writeoffs_excluding_collateral_reserves_uncollected_interest_and_points',
            ('loss_and_compensation','pool_loss_allocation'):'pro_rata_to_supplier_claims_at_loss_recognition',
            ('loss_and_compensation','compensation'):'pro_rata_to_that_incident_recognized_supplier_losses_from_remaining_reserve_capped_at_actual_loss',
            ('oracle_and_execution','stale_price_policy'):'block_new_borrow_collateral_removal_and_liquidations_allow_repay_and_collateral_addition_no_last_price_execution_guarantee',
        }
        for (section,key), expected in policies.items():
            if settings[section][key] != expected:
                raise ValueError(f'unsupported policy: {section}.{key}')
        if (settings['supplier_points']['idle_supply_points'] is not False
            or settings['supplier_points']['cash_redemption_value'] is not None
            or settings['supplier_points']['future_token_entitlement'] is not None):
            raise ValueError('cash-valued or idle points are unsupported')
        if type(actors) is not dict or not 1 <= len(actors) <= 512:
            raise ValueError('bounded actor mapping required')
        wallets = {}
        for ident, funds in actors.items():
            if type(ident) is not str or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}', ident):
                raise ValueError('invalid actor ID')
            exact_shape(funds, {'usdc', 'near'})
            wallets[ident] = {'usdc': amount(funds['usdc']), 'near': amount(funds['near'])}
        reserve = amount(settings['loss_and_compensation']['reserve_usd_user_selected'])
        treasury = amount(settings['loss_and_compensation']['team_other_initial_cash_usd'])
        self.settings, self.initial_actors = settings, deepcopy(actors)
        self.initial_market = {'market_usdc':market_usdc, 'market_near':market_near}
        self.state = {'second':0, 'oracle':None, 'wallets':wallets,
            'suppliers':{a:F(0) for a in wallets}, 'points':{a:F(0) for a in wallets},
            'loans':{a:{'principal':F(0),'collateral':F(0),'supplier_interest':{},
                         'protocol_interest':F(0)} for a in wallets},
            'cash':F(0), 'queue':[], 'reserve':reserve, 'treasury':treasury,
            'protocol_cash':F(0), 'service_cash':F(0),
            'market_usdc':amount(market_usdc), 'market_near':amount(market_near),
            'principal_losses':F(0), 'interest_losses':F(0), 'compensation':F(0),
            'incidents':[], 'spending':{}, 'history_hash':'0'*64}
        self.journal, self.cache = [], {}
        self.initial_totals = self._totals()
        self.check()

    def _totals(self):
        s = self.state
        usdc = sum(w['usdc'] for w in s['wallets'].values()) + sum(s[k] for k in
            ('cash','reserve','treasury','protocol_cash','service_cash','market_usdc'))
        near = sum(w['near'] for w in s['wallets'].values()) + s['market_near'] + sum(
            loan['collateral'] for loan in s['loans'].values())
        return usdc, near

    def principal(self):
        return sum((v['principal'] for v in self.state['loans'].values()), F(0))

    @staticmethod
    def debt(loan):
        return loan['principal'] + sum(loan['supplier_interest'].values(),F(0)) + loan['protocol_interest']

    def utilization(self):
        debt = self.principal()
        return debt / (self.state['cash']+debt) if self.state['cash']+debt else F(0)

    def apr(self):
        u = self.utilization()
        return (self.base+(self.kink_apr-self.base)*u/self.kink if u <= self.kink else
                self.kink_apr+(self.full_apr-self.kink_apr)*(u-self.kink)/(1-self.kink))

    def _wallet(self, actor):
        if actor not in self.state['wallets']:
            raise ValueError('unknown actor')
        return self.state['wallets'][actor]

    def _prices(self):
        price = self.state['oracle']
        if price is None or not 0 <= self.state['second']-price['observed_second'] <= self.max_age:
            raise ValueError('fresh oracle observation required')
        return price['near_usd'], price['usdc_usd']

    def health(self, actor):
        near, usdc = self._prices()
        loan = self.state['loans'][actor]
        return loan['collateral']*near*self.threshold/(self.debt(loan)*usdc) if self.debt(loan) else None

    def queued(self, actor):
        return sum((q['amount'] for q in self.state['queue'] if q['actor']==actor),F(0))

    def _service_queue(self):
        s = self.state
        while s['cash'] and s['queue']:
            q = s['queue'][0]
            paid = min(s['cash'], q['amount'])
            s['cash'] -= paid
            s['suppliers'][q['actor']] -= paid
            s['wallets'][q['actor']]['usdc'] += paid
            q['amount'] -= paid
            if q['amount'] == 0:
                s['queue'].pop(0)

    def check(self):
        s = self.state
        if self._totals() != self.initial_totals:
            raise ValueError('asset conservation failed')
        if s['cash']+self.principal() != sum(s['suppliers'].values()):
            raise ValueError('principal claims do not reconcile')
        if not 0 <= self.utilization() <= 1:
            raise ValueError('invalid utilization')
        for actor, w in s['wallets'].items():
            loan = s['loans'][actor]
            if min(w.values()) < 0 or min(loan['principal'],loan['collateral'],loan['protocol_interest']) < 0:
                raise ValueError('negative account')
            if any(v < 0 for v in loan['supplier_interest'].values()):
                raise ValueError('negative interest claim')
            if not 0 <= self.queued(actor) <= s['suppliers'][actor] or s['points'][actor] < 0:
                raise ValueError('invalid supplier claim')
        if min(s[k] for k in ('cash','reserve','treasury','protocol_cash','service_cash','market_usdc','market_near')) < 0:
            raise ValueError('negative settlement balance')
        if any(q['amount'] <= 0 for q in s['queue']):
            raise ValueError('invalid queue entry')

    def apply(self, event_id, kind, **payload):
        if type(event_id) is not str or not re.fullmatch(r'[a-zA-Z0-9_-]{1,96}', event_id):
            raise ValueError('invalid event ID')
        if kind not in self.SCHEMAS:
            raise ValueError('unknown lending action')
        exact_shape(payload, self.SCHEMAS[kind])
        event = {'id':event_id, 'kind':kind, 'payload':deepcopy(payload)}
        identity = fingerprint(event)
        if event_id in self.cache:
            old_identity, old = self.cache[event_id]
            if old_identity != identity:
                raise ValueError('event ID reused with changed payload')
            return deepcopy(old)
        old_state = deepcopy(self.state)
        try:
            detail = getattr(self, '_'+kind)(**payload)
            self.check()
            self.state['history_hash'] = fingerprint({'previous':old_state['history_hash'],
                'event':event,'detail':detail,'state':self.state})
            receipt = {'event':event,'detail':encoded(detail), 'state_sha256':fingerprint(self.state),
                       'history_hash':self.state['history_hash']}
        except Exception:
            self.state = old_state
            raise
        self.cache[event_id] = identity, deepcopy(receipt)
        self.journal.append(deepcopy(receipt))
        return receipt

    def _advance(self, second):
        s = self.state
        integer(second, s['second'], 366*86400)
        dt = second-s['second']
        total_supply, principal, apr = sum(s['suppliers'].values()), self.principal(), self.apr()
        interests = F(0)
        if total_supply:
            for actor, claim in s['suppliers'].items():
                eligible = claim-self.queued(actor)
                s['points'][actor] += floor_grid(principal*eligible/total_supply*self.points_rate*F(dt,86400))
            for loan in s['loans'].values():
                interest = loan['principal']*apr*F(dt,YEAR)
                fee, suppliers = floor_grid(interest*self.fee_share), interest*(1-self.fee_share)
                loan['protocol_interest'] += fee
                interests += fee
                for actor, claim in s['suppliers'].items():
                    share = floor_grid(suppliers*claim/total_supply)
                    loan['supplier_interest'][actor] = loan['supplier_interest'].get(actor,F(0)) + share
                    interests += share  # rounding dust stays with the borrower, never minted
        s['second'] = second
        return {'elapsed_seconds':dt, 'borrow_apr':apr, 'interest_receivable_accrued':interests}

    def _oracle(self, near_usd, usdc_usd, observed_second):
        integer(observed_second,0,self.state['second'])
        old = self.state['oracle']
        if old and observed_second < old['observed_second']:
            raise ValueError('oracle timestamp moved backwards')
        self.state['oracle'] = {'near_usd':amount(near_usd,positive=True),
            'usdc_usd':amount(usdc_usd,positive=True),'observed_second':observed_second}
        return {'published':True}

    def _supply(self, actor, usdc):
        w, cash = self._wallet(actor), amount(usdc,positive=True)
        if w['usdc'] < cash:
            raise ValueError('supplier has insufficient funds')
        w['usdc'] -= cash
        self.state['cash'] += cash
        self.state['suppliers'][actor] += cash
        self._service_queue()
        return {'supplied':cash}

    def _withdraw(self, actor, usdc):
        self._wallet(actor)
        cash = amount(usdc,positive=True)
        if cash > self.state['suppliers'][actor]-self.queued(actor):
            raise ValueError('withdrawal exceeds unqueued claim')
        self.state['queue'].append({'actor':actor,'amount':cash})
        before = self.state['wallets'][actor]['usdc']
        self._service_queue()
        return {'requested':cash,'paid_now':self.state['wallets'][actor]['usdc']-before,
                'actor_total_queued':self.queued(actor)}

    def _post_collateral(self, actor, near):
        w, tokens = self._wallet(actor), amount(near,positive=True)
        if w['near'] < tokens:
            raise ValueError('borrower has insufficient collateral')
        w['near'] -= tokens
        self.state['loans'][actor]['collateral'] += tokens
        return {'collateral_added':tokens}

    def _remove_collateral(self, actor, near):
        w, tokens = self._wallet(actor), amount(near,positive=True)
        loan = self.state['loans'][actor]
        if tokens > loan['collateral']:
            raise ValueError('collateral withdrawal exceeds balance')
        # Fresh observations are required even if no debt; deliberately conservative.
        price, usdc = self._prices()
        if self.debt(loan)*usdc > (loan['collateral']-tokens)*price*self.ltv:
            raise ValueError('collateral removal violates LTV')
        loan['collateral'] -= tokens
        w['near'] += tokens
        return {'collateral_removed':tokens}

    def _borrow(self, actor, usdc):
        w, cash = self._wallet(actor), amount(usdc,positive=True)
        near_price, usdc_price = self._prices()
        loan, s = self.state['loans'][actor], self.state
        if s['queue'] or cash > s['cash']:
            raise ValueError('available cash reserved for withdrawals or insufficient')
        if loan['principal']+cash > self.actor_cap or self.principal()+cash > self.pool_cap:
            raise ValueError('principal cap exceeded')
        if (self.debt(loan)+cash)*usdc_price > loan['collateral']*near_price*self.ltv:
            raise ValueError('borrowing violates LTV')
        s['cash'] -= cash
        w['usdc'] += cash
        loan['principal'] += cash
        return {'borrowed':cash}

    def _pay_loan(self, payer, borrower, cash):
        w, loan, s = self._wallet(payer), self.state['loans'][borrower], self.state
        if not 0 < cash <= self.debt(loan) or cash > w['usdc']:
            raise ValueError('invalid or unfunded repayment')
        w['usdc'] -= cash
        due = self.debt(loan)-loan['principal']
        paid_interest = min(due,cash)
        if due:
            ratio = paid_interest/due
            # Partial payments split on the grid; the sub-grid remainder reduces principal.
            part = (lambda v: v) if ratio == 1 else (lambda v: floor_grid(v*ratio))
            paid_interest = F(0)
            for owner, claim in list(loan['supplier_interest'].items()):
                paid = part(claim)
                s['wallets'][owner]['usdc'] += paid
                loan['supplier_interest'][owner] -= paid
                paid_interest += paid
            fee = part(loan['protocol_interest'])
            s['protocol_cash'] += fee
            loan['protocol_interest'] -= fee
            paid_interest += fee
        paid_principal = cash-paid_interest
        loan['principal'] -= paid_principal
        s['cash'] += paid_principal
        self._service_queue()
        return {'paid_interest':paid_interest,'paid_principal':paid_principal}

    def _repay(self, actor, usdc):
        self._wallet(actor)
        return self._pay_loan(actor,actor,amount(usdc,positive=True))

    def _liquidate(self, actor, borrower, max_repay_usdc, market_near_usd, impact_bps, execution_cost_usdc):
        self._wallet(actor); self._wallet(borrower)
        if actor == borrower:
            raise ValueError('self liquidation unsupported; repay instead')
        near, usdc = self._prices()
        loan, s = self.state['loans'][borrower], self.state
        hf = self.health(borrower)
        if hf is None or hf >= 1:
            raise ValueError('position not liquidatable')
        impact = F(integer(impact_bps,0,9999),10000)
        market_price = amount(market_near_usd,positive=True)
        cost = amount(execution_cost_usdc)
        limit = self.debt(loan)*(1 if hf <= self.full_close else self.close)
        seized_per_usdc = (1+self.bonus)*usdc/near
        proceeds_per_near = market_price/usdc*(1-impact)
        cash = min(amount(max_repay_usdc,positive=True),limit,
                   max(F(0),s['wallets'][actor]['usdc']-cost),
                   loan['collateral']/seized_per_usdc,
                   s['market_usdc']/(seized_per_usdc*proceeds_per_near))
        seized = cash*seized_per_usdc
        proceeds = seized*proceeds_per_near
        if cash <= 0 or proceeds < cash+cost:
            raise ValueError('liquidation unprofitable or unfunded under supplied quote')
        detail = self._pay_loan(actor,borrower,cash)
        loan['collateral'] -= seized
        s['market_near'] += seized
        s['market_usdc'] -= proceeds
        s['wallets'][actor]['usdc'] += proceeds-cost
        s['service_cash'] += cost
        return {**detail,'repaid':cash,'collateral_sold_near':seized,
                'sale_proceeds_usdc':proceeds,'execution_cost_usdc':cost,
                'liquidator_profit_usdc':proceeds-cash-cost,'quote_is_scenario_input':True}

    def _writeoff(self, borrower):
        self._wallet(borrower)
        s, loan = self.state, self.state['loans'][borrower]
        if loan['collateral'] or not self.debt(loan):
            raise ValueError('writeoff requires exhausted collateral and residual debt')
        principal, interest = loan['principal'], self.debt(loan)-loan['principal']
        claims = deepcopy(s['suppliers']); total = sum(claims.values())
        if principal > total:
            raise ValueError('unreconciled principal loss')
        losses = {a:principal*c/total if total else F(0) for a,c in claims.items()}
        # Accrued supplier interest lost on this loan belongs to its recorded owners.
        for a, loss in loan['supplier_interest'].items():
            losses[a] += loss
        for a, claim in claims.items():
            principal_loss = principal*claim/total if total else F(0)
            s['suppliers'][a] -= principal_loss
            ratio = s['suppliers'][a]/claim if claim else F(0)
            for q in s['queue']:
                if q['actor'] == a:
                    q['amount'] *= ratio
        s['queue'] = [q for q in s['queue'] if q['amount']]
        total_supplier_loss = sum(losses.values())
        compensation = min(s['reserve'],total_supplier_loss)
        if total_supplier_loss:
            for a, loss in losses.items():
                s['wallets'][a]['usdc'] += compensation*loss/total_supplier_loss
        s['reserve'] -= compensation
        s['compensation'] += compensation
        s['principal_losses'] += principal
        s['interest_losses'] += interest
        incident = {'borrower':borrower,'principal_loss':principal,'interest_loss':interest,
                    'supplier_losses':losses,'compensation':compensation,
                    'protocol_interest_loss':loan['protocol_interest']}
        s['incidents'].append(deepcopy(incident))
        loan['principal'], loan['protocol_interest'], loan['supplier_interest'] = F(0),F(0),{}
        self._service_queue()
        return incident

    def _spend(self, category, usdc):
        limits = {'operations':F(30000),'promotion':F(20000),'partner_support_and_measurement':F(10000)}
        cash = amount(usdc,positive=True)
        if type(category) is not str or category not in limits:
            raise ValueError('unsupported spending category')
        spent = self.state['spending'].get(category,F(0))
        if spent+cash > limits[category] or cash > self.state['treasury']:
            raise ValueError('spending exceeds selected envelope')
        self.state['treasury'] -= cash
        self.state['service_cash'] += cash
        self.state['spending'][category] = spent+cash
        return {'category':category,'paid':cash,'attention_or_delivery_inferred':False}

    def snapshot(self):
        return encoded(deepcopy(self.state))

    def report(self):
        return {'schema_version':'lending-kernel-report.v1','engine_sha256':ENGINE_SHA256,
            'settings':deepcopy(self.settings),'actors':deepcopy(self.initial_actors),
            'market':deepcopy(self.initial_market),'events':deepcopy(self.journal),
            'final_state':self.snapshot(), 'limitations':[
                'Exact-rational settlement except accrual and partial interest splits, rounded down to 1e-12 units.',
                'Market quotes, depth, actor resources and observations are supplied scenario inputs.',
                'This kernel alone supplies no Laya decisions, audience conversion or calibrated event odds.',
                'Interest pays to supplier wallets on collection; redeposit requires another funded action.',
                'Treasury/reserve use USDC units initially valued at $1, not a guaranteed dollar value after a depeg.',
                'Unsold stranded collateral requires an explicit recovery policy; this kernel writes off only after collateral is exhausted.',
                'Additional team capital and cap changes are unsupported here until explicit actions are added.']}


def replay_lending(report):
    if report['schema_version'] != 'lending-kernel-report.v1' or report['engine_sha256'] != ENGINE_SHA256:
        raise ValueError('report schema or engine identity differs')
    pool = LendingPool(report['settings'],report['actors'],**report['market'])
    for receipt in report['events']:
        e = receipt['event']
        actual = pool.apply(e['id'],e['kind'],**e['payload'])
        if actual != receipt:
            raise ValueError('lending event replay mismatch')
    if pool.snapshot() != report['final_state']:
        raise ValueError('lending terminal state replay mismatch')
    return pool
