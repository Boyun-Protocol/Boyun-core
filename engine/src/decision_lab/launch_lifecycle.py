"""Versioned fourteen-day launch estimate with conserved real cash and causal policies.

Virtual curve reserves price trades but never become withdrawable money. This is
a disclosed static-fee estimate, not a pump.fun transaction/program adapter.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

from .agent_worlds import canonical, digest, _int, _text
from .launch_decision_policy import HORIZON, HOUR, volume_signal, exit_deferred, response_branches
from .randomness import keyed_rng


LIFECYCLE_HASH = sha256(Path(__file__).read_bytes() + Path(__file__).with_name('launch_decision_policy.py').read_bytes()
                        + Path(__file__).with_name('randomness.py').read_bytes()).hexdigest()


def validate_lifecycle(value):
    required = {'schema_version', 'id', 'start_time', 'decision_seconds', 'supply', 'curve_inventory',
                'virtual_cash_cents', 'virtual_tokens', 'fee_bps', 'max_slippage_bps', 'founder', 'actors',
                'kol_ids', 'kol_cash_cents', 'kol_supply_bps', 'events', 'campaigns', 'regime',
                'activity_multiplier', 'assumptions'}
    if type(value) is not dict or set(value) != required or value['schema_version'] != 'launch-lifecycle.v1':
        raise ValueError('launch-lifecycle.v1 shape required')
    if len(canonical(value)) > 524288:
        raise ValueError('bounded lifecycle world required')
    start = datetime.fromisoformat(value['start_time'].replace('Z', '+00:00'))
    if start.utcoffset() is None:
        raise ValueError('timezone required')
    schedule = value['decision_seconds']
    if type(schedule) is not list or not 337 <= len(schedule) <= 4096:
        raise ValueError('bounded fourteen-day schedule required')
    for second in schedule:
        _int(second, 0, HORIZON)
    if schedule != sorted(set(schedule)) or schedule[0] != 0 or schedule[-1] != HORIZON:
        raise ValueError('full horizon required')
    if not set(range(0, HORIZON + 1, HOUR)) <= set(schedule):
        raise ValueError('every hourly boundary required')
    _int(value['supply'], 1)
    _int(value['curve_inventory'], 1, value['supply'] - 1)
    _int(value['virtual_tokens'], value['curve_inventory'] + 1)
    _int(value['virtual_cash_cents'], 1)
    _int(value['fee_bps'], 0, 2000)
    _int(value['max_slippage_bps'], 0, 10000)
    _int(value['activity_multiplier'], 1, 5)
    if value['regime'] not in {'BULL', 'BEAR'}:
        raise ValueError('explicit conditional regime required')
    actors = value['actors']
    if type(actors) is not list or not 2 <= len(actors) <= 32:
        raise ValueError('bounded actor roster required')
    identifiers = set()
    for actor in actors:
        if set(actor) != {'id', 'role', 'goal', 'cash_cents', 'ticket_cents'}:
            raise ValueError('explicit actor role and resources required')
        _text(actor['id'], 48)
        _text(actor['goal'], 800)
        if actor['id'] in identifiers or actor['id'] in {'venue', 'reserve', 'fees', 'services', 'migration'}:
            raise ValueError('unique actor IDs required')
        identifiers.add(actor['id'])
        _int(actor['cash_cents'])
        _int(actor['ticket_cents'])
    founder = value['founder']
    if set(founder) != {'id', 'capital_cents', 'reserve_cents', 'position_cents', 'upfront_cents',
                        'loss_budget_cents', 'response_delay_seconds'} or founder['id'] not in identifiers:
        raise ValueError('explicit founder policy required')
    for key in ('capital_cents', 'reserve_cents', 'position_cents', 'upfront_cents', 'loss_budget_cents'):
        _int(founder[key])
    _int(founder['response_delay_seconds'], 0, 1799)
    if founder['reserve_cents'] + founder['position_cents'] + founder['upfront_cents'] > founder['capital_cents']:
        raise ValueError('funded reserve and position budget required')
    if next(actor for actor in actors if actor['id'] == founder['id'])['cash_cents'] != 0:
        raise ValueError('founder funding must not be double counted')
    _int(value['kol_cash_cents'], 0, founder['upfront_cents'])
    _int(value['kol_supply_bps'], 0, 1000)
    if type(value['kol_ids']) is not list or len(set(value['kol_ids'])) != len(value['kol_ids']) or not set(value['kol_ids']) <= identifiers - {founder['id']}:
        raise ValueError('explicit paid partner recipients required')
    if (value['kol_cash_cents'] or value['kol_supply_bps']) and not value['kol_ids']:
        raise ValueError('KOL grants need recipients')
    for collection in ('events', 'campaigns'):
        if type(value[collection]) is not list or len(value[collection]) > 128:
            raise ValueError('bounded event list required')
    for event in value['events']:
        if set(event) != {'id', 'second', 'text', 'source_ref', 'evidence_status'}:
            raise ValueError('sourced or justified event required')
        _int(event['second'], 0, HORIZON)
        _text(event['text'], 800)
    for campaign in value['campaigns']:
        if set(campaign) != {'id', 'due_second', 'expires_second', 'delivery_bps', 'text'}:
            raise ValueError('explicit campaign delivery required')
        _int(campaign['due_second'], 0, HORIZON)
        _int(campaign['expires_second'], campaign['due_second'] + 1, HORIZON + 86400)
        _int(campaign['delivery_bps'], 0, 10000)
    if type(value['assumptions']) is not list or not value['assumptions']:
        raise ValueError('explicit lifecycle assumptions required')
    return deepcopy(value)


class LaunchLifecycle:
    def __init__(self, package, seed=31, response_policy='pause-and-observe'):
        self.package = validate_lifecycle(package)
        self.seed = _int(seed, 0, 10**9)
        if response_policy not in {'pause-and-observe', 'staged-exit', 'fork-at-first-alert'}:
            raise ValueError('explicit response policy required')
        self.response_policy = response_policy
        self.schedule = list(package['decision_seconds'])
        self.index = 0
        self.actors = {actor['id']: actor for actor in self.package['actors']}
        self.founder = package['founder']['id']
        self.wallets = {actor['id']: {'cash_cents': actor['cash_cents'], 'tokens': 0} for actor in package['actors']}
        self.wallets[self.founder]['cash_cents'] = package['founder']['capital_cents'] - package['founder']['reserve_cents']
        self.wallets.update(reserve={'cash_cents': package['founder']['reserve_cents'], 'tokens': 0},
                            venue={'cash_cents': 0, 'tokens': package['curve_inventory']},
                            migration={'cash_cents': 0, 'tokens': package['supply'] - package['curve_inventory']},
                            fees={'cash_cents': 0, 'tokens': 0}, services={'cash_cents': 0, 'tokens': 0})
        self.initial_totals = (self.cash_total(), self.token_total())
        self.virtual_cash = package['virtual_cash_cents']
        self.virtual_tokens = package['virtual_tokens']
        self.phase = 'curve'
        self.migrated_at = None
        self.prepared_index = -1
        self.trades = []
        self.history = []
        self.public = []
        self.messages = []
        self.last_choices = {}
        self.last_fills = {}
        self.cumulative = {actor: {'bought_cents': 0, 'sold_cents': 0} for actor in self.actors}
        self.response = None
        self.alert_pending = False
        self.founder_buys = 0
        self.ongoing_spent = 0
        self.post_migration_funded = False
        self.kol_granted = 0
        self.mm_paused = False
        self.preparation_receipts = []
        self.current_events = []
        self.chain_hash = digest({'package': package, 'seed': seed, 'engine': LIFECYCLE_HASH})

    @property
    def second(self):
        return self.schedule[self.index]

    def cash_total(self):
        return sum(wallet['cash_cents'] for wallet in self.wallets.values())

    def token_total(self):
        return sum(wallet['tokens'] for wallet in self.wallets.values())

    def _transfer(self, sender, recipient, cash=0, tokens=0):
        if cash < 0 or tokens < 0 or self.wallets[sender]['cash_cents'] < cash or self.wallets[sender]['tokens'] < tokens:
            raise ValueError('unfunded transfer')
        self.wallets[sender]['cash_cents'] -= cash
        self.wallets[recipient]['cash_cents'] += cash
        self.wallets[sender]['tokens'] -= tokens
        self.wallets[recipient]['tokens'] += tokens

    def _price(self):
        if self.phase == 'curve':
            return Fraction(self.virtual_cash, 100 * self.virtual_tokens)
        return Fraction(self.wallets['venue']['cash_cents'], 100 * max(1, self.wallets['venue']['tokens']))

    def market(self):
        now = self.second if self.index < len(self.schedule) else HORIZON
        circulating = (self.package['supply'] if self.phase == 'pool' else
                       self.package['supply'] - self.wallets['venue']['tokens'] - self.wallets['migration']['tokens'])
        return {'second': now, 'phase': self.phase, 'migrated_at': self.migrated_at,
                'price_usd_exact': str(self._price()), 'market_cap_usd_exact': str(self._price() * circulating),
                'fdv_usd_exact': str(self._price() * self.package['supply']),
                'circulating_tokens': circulating,
                'real_cash_cents': self.wallets['venue']['cash_cents'], 'real_tokens': self.wallets['venue']['tokens'],
                'total_volume_cents': sum(trade['cash_cents'] for trade in self.trades),
                'six_hour_signal': volume_signal(self.trades, now)}

    def _quoted_output(self, buy, amount):
        venue = self.wallets['venue']
        cash, tokens = ((self.virtual_cash, self.virtual_tokens) if self.phase == 'curve'
                        else (venue['cash_cents'], venue['tokens']))
        if buy:
            net = amount * (10000 - self.package['fee_bps']) // 10000
            return min(venue['tokens'], tokens * net // (cash + net))
        gross = cash * amount // max(1, tokens + amount)
        return gross - gross * self.package['fee_bps'] // 10000

    def _trade(self, actor, buy, amount, reason, minimum_output=0):
        if type(amount) is not int or amount <= 0:
            return {'actor': actor, 'status': 'no_inventory_or_budget', 'reason': reason}
        fee_bps = self.package['fee_bps']
        venue = self.wallets['venue']
        input_reserve, output_reserve = ((self.virtual_cash, self.virtual_tokens) if self.phase == 'curve'
                                        else (venue['cash_cents'], venue['tokens']))
        if buy:
            if self.wallets[actor]['cash_cents'] < amount:
                raise ValueError('unaffordable buy')
            net = amount * (10000 - fee_bps) // 10000
            tokens = output_reserve * net // (input_reserve + net)
            if self.phase == 'curve' and tokens > venue['tokens']:
                tokens = venue['tokens']
                net = (input_reserve * tokens + output_reserve - tokens - 1) // (output_reserve - tokens)
                amount = (net * 10000 + 9999 - fee_bps) // (10000 - fee_bps)
            fee = amount - net
            if tokens < minimum_output:
                return {'actor': actor, 'status': 'rejected_slippage', 'reason': reason}
            if tokens <= 0 or tokens >= output_reserve:
                return {'actor': actor, 'status': 'rejected_dust', 'reason': reason}
            self._transfer(actor, 'venue', cash=net)
            self._transfer(actor, 'fees', cash=fee)
            self._transfer('venue', actor, tokens=tokens)
            if self.phase == 'curve':
                self.virtual_cash += net
                self.virtual_tokens -= tokens
            if actor == self.founder:
                self.founder_buys += amount
                if reason == 'actor_choice':
                    self.ongoing_spent += amount
            self.cumulative[actor]['bought_cents'] += amount
        else:
            tokens = min(amount, self.wallets[actor]['tokens'])
            gross = input_reserve * tokens // (output_reserve + tokens)
            if gross > venue['cash_cents'] or gross <= 0:
                return {'actor': actor, 'status': 'rejected_liquidity', 'reason': reason}
            fee = gross * fee_bps // 10000
            amount = gross - fee
            if amount < minimum_output:
                return {'actor': actor, 'status': 'rejected_slippage', 'reason': reason}
            self._transfer(actor, 'venue', tokens=tokens)
            self._transfer('venue', actor, cash=amount)
            self._transfer('venue', 'fees', cash=fee)
            if self.phase == 'curve':
                self.virtual_cash -= gross
                self.virtual_tokens += tokens
            self.cumulative[actor]['sold_cents'] += amount
        self.trades.append({'second': self.second, 'cash_cents': amount})
        receipt = {'actor': actor, 'status': 'executed', 'side': 'buy' if buy else 'sell',
                   'cash_cents': amount, 'tokens': tokens, 'fee_cents': fee, 'reason': reason}
        self.last_fills[actor] = deepcopy(receipt)
        if self.phase == 'curve' and venue['tokens'] == 0:
            self._transfer('migration', 'venue', tokens=self.wallets['migration']['tokens'])
            self.phase = 'pool'
            self.migrated_at = self.second
            self.current_events.append({'kind': 'migration', 'second': self.second,
                                        'text': 'Estimate migration: only real collected cash funds the pool; virtual cash is not money.'})
        return receipt

    def _campaigns(self):
        result = []
        for campaign in self.package['campaigns']:
            if self.second < campaign['due_second']:
                continue
            succeeds = keyed_rng(self.seed, 'lifecycle-delivery', campaign['id']).randrange(10000) < campaign['delivery_bps']
            status = 'failed' if not succeeds else 'expired' if self.second >= campaign['expires_second'] else 'active'
            result.append({'id': campaign['id'], 'status': status, 'text': campaign['text']})
        return result

    def _founder_exit_quote(self):
        tokens = self.wallets[self.founder]['tokens']
        reserve_cash, reserve_tokens = ((self.virtual_cash, self.virtual_tokens) if self.phase == 'curve'
                                       else (self.wallets['venue']['cash_cents'], self.wallets['venue']['tokens']))
        gross = reserve_cash * tokens // max(1, reserve_tokens + tokens)
        return min(gross, self.wallets['venue']['cash_cents']) * (10000 - self.package['fee_bps']) // 10000

    def prepare(self):
        if self.prepared_index == self.index:
            return
        self.preparation_before = deepcopy(self.wallets)
        self.preparation_market_before = self.market()
        self.preparation_receipts = []
        self.current_events = [deepcopy(event) for event in self.package['events'] if event['second'] == self.second]
        founder = self.package['founder']
        if self.index == 0:
            self._transfer(self.founder, 'services', cash=founder['upfront_cents'] - self.package['kol_cash_cents'])
            recipients = self.package['kol_ids']
            for recipient in recipients:
                share = self.package['kol_cash_cents'] // len(recipients)
                self._transfer(self.founder, recipient, cash=share)
            remainder = self.package['kol_cash_cents'] - sum(self.package['kol_cash_cents'] // len(recipients) for _ in recipients)
            if remainder:
                self._transfer(self.founder, 'services', cash=remainder)
            self.preparation_receipts.append(self._trade(self.founder, True, founder['position_cents'] // 2, 'committed_launch_50_percent'))
            if recipients:
                grant = min(self.wallets[self.founder]['tokens'], self.package['supply'] * self.package['kol_supply_bps'] // 10000)
                for recipient in recipients:
                    self._transfer(self.founder, recipient, tokens=grant // len(recipients))
                self.kol_granted = grant // len(recipients) * len(recipients)
        if self.phase == 'pool' and not self.post_migration_funded and self.response is None:
            self.preparation_receipts.append(self._trade(self.founder, True, founder['position_cents'] // 5, 'confirmed_migration_20_percent'))
            self.post_migration_funded = True
        signal = volume_signal(self.trades, self.second)
        available_commands = [message for message in self.messages if message['available_second'] <= self.second]
        if available_commands:
            self.mm_paused = available_commands[-1]['choice'] == 'pause_mm'
        liquidatable = self.wallets[self.founder]['cash_cents'] + self.wallets['reserve']['cash_cents'] + self._founder_exit_quote()
        loss_alert = liquidatable < founder['capital_cents'] - founder['loss_budget_cents']
        if self.response is None and (signal['exit_trigger'] is True or loss_alert):
            self.alert_pending = True
            if self.response_policy != 'fork-at-first-alert':
                self.trigger_response(self.second)
        if self.response is not None and self.response_policy == 'staged-exit':
            previous_price = next((row['market_after']['price_usd_exact'] for row in reversed(self.history)
                                   if row['second'] <= self.second - HOUR), None)
            defer = exit_deferred(signal, self._price(), previous_price)
            for tranche in self.response['tranches']:
                if tranche['status'] == 'scheduled' and tranche['due_second'] == self.second:
                    if defer is True:
                        tranche['status'] = 'deferred_until_next_hour'
                        next_due = self.second + HOUR
                        if next_due <= HORIZON:
                            tranche.update(status='scheduled', due_second=next_due)
                            self.schedule = sorted(set(self.schedule) | {next_due})
                        continue
                    amount = min(tranche['tokens'], self.wallets[self.founder]['tokens'])
                    receipt = self._trade(self.founder, False, amount, 'staged_exit_tranche')
                    self.preparation_receipts.append(receipt)
                    tranche['status'] = receipt['status']
                    self.response['tranches_completed'] += int(receipt['status'] in {'executed', 'no_inventory_or_budget'})
        self.prepared_index = self.index
        if (self.cash_total(), self.token_total()) != self.initial_totals:
            raise RuntimeError('lifecycle preparation conservation failure')

    def trigger_response(self, second):
        if self.response is not None:
            return
        branch = response_branches(second, decision_delay_seconds=self.package['founder']['response_delay_seconds'])
        selected = branch[1] if self.response_policy == 'staged-exit' else branch[0]
        inventory = self.wallets[self.founder]['tokens']
        tranches = []
        for index, entry in enumerate(selected['tranches']):
            tranches.append({**entry, 'status': 'scheduled' if entry['due_second'] <= HORIZON else 'pending_after_horizon',
                             'tokens': inventory // 4 + (inventory % 4 if index == 3 else 0)})
        self.response = {'alert_second': second, 'policy': self.response_policy, 'tranches': tranches,
                         'tranches_completed': 0, 'inventory_at_alert': inventory}
        self.schedule = sorted(set(self.schedule) | {entry['due_second'] for entry in tranches if entry['due_second'] <= HORIZON})
        for actor, information in self.actors.items():
            if information['role'] == 'mm':
                self.messages.append({'sender': self.founder, 'recipient': actor, 'choice': 'pause_mm',
                                      'available_second': second + 60})
        if second + 60 <= HORIZON:
            self.schedule = sorted(set(self.schedule) | {second + 60})

    def fork(self, response_policy):
        if response_policy not in {'pause-and-observe', 'staged-exit'}:
            raise ValueError('explicit comparative branch required')
        result = deepcopy(self)
        result.response_policy = response_policy
        if result.alert_pending:
            result.trigger_response(result.second)
        return result

    def menu(self, actor):
        wallet = self.wallets[actor]
        info = self.actors[actor]
        menu = {'wait': 'Wait; preserve cash and inventory.'}
        max_buy = min(wallet['cash_cents'], info['ticket_cents'])
        if actor == self.founder:
            remaining = self.package['founder']['position_cents'] * 3 // 10 - self.ongoing_spent
            if self.response is not None or volume_signal(self.trades, self.second)['funding_gate_open'] is not True:
                max_buy = 0
            max_buy = min(max_buy, max(0, remaining))
            menu.update(pause_mm='Send the MM a private pause instruction, delivered at the next minute or boundary.',
                        review_campaign='Privately ask the MM to review inventory and campaign conditions; no forced price support.')
        elif info['role'] == 'mm' and self.mm_paused:
            max_buy = 0
        if max_buy:
            menu.update(buy_small=f'Buy using {max(1, max_buy // 4)} cash cents.', buy_all=f'Buy using at most {max_buy} cash cents.')
        if wallet['tokens'] and actor != self.founder:
            menu.update(sell_small=f'Sell {max(1, wallet["tokens"] // 4)} tokens.', sell_all=f'Sell {wallet["tokens"]} tokens.')
        if info['role'] in {'kol', 'partnership', 'organic', 'foundation'}:
            menu['publish'] = 'Publish a bounded public update; not proof of demand or a guaranteed price effect.'
        return menu

    def observation(self, actor):
        own = self.actors[actor]
        market = self.market()
        visible = [event for event in self.package['events'] if event['second'] <= self.second]
        messages = [message for message in self.messages if message['recipient'] == actor and message['available_second'] <= self.second]
        state = {'actor': {'id': actor, 'role': own['role'], 'goal': own['goal']},
                 'second': self.second, 'regime': self.package['regime'], 'own': deepcopy(self.wallets[actor]),
                 'market': market, 'campaigns': self._campaigns(), 'coordination': messages[-2:],
                 'events': visible[-3:], 'public_posts': deepcopy(self.public[-3:]),
                 'memory': {'own_last_choice': self.last_choices.get(actor), 'own_last_fill': self.last_fills.get(actor),
                            'own_totals': deepcopy(self.cumulative[actor]),
                            'recent_public_prices': [[row['second'], row['market_after']['price_usd_exact']] for row in self.history[-4:]],
                            'full_history_checkpoints': len(self.history)},
                 'limitations': 'Conditional estimate. Event schedules do not establish outcomes; model scores are not real odds.'}
        if actor == self.founder:
            state['own_policy'] = {'reserve_cents': self.wallets['reserve']['cash_cents'],
                                   'remaining_position_cents': self.package['founder']['position_cents'] - self.founder_buys,
                                   'response': deepcopy(self.response)}
        return state

    def advance(self, choices):
        if self.prepared_index != self.index:
            raise ValueError('prepare commitments and policies before choices')
        if type(choices) is not dict or set(choices) != set(self.actors) or any(choice not in self.menu(actor) for actor, choice in choices.items()):
            raise ValueError('exact current affordable choice coverage required')
        observations = {actor: self.observation(actor) for actor in self.actors}
        staged = deepcopy(self)
        checkpoint = staged._settle(choices, observations)
        if (staged.cash_total(), staged.token_total()) != self.initial_totals:
            raise RuntimeError('lifecycle conservation failure')
        self.__dict__ = staged.__dict__
        return checkpoint

    def _settle(self, choices, observations):
        before = self.market()
        balances_before = deepcopy(self.wallets)
        receipts = deepcopy(self.preparation_receipts)
        quoted = {}
        for actor, choice in choices.items():
            if choice.startswith(('buy_', 'sell_')):
                amount = min(self.wallets[actor]['cash_cents'], self.actors[actor]['ticket_cents']) if choice.startswith('buy_') else self.wallets[actor]['tokens']
                if actor == self.founder:
                    amount = min(amount, max(0, self.package['founder']['position_cents'] * 3 // 10 - self.ongoing_spent))
                if choice.endswith('small'):
                    amount = max(1, amount // 4)
                quoted[actor] = self._quoted_output(choice.startswith('buy_'), amount)
        order = list(self.actors)
        keyed_rng(self.seed, 'lifecycle-order', self.second).shuffle(order)
        for actor in order:
            choice = choices[actor]
            if choice.startswith('buy_'):
                amount = min(self.wallets[actor]['cash_cents'], self.actors[actor]['ticket_cents'])
                if actor == self.founder:
                    amount = min(amount, max(0, self.package['founder']['position_cents'] * 3 // 10 - self.ongoing_spent))
                if choice == 'buy_small':
                    amount = max(1, amount // 4)
                receipts.append(self._trade(actor, True, amount, 'actor_choice',
                                            quoted[actor] * (10000 - self.package['max_slippage_bps']) // 10000))
            elif choice.startswith('sell_'):
                amount = self.wallets[actor]['tokens']
                if choice == 'sell_small':
                    amount = max(1, amount // 4)
                receipts.append(self._trade(actor, False, amount, 'actor_choice',
                                            quoted[actor] * (10000 - self.package['max_slippage_bps']) // 10000))
            elif choice == 'publish':
                self.public.append({'second': self.second, 'actor': actor, 'text': 'A modeled participant published an update; independent recipients reassess.'})
            elif choice in {'pause_mm', 'review_campaign'}:
                for recipient, info in self.actors.items():
                    if info['role'] == 'mm':
                        self.messages.append({'sender': actor, 'recipient': recipient, 'choice': choice,
                                              'available_second': self.second + 60})
            if self.actors[actor]['role'] == 'mm':
                available = [message for message in self.messages if message['recipient'] == actor and message['available_second'] <= self.second]
                if available:
                    self.mm_paused = available[-1]['choice'] == 'pause_mm'
        after = self.market()
        previous_volume = before['six_hour_signal']['current_volume_cents']
        if previous_volume and sum(row['cash_cents'] for row in self.trades if row['second'] == self.second) > previous_volume // 3:
            self.current_events.append({'kind': 'volume_spike', 'second': self.second,
                                        'text': 'Current barrier turnover exceeds twice the prior six-hour hourly mean; descriptive assumed detector.'})
        if before['real_cash_cents'] and after['real_cash_cents'] < before['real_cash_cents'] // 2:
            self.current_events.append({'kind': 'liquidity_drain', 'second': self.second,
                                        'text': 'Real venue cash fell by more than half across this barrier; sampled detector, not calibrated odds.'})
        checkpoint = {'schema_version': 'launch-lifecycle-checkpoint.v1', 'engine_sha256': LIFECYCLE_HASH,
                      'step': self.index, 'second': self.second, 'previous_hash': self.chain_hash,
                      'market_before': before, 'market_after': after, 'preparation_balances_before': self.preparation_before,
                      'preparation_market_before': self.preparation_market_before,
                      'balances_before': balances_before, 'balances_after': deepcopy(self.wallets),
                      'choices': deepcopy(choices), 'observations': observations, 'settlements': receipts,
                      'events': deepcopy(self.current_events), 'campaigns': self._campaigns(),
                      'response': deepcopy(self.response), 'kol_tokens_granted': self.kol_granted}
        checkpoint['checkpoint_sha256'] = digest(checkpoint)
        self.chain_hash = checkpoint['checkpoint_sha256']
        self.history.append({'second': self.second, 'market_after': deepcopy(after), 'choices': deepcopy(choices)})
        self.last_choices = deepcopy(choices)
        self.index += 1
        return checkpoint

    def summary(self):
        controlled_cash = self.wallets[self.founder]['cash_cents'] + self.wallets['reserve']['cash_cents']
        return {'founder_controlled_cash_cents': controlled_cash,
                'founder_net_cash_cents': controlled_cash - self.package['founder']['capital_cents'],
                'founder_inventory_tokens': self.wallets[self.founder]['tokens'],
                'estimated_inventory_exit_cents': self._founder_exit_quote(),
                'phase': self.phase, 'migrated_at': self.migrated_at, 'response': deepcopy(self.response),
                'executed_turnover_cents': sum(trade['cash_cents'] for trade in self.trades),
                'trade_count': len(self.trades), 'last_second': self.history[-1]['second'] if self.history else None,
                'reserve_cents': self.wallets['reserve']['cash_cents'], 'final_hash': self.chain_hash}
