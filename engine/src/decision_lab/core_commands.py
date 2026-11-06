"""CLI adapters for local core modules and deliberate single provider requests."""
import os
from pathlib import Path
import re
import sys

from . import providers
from .evaluation import evaluate_forecasts
from .experiments import ALLOWED_PARAMETERS, compare_policies, sensitivity
from .integrity import create_commitment, near_anchor_action, verify_commitment
from .io_helpers import json_bytes, read_json, reserve_outputs, write_artifacts
from .policy_preparation import validate_request
from .simulation import default_scenario, load_pool


def register_core_commands(commands, policy_commands):
    experiment = commands.add_parser("experiment", help="Matched synthetic comparisons; no model calls")
    experiments = experiment.add_subparsers(dest="experiment_command", required=True)
    policies = experiments.add_parser("policies")
    policies.add_argument("--policy-bundle", required=True)
    sweep = experiments.add_parser("sensitivity")
    sweep.add_argument("--policy-bundle")
    sweep.add_argument("--parameter", required=True, choices=sorted(ALLOWED_PARAMETERS))
    sweep.add_argument("--value", type=int, action="append", required=True, dest="values")
    for command in (policies, sweep):
        command.add_argument("--scenario")
        command.add_argument("--pool")
        command.add_argument("--worlds", type=int, default=100)
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--output", required=True)
    evaluation = commands.add_parser("evaluate", help="Score supplied chronological binary forecasts")
    evaluation.add_argument("--input", required=True)
    evaluation.add_argument("--output", required=True)
    receipts = commands.add_parser("receipt", help="Private openings and unsigned actions; no publication")
    receipt_commands = receipts.add_subparsers(dest="receipt_command", required=True)
    create = receipt_commands.add_parser("create")
    create.add_argument("--input", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--opening-output", required=True)
    verify = receipt_commands.add_parser("verify")
    verify.add_argument("--input", required=True)
    verify.add_argument("--public", required=True)
    verify.add_argument("--opening", required=True)
    near = receipt_commands.add_parser("near-action")
    near.add_argument("--public", required=True)
    near.add_argument("--network", choices=("testnet",), required=True)
    near.add_argument("--signer", required=True)
    near.add_argument("--contract", required=True)
    near.add_argument("--output", required=True)
    generate = policy_commands.add_parser("generate", help="Send one explicit opt-in provider request; never retry")
    generate.add_argument("--request", required=True)
    generate.add_argument("--pool")
    generate.add_argument("--protocol", choices=("openai", "gemini"), required=True)
    generate.add_argument("--endpoint", required=True, help="Full explicitly selected REST endpoint")
    generate.add_argument("--api-key-env", required=True, help="Environment variable containing the key")
    generate.add_argument("--allow-network", action="store_true")
    generate.add_argument("--timeout", type=int, default=60)
    generate.add_argument("--output", required=True)


def _failure(status, code, attempts, remote_outcome):
    return {"schema_version": "provider-transport-attempt.v1", "status": status,
            "error_code": code, "transport_attempts": attempts, "remote_outcome": remote_outcome,
            "usage": None, "cost_usd": None, "usage_status": "unknown",
            "automatic_retry": False,
            "limitations": "A transport attempt does not prove model execution or billing. Retain these files; investigate remote outcome before any deliberate resubmission."}


def _generate(args):
    if not args.allow_network:
        raise ValueError("generation requires explicit --allow-network")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.api_key_env):
        raise ValueError("invalid key environment variable name")
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise ValueError("selected key environment variable is empty or absent")
    pool = read_json(args.pool) if args.pool else load_pool()
    request = validate_request(read_json(args.request), pool)
    output = Path(args.output)
    receipt_path = output.with_suffix(".transport.json")
    if receipt_path == output:
        raise ValueError("output conflicts with transport receipt")
    with reserve_outputs((output, receipt_path)) as reserved:
        # Durable intent precedes dispatch. A crash leaves an honest unknown
        # outcome marker rather than encouraging an automatic duplicate call.
        marker = {"schema_version": "policy-generation-status.v1", "status": "dispatch_pending",
                  "remote_outcome": "unknown", "automatic_retry": False}
        reserved.write(output, json_bytes(marker))
        reserved.write(receipt_path, json_bytes(_failure("dispatch_pending", None, None, "unknown")))
        reserved.sync_directories()
        reserved.preserve = True
        try:
            response, receipt = providers.generate_response(request, pool, endpoint=args.endpoint,
                api_key=api_key, protocol=args.protocol, timeout_seconds=args.timeout)
        except BaseException as error:
            attempts, remote, code = 1, "unknown", "unexpected_failure"
            if isinstance(error, providers.ProviderError):
                attempts = error.request_count if type(error.request_count) is int and error.request_count in (0, 1) else 1
                remote = error.remote_outcome if error.remote_outcome in {"not_dispatched", "unknown", "response_received"} else "unknown"
                code = error.code if error.code in {"invalid_input", "timeout", "transport", "invalid_response"} else "provider_failure"
            marker.update(status="failed", remote_outcome=remote)
            reserved.write(output, json_bytes(marker))
            reserved.write(receipt_path, json_bytes(_failure("failed", code, attempts, remote)))
            if not isinstance(error, Exception):
                raise
            print("Provider generation failed; private evidence retained. No automatic retry; remote execution and billing may be unknown.", file=sys.stderr)
            return 2
        # Write the receipt first, so a later response write failure retains
        # evidence of the request. Both descriptors were reserved pre-dispatch.
        reserved.write(receipt_path, json_bytes(receipt))
        reserved.write(output, json_bytes(response))
    print("Saved private provider response and transport receipt. Provider usage unverified; cost unknown. No automatic retry.")
    return 0


def run_core_command(args):
    """Return None for legacy commands, otherwise a process exit code."""
    generate = args.command == "policy" and args.policy_command == "generate"
    if not generate and args.command not in {"experiment", "evaluate", "receipt"}:
        return None
    try:
        if generate:
            return _generate(args)
        if args.command == "experiment":
            scenario = read_json(args.scenario) if args.scenario else default_scenario()
            pool = read_json(args.pool) if args.pool else load_pool()
            policy = read_json(args.policy_bundle) if args.policy_bundle else None
            if args.experiment_command == "policies":
                result = compare_policies(scenario, pool, policy, worlds=args.worlds, seed=args.seed)
            else:
                result = sensitivity(scenario, pool, parameter=args.parameter, values=args.values,
                                     worlds=args.worlds, seed=args.seed, policy_bundle=policy)
            artifacts = [(Path(args.output), json_bytes(result))]
            notice = "Saved conditional synthetic comparison. 0 model calls; not calibrated real-world odds."
        elif args.command == "evaluate":
            artifacts = [(Path(args.output), json_bytes(evaluate_forecasts(read_json(args.input))))]
            notice = "Saved scores for supplied records; source content and historical relevance unverified."
        elif args.receipt_command == "verify":
            matched = verify_commitment(Path(args.input).read_bytes(), read_json(args.public), read_json(args.opening))
            print("Artifact commitment matches." if matched else "Artifact commitment does not match.")
            return 0 if matched else 2
        elif args.receipt_command == "create":
            public, private = create_commitment(Path(args.input).read_bytes())
            artifacts = [(Path(args.output), json_bytes(public)), (Path(args.opening_output), json_bytes(private))]
            notice = "Saved local public commitment and private opening. Nothing published; protect the opening and artifact."
        else:
            action = near_anchor_action(read_json(args.public), network=args.network,
                                        signer_id=args.signer, contract_id=args.contract)
            artifacts = [(Path(args.output), json_bytes(action))]
            notice = "Saved unsigned NEAR testnet action. Contract compatibility unverified; nothing signed or submitted."
        write_artifacts(artifacts)
    except (ValueError, OSError, KeyError, TypeError):
        # Inputs and keys can be confidential; never reflect exception text.
        if generate:
            print("Provider generation could not complete: check explicit opt-in/key, input, and output paths. Inspect any retained private evidence; remote execution/billing may be unknown. No automatic retry.", file=sys.stderr)
        else:
            print("Cannot complete command: invalid input or inaccessible/existing output.", file=sys.stderr)
        return 2
    print(notice)
    return 0
