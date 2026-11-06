"""Terminal user workflow; model calls require an explicit route and opt-in."""
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys

from . import decision_sessions as sessions
from .decision_evidence import build_evidence_context


def _model_args(parser,*,actor_only=False):
    parser.add_argument('--transport',choices=('agy','openai','gemini')+(('typesafe',) if actor_only else ()),required=True)
    parser.add_argument('--model',required=True)
    parser.add_argument('--allow-model',action='store_true')
    parser.add_argument('--public-input',action='store_true',help='Required for public development CLI; never pass confidential inputs there')
    parser.add_argument('--endpoint')
    parser.add_argument('--api-key-env',help='Name of selected environment variable; do not pass a secret here')
    if actor_only:
        parser.add_argument('--http-client',choices=('urllib','curl'),help='TypeSafe only: explicit HTTP transport')
        parser.add_argument('--env-file',help='TypeSafe only: explicit local file; reads only the selected named key')
    parser.add_argument('--timeout',type=int,default=180)
    parser.add_argument('--max-output-tokens',type=int,default=4096)


def register_decision_commands(commands):
    group=commands.add_parser('decision',help='Guided launch feasibility: question, review, live roles, decision memo')
    children=group.add_subparsers(dest='decision_command',required=True)
    for name in ('start','say','branch','review','run','status','report','recover'):
        parser=children.add_parser(name)
        parser.add_argument('--session-dir',required=True)
        if name in ('start','say','branch','review','run'):_model_args(parser)
        if name in ('start','say','branch'):
            field='question' if name=='start' else 'message'
            source=parser.add_mutually_exclusive_group(required=True)
            source.add_argument('--'+field);source.add_argument('--'+field+'-file',help='Private text file; avoids putting native-route inputs in shell history')
        if name=='branch':parser.add_argument('--source-dir',required=True,help='Completed baseline session; source is not modified')
        if name=='start':
            parser.add_argument('--network',choices=('near','solana'),default='near')
            parser.add_argument('--public-archive',help='Explicit read-only local forward archive')
            parser.add_argument('--wallet-observations',action='append',default=[])
            parser.add_argument('--planning-call-limit',type=int,default=8)
        if name=='review':
            parser.add_argument('--seed',type=int,help='Defaults to baseline seed for a branch, otherwise 42')
            parser.add_argument('--max-calls',type=int,required=True)
            parser.add_argument('--max-external-cash-cents',type=int,help='Defaults to the baseline analysis bound for a branch')
        if name=='run':parser.add_argument('--review-hash',required=True)
    compare=children.add_parser('compare',help='Offline cash comparison of completed matched plans; zero model requests')
    compare.add_argument('--session-dir',required=True,help='Completed baseline')
    compare.add_argument('--against',action='append',required=True,help='Completed alternative; repeat up to seven times')
    compare.add_argument('--label',action='append',help='Optional label for every member, baseline first')
    compare.add_argument('--output-dir',required=True,help='New private directory for JSON and readable report')


def _client(args):
    from .agent_models import AgyTextModel,NativeTextModel
    if not args.allow_model:raise ValueError('explicit model access required')
    if args.transport!='typesafe' and any(getattr(args,key,None)is not None for key in ('env_file','http_client')):
        raise ValueError('env-file and HTTP transport apply only to TypeSafe')
    if args.transport=='typesafe':
        from .jev_commands import typesafe_actor_client
        return typesafe_actor_client(args)
    if args.transport=='agy':
        binary=shutil.which('agy')
        if not binary or args.endpoint or args.api_key_env:raise ValueError('invalid installed CLI configuration')
        return AgyTextModel(model=args.model,binary=binary,public_input=args.public_input,timeout_seconds=args.timeout)
    if not args.endpoint or not args.api_key_env or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',args.api_key_env):
        raise ValueError('explicit endpoint and selected key variable required')
    return NativeTextModel(model=args.model,endpoint=args.endpoint,api_key=os.environ.get(args.api_key_env,''),
        protocol=args.transport,timeout_seconds=args.timeout,max_output_tokens=args.max_output_tokens)


def _input(args,field):
    value=getattr(args,field)
    if value is None:
        path=getattr(args,field+'_file')
        fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|getattr(os,'O_NOFOLLOW',0))
        import stat
        with os.fdopen(fd,'rb') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):raise ValueError('regular input file required')
            raw=handle.read(16001)
        if len(raw)>16000:raise ValueError('input exceeds budget')
        value=raw.decode('utf-8')
    return sessions._text(value)


def _status(state):
    p=state['proposal']
    print(json.dumps({'status':state['status'],'revision':state['revision'],
        'planning_attempts':state['planning_attempts'],'planning_call_limit':state['planning_call_limit'],
        'summary':p['summary'] if p else None,'questions':p['questions'] if p else [],
        'limitations':p['limitations'] if p else [],'error':state['error'],'run_path':state['run_path']},indent=2,ensure_ascii=True))


def run_decision_command(args):
    if args.command!='decision':return None
    try:
        action=args.decision_command
        if action in ('start','say','branch','review','run'):client=_client(args)
        if action=='start':
            question=_input(args,'question')
            evidence=build_evidence_context(wallet_snapshots=[sessions._read(p) for p in args.wallet_observations],
                archive_path=args.public_archive,network=args.network)
            state=sessions.start_session(session_dir=args.session_dir,question=question,client=client,
                evidence_context=evidence,planning_call_limit=args.planning_call_limit)
        elif action=='say':state=sessions.reply_session(session_dir=args.session_dir,message=_input(args,'message'),client=client)
        elif action=='branch':
            state=sessions.branch_session(source_dir=args.source_dir,session_dir=args.session_dir,
                message=_input(args,'message'),client=client)
        elif action=='compare':
            from .decision_comparisons import compare_decisions,render_comparison_report
            paths=[Path(args.session_dir)]+[Path(p)for p in args.against]
            if not 2<=len(paths)<=8 or len({p.resolve()for p in paths})!=len(paths):
                raise ValueError('two to eight distinct sessions required')
            labels=args.label or ['Baseline']+[f'Alternative {i}'for i in range(1,len(paths))]
            if len(labels)!=len(paths):raise ValueError('one label per session required')
            members=[]
            for path,label in zip(paths,labels):
                state=sessions.read_session(path)
                if state['status']!='completed':raise ValueError('completed sessions required')
                run=sessions._run_directory(path,state)
                members.append({'label':label,'state':state,'manifest':sessions._read(run/'manifest.json'),
                                'result':sessions._read(run/'result.json')})
            comparison=compare_decisions(members);report=render_comparison_report(comparison)
            output=Path(args.output_dir);output.parent.mkdir(parents=True,exist_ok=True);output.mkdir(mode=0o700)
            sessions._write(output,'comparison.json',comparison)
            sessions._write(output,'comparison-report.md',report,text=True)
            print(json.dumps({'status':'completed','plans':len(members),'model_requests':0,
                              'comparison_report':str(output/'comparison-report.md')},ensure_ascii=True));return 0
        elif action=='review':
            review=sessions.review_session(session_dir=args.session_dir,client=client,seed=args.seed,max_calls=args.max_calls,
                max_external_cash_cents=args.max_external_cash_cents)
            print(json.dumps(review,indent=2,ensure_ascii=True));return 0
        elif action=='run':state=sessions.run_session(session_dir=args.session_dir,client=client,review_hash=args.review_hash)
        elif action=='recover':state=sessions.recover_session(session_dir=args.session_dir)
        elif action=='report':
            state=sessions.read_session(args.session_dir)
            if state['status']!='completed':raise ValueError('no completed decision report')
            path=sessions._run_directory(Path(args.session_dir),state)/'decision-report.md'
            if path.is_symlink() or path.stat().st_size>sessions.MAX_FILE:raise ValueError('bounded report required')
            print(path.read_text());return 0
        else:state=sessions.read_session(args.session_dir)
        _status(state)
        return 2 if state['status'] in ('planning_failed','execution_failed') else 0
    except (OSError,ValueError,KeyError,TypeError,RecursionError,OverflowError,sqlite3.Error):
        print('Decision operation blocked or failed. Check required answers, current review hash, explicit route/budget and private session artifacts. No automatic retry or fallback.',file=sys.stderr)
        return 2
