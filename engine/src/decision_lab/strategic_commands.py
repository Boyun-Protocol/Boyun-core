"""Private offline strategic analysis; no authoring, inference or execution."""
from pathlib import Path
import sys

from .io_helpers import json_bytes, reserve_outputs
from .scenario_commands import _read


def register_strategic_commands(commands):
    mechanics = commands.add_parser('mechanics', help='Explicit strategic/probability mechanics, advisory only')
    children = mechanics.add_subparsers(dest='mechanics_command', required=True)
    for name, help_text in (('game', 'Exact expected utility, pure Nash and pure-action dominance'),
                            ('bayes', 'Exact finite-hypothesis update from explicit priors and likelihoods')):
        child = children.add_parser(name, help=help_text)
        child.add_argument('--input', required=True)
        child.add_argument('--output', required=True)


def run_strategic_command(args):
    if args.command != 'mechanics':
        return None
    from .strategic_games import analyze_game
    from .probability_updates import update_beliefs
    try:
        if args.mechanics_command not in {'game', 'bayes'}:
            raise ValueError('unsupported mechanics command')
        with reserve_outputs([Path(args.output)]) as reservation:
            operation = analyze_game if args.mechanics_command == 'game' else update_beliefs
            result = operation(_read(args.input))
            reservation.write(args.output, json_bytes(result))
        print('Saved private advisory mechanics analysis. No model, network or ledger execution.')
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        print('Strategic operation failed: inspect the explicit schema, provenance, beliefs/likelihoods, limits and output availability. No provider was called.', file=sys.stderr)
        return 2
