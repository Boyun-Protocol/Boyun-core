"""Explicit CLI boundary for timeline inference, replay and actor projections."""
import json
from pathlib import Path

from .io_helpers import read_json, reserve_outputs, json_bytes


def register_timeline_commands(commands):
    group = commands.add_parser('timeline', help='Bounded timestamped financial actor pilot')
    children = group.add_subparsers(dest='timeline_command', required=True)
    run = children.add_parser('run')
    run.add_argument('--input', required=True)
    run.add_argument('--output-dir', required=True)
    run.add_argument('--allow-model', action='store_true')
    run.add_argument('--env-file', required=True)
    run.add_argument('--api-key-env', default='TYPESAFE_API_KEY')
    run.add_argument('--model', default='jev-1.14.0')
    run.add_argument('--http-client', choices=('urllib', 'curl'), default='curl')
    run.add_argument('--timeout', type=int, default=60)
    run.add_argument('--seed', type=int, default=7)
    run.add_argument('--max-calls', type=int, required=True)
    replay = children.add_parser('replay')
    replay.add_argument('--input', required=True)
    replay.add_argument('--output', required=True)
    replay.add_argument('--actor', help='Save only this actor projection after exact replay')
    export = children.add_parser('export', help='Offline self-contained actor graph from verified timeline')
    export.add_argument('--input', required=True)
    export.add_argument('--actor', required=True)
    export.add_argument('--output', required=True)
    export.add_argument('--receipts-dir', help='Optional private directory of recorded model responses')


def run_timeline_command(args):
    if args.command != 'timeline':
        return None
    from .evolving_worlds import replay_evolving, evolving_actor_trajectory
    from .timeline_orchestration import run_timeline
    try:
        if args.timeline_command == 'export':
            from .agent_commands import _read_replay
            from .timeline_presentation import timeline_html
            responses = []
            if args.receipts_dir:
                paths = sorted(Path(args.receipts_dir).glob('call-*.response.json'))
                if len(paths) > 128:
                    raise ValueError('response listing exceeds call budget')
                responses = [read_json(path) for path in paths]
            html = timeline_html(_read_replay(args.input), args.actor, responses)
            with reserve_outputs([Path(args.output)]) as reservation:
                reservation.write(args.output, html.encode())
            print('Saved self-contained actor timeline. Zero model calls.')
            return 0
        if args.timeline_command == 'replay':
            from .agent_commands import _read_replay
            report = _read_replay(args.input)
            result = evolving_actor_trajectory(report, args.actor) if args.actor else replay_evolving(report)
            with reserve_outputs([Path(args.output)]) as reservation:
                reservation.write(args.output, json_bytes(result))
            print('Timeline replay verified. Zero model calls.')
            return 0
        from .jev_commands import typesafe_actor_client
        client = typesafe_actor_client(args)
        manifest = run_timeline(package=read_json(args.input), client=client,
                                output_dir=args.output_dir, seed=args.seed, max_calls=args.max_calls)
        print(json.dumps(manifest, indent=2))
        return 0 if manifest['status'] == 'completed' else 2
    except (ValueError, OSError, KeyError, TypeError):
        print('Timeline operation failed. Inspect private receipts, input and explicit budget. No automatic retry.')
        return 2
