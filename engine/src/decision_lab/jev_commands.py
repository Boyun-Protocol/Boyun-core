"""Offline inspection and explicit credential boundary for Jev actor inference."""
import json
import os
from pathlib import Path
import re
import sys

from .agent_worlds import AgentWorld,digest
from .agent_orchestration import _live_prompt_preflight
from .decision_sessions import _read,_write
from .jev import ENDPOINT,TypeSafeClient,JevActorModel,prepare_actor_request


def typesafe_actor_client(args):
    """Read one explicitly selected native key; never auto-load a dotenv file."""
    from .env_config import load_env_key
    endpoint=getattr(args,'endpoint',None)
    if not args.allow_model or (endpoint is not None and endpoint!=ENDPOINT):
        raise ValueError('explicit model access and pinned TypeSafe endpoint required')
    selected=getattr(args,'api_key_env',None)
    if selected is not None and (type(selected)is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',selected)):
        raise ValueError('explicit named environment variable required')
    env_file=getattr(args,'env_file',None)
    if env_file is not None:key=load_env_key(env_file,name=selected or 'TYPESAFE_API_KEY')
    else:
        if selected is None:raise ValueError('explicit environment variable or env file required')
        key=os.environ.get(selected,'')
    client=TypeSafeClient(api_key=key,endpoint=endpoint or ENDPOINT,model=args.model,
                         timeout_seconds=args.timeout,http_client=getattr(args,'http_client',None)or'urllib')
    return JevActorModel(client=client)


def register_jev_commands(commands):
    group=commands.add_parser('jev',help='Prepare bounded System One actor questions offline; use agents simulate to call TypeSafe')
    children=group.add_subparsers(dest='jev_command',required=True)
    prepare=children.add_parser('prepare')
    prepare.add_argument('--world',required=True,help='Existing authored agent-world.v1 JSON')
    prepare.add_argument('--output-dir',required=True,help='New private initial-observation request directory')
    prepare.add_argument('--seed',type=int,default=42)
    prepare.add_argument('--min-confidence',type=float,default=.6,help='Inspect a policy gate; normal CLI inference uses .6')


def run_jev_command(args):
    if args.command!='jev':return None
    try:
        world=_read(args.world);engine=AgentWorld(world,seed=args.seed);_live_prompt_preflight(engine.world)
        requests={actor:prepare_actor_request(o,min_confidence=args.min_confidence)for actor,o in engine.observations().items()}
        root=Path(args.output_dir);root.parent.mkdir(parents=True,exist_ok=True);root.mkdir(mode=0o700)
        _write(root,'world.json',engine.world)
        for actor,request in requests.items():_write(root,actor+'.request.json',request)
        plan={'schema_version':'jev-actor-plan.v1','world_sha256':digest(engine.world),'actor_count':len(requests),
              'required_calls':len(requests)*world['rounds'],'model_requests':0,'seed':args.seed,
              'policy_version':'jev-menu.v1','min_confidence':args.min_confidence,
              'scope':'Initial observations only; later-round questions are generated from actual permitted engine observations.',
              'limitations':['This is preparation, not authenticated Jev inference or a behavioral benchmark.',
                 'Jev chooses structured actions; frontier generation of the world is separate. No free-text message generation.',
                 'Choice probability/confidence values are not real-world event odds.']}
        _write(root,'plan.json',plan)
        print(json.dumps(plan,ensure_ascii=True,indent=2));return 0
    except (OSError,ValueError,KeyError,TypeError,RecursionError,OverflowError):
        print('Jev preparation blocked. Check authored world, observation byte budget and fresh output directory. Zero model requests.',file=sys.stderr)
        return 2
