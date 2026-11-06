"""Bounded, read-only discovery of recorded product results.

Listing never restores a session or calls a model. Opening replays each completed
world; archived results never replace the user's mutable current session. Local
file modification times are labelled as such, not execution timestamps.
"""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import os
from pathlib import Path
import re
from statistics import mean,median

from .agent_worlds import _int,_shape,canonical,digest
from .decision_sessions import _read
from .strategic_models import PROBABILITY_MEANING
from .strategic_worlds import replay_strategic_world

SESSION=re.compile(r'[0-9a-f]{32}\Z')
RUN=re.compile(r'run-[0-9a-f]{32}\Z')
MAX_SESSIONS=128
MAX_RUNS=256
MAX_ITEMS=32
MAX_CHILD_ENTRIES=4096


def summarize_provider_receipts(receipts,local_turns=0):
    """Summarize recorded evidence without reclassifying historical providers."""
    models=set();tokens=[];estimates=[];native_count=0
    for receipt in receipts:
        model=receipt.get('model_reported')or receipt.get('model_declared')
        if model is not None:
            if type(model)is not str or len(model)>160 or any(ord(c)<32 for c in model):raise ValueError('bounded reported model identity required')
            models.add(model)
        if receipt.get('transport')not in {'typesafe_systemone_http','typesafe_systemone_curl'}:continue
        native_count+=1
        usage=receipt.get('usage')
        if type(usage)is dict and usage.get('input_tokens')is not None:
            _int(usage['input_tokens'],0,10**9);tokens.append(usage['input_tokens'])
        estimate=receipt.get('input_cost_estimate_usd')
        if estimate is not None:
            if type(estimate)not in (int,float):raise ValueError('numeric input cost estimate required')
            amount=Decimal(str(estimate))
            if not amount.is_finite()or amount<0 or amount>10**9:raise ValueError('bounded input cost estimate required')
            estimates.append(amount)
    return {'models':sorted(models),'recorded_model_calls':len(receipts),'local_decision_turns':local_turns,
        'native_typesafe_receipts':native_count,'input_token_receipts':len(tokens),'input_cost_estimate_receipts':len(estimates),
        'recorded_input_tokens':sum(tokens)if tokens else None,
        'input_cost_estimate_usd':float(sum(estimates))if estimates else None,'cost_usd':None,
        'scope':'Completed-world actor receipts only; authoring and failed/incomplete calls are excluded. Totals cover only receipts with the relevant recorded field.',
        'identity_meaning':'Provider-reported model identity and input usage, not independent attestation. Input cost is a list-price estimate, not billed cost.'}


def _folder(root,session_id,run_id):
    if type(session_id)is not str or not SESSION.fullmatch(session_id)or type(run_id)is not str or not RUN.fullmatch(run_id):
        raise KeyError('recorded result not found')
    root=Path(root);session=root/session_id;run=session/run_id
    if root.is_symlink()or session.is_symlink()or run.is_symlink()or not run.is_dir():
        raise KeyError('recorded result not found')
    return run


def _timestamp(path):
    return datetime.fromtimestamp(path.stat().st_mtime,tz=timezone.utc).isoformat()


def _review(path,state):
    try:
        value=_read(path/'review.json')
        if type(value)is not dict:raise ValueError('invalid archived review')
        check=deepcopy(value);expected=check.pop('sha256',None)
        if digest(check)!=expected:raise ValueError('invalid archived review identity')
        _int(value['worlds'],1,4)
        return value
    except FileNotFoundError:
        value=state.get('review')if type(state)is dict and state.get('run_id')==path.name else None
        if type(value)is dict and type(value.get('worlds'))is int and 1<=value['worlds']<=4:
            check=deepcopy(value);expected=check.pop('sha256',None)
            if digest(check)!=expected:raise ValueError('invalid historical review identity')
            return value
        return None


def _state(path):
    try:
        value=_read(path.parent/'state.json')
        return value if type(value)is dict else {}
    except (OSError,ValueError,TypeError,UnicodeError,RecursionError,OverflowError):return {}


def _entry(path):
    first=_read(path/'world-0.json');_shape(first,{'world_index','result','decisions'})
    if first['world_index']!=0 or type(first['result'])is not dict or first['result'].get('status')!='completed':raise ValueError('completed first world required')
    world=first['result']['world'];state=_state(path);review=_review(path,state)
    if type(world)is not dict or type(world.get('actors'))is not list or not 2<=len(world['actors'])<=100:
        raise ValueError('bounded world metadata required')
    _int(world['rounds'],1,8)
    count=sum(1 for index in range(4)if (path/f'world-{index}.json').is_file()and not(path/f'world-{index}.json').is_symlink())
    requested=review['worlds']if review else None
    title=world.get('title')
    if type(title)is not str or not 1<=len(title)<=4000:raise ValueError('bounded world title required')
    return {'session_id':path.parent.name,'run_id':path.name,'title':title[:200],
        'completed_worlds':count,'requested_worlds':requested,
        'status':'completed'if requested is not None and count==requested else'partial'if requested else'recorded',
        'actor_count':len(world['actors']),'rounds':world['rounds'],
        'updated_at':_timestamp(path/'world-0.json'),'time_meaning':'local_result_file_modified_at',
        'replay_verified':False,'model':review.get('model')if review else None}


def list_saved_results(root):
    root=Path(root);entries=[];scanned=0;truncated=False;skipped=0
    with os.scandir(root)as sessions:
        for session_index,session in enumerate(sessions):
            if session_index>=MAX_SESSIONS:truncated=True;break
            if not SESSION.fullmatch(session.name)or not session.is_dir(follow_symlinks=False):continue
            with os.scandir(session.path)as runs:
                for child_index,run in enumerate(runs):
                    if child_index>=MAX_CHILD_ENTRIES:truncated=True;break
                    if not RUN.fullmatch(run.name)or not run.is_dir(follow_symlinks=False):continue
                    if scanned>=MAX_RUNS:truncated=True;break
                    scanned+=1
                    try:entries.append(_entry(Path(run.path)))
                    except (OSError,ValueError,KeyError,TypeError,UnicodeError,RecursionError,OverflowError):skipped+=1
            if scanned>=MAX_RUNS:break
    entries.sort(key=lambda e:(e['updated_at'],e['session_id'],e['run_id']),reverse=True)
    return {'schema_version':'product-result-index.v1','runs':entries[:MAX_ITEMS],
        'truncated':truncated or len(entries)>MAX_ITEMS,'skipped_runs':skipped,
        'model_requests':0,'verification':'Index metadata only; opening verifies exact world replay.'}


def saved_result(root,session_id,run_id):
    path=_folder(root,session_id,run_id);state=_state(path);review=_review(path,state)
    results=[];world=None
    for index in range(4):
        item_path=path/f'world-{index}.json'
        if not item_path.exists():break
        value=_read(item_path);_shape(value,{'world_index','result','decisions'})
        if value['world_index']!=index or type(value['result'])is not dict or value['result'].get('status')!='completed':raise ValueError('completed indexed worlds required')
        replay_strategic_world(value['result'])
        if world is None:world=value['result']['world']
        elif world!=value['result']['world']:raise ValueError('recorded worlds differ')
        if type(value['decisions'])is not list or len(value['decisions'])>800:raise ValueError('bounded recorded decisions required')
        results.append(value)
    if not results:raise KeyError('recorded result not found')
    requested=review['worlds']if review else None
    if requested is not None and len(results)>requested:raise ValueError('more results than reviewed worlds')
    if review and review.get('world_sha256')!=digest(world):raise ValueError('reviewed world differs')
    metrics={m['id']:{'label':m['label'],'unit':m['unit'],
        'mean':mean(r['result']['final_metrics'][m['id']]for r in results),
        'median':median(r['result']['final_metrics'][m['id']]for r in results),
        'min':min(r['result']['final_metrics'][m['id']]for r in results),
        'max':max(r['result']['final_metrics'][m['id']]for r in results)}for m in world['metrics']}
    receipts=[d.get('receipt')for r in results for d in r['decisions']if type(d)is dict and type(d.get('receipt'))is dict and d['receipt'].get('local_decision')is not True]
    local_turns=sum(1 for r in results for d in r['decisions']if type(d)is dict and type(d.get('receipt'))is dict and d['receipt'].get('local_decision')is True)
    cost=summarize_provider_receipts(receipts,local_turns)
    status='completed'if requested is not None and requested==len(results)else'partial'if requested else'recorded'
    question=None
    if (path/'context.json').exists():
        context=_read(path/'context.json');_shape(context,{'question','world_sha256'})
        if type(context['question'])is not str or len(context['question'])>8000 or context['world_sha256']!=digest(world):raise ValueError('invalid frozen question context')
        question=context['question']
    return {'schema_version':'product-saved-result.v1','id':session_id,'session_id':session_id,'run_id':run_id,'question':question,
        'status':status,'read_only':True,'proposal':{'world':world},'review':review,'results':results,
        'summary':{'requested_worlds':requested,'completed_worlds':len(results),'metrics':metrics,'probability_meaning':PROBABILITY_MEANING,
            'limitations':['Replay verifies recorded settlement, not empirical forecasting accuracy.',
                'Historical requested-world count is unknown when no frozen run review survives. No missing denominator is invented.']},
        'progress':{'completed_calls':len(receipts),'completed_worlds':len(results)},'cost':cost,
        'archive':{'replay_verified':True,'requested_worlds_known':requested is not None,'time_meaning':'local_result_file_modified_at','updated_at':_timestamp(path/'world-0.json')},
        'model_requests':0}


def saved_result_bytes(root,session_id,run_id):
    return canonical(saved_result(root,session_id,run_id)['results'])+b'\n'
