"""CLI boundary for case reports: validate a brief, then render the document set."""
from __future__ import annotations

import json
import sys

from .case_brief import load_brief, read_artefacts
from .case_report import render_case


def register_case_commands(commands):
    group = commands.add_parser('case',
                                help='Build a case report from an interview-driven brief')
    children = group.add_subparsers(dest='case_command', required=True)
    build = children.add_parser('build', help='Render the five documents, figures and data')
    build.add_argument('--case', required=True, help='Case directory containing brief.json')
    build.add_argument('--out', help='Explicit output directory; defaults to <case>/report')
    build.add_argument('--worlds', type=int, help='Override the sampled world count')
    build.add_argument('--public', action='store_true',
                       help='Render the redacted public version: no identity, interview or raw data')
    validate = children.add_parser('validate',
                                   help='Check the brief and every named artefact, render nothing')
    validate.add_argument('--case', required=True)


def run_case_command(args):
    if args.command != 'case':
        return None
    try:
        brief = load_brief(args.case)
        if args.case_command == 'validate':
            artefacts = read_artefacts(args.case, brief)
            print(json.dumps({'case': brief['id'], 'question': brief['question'],
                              'artefacts': sorted(artefacts),
                              'interview_files': len(brief.get('interview_files', [])),
                              'rendered': False}, indent=2))
            return 0
        result = render_case(args.case, args.out, worlds=args.worlds,
                             public=getattr(args, 'public', False))
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError, OverflowError) as error:
        print(f'case report blocked: {error}. Nothing was written outside the report directory.',
              file=sys.stderr)
        return 2
