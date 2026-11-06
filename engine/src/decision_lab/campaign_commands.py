"""Budgeted long-horizon campaign experiments, planning and offline replay."""
import json

from .io_helpers import read_json


def register_campaign_commands(commands):
    group = commands.add_parser('campaign', help='Long-horizon actor decisions with paid exposure and private signals')
    children = group.add_subparsers(dest='campaign_command', required=True)
    for name in ('plan', 'run'):
        command = children.add_parser(name)
        command.add_argument('--input', required=True)
        command.add_argument('--worlds', type=int, required=True)
        command.add_argument('--max-calls', type=int, required=True)
        command.add_argument('--evidence-register', help='Reviewed simulation-evidence.v1 sidecar; required before paid inference')
        command.add_argument('--committed-plan', help='JSON list of funded campaign orders executed before actor decisions')
        command.add_argument('--argmax-legacy', action='store_true', help='Explicitly reproduce the old confidence-gated maximum-score policy')
        command.add_argument('--stress', action='store_true', help='Artificial activity bias, not a realism forecast')
        command.add_argument('--buy-multiplier', type=int, default=4)
        command.add_argument('--sell-multiplier', type=int, default=4)
        command.add_argument('--ticket-multiplier', type=int, default=2)
        if name == 'run':
            command.add_argument('--output-dir', required=True)
            command.add_argument('--seed', type=int, default=7)
            command.add_argument('--allow-model', action='store_true')
            command.add_argument('--env-file', required=True)
            command.add_argument('--api-key-env', default='TYPESAFE_API_KEY')
            command.add_argument('--model', default='jev-1.14.0')
            command.add_argument('--http-client', choices=('curl', 'urllib'), default='curl')
            command.add_argument('--timeout', type=int, default=60)
    replay = children.add_parser('replay')
    replay.add_argument('--directory', required=True)
    summary = children.add_parser('summary', help='Replay-verified final trading and volume counts')
    summary.add_argument('--directory', required=True)


def run_campaign_command(args):
    if args.command != 'campaign':
        return None
    from .campaign_worlds import campaign_plan
    from .campaign_orchestration import run_campaign_experiment, replay_campaign_experiment, summarize_campaign_experiment
    try:
        if args.campaign_command == 'summary':
            result = summarize_campaign_experiment(args.directory)
        elif args.campaign_command == 'replay':
            result = replay_campaign_experiment(args.directory)
        else:
            package = read_json(args.input)
            commitments = read_json(args.committed_plan) if args.committed_plan else None
            evidence = read_json(args.evidence_register) if args.evidence_register else None
            stress = None
            if args.stress:
                from .campaign_stress import stress_config, stress_package
                stress = stress_config(args.buy_multiplier, args.sell_multiplier, args.ticket_multiplier)
            elif (args.buy_multiplier, args.sell_multiplier, args.ticket_multiplier) != (4, 4, 2):
                raise ValueError('activity multipliers require explicit stress mode')
            if args.campaign_command == 'plan':
                if stress is not None:
                    package = stress_package(package, stress)
                result = campaign_plan(package, worlds=args.worlds, max_calls=args.max_calls)
                result['stress_policy'] = stress
                result['decision_policy'] = 'artificial_stress_sampling' if stress else 'legacy_argmax_with_confidence_gate' if args.argmax_legacy else 'sample_jev_action_and_coordination_scores'
                if commitments is not None:
                    from .committed_campaigns import validate_commitments
                    result['committed_plan'] = validate_commitments(package, commitments)
                result['execution_ready'] = False
                result['evidence_status'] = 'not_reviewed; --evidence-register required for run'
                if evidence is not None:
                    from .campaign_evidence import campaign_evidence_context, review_campaign_evidence
                    context = campaign_evidence_context(package, commitments=commitments, stress=stress,
                                                        sample_actions=not args.argmax_legacy)
                    result['evidence_audit'] = review_campaign_evidence(evidence, context)
                    result['evidence_status'] = result['evidence_audit']['status']
                    result['execution_ready'] = True
            else:
                if evidence is None:
                    print('Campaign run blocked: add --evidence-register with reviewed assumptions and outcome mechanisms. No key was read or inference sent.')
                    return 2
                from .campaign_evidence import campaign_evidence_context, review_campaign_evidence
                from .campaign_stress import stress_package
                reviewed_package = stress_package(package, stress) if stress is not None else package
                review_campaign_evidence(evidence, campaign_evidence_context(reviewed_package, commitments=commitments,
                                         stress=stress, sample_actions=not args.argmax_legacy))
                from .jev_commands import typesafe_actor_client
                adapter = typesafe_actor_client(args)
                result = run_campaign_experiment(package=package, client=adapter.client,
                                                 output_dir=args.output_dir, worlds=args.worlds,
                                                 max_calls=args.max_calls, seed=args.seed, stress=stress,
                                                 commitments=commitments, sample_actions=not args.argmax_legacy,
                                                 evidence_register=evidence)
        print(json.dumps(result, indent=2))
        return 2 if result.get('status') == 'failed' else 0
    except (ValueError, OSError, KeyError, TypeError):
        print('Campaign operation failed. Check the input, evidence register, budget and private receipts. No automatic retry.')
        return 2
