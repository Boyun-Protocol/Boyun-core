"""Explicit live-model CLI and offline agent-world replay. UI is not involved."""
import os
import json
from pathlib import Path
import re
import shutil
import sys

from .io_helpers import json_bytes,reserve_outputs,_unique_object,_finite_float
from .scenario_commands import _read


def _read_replay(path):
    from .agent_worlds import MAX_REPORT_BYTES
    with Path(path).open('rb')as handle:raw=handle.read(MAX_REPORT_BYTES+1)
    if len(raw)>MAX_REPORT_BYTES:raise ValueError('replay exceeds report budget')
    return json.loads(raw,object_pairs_hook=_unique_object,parse_float=_finite_float,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))


def register_agent_commands(commands):
    group=commands.add_parser('agents',help='Construct and run communicating model roles, or replay without models')
    children=group.add_subparsers(dest='agents_command',required=True)
    replay=children.add_parser('replay');replay.add_argument('--input',required=True);replay.add_argument('--output',required=True)
    simulate=children.add_parser('simulate',help='Explicit model access; preserves private per-call and world artifacts')
    source=simulate.add_mutually_exclusive_group(required=True);source.add_argument('--brief');source.add_argument('--world')
    simulate.add_argument('--transport',choices=('agy','openai','gemini','typesafe','ollama','laya','laya-http'),required=True)
    simulate.add_argument('--model',required=True);simulate.add_argument('--allow-model',action='store_true')
    simulate.add_argument('--public-input',action='store_true',help='Required for development CLI; never use confidential inputs there')
    simulate.add_argument('--endpoint');simulate.add_argument('--api-key-env',help='Read only this explicitly selected key variable, never save it')
    simulate.add_argument('--http-client',choices=('urllib','curl'),help='TypeSafe only: explicit HTTP transport')
    simulate.add_argument('--env-file',help='TypeSafe only: explicit bounded local file; reads only the named key')
    simulate.add_argument('--timeout',type=int,default=180);simulate.add_argument('--max-output-tokens',type=int,default=4096)
    simulate.add_argument('--max-calls',type=int,required=True);simulate.add_argument('--seed',type=int,default=42)
    simulate.add_argument('--output-dir',required=True,help='New private run directory; existing directories are refused')


def run_agent_command(args):
    if args.command!='agents':return None
    try:
        if args.agents_command=='replay':
            from .agent_worlds import replay_agent_world
            with reserve_outputs([Path(args.output)])as reservation:
                result=replay_agent_world(_read_replay(args.input));reservation.write(args.output,json_bytes(result))
            print('Agent-world replay verified and saved privately. Zero model calls.')
            return 0
        if not args.allow_model:raise ValueError('explicit model access required')
        from .agent_models import AgyTextModel,NativeTextModel
        from .agent_orchestration import run_live
        if args.transport!='typesafe' and (args.env_file is not None or args.http_client is not None):
            raise ValueError('env-file and HTTP transport apply only to TypeSafe')
        if args.transport in ('ollama','laya','laya-http'):
            if args.brief or args.api_key_env or (args.endpoint and args.transport!='laya-http'):raise ValueError('Local actor route requires an authored world and no key')
            from .jev import JevActorModel
            if args.transport=='laya-http':
                from .laya_http_client import LayaHTTPClient
                local_client=LayaHTTPClient(endpoint=args.endpoint or 'http://127.0.0.1:8765/v1/systemone',timeout_seconds=args.timeout)
                if args.model!=local_client.model:raise ValueError('Laya model identity mismatch')
            elif args.transport=='laya':
                from .laya_choices import LayaChoiceClient
                local_client=LayaChoiceClient(model=args.model,timeout_seconds=args.timeout)
            else:
                from .local_choices import LocalChoiceClient
                local_client=LocalChoiceClient(model=args.model,timeout_seconds=args.timeout)
            client=JevActorModel(client=local_client)
        elif args.transport=='typesafe':
            if args.brief:raise ValueError('Jev cannot construct a world; provide authored world')
            from .jev_commands import typesafe_actor_client
            client=typesafe_actor_client(args)
        elif args.transport=='agy':
            binary=shutil.which('agy')
            if not binary:raise ValueError('installed Antigravity CLI unavailable')
            if args.endpoint or args.api_key_env:raise ValueError('CLI does not take endpoint or key')
            client=AgyTextModel(model=args.model,binary=binary,public_input=args.public_input,timeout_seconds=args.timeout)
        else:
            if (not args.endpoint or not args.api_key_env or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',args.api_key_env)):raise ValueError('explicit endpoint and key variable required')
            client=NativeTextModel(model=args.model,endpoint=args.endpoint,api_key=os.environ.get(args.api_key_env,''),protocol=args.transport,timeout_seconds=args.timeout,max_output_tokens=args.max_output_tokens)
        result=run_live(client=client,output_dir=args.output_dir,brief=_read(args.brief)if args.brief else None,
                        world=_read(args.world)if args.world else None,seed=args.seed,max_calls=args.max_calls)
        print(f'Agent run {result["status"]}: {result["attempted_calls"]} model attempts, {result["completed_rounds"]} completed rounds. Inspect private manifest and receipts; dollar cost unknown.')
        if result.get('error')and result['error'].get('details'):
            print(json.dumps(result['error']['details']),file=sys.stderr)
        return 0 if result['status']=='completed'else 2
    except (OSError,ValueError,KeyError,TypeError,RecursionError,OverflowError):
        print('Agent operation failed. Check explicit schema, call budget, model access and fresh output path. No retry or hidden fallback; inspect any preserved private manifest.',file=sys.stderr)
        return 2
