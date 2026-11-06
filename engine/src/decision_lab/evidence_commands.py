"""Explicit offline evidence audit commands."""
import json

from .io_helpers import read_json
from .simulation_evidence import audit_evidence


def register_evidence_commands(commands):
    group = commands.add_parser('evidence', help='Offline assumption, mechanism and outcome provenance checks')
    children = group.add_subparsers(dest='evidence_command', required=True)
    audit = children.add_parser('audit', help='Check a reviewed target inventory; no URL fetches or inference')
    audit.add_argument('--input', required=True, help='simulation-evidence.v1 register')
    audit.add_argument('--targets', required=True, help='Reviewed mapping from target IDs to claim kinds')


def run_evidence_command(args):
    if args.command != 'evidence':
        return None
    try:
        result = audit_evidence(read_json(args.input), required_targets=read_json(args.targets))
        print(json.dumps(result, indent=2))
        return 2 if result['status'] == 'blocked' else 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError):
        print('Evidence audit failed. Check the register, timestamps and reviewed target inventory; no inference was sent.')
        return 2
