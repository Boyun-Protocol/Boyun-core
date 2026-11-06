"""Local authoring/validation/execution CLI; no model transport or chat loop."""
import json
from pathlib import Path
import sys

from .io_helpers import _finite_float, _unique_object, json_bytes, reserve_outputs
from .scenario_authoring import (
    MAX_BYTES, apply_authoring_response, authoring_guidelines, capabilities,
    compile_draft, prepare_authoring_request, run_package,
)


def register_scenario_commands(commands):
    scenario = commands.add_parser('scenario', help='Agent-independent drafts and data-only execution; no model calls')
    children = scenario.add_subparsers(dest='scenario_command', required=True)
    for name in ('capabilities', 'guidelines', 'validate', 'prepare', 'apply', 'run'):
        command = children.add_parser(name)
        command.add_argument('--output', required=True)
        if name in {'validate', 'prepare', 'apply'}:
            command.add_argument('--input', required=True, help='Local scenario-draft.v1 JSON')
        if name == 'prepare':
            command.add_argument('--model', required=True, help='Declared agent/model label; no request sent')
        if name == 'apply':
            command.add_argument('--response', required=True, help='Revision-bound scenario-authoring-response.v1 JSON')
        if name == 'run':
            source = command.add_mutually_exclusive_group(required=True)
            source.add_argument('--input', help='Draft: compile and execute only when ready')
            source.add_argument('--package', help='Explicit complete module input; bypasses authoring only')
            command.add_argument('--worlds', type=int, default=100)
            command.add_argument('--seed', type=int, default=42)


def _read(path):
    with Path(path).open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('input exceeds size limit')
    return json.loads(raw, object_pairs_hook=_unique_object, parse_float=_finite_float,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def run_scenario_command(args):
    if args.command != 'scenario':
        return None
    try:
        # Reserve before expensive local work; never overwrite an existing file.
        with reserve_outputs([Path(args.output)]) as reservation:
            kind = args.scenario_command
            if kind == 'guidelines':
                raw = authoring_guidelines().encode()
            else:
                if kind == 'capabilities':
                    value = capabilities()
                elif kind == 'validate':
                    value = compile_draft(_read(args.input))
                elif kind == 'prepare':
                    value = prepare_authoring_request(_read(args.input), args.model)
                elif kind == 'apply':
                    value = apply_authoring_response(_read(args.input), _read(args.response))
                elif args.package:
                    value = run_package(_read(args.package), worlds=args.worlds, seed=args.seed)
                else:
                    compilation = compile_draft(_read(args.input))
                    if not compilation['ready']:
                        raise ValueError('draft is not ready')
                    value = run_package(compilation['package'], worlds=args.worlds, seed=args.seed)
                raw = json_bytes(value)
            reservation.write(args.output, raw)
        print('Saved private local scenario artifact. No model or network calls.')
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        print('Scenario operation failed: inspect the published schema, missing fields, limits and output availability. No provider was called.', file=sys.stderr)
        return 2
