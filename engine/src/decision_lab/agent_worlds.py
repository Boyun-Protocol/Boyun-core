"""Data-only agent communication and financial worlds; no model/provider imports.

The orchestrator supplies inert proposals. This engine controls observations,
subscriptions, round barriers, identities, capabilities and integer settlement.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from math import isqrt
import re
from pathlib import Path

from .finance import Balance, ConstantProductMarket, Ledger
from .randomness import keyed_rng

MAX_ACTORS = 16
MAX_ROUNDS = 16
MAX_TURNS = 128
MAX_BYTES = 262144
MAX_REPORT_BYTES = 8*1024*1024
ENGINE_SHA256 = sha256(Path(__file__).read_bytes() + Path(__file__).with_name('finance.py').read_bytes()
                       + Path(__file__).with_name('randomness.py').read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()


def digest(value):
    return sha256(canonical(value)).hexdigest()


def _shape(value,keys):
    if type(value)is not dict or set(value)!=set(keys):raise ValueError('invalid object shape')


def _int(value,low=0,high=10**12):
    if type(value)is not int or not low<=value<=high:raise ValueError('integer outside bounds')
    return value


def _text(value,limit=1600):
    if type(value)is not str or not value.strip() or len(value)>limit:raise ValueError('invalid bounded text')
    return value


def _id(value):
    if type(value)is not str or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}',value):raise ValueError('invalid identifier')
    return value


def _list(value,limit,minimum=0):
    if type(value)is not list or not minimum<=len(value)<=limit:raise ValueError('invalid bounded list')
    return value


def _strings(value,limit,textlimit=1600):
    for item in _list(value,limit):_text(item,textlimit)
    if len(set(value))!=len(value):raise ValueError('duplicate list entries')


def validate_agent_world(value):
    if len(canonical(value))>MAX_BYTES:raise ValueError('world exceeds size budget')
    _shape(value,{'schema_version','id','event_description','network','rounds','market','agents','events','assumptions'})
    if value['schema_version']!='agent-world.v1':raise ValueError('unsupported agent world')
    _id(value['id']);_text(value['event_description'],8000);_text(value['network'],32)
    _int(value['rounds'],1,MAX_ROUNDS)
    market=value['market'];_shape(market,{'project_capital_cents','launch_cost_cents','lp_cash_cents','project_token_units','lp_token_units','fee_bps','max_slippage_bps'})
    for key in market:_int(market[key])
    if (not market['lp_cash_cents'] or not market['lp_token_units']
        or market['launch_cost_cents']+market['lp_cash_cents']>market['project_capital_cents']
        or market['lp_token_units']>market['project_token_units']
        or market['fee_bps']>=10000 or market['max_slippage_bps']>10000):raise ValueError('invalid funded market')
    agents=_list(value['agents'],MAX_ACTORS,1)
    if len(agents)*value['rounds']>MAX_TURNS:raise ValueError('turn work budget exceeded')
    ids=set()
    for actor in agents:
        _shape(actor,{'id','name','role','description','goal','initial_cash_cents','position_limit_cents','allowed_actions','attention_capacity','subscriptions'})
        ident=_id(actor['id'])
        if ident in ids or ident in {'project','pool','services','news'}:raise ValueError('duplicate or reserved actor')
        ids.add(ident)
        for key in ('name','role','description','goal'):_text(actor[key])
        _int(actor['initial_cash_cents']);_int(actor['position_limit_cents'])
        _int(actor['attention_capacity'],0,16)
        _strings(actor['allowed_actions'],4,16);_strings(actor['subscriptions'],MAX_ACTORS+1,48)
        if 'hold'not in actor['allowed_actions'] or not set(actor['allowed_actions'])<={'hold','buy','sell','publish'}:raise ValueError('unsupported action capability')
    for actor in agents:
        if actor['id']in actor['subscriptions']or not set(actor['subscriptions'])<=ids|{'news'}:raise ValueError('unknown subscription source')
    event_ids=set()
    for event in _list(value['events'],64):
        _shape(event,{'id','round','text','provenance'});ident=_id(event['id'])
        if ident in event_ids:raise ValueError('duplicate event')
        event_ids.add(ident);_int(event['round'],1,value['rounds']);_text(event['text']);_text(event['provenance'])
    _strings(value['assumptions'],32)
    if not value['assumptions']:raise ValueError('explicit assumptions required')
    # Conservative pretty-JSON bound for observations, repeated own history,
    # proposals, publication/citation text, and financial receipts. Reject before
    # construction or model calls rather than accepting unreplayable reports.
    max_message=max([4096]+[len(canonical(event))+512 for event in value['events']])
    expansion=len(canonical(value))*8+65536
    for round_id in range(1,value['rounds']+1):
        for actor in agents:
            remembered=min(64,round_id*actor['attention_capacity'])
            expansion+=4*(len(canonical(actor))+8192+remembered*max_message+(round_id-1)*16384+32768)
    if expansion>MAX_REPORT_BYTES:raise ValueError('conservative report expansion budget exceeded')
    return deepcopy(value)


class AgentWorld:
    def __init__(self,world,seed=42):
        self.world=validate_agent_world(world);self.seed=_int(seed,0,10**9);self.round=1
        m=self.world['market']
        accounts={a['id']:Balance(a['initial_cash_cents'])for a in self.world['agents']}
        accounts.update(project=Balance(m['project_capital_cents'],m['project_token_units']),pool=Balance(),services=Balance())
        self.ledger=Ledger(accounts);self.initial_totals=list(self.ledger.totals())
        self.ledger.transfer('launch-cost','project','services',m['launch_cost_cents'])
        self.ledger.transfer('initial-liquidity','project','pool',m['lp_cash_cents'],m['lp_token_units'])
        self.shares=isqrt(m['lp_cash_cents']*m['lp_token_units'])
        self.history=[];self.published=[];self.memory={a['id']:[]for a in self.world['agents']}
        self.cost_basis={a['id']:0 for a in self.world['agents']};self.settlements=[]
        self.journal=[asdict(t)for t in self.ledger.journal]

    def observations(self):
        if self.round>self.world['rounds']:return {}
        pool=asdict(self.ledger.accounts['pool']);result={}
        external=[{'id':'event:'+e['id'],'source':'news','published_round':e['round'],'text':e['text'],'stance':'external','citations':[],'provenance':e['provenance']}
                  for e in self.world['events']if e['round']<=self.round]
        for actor in self.world['agents']:
            old=self.memory[actor['id']];seen={m['id']for m in old}
            eligible=[m for m in external+self.published if m['source']in actor['subscriptions']and m['id']not in seen]
            # Prior actor publications only. New events may arrive this round.
            eligible=[m for m in eligible if m['source']=='news'or m['published_round']<self.round]
            keyed_rng(self.seed,'agent-feed',actor['id'],self.round).shuffle(eligible)
            delivered=eligible[:actor['attention_capacity']]
            memory=(old+delivered)[-64:]
            obs={'schema_version':'agent-observation.v1','world_id':self.world['id'],'round':self.round,
                 'network':self.world['network'],'event_description':self.world['event_description'],
                 'actor':deepcopy(actor),'balance':asdict(self.ledger.accounts[actor['id']]),
                 'cost_basis_cents':self.cost_basis[actor['id']],'public_market':{**pool,'fee_bps':self.world['market']['fee_bps'],'max_slippage_bps':self.world['market']['max_slippage_bps']},
                 'messages':deepcopy(memory),'new_message_ids':[m['id']for m in delivered],
                 'own_history':[{'round':h['round'],'proposal':next(p for p in h['proposals']if p['actor_id']==actor['id']),
                                 'settlement':next(s for s in h['settlements']if s['actor_id']==actor['id'])}for h in self.history],
                 'limitations':['Message text and external events are supplied claims, not authenticated facts.','Only your delivered information, own account and public pool are visible.']}
            obs['observation_sha256']=digest(obs);result[actor['id']]=obs
        return result

    def _validate_turn(self,turn,obs):
        _shape(turn,{'schema_version','actor_id','round','observation_sha256','action','message','reason'})
        if (turn['schema_version']!='agent-turn.v1'or turn['actor_id']!=obs['actor']['id']
            or type(turn['round'])is not int or turn['round']!=self.round or turn['observation_sha256']!=obs['observation_sha256']):raise ValueError('turn does not bind current actor observation')
        action=turn['action'];_shape(action,{'kind','amount','evidence_ids'})
        if action['kind']not in {'hold','buy','sell'}or action['kind']not in obs['actor']['allowed_actions']:raise ValueError('actor lacks action capability')
        _int(action['amount']);_strings(action['evidence_ids'],16,80);_text(turn['reason'])
        if (action['kind']=='hold'and action['amount']!=0)or(action['kind']!='hold'and (not action['amount']or not action['evidence_ids'])):raise ValueError('trade requires positive amount and personally observed evidence')
        known={m['id']for m in obs['messages']}
        if not set(action['evidence_ids'])<=known:raise ValueError('unobserved action evidence')
        message=turn['message']
        if message is not None:
            if 'publish'not in obs['actor']['allowed_actions']:raise ValueError('actor lacks publication capability')
            _shape(message,{'text','stance','citations'});_text(message['text'],1200)
            if message['stance']not in {'bullish','bearish','uncertain'}:raise ValueError('invalid message stance')
            _strings(message['citations'],16,80)
            if not set(message['citations'])<=known:raise ValueError('unobserved message citation')
        return deepcopy(turn)

    def advance(self,proposals):
        if self.round>self.world['rounds']:raise ValueError('world completed')
        observations=self.observations();_list(proposals,len(observations),len(observations))
        by_id={}
        for turn in proposals:
            if type(turn)is not dict or type(turn.get('actor_id'))is not str or turn['actor_id']not in observations or turn['actor_id']in by_id:raise ValueError('exact actor coverage required')
            by_id[turn['actor_id']]=self._validate_turn(turn,observations[turn['actor_id']])
        # Stage a whole round. Failed structure leaves both communication and money unchanged.
        ledger=Ledger(dict(self.ledger.accounts));m=self.world['market']
        market=ConstantProductMarket(ledger,fee_bps=m['fee_bps'],lp_shares={'project':self.shares})
        costs=self.cost_basis.copy();order=[a['id']for a in self.world['agents']];keyed_rng(self.seed,'agent-execution',self.round).shuffle(order)
        receipts=[];published=[]
        start=self.ledger.accounts['pool']
        for actor_id in order:
            turn=by_id[actor_id];action=turn['action'];kind=action['kind'];amount=action['amount']
            receipt={'round':self.round,'actor_id':actor_id,'kind':kind,'amount':amount,'status':'held'if kind=='hold'else'executed','reason':None,'fill':None}
            if kind!='hold':
                actor=observations[actor_id]['actor'];balance=ledger.accounts[actor_id]
                if kind=='buy'and(amount>balance.cash_cents or costs[actor_id]+amount>actor['position_limit_cents']):
                    receipt.update(status='rejected',reason='budget_or_position_limit')
                elif kind=='sell'and amount>balance.token_units:receipt.update(status='rejected',reason='insufficient_tokens')
                else:
                    rin,rout=(start.cash_cents,start.token_units)if kind=='buy'else(start.token_units,start.cash_cents)
                    effective=amount*(10000-m['fee_bps'])//10000
                    quote=rout*effective//(rin+effective);minimum=max(1,quote*(10000-m['max_slippage_bps'])//10000)
                    try:
                        event=f'agent:{self.round}:{actor_id}'
                        if kind=='buy':fill=market.buy(actor_id,amount,event,min_tokens=minimum);costs[actor_id]+=fill.cash_cents
                        else:fill=market.sell(actor_id,amount,event,min_cash_cents=minimum);costs[actor_id]=costs[actor_id]*(balance.token_units-fill.token_units)//balance.token_units
                        receipt['fill']=asdict(fill)
                    except ValueError:receipt.update(status='rejected',reason='settlement_or_slippage')
            receipts.append(receipt)
            if turn['message']is not None:
                published.append({'id':f'agent:{self.round}:{actor_id}','source':actor_id,'published_round':self.round,**deepcopy(turn['message']),'provenance':'unverified_agent_claim'})
        if list(ledger.totals())!=self.initial_totals:raise RuntimeError('conservation invariant failed')
        history={'round':self.round,'observations':observations,'proposals':[by_id[a['id']]for a in self.world['agents']],
                 'execution_order':order,'settlements':receipts,'published_messages':published}
        self.memory={actor_id:deepcopy(obs['messages'])for actor_id,obs in observations.items()}
        self.ledger=ledger;self.cost_basis=costs;self.history.append(history);self.published.extend(published)
        self.settlements.extend(receipts);self.journal.extend(asdict(t)for t in ledger.journal);self.round+=1
        return self.report()

    def report(self):
        return deepcopy({'schema_version':'agent-world-results.v1','world':self.world,'world_sha256':digest(self.world),
            'engine_sha256':ENGINE_SHA256,'seed':self.seed,'status':'completed'if self.round>self.world['rounds']else'active',
            'completed_rounds':self.round-1,'initial_totals':self.initial_totals,'ending_totals':list(self.ledger.totals()),
            'balances':{owner:asdict(balance)for owner,balance in self.ledger.accounts.items()},
            'project_cash_profit_cents':self.ledger.accounts['project'].cash_cents-self.world['market']['project_capital_cents'],
            'locked_project_lp_shares':self.shares,'cost_basis_cents':self.cost_basis,'messages':self.published,
            'history':self.history,'settlements':self.settlements,'journal':self.journal,
            'limitations':['Model-authored messages are claims, not verified external facts.','Single synthetic AMM; assets are not live NEAR balances or a launchpad specification.',
                          'Unwithdrawn tokens and locked LP shares are excluded from project cash profit.','Recorded decisions replay exactly; fresh model decisions and market realism are not guaranteed.']})


def replay_agent_world(report):
    if type(report)is not dict or report.get('schema_version')!='agent-world-results.v1'or len(canonical(report))>MAX_REPORT_BYTES:raise ValueError('invalid replay report')
    engine=AgentWorld(report['world'],report['seed'])
    for phase in _list(report['history'],MAX_ROUNDS):engine.advance(phase['proposals'])
    replayed=engine.report()
    if replayed!=report:raise ValueError('report does not match replay')
    return replayed
