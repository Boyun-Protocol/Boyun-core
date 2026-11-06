"""NEAR lending launch case: hourly settlement, daily/triggered decisions, campaign delivery.

Inputs are the user-selected case files (settings, funded cast, campaign calendar and a
replayed price path). Decisions come from an explicitly supplied client; settlement stays
in LendingPool. Outsiders become aware only when a followed channel actually delivers;
no conversion rate is assumed. Campaign spending happens only on actual delivery.
"""
from collections import deque
from decimal import Decimal
from fractions import Fraction as F
import json
from pathlib import Path

from .jev import validate_answers
from .lending import LendingPool, fingerprint
from .lending_choices import decide_lending, lending_request, settle_lending_choice

HOUR = 3600
TEAM_OPTIONS = ('status_update', 'extra_kol', 'partner_retention', 'no_action')
SUPPLIER_ROLES = ('friendly_supplier', 'independent_supplier', 'independent_supplier_cohort')
BORROWER_ROLES = ('near_borrower', 'near_borrower_cohort')
DECIDING_ROLES = SUPPLIER_ROLES + BORROWER_ROLES + ('points_seeker',)
BORROW_STEP_USDC = 12500  # a quarter of the selected $50K per-borrower cap
EXTRA_KOL_USDC = 10000


class CachedClient:
    """Append-only decision cache so an interrupted run resumes without repeat calls."""
    def __init__(self, client, path=None):
        self.client, self.path, self.saved = client, path, {}
        self.calls = {'new': 0, 'cached': 0}
        if path and Path(path).exists():
            for line in Path(path).read_text().splitlines():
                entry = json.loads(line)
                self.saved.setdefault(entry['key'], deque()).append(entry['response'])

    def evaluate(self, *, state, questions):
        key = fingerprint({'state': state, 'questions': questions})
        if self.saved.get(key):
            self.calls['cached'] += 1
            return self.saved[key].popleft()
        response = self.client.evaluate(state=state, questions=questions)
        self.calls['new'] += 1
        if self.path:
            with open(self.path, 'a') as handle:
                handle.write(json.dumps({'key': key, 'response': response}, sort_keys=True) + '\n')
        return response


def price_text(value):
    return format(Decimal(str(value)).quantize(Decimal('0.000001')), 'f')


def usd(value):
    return f'${float(value):,.0f}'


class LendingCase:
    def __init__(self, settings, cast, calendar, path, client, days):
        if type(days) is not int or not 1 <= days <= 90:
            raise ValueError('days must be 1..90')
        rows = path['path']
        if len(rows) < days * 24 or [r['hour'] for r in rows[:days * 24]] != list(range(days * 24)):
            raise ValueError('price path must cover every simulated hour in order')
        self.rows, self.days, self.client, self.cal = rows, days, client, calendar
        self.cad = calendar['cadence']
        self.actors = {a['id']: a for a in cast['actors']}
        wallets = {a['id']: {'usdc': a.get('usdc', 0) + a.get('deposited_usdc', 0) + a.get('outside_usdc', 0),
                             'near': a.get('near', 0)}
                   for a in cast['actors'] if a['role'] in DECIDING_ROLES + ('liquidator',)}
        self.pool = LendingPool(settings, wallets, market_usdc=calendar['liquidation']['exit_market_usdc'])
        self.aware_since = {a: 0 for a in calendar['aware_from_opening']}
        self.queue = [dict(item, status='scheduled', delayed=False) for item in calendar['items']]
        self.campaign, self.decisions, self.daily, self.triggers = [], [], [], []
        self.public_news, self.private_news = [], {}
        self.edges, self.cooldown, self.counter = {}, {}, 0
        self.extra_kol_used = False

    # ---- ledger helpers -------------------------------------------------
    def apply(self, kind, prefix, **payload):
        self.counter += 1
        return self.pool.apply(f'{prefix}-{self.counter}', kind, **payload)

    def price(self, hour):
        return self.rows[hour]['near_close_scaled']

    def metrics(self, hour):
        s = self.pool.state
        return {'hour': hour, 'day': hour // 24, 'near_usd': self.price(hour),
                'supply_usdc': float(sum(s['suppliers'].values())), 'borrowed_usdc': float(self.pool.principal()),
                'utilization': float(self.pool.utilization()), 'borrow_apr': float(self.pool.apr()),
                'queued_usdc': float(sum((q['amount'] for q in s['queue']), F(0))),
                'reserve_usdc': float(s['reserve']), 'treasury_usdc': float(s['treasury']),
                'principal_losses': float(s['principal_losses']), 'aware_actors': len(self.aware_since),
                'supply_by_actor': {a: float(v) for a, v in s['suppliers'].items() if v},
                'points_by_actor': {a: float(v) for a, v in s['points'].items() if v}}

    # ---- campaign -------------------------------------------------------
    def ask_partner(self, item, hour):
        options = {'accept': f"Publish now; paid {usd(item['spend']['usdc'])} on delivery.",
                   'decline': 'Decline this request.'}
        if not item['delayed']:
            options['delay'] = 'Delay three days, then decide.'
        state = {'role': 'distribution_partner', 'day': str(hour // 24),
                 'profile': self.cal['distribution_partners'][item['partner']],
                 'request': item['news'][:200], 'protocol_supply_usdc': usd(sum(self.pool.state['suppliers'].values()))}
        questions = {'action': {'type': 'choice', 'instructions':
                     'Decide whether to publish this paid announcement to your audience.', 'criteria': options}}
        return self.ask(item['partner'], 'distribution_partner', hour, item['id'], state, questions)

    def deliver(self, item, hour):
        if item['kind'] == 'partner':
            choice = self.ask_partner(item, hour)
            if choice == 'delay':
                item.update(hour=hour + self.cad['partner_delay_hours'], delayed=True)
                return
            if choice == 'decline':
                item['status'] = 'declined'
                self.campaign.append({**item, 'decided_hour': hour})
                return
            self.apply('spend', 'spend', **item['spend'])
        news = item.get('news') or self.status_text(hour)
        self.public_news.append({'hour': hour, 'channels': item['channels'], 'text': news})
        for actor, channels in self.cal['follows'].items():
            if actor not in self.aware_since and set(channels) & set(item['channels']):
                self.aware_since[actor] = hour
        item['status'] = 'delivered'
        self.campaign.append({**item, 'delivered_hour': hour, 'news': news})
        if item['kind'] == 'status_update':
            self.fire('update', hour, [a for a, c in self.cal['follows'].items()
                                       if set(c) & set(item['channels']) and a in self.aware_since])

    def status_text(self, hour):
        m = self.metrics(hour)
        return (f"Day {m['day']} update: supply {usd(m['supply_usdc'])}, borrowed {usd(m['borrowed_usdc'])}, "
                f"utilization {m['utilization']:.0%}, queued withdrawals {usd(m['queued_usdc'])}.")

    def run_campaign(self, hour):
        for item in self.queue:
            if item['status'] == 'scheduled' and item['hour'] == hour:
                self.deliver(item, hour)

    # ---- liquidation ----------------------------------------------------
    def liquidate(self, hour):
        spec = self.cal['liquidation']['liquidators']
        depth = {a: F(v['depth_usd_per_hour']) for a, v in spec.items()}
        price = F(price_text(self.price(hour)))
        bonus = self.pool.bonus
        for borrower in sorted(self.pool.state['loans']):
            loan = self.pool.state['loans'][borrower]
            for liquidator in sorted(spec):
                health = self.pool.health(borrower) if self.pool.debt(loan) else None
                if health is None or health >= 1 or depth[liquidator] <= 0:
                    break
                v = spec[liquidator]
                margin = (1 + bonus) * (1 - F(v['impact_bps'], 10000)) - 1
                if margin < F(v['min_profit_bps'], 10000):
                    continue
                try:
                    receipt = self.apply('liquidate', f'liq{hour}', actor=liquidator, borrower=borrower,
                        max_repay_usdc=int(depth[liquidator] / (1 + bonus)) + 1, market_near_usd=price_text(self.price(hour)),
                        impact_bps=v['impact_bps'], execution_cost_usdc=v['cost_usdc'])
                except ValueError:
                    continue
                depth[liquidator] -= F(receipt['detail']['collateral_sold_near']) * price
            if not loan['collateral'] and self.pool.debt(loan):
                self.apply('writeoff', f'wo{hour}', borrower=borrower)

    # ---- triggers -------------------------------------------------------
    def fire(self, name, hour, actors):
        self.triggers.append({'hour': hour, 'trigger': name, 'actors': sorted(actors)})
        for actor in actors:
            if hour - self.cooldown.get(actor, -10**9) >= self.cad['trigger_cooldown_hours']:
                self.cooldown[actor] = hour
                self.pending.setdefault(actor, name)

    def edge(self, key, condition):
        rising = condition and not self.edges.get(key, False)
        self.edges[key] = condition
        return rising

    def check_triggers(self, hour):
        aware = [a for a in self.aware_since if self.actors[a]['role'] in DECIDING_ROLES]
        suppliers = [a for a in aware if self.role(a, hour) == 'supplier']
        if hour >= 24:
            move = self.price(hour) / self.price(hour - 24) - 1
            if self.edge('near', abs(move) >= float(self.cad['near_move_trigger'])):
                self.fire('near_move', hour, aware + ['team'])
        if self.edge('util', self.pool.utilization() >= F(self.cad['utilization_trigger'])):
            self.fire('utilization', hour, suppliers + ['team'])
        if self.edge('queue', bool(self.pool.state['queue'])):
            self.fire('queue', hour, suppliers + ['team'])
        for actor in aware:
            if self.actors[actor]['role'] in BORROWER_ROLES + ('points_seeker',):
                health = self.pool.health(actor)
                if self.edge(('health', actor), health is not None and health < F(self.cad['health_trigger'])):
                    self.fire('health', hour, [actor])

    # ---- decisions ------------------------------------------------------
    def role(self, actor, hour):
        kind = self.actors[actor]['role']
        if kind == 'points_seeker':
            return 'borrower' if self.pending.get(actor) == 'health' or (hour // 24) % 2 else 'supplier'
        return 'supplier' if kind in SUPPLIER_ROLES else 'borrower'

    def news_for(self, actor, hour):
        channels = set(self.cal['follows'].get(actor, ['team_socials', 'discord']))
        window = self.cad['news_window_hours']
        recent = [n['text'] for n in self.public_news
                  if hour - n['hour'] <= window and channels & set(n['channels'])]
        parts = []
        if hour >= 24:
            parts.append(f'NEAR 24h {self.price(hour) / self.price(hour - 24) - 1:+.1%}.')
        private = self.private_news.get(actor)
        if private and hour - private['hour'] <= window:
            parts.append(private['text'])
        if recent:
            parts.append(recent[-1])
        parts.append(self.cal['outside_option_news'])
        return ' '.join(parts)[:240]

    def ask(self, actor, role, hour, reason, state, questions):
        response = self.client.evaluate(state=state, questions=questions)
        answer = validate_answers(response['answers'], questions)['action']
        self.decisions.append({'hour': hour, 'actor': actor, 'role': role, 'reason': reason,
                               'options': sorted(questions['action']['criteria']), 'choice': answer['choice'],
                               'confidence': answer.get('confidence'), 'probabilities': answer.get('probabilities')})
        return answer['choice']

    def decide_actor(self, actor, hour, reason):
        role, spec = self.role(actor, hour), self.actors[actor]
        total_usdc = spec.get('usdc', 0) + spec.get('deposited_usdc', 0) + spec.get('outside_usdc', 0)
        step_usdc = (BORROW_STEP_USDC if role == 'borrower' else min(100000, max(1000, total_usdc // 4)))
        step_near = min(100000, max(1, spec.get('near', 0) // 4))
        profile = (spec.get('incentive') or spec.get('need') or '')[:160]
        request = lending_request(self.pool, actor, role, news=self.news_for(actor, hour), profile=profile,
                                  step_usdc=step_usdc, step_near=step_near)
        record = decide_lending(self.pool, request, self.client)
        self.counter += 1
        settled = settle_lending_choice(self.pool, record, f'd{hour}-{self.counter}')
        q = record['response']['answers']['action'] if record['model_used'] else {}
        self.decisions.append({'hour': hour, 'actor': actor, 'role': role, 'reason': reason,
                               'options': sorted(request['actions']), 'choice': record['choice'],
                               'model_used': record['model_used'], 'confidence': q.get('confidence'),
                               'probabilities': q.get('probabilities'),
                               'event_id': settled.get('event_id') or settled['event']['id']})

    def decide_team(self, hour, reason):
        s, m = self.pool.state, self.metrics(hour)
        options = {'status_update': 'Publish a public status update with current figures.',
                   'partner_retention': 'Send friendly partners a private message asking them to stay.',
                   'no_action': 'Take no action now.'}
        promo_left = F(20000) - s['spending'].get('promotion', F(0))
        if not self.extra_kol_used and promo_left >= EXTRA_KOL_USDC:
            options['extra_kol'] = f'Ask the KOL for one more paid post ({usd(EXTRA_KOL_USDC)} on delivery).'
        state = {'role': 'team', 'day': str(hour // 24), 'trigger': reason, 'near_usd': price_text(self.price(hour)),
                 'supply_usdc': usd(m['supply_usdc']), 'borrowed_usdc': usd(m['borrowed_usdc']),
                 'utilization': f"{m['utilization']:.0%}", 'queued_withdrawals_usdc': usd(m['queued_usdc']),
                 'reserve_usdc': usd(m['reserve_usdc']), 'treasury_usdc': usd(m['treasury_usdc']),
                 'losses_usdc': usd(m['principal_losses']), 'aware_actors': str(m['aware_actors'])}
        questions = {'action': {'type': 'choice', 'criteria': options, 'instructions':
                     'You run the lending protocol team. You may only communicate or spend held promotion.'}}
        choice = self.ask('team', 'team', hour, reason, state, questions)
        if choice == 'status_update':
            self.deliver({'id': f'team_update_{hour}', 'kind': 'status_update',
                          'channels': ['team_socials', 'discord'], 'status': 'scheduled'}, hour)
        elif choice == 'partner_retention':
            text = 'Private from team: please keep your deposit; $10K reserve covers losses pro rata.'
            for actor, spec in self.actors.items():
                if spec['role'] == 'friendly_supplier':
                    self.private_news[actor] = {'hour': hour, 'text': text}
        elif choice == 'extra_kol':
            self.extra_kol_used = True
            self.queue.append({'id': f'extra_kol_{hour}', 'hour': hour + 1, 'kind': 'partner',
                'partner': 'amplifier_kol', 'channels': ['paid_kol'], 'status': 'scheduled', 'delayed': False,
                'spend': {'category': 'promotion', 'usdc': EXTRA_KOL_USDC},
                'news': 'Paid KOL follow-up: NEAR lending market update and supplier points.'})

    def decide(self, hour):
        due = dict(self.pending)
        if hour % 24 == self.cad['daily_decision_hour']:
            for actor in self.aware_since:
                if self.actors[actor]['role'] in DECIDING_ROLES:
                    due.setdefault(actor, 'daily')
            day = hour // 24
            if day and day % self.cad['team_weekly_days'] == 0:
                due.setdefault('team', 'weekly')
        for actor in sorted(due):
            if actor == 'team':
                self.decide_team(hour, due[actor])
            else:
                self.decide_actor(actor, hour, due[actor])

    # ---- main loop ------------------------------------------------------
    def run(self):
        for actor, spec in sorted(self.actors.items()):
            if spec.get('deposited_usdc'):
                self.apply('supply', 'open', actor=actor, usdc=spec['deposited_usdc'])
        for hour in range(self.days * 24):
            self.pending = {}
            self.apply('advance', 'adv', second=hour * HOUR)
            self.apply('oracle', 'px', near_usd=price_text(self.price(hour)),
                       usdc_usd=price_text(self.rows[hour]['usdc_usdt_close']), observed_second=hour * HOUR)
            self.run_campaign(hour)
            self.liquidate(hour)
            self.check_triggers(hour)
            self.decide(hour)
            if hour % 24 == 23:
                self.daily.append(self.metrics(hour))
        return self


def run_case(settings, cast, calendar, path, client, *, days=90, cache_path=None):
    cached = CachedClient(client, cache_path)
    case = LendingCase(settings, cast, calendar, path, cached, days).run()
    return {'pool': case.pool, 'decisions': case.decisions, 'campaign': case.campaign,
            'aware_since': case.aware_since, 'daily': case.daily, 'triggers': case.triggers,
            'calls': dict(cached.calls)}
