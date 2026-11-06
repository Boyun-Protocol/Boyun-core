"""Explicit saved-world operations; no authoring or model inference."""
from pathlib import Path
import sys

from .io_helpers import json_bytes, reserve_outputs
from .scenario_commands import _read


def register_choice_commands(commands):
    world = commands.add_parser('world', help='Start, step, verify or fork an explicit choice world')
    children = world.add_subparsers(dest='world_command',required=True)
    for name in ('start','step','validate','options','fork'):
        child = children.add_parser(name)
        child.add_argument('--input',required=True)
        child.add_argument('--output',required=True)
        if name == 'start':
            child.add_argument('--seed',type=int,default=42)
            child.add_argument('--world-id',type=int,default=0)
        elif name == 'step':
            child.add_argument('--choice-id',required=True)
            child.add_argument('--action-id',required=True)
        elif name == 'fork':
            child.add_argument('--branch-id',required=True)


def run_choice_command(args):
    if args.command != 'world':
        return None
    from .choice_worlds import (start_choice_world,step_choice_world,validate_choice_snapshot,
                               choice_options,fork_choice_world)
    try:
        with reserve_outputs([Path(args.output)]) as reservation:
            value = _read(args.input)
            if args.world_command == 'start':
                result = start_choice_world(value,seed=args.seed,world_id=args.world_id)
            elif args.world_command == 'step':
                result = step_choice_world(value,args.choice_id,args.action_id)
            elif args.world_command == 'fork':
                result = fork_choice_world(value,args.branch_id)
            elif args.world_command == 'options':
                result = choice_options(value)
            else:
                result = validate_choice_snapshot(value)
            reservation.write(args.output,json_bytes(result))
        print('Saved private choice-world artifact. No model, network or financial transaction.')
        return 0
    except (ValueError,KeyError,TypeError,OSError,RecursionError,OverflowError):
        print('World operation failed: check the explicit input, history, choice eligibility, identity and output path.',file=sys.stderr)
        return 2
