"""Execute funded scenario commitments before independent actor decision barriers."""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from .agent_worlds import _int, _shape, digest
from .campaign_worlds import CampaignWorld
from .finance import Ledger
from .randomness import keyed_rng


PLAN_ENGINE_HASH = sha256(Path(__file__).read_bytes()).hexdigest()


def validate_commitments(package, commitments):
    if type(commitments) is not list or not 1 <= len(commitments) <= 16:
        raise ValueError('bounded funded commitments required')
    actors = {actor['id']: actor for actor in package['actors']}
    products = {item['id']: item for item in package['campaigns']}
    paid = set()
    budgets = {actor: value['cash_cents'] for actor, value in actors.items()}
    for item in commitments:
        _shape(item, {'payer', 'campaign_id', 'order_second'})
        _int(item['order_second'], 0, package['decision_seconds'][-1])
        if item['order_second'] not in package['decision_seconds']:
            raise ValueError('commitment needs an explicit decision time')
        payer, product = item['payer'], item['campaign_id']
        if payer not in actors or product not in products or product not in actors[payer]['campaign_ids']:
            raise ValueError('unauthorized campaign commitment')
        if (payer, product) in paid:
            raise ValueError('duplicate campaign commitment')
        paid.add((payer, product))
        budgets[payer] -= products[product]['price_cents']
        if budgets[payer] < 0:
            raise ValueError('campaign plan exceeds initial payer funding')
    return deepcopy(commitments)


class CommittedCampaignWorld(CampaignWorld):
    def __init__(self, package, seed, commitments):
        super().__init__(package, seed)
        self.commitments = validate_commitments(self.package, commitments)
        self.commitment_receipts = []
        self.prepared_step = -1
        self.chain_hash = digest({'base_hash': self.chain_hash, 'commitments': self.commitments,
                                  'plan_engine_sha256': PLAN_ENGINE_HASH})

    def prepare_step(self):
        if self.prepared_step == self.index:
            return
        second = self.second
        ledger = Ledger(dict(self.ledger.accounts))
        orders = deepcopy(self.orders)
        summaries = deepcopy(self.summary)
        receipts = []
        for item in self.commitments:
            if item['order_second'] != second:
                continue
            payer, product = item['payer'], item['campaign_id']
            if any(order['actor_id'] == payer and order['campaign_id'] == product for order in orders):
                raise ValueError('campaign already ordered before commitment')
            campaign = next(value for value in self.package['campaigns'] if value['id'] == product)
            before = asdict(ledger.accounts[payer])
            ledger.transfer(f'commitment:{payer}:{product}', payer, 'services', campaign['price_cents'])
            succeeds = keyed_rng(self.seed, 'campaign-delivery', payer, product).randrange(10000) < campaign['delivery_bps']
            orders.append({'actor_id': payer, 'campaign_id': product, 'ordered_second': second,
                           'delivery_succeeds': succeeds})
            summaries[payer]['campaign_spend_cents'] += campaign['price_cents']
            receipts.append({'payer': payer, 'campaign_id': product, 'order_second': second,
                             'cost_cents': campaign['price_cents'], 'balance_before': before,
                             'balance_after': asdict(ledger.accounts[payer]),
                             'mechanism': 'funded scenario commitment; not an actor-selected purchase'})
        if ledger.totals() != self.initial_totals:
            raise RuntimeError('commitment conservation failure')
        self.ledger, self.orders, self.summary = ledger, orders, summaries
        self.commitment_receipts = receipts
        self.prepared_step = self.index

    def menu(self, actor_id):
        actions, signals = super().menu(actor_id)
        reserved = {item['campaign_id'] for item in self.commitments if item['payer'] == actor_id}
        return {key: value for key, value in actions.items()
                if value['kind'] != 'campaign' or value['campaign_id'] not in reserved}, signals

    def advance(self, decisions):
        if self.prepared_step != self.index:
            raise ValueError('execute due commitments before actor observations')
        receipts = deepcopy(self.commitment_receipts)
        checkpoint = super().advance(decisions)
        checkpoint['plan_engine_sha256'] = PLAN_ENGINE_HASH
        checkpoint['committed_plan_execution'] = receipts
        checkpoint.pop('checkpoint_sha256')
        checkpoint['checkpoint_sha256'] = digest(checkpoint)
        self.chain_hash = checkpoint['checkpoint_sha256']
        return checkpoint
