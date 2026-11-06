"""Explicit CLI for controlled peer-subscription experiments; no UI dependency."""
import json
from pathlib import Path
import sys

from . import decision_commands
from .io_helpers import json_bytes, reserve_outputs
from .social_experiments import prepare_social_experiment, run_social_experiment, _read


def register_social_commands(commands):
    group = commands.add_parser('social', help='Prepare or run matched peer-information treatments')
    children = group.add_subparsers(dest='social_command', required=True)
    for name in ('prepare', 'inspect', 'run'):
        parser = children.add_parser(name)
        parser.add_argument('--input', required=True, help='Explicit social-experiment.v1 protocol file')
        if name == 'prepare':
            parser.add_argument('--output', required=True, help='New private validated plan file')
        if name == 'run':
            parser.add_argument('--output-dir', required=True, help='Fresh private experiment directory')
            parser.add_argument('--max-calls', required=True, type=int)
            decision_commands._model_args(parser,actor_only=True)


def run_social_command(args):
    if args.command != 'social':
        return None
    try:
        protocol = _read(args.input)
        plan = prepare_social_experiment(protocol)
        if args.social_command == 'prepare':
            output = Path(args.output)
            with reserve_outputs([output]) as reserved:
                reserved.write(output, json_bytes(plan))
            print(json.dumps({'status': 'prepared', 'required_calls': plan['required_calls'],
                              'protocol_sha256': plan['protocol_sha256'], 'model_requests': 0}))
            return 0
        if args.social_command == 'inspect':
            print(json.dumps(plan, ensure_ascii=True, indent=2))
            return 0
        # Validate the entire call matrix before constructing any provider route.
        if type(args.max_calls) is not int or not plan['required_calls'] <= args.max_calls <= 256:
            raise ValueError('complete bounded call budget required')
        client = decision_commands._client(args)
        manifest = run_social_experiment(protocol=protocol, client=client, output_dir=args.output_dir,
                                         max_calls=args.max_calls)
        print(json.dumps({key: manifest[key] for key in ('status', 'required_calls', 'attempted_calls',
                                                         'completed_pairs', 'failed_arms')}, ensure_ascii=True))
        return 0 if manifest['status'] == 'completed' else 2
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        print('Social experiment blocked or failed. Check the declared peer treatment, complete call budget, '
              'explicit model route and fresh private output path. No automatic retry or model fallback.', file=sys.stderr)
        return 2
