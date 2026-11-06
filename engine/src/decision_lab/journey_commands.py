"""One-question terminal journey sharing product construction, review and execution."""
import getpass
import os
from pathlib import Path
import re
import sys
import time
from .io_helpers import read_json,write_artifacts
from .product_api import ProductManager,examples,estimate_typesafe_usage
from .product_reports import pdf_available


def register_journey_commands(commands):
    journey=commands.add_parser('journey',help='Guided private setup → personas → review → run → Markdown/PDF')
    journey.add_argument('--output-dir',required=True,help='NEW private directory; never overwritten')
    journey.add_argument('--offline',action='store_true',help='Local deterministic rules; no model or NEAR network calls')
    journey.add_argument('--api-key-env',help='Read a named process variable instead of a hidden terminal key prompt')
    journey.add_argument('--author-near-ai',action='store_true',help='Use a separately approved NEAR AI world-author call before persona execution')
    journey.add_argument('--author-api-key-env',default='NEAR_AI_CLOUD_API_KEY')
    journey.add_argument('--author-model',help='Exact Cloud model ID; defaults to NEAR_AI_CLOUD_MODEL in the process')
    journey.add_argument('--author-max-calls',type=int,choices=range(1,7),default=3,
                         help='Total initial + clarification author requests (default 3); each requires AUTHOR')
    journey.add_argument('--format',choices=('md','pdf','both'),default='md')
    journey.add_argument('--world',help='Explicit validated strategic-world JSON from your own agent; no narrative authoring')
    report=commands.add_parser('report',help='Export a recorded product run without inference')
    report.add_argument('--product-dir',required=True)
    report.add_argument('--session',required=True)
    report.add_argument('--run',help='Preserved run ID; omit for the current session')
    report.add_argument('--output',required=True,help='NEW .md or .pdf file')


def _private_destination(path):
    path=Path(path).expanduser().absolute()
    for parent in (path,*path.parents):
        if parent.is_symlink():raise ValueError('symlinked output path refused')
    if path.exists():raise ValueError('output already exists')
    return path


def _say(value,write):
    # Terminal controls from scenario text must never be interpreted.
    write(''.join(c if c in '\n\t'or ord(c)>=32 and ord(c)!=127 else '?'for c in str(value)))


def _choose(title,options,read,write):
    _say(title,write)
    for i,(_,label)in enumerate(options,1):_say(f'  {i}. {label}',write)
    while True:
        raw=read('Choice [1]: ').strip()or'1'
        if raw.isdigit()and 1<=int(raw)<=len(options):return options[int(raw)-1][0]
        _say('Choose one of the listed numbers.',write)


def _number(title,default,low,high,read,write):
    while True:
        value=read(f'{title} [{default}; {low}–{high}]: ').strip()or str(default)
        if value.isdigit()and low<=int(value)<=high:return int(value)
        _say('Enter a whole number within the shown limits.',write)


def journey(args,*,read=input,write=print,secret_read=None,manager_factory=ProductManager):
    if args.format in ('pdf','both')and not pdf_available():raise ValueError('Install the pdf extra before starting, or choose --format md')
    output=_private_destination(args.output_dir)
    author_requested=getattr(args,'author_near_ai',False)
    author_limit=getattr(args,'author_max_calls',3)
    if author_requested and (type(author_limit)is not int or not 1<=author_limit<=6):
        raise ValueError('author request limit must be a whole number from 1 to 6')
    if author_requested and (args.offline or args.world):raise ValueError('Cloud author requires live access and no imported world')
    if args.offline and args.api_key_env:raise ValueError('offline mode does not accept a provider key')
    mode='offline'if args.offline else _choose('Where should decisions run?',[
        ('offline','Offline rules: zero model calls, deterministic own-action utility'),
        ('typesafe','My TypeSafe key: remote typed decisions, charged after review')],read,write)
    key=''
    if mode=='typesafe':
        _say('TypeSafe receives persona state. Your key stays only in this process; no key file is written.',write)
        if args.api_key_env:
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',args.api_key_env):raise ValueError('invalid environment variable name')
            key=os.environ.get(args.api_key_env,'')
        else:
            if secret_read is None:
                if not sys.stdin.isatty():raise ValueError('Hidden key entry requires a terminal; select an environment variable for scripts')
                secret_read=getpass.getpass
            key=secret_read('TypeSafe API key (hidden): ')
        if not key:raise ValueError('provider key missing')
    # Validate the input before creating any private artifacts.
    world=read_json(args.world)if args.world else None
    output.mkdir(mode=0o700,parents=True)
    manager=manager_factory(output/'product')
    try:
        manager.configure_access({'mode':mode,'api_key':key,'accept_host_access':False});key=''
        if author_requested:
            if mode=='offline':raise ValueError('offline access disables Cloud authoring')
            name=getattr(args,'author_api_key_env','NEAR_AI_CLOUD_API_KEY')
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',name):raise ValueError('invalid author key environment name')
            model=getattr(args,'author_model',None)or os.environ.get('NEAR_AI_CLOUD_MODEL','')
            manager.configure_author({'mode':'near_ai','api_key':os.environ.get(name,''),'model':model,'accept_host_access':False})
            question=read('Describe the decision, available capital and whose perspectives matter: ').strip()
            _say(f'NEAR AI Cloud receives this brief; this host sees plaintext. No TEE attestation is verified. Author billing is separate from Jev. Up to {author_limit} author requests including the initial call; every request requires AUTHOR. This is a request-count limit, not a dollar-price guarantee.',write)
            if read('Type AUTHOR to approve one world-construction request, or Enter to stop: ').strip()!='AUTHOR':
                _say('Stopped before author inference.',write);return 0
            s=manager.create({'mode':'author','example_id':None,'question':question,'public_input':True})
            author_calls=1
            while True:
                while s['status']=='authoring':
                    time.sleep(.1);s=manager.snapshot(s['id'])
                _say(f'Author requests: {author_calls} / {author_limit}. No actor request yet.',write)
                if s['status']=='ready':break
                if s['status']!='draft' or not s.get('proposal',{}).get('questions'):
                    _say('Author did not return a complete valid world. Review saved private records; no actor calls were made. No automatic retry.',write)
                    details=s.get('error_details')or{}
                    if details.get('http_status')==402:
                        _say('Cloud quota is unavailable. Manage NEAR AI Cloud billing at https://cloud.near.ai; TypeSafe actor billing is separate.',write)
                    elif details.get('http_status')==429:
                        _say('Cloud rate limited this request. Respect its cooldown before a separate explicit attempt.',write)
                        cooldown=details.get('retry_after_seconds')
                        if type(cooldown)in (int,float) and 0<=cooldown<=86400:
                            _say(f'Provider cooldown: at least {cooldown} seconds from the failure.',write)
                    return 2
                questions=s['proposal']['questions']
                _say(s['proposal']['summary'],write)
                if author_calls>=author_limit:
                    _say('Author request limit reached. Remaining questions are saved privately; no actor execution. Start a new explicitly budgeted journey to continue.',write)
                    for q in questions:_say(q['prompt'],write)
                    return 2
                answers=[]
                for q in questions:
                    answer=_choose(q['prompt'],[(choice,choice)for choice in q['choices']],read,write)
                    answers.append(f"{q['id']}: {q['prompt']}\nAnswer: {answer}")
                clarification='\n\n'.join(answers)
                _say('Answers prepared locally; not sent yet:\n'+clarification,write)
                _say(f'The next author request is {author_calls+1} of {author_limit}; Cloud billing is separate and may be charged. No Jev request yet.',write)
                if read('Type AUTHOR to send these answers for a revised world, or Enter to stop: ').strip()!='AUTHOR':
                    _say('Stopped before clarification request. Earlier author requests may already be billed; no actor calls were made.',write)
                    return 0
                s=manager.say(s['id'],{'message':clarification,'public_input':True})
                author_calls+=1
        elif world is None:
            choices=examples();index=_choose('Which ready decision world?',[(i,e['title'])for i,e in enumerate(choices)],read,write);example=choices[index]
            question=read('Your question [use the example]: ').strip()or example['question']
            _say('Ready-world rules are fixed templates. Your question is retained, not interpreted by a model.',write)
            focus=_choose('Whose perspective matters most?',[(v,l)for v,l in [('balanced','Balanced'),('retail','Retail'),('liquidity','Whales and liquidity'),('team','Team and partners')]],read,write)
            retail='balanced'
            if focus in ('balanced','retail'):retail=_choose('Retail decision style?', [('balanced','Curiosity and caution'),('degen','Momentum-seeking / degen'),('cautious','Evidence-seeking / cautious')],read,write)
            team=_choose('Team emphasis (motivation, not an allocation)?',[('balanced','Visibility and readiness'),('marketing','Marketing and audience discovery'),('liquidity','Liquidity / market-making readiness; no live execution')],read,write)
            s=manager.create({'mode':'example','example_id':example['id'],'question':question,'public_input':False,
                'persona_options':{'focus':focus,'retail_style':retail,'team_priority':team}})
        else:
            question=read('Your question [use imported title]: ').strip()or world.get('title','Imported world')
            s=manager.import_world(world,question)
        world=s['proposal']['world']
        _say(world['title']+'\n'+world['description'],write)
        for actor in world['actors']:
            _say(f"{actor['name']}: {actor['role']}\n  Motivation: {actor['motivation']}\n  Goal: {actor['goal']}\n  Starting cash: {actor['initial_cash_cents']} cents\n  Actions: "+', '.join(a['label']+' ('+str(a['cost_cents'])+' cents)'for a in actor['actions']),write)
        minimum=max([1]+[e['round']for e in world['events']])
        world['rounds']=_number('Decision rounds',world['rounds'],minimum,8,read,write)
        maxworlds=min(4,800//(len(world['actors'])*world['rounds']))
        count=_number('Fresh worlds',1,1,maxworlds,read,write)
        policy=_choose('How to select actions?',[('argmax','Highest score; simplest first run'),('sample','Seeded draw from action scores; not calibrated odds')],read,write)
        calls=len(world['actors'])*world['rounds']*count
        estimate=estimate_typesafe_usage(world,count)if mode=='typesafe'else None
        credits=0
        review=manager.review(s['id'],{'world':world,'actor_route':mode,'mode':policy,'worlds':count,'seed':42,'max_calls':calls,'max_credits':credits})
        _say(f'Review: {len(world["actors"])} personas × {world["rounds"]} rounds × {count} worlds. Provider-call ceiling: {calls if mode=="typesafe"else 0}. Native TypeSafe is token-billed; a call ceiling is not a dollar cap.',write)
        if estimate:_say(f"Illustrative input-cost upper estimate: ${estimate['input_cost_upper_estimate_usd']}; {estimate['basis']}",write)
        _say('Offline rules ignore narrative motivations and joint responses; one-hot scores are policy, not confidence.'if mode=='offline'else('Authoring already requested and may be billed; no actor request yet. No fallback or automatic retry.'if author_requested else'No paid request yet. Prices/billing are provider controlled. No fallback or automatic retry.'),write)
        if mode=='typesafe'and read('Check TypeSafe model access without inference? [y/N]: ').strip().lower()=='y':
            health=manager.check_typesafe_access()
            if health['status']!='ready':raise ValueError('actor access check failed; no actor execution; inspect any prior author receipts')
            _say('Available native models: '+', '.join(health['models']),write)
        if read('Type RUN to execute this exact review, or Enter to stop: ').strip()!='RUN':
            _say('Stopped before actor execution. Authoring already requested and may be billed.'if author_requested else'Stopped before execution. No paid calls.',write);return 0
        manager.run(s['id'],{'review_sha256':review['review']['sha256'],'public_input':False})
        last=None
        while True:
            state=manager.snapshot(s['id'])
            if state['status']not in ('running','authoring'):break
            progress=state['progress'];mark=(progress['completed_calls'],progress['completed_worlds'])
            if mark!=last:
                _say(f"{'Local turns'if mode=='offline'else'Actor responses'}: {mark[0]}/{calls}; completed worlds: {mark[1]}/{count}",write);last=mark
            time.sleep(.1)
        formats=('md','pdf')if args.format=='both'else(args.format,)
        artifacts=[(output/('scenario-report.'+fmt),manager.report(s['id'],fmt))for fmt in formats]
        write_artifacts(artifacts)
        _say(f"{state['status']}: {len(state['results'])}/{count} completed worlds. Reports: "+', '.join(str(p)for p,_ in artifacts),write)
        return 0 if state['status']=='completed'else 2
    except (EOFError,KeyboardInterrupt):
        _say('Stopping future turns. Waiting for any already-dispatched request to finish; inspect saved receipts before retrying.',write)
        raise
    finally:
        key='';manager.close()


def run_journey_command(args):
    if args.command not in ('journey','report'):return None
    try:
        if args.command=='journey':return journey(args)
        output=_private_destination(args.output);fmt=output.suffix.lstrip('.')
        if fmt not in ('md','pdf'):raise ValueError('choose a .md or .pdf file')
        if fmt=='pdf'and not pdf_available():raise ValueError('optional PDF dependency unavailable')
        manager=ProductManager(args.product_dir)
        try:raw=manager.report(args.session,fmt,args.run)
        finally:manager.close()
        write_artifacts([(output,raw)]);print('Private report exported without inference.');return 0
    except (EOFError,KeyboardInterrupt):
        print('\nJourney interrupted. Inspect saved receipts before another run; no automatic retry.',file=sys.stderr);return 130
    except (OSError,ValueError,KeyError,TypeError):
        print('Journey/report stopped: check inputs, a NEW regular output path, selected credential source and optional PDF dependency. No secret diagnostics printed.',file=sys.stderr);return 2
