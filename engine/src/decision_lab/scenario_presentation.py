"""Five-slide, data-only presentation derived from completed engine records.

No model calls, prose generation, inferred forecasts or new scenario sampling.
Every settlement report replays before chart values are computed. Large monetary
and utility integers stay exact strings; small bounded metrics have chart values.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from decimal import Decimal,localcontext,ROUND_HALF_EVEN
from fractions import Fraction
import math

from .agent_worlds import canonical,digest,_int
from .strategic_models import _validate_choice,PROBABILITY_MEANING
from .strategic_worlds import replay_strategic_world
from .product_insights import build_insights
from .product_history import summarize_provider_receipts

MAX_PRESENTATION_BYTES=2*1024*1024


def _fraction(value):
    value=Fraction(value)
    return str(value.numerator)if value.denominator==1 else f'{value.numerator}/{value.denominator}'


def _money(cents):
    value=Fraction(cents)
    with localcontext()as context:
        context.prec=80
        usd=Decimal(value.numerator)/Decimal(value.denominator)/100
        return format(usd.quantize(Decimal('.01'),rounding=ROUND_HALF_EVEN),'f')


def _stats(values):
    values=sorted(values);count=len(values)
    avg=Fraction(sum(values),count)
    med=Fraction(values[count//2])if count%2 else Fraction(values[count//2-1]+values[count//2],2)
    return {'mean':float(avg),'median':float(med),'min':values[0],'max':values[-1],
        'mean_exact':_fraction(avg),'median_exact':_fraction(med)}


def _validated(snapshot):
    if type(snapshot)is not dict or type(snapshot.get('results'))is not list or not 1<=len(snapshot['results'])<=4:
        raise ValueError('one to four completed recorded worlds required')
    results=snapshot['results'];world=None;seen=set();decisions=[]
    for entry in results:
        if type(entry)is not dict or set(entry)!={'world_index','result','decisions'}:raise ValueError('recorded world entry required')
        _int(entry['world_index'],0,3)
        if entry['world_index']in seen:raise ValueError('unique world indexes required')
        seen.add(entry['world_index']);report=entry['result'];replay_strategic_world(report)
        if report['status']!='completed':raise ValueError('presentation uses completed worlds only')
        if world is None:world=report['world']
        elif world!=report['world']:raise ValueError('one reviewed world definition required')
        if type(entry['decisions'])is not list or len(entry['decisions'])!=len(world['actors'])*world['rounds']:
            raise ValueError('complete decision metadata required')
        indexed={}
        for item in entry['decisions']:
            if type(item)is not dict or type(item.get('actor_id'))is not str:raise ValueError('recorded actor decision required')
            _int(item.get('round'),1,world['rounds']);key=(item['round'],item['actor_id'])
            if key in indexed:raise ValueError('duplicate decision metadata')
            indexed[key]=item
        for record in report['rounds']:
            for actor_id,selected in record['decisions'].items():
                item=indexed.get((record['round'],actor_id));obs=record['observations'][actor_id]
                if item is None or item.get('action_id')!=selected['action_id']or item.get('observation_sha256')!=selected['observation_sha256']:
                    raise ValueError('decision metadata differs from settled trajectory')
                menu={a['id']:a for a in obs['actions']}
                _validate_choice({'type':'choice','choice':item.get('argmax_action_id'),'confidence':item.get('confidence'),
                    'probabilities':item.get('probabilities')},menu)
                if item.get('selection_mode')not in ('argmax','sample'):raise ValueError('declared decision selection mode required')
                if item['selection_mode']=='argmax'and item['action_id']!=item['argmax_action_id']:raise ValueError('argmax action differs')
                decisions.append((entry['world_index'],item))
    proposal=snapshot.get('proposal')
    if type(proposal)is dict and proposal.get('world')is not None and proposal['world']!=world:
        raise ValueError('snapshot world differs from recorded result')
    requested=[]
    for container,key in ((snapshot.get('review'),'worlds'),(snapshot.get('summary'),'requested_worlds')):
        if type(container)is dict and container.get(key)is not None:
            _int(container[key],1,4);requested.append(container[key])
    if requested and (len(set(requested))!=1 or requested[0]<len(results)):raise ValueError('inconsistent requested-world denominator')
    return world,sorted(results,key=lambda e:e['world_index']),decisions,requested[0]if requested else None


def _provider(decisions):
    local=[d['receipt']for _,d in decisions if type(d.get('receipt'))is dict and d['receipt'].get('local_decision')is True]
    receipts=[d['receipt']for _,d in decisions if type(d.get('receipt'))is dict and d['receipt'].get('local_decision')is not True]
    return summarize_provider_receipts(receipts,len(local))


def _metrics(world,results):
    metrics=[]
    for metric in world['metrics']:
        paths=[{'world_index':e['world_index'],'values':[metric['initial']]+[r['metrics_after'][metric['id']]for r in e['result']['rounds']]}for e in results]
        aggregated=[_stats([p['values'][r]for p in paths])for r in range(world['rounds']+1)]
        metrics.append({'id':metric['id'],'label':metric['label'],'unit':metric['unit'],'initial':metric['initial'],
            'bounds':{'min':metric['min'],'max':metric['max']},'final':aggregated[-1],
            'rounds':list(range(world['rounds']+1)),'series':paths,
            'mean':[s['mean']for s in aggregated],'median':[s['median']for s in aggregated],
            'min':[s['min']for s in aggregated],'max':[s['max']for s in aggregated]})
    return metrics


def _resources(world,results,provider):
    actors=[]
    for actor in world['actors']:
        values=[e['result']['actor_results'][actor['id']]for e in results];n=len(values)
        cost=Fraction(sum(v['cost_cents']for v in values),n)
        remaining=Fraction(sum(v['cash_cents']for v in values),n)
        utility=Fraction(sum(v['utility']for v in values),n)
        initial=actor['initial_cash_cents']
        actors.append({'id':actor['id'],'name':actor['name'],'role':actor['role'],
            'initial_cash_cents':str(initial),'mean_remaining_cents':_fraction(remaining),'mean_cost_cents':_fraction(cost),
            'mean_cost_usd':_money(cost),'mean_remaining_usd':_money(remaining),
            'cost_fraction':float(cost/initial)if initial else 0.0,
            'mean_utility_exact':_fraction(utility),'utility_meaning':'Declared preference points; not cash profit.'})
    return {'id':'resources','kind':'cash-costs','title':'Where resources went','actors':actors,
        'world_costs':[{'world_index':e['world_index'],'cost_cents':str(e['result']['total_cost_cents']),
                        'cost_usd':_money(e['result']['total_cost_cents'])}for e in results],
        'provider':provider,'cash_meaning':'Modeled action spending and cash remaining. No token sales, asset valuation or profit is computed.',
        'numeric_format':'Cents and utility are exact strings or numerator/denominator strings; USD display rounds half-even to two decimals.'}


def _scenarios(world,results,decisions,requested):
    grouped={}
    for entry in results:
        report=entry['result'];outcome={'final_metrics':report['final_metrics'],
            'cash_cents':{key:v['cash_cents']for key,v in report['actor_results'].items()},'total_cost_cents':report['total_cost_cents']}
        key=digest(outcome)
        if key not in grouped:grouped[key]={'outcome':outcome,'world_indexes':[],'representative':report}
        grouped[key]['world_indexes'].append(entry['world_index'])
    clusters=[]
    for i,(key,group)in enumerate(grouped.items(),1):
        record=group['representative'];count=len(group['world_indexes'])
        actions=[{'actor_id':a['id'],'name':a['name'],'sequence':[{'round':r['round'],'action_id':r['decisions'][a['id']]['action_id'],
            'label':next(action['label']for action in a['actions']if action['id']==r['decisions'][a['id']]['action_id'])}for r in record['rounds']]}for a in world['actors']]
        clusters.append({'id':key,'label':f'Observed scenario {i}','world_indexes':group['world_indexes'],'count':count,
            'completed_frequency':count/len(results),'requested_frequency':count/requested if requested else None,
            'final_metrics':group['outcome']['final_metrics'],'total_cost_cents':str(group['outcome']['total_cost_cents']),
            'cash_cents':{key:str(value)for key,value in group['outcome']['cash_cents'].items()},'representative_actions':actions})
    action_rows=[]
    for actor in world['actors']:
        actor_decisions=[d for _,d in decisions if d['actor_id']==actor['id']]
        for action in actor['actions']:
            exposed=[d['probabilities'][action['id']]for d in actor_decisions if action['id']in d['probabilities']]
            count=sum(d['action_id']==action['id']for d in actor_decisions)
            action_rows.append({'actor_id':actor['id'],'name':actor['name'],'action_id':action['id'],'label':action['label'],
                'count':count,'decision_count':len(actor_decisions),'selection_frequency':count/len(actor_decisions),
                'available_count':len(exposed),'mean_model_score':math.fsum(exposed)/len(exposed)if exposed else None})
    return {'id':'scenarios','kind':'scenario-clusters','title':'The scenarios actually observed','clusters':clusters,'actions':action_rows,
        'cluster_rule':'Exactly equal final metrics, per-actor remaining cash and total modeled spending; no invented best/worst thresholds.',
        'frequency_meaning':'Conditional frequencies among recorded runs under these rules, not real-world event probabilities.',
        'action_score_meaning':PROBABILITY_MEANING+' Mean scores use only decisions where that action was affordable; selection frequency counts actual chosen actions.'}


def _evidence(world,results):
    delivered=set();published=set();interactions=Counter();event_ids=set()
    for entry in results:
        w=entry['world_index']
        for record in entry['result']['rounds']:
            for message in record['published_messages']:published.add((w,message['id']))
            for target,obs in record['observations'].items():
                for message in obs['messages']:delivered.add((w,target,message['source'],message['id']))
                for event in obs['events']:event_ids.add((w,event['id']))
            interactions.update(record['matched_interaction_ids'])
    edges=[{'source':source,'target':actor['id'],'delivered_messages':sum(d[1]==actor['id']and d[2]==source for d in delivered),
        'kind':'subscription','meaning':'Subscribed messages arrive in later rounds.'}for actor in world['actors']for source in actor['subscriptions']]
    provenance=Counter();refs=set()
    def visit(value):
        if type(value)is dict:
            p=value.get('provenance')
            if type(p)is dict:
                provenance[p['status']]+=1;refs.update(p['source_refs'])
            for item in value.values():visit(item)
        elif type(value)is list:
            for item in value:visit(item)
    visit(world)
    return {'id':'evidence','kind':'network-evidence','title':'What connected these outcomes',
        'nodes':[{'id':a['id'],'name':a['name'],'role':a['role']}for a in world['actors']],
        'edges':edges,'counts':{'published_messages':len(published),'distinct_deliveries':len(delivered),
            'visible_scheduled_events':len(event_ids),'matched_interactions':sum(interactions.values())},
        'matched_rules':[{'id':key,'count':value}for key,value in sorted(interactions.items())],
        'provenance_counts':dict(sorted(provenance.items())),'source_refs':sorted(refs),
        'evidence_meaning':'Declared references and assumptions from the reviewed package; links do not prove fitted coefficients or empirical validity.',
        'limitations':list(dict.fromkeys(world['limitations']+results[0]['result']['limitations']+[
            'Only completed recorded worlds contribute to charts; failures and unattempted worlds do not become zero-valued outcomes.',
            'This deck derives data in code and makes zero new model calls. No calibrated event odds are inferred.',
            'Local presentation contains scenario details. Review before sharing; nothing is automatically published.']))}


def build_presentation(snapshot):
    world,results,decisions,requested=_validated(snapshot)
    provider=_provider(decisions);completed=len(results)
    denominators={'requested_worlds':requested,'completed_worlds':completed,
        'uncompleted_worlds':requested-completed if requested is not None else None,
        'requested_worlds_known':requested is not None,
        'meaning':'Uncompleted combines failed, interrupted or unattempted worlds; historical unknown denominators remain null.'}
    deck={'schema_version':'scenario-presentation.v1','title':world['title'],
        'source':{'session_id':snapshot.get('session_id',snapshot.get('id')),'run_id':snapshot.get('run_id'),
            'world_sha256':digest(world),'engine_sha256s':sorted({e['result']['engine_sha256']for e in results}),
            'model_requests':0,'replay_verified':True},'denominators':denominators,
        'slides':[{'id':'overview','kind':'overview','title':world['title'],'description':world['description'],
                'actor_count':len(world['actors']),'round_count':world['rounds'],'models':provider['models'],
                'scenario_count':len({digest({'metrics':e['result']['final_metrics'],'actors':e['result']['actor_results']})for e in results}),
                'denominators':deepcopy(denominators),'meaning':'A presentation of conditional simulated outcomes, not a financial forecast.'},
            {'id':'outcomes','kind':'metric-trajectories','title':'How the world changed','metrics':_metrics(world,results),
                'trajectory_meaning':'Round 0 is the supplied initial state; later points are recorded post-action round metrics, including scheduled effects visible by that round.'},
            _resources(world,results,provider),_scenarios(world,results,decisions,requested),_evidence(world,results)],
        'decision_insights':build_insights(snapshot)}
    if len(canonical(deck))>MAX_PRESENTATION_BYTES:raise ValueError('presentation exceeds bounded chart payload')
    return deck
