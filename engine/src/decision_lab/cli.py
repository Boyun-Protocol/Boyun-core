"""Command line boundary for explicit synthetic experiments."""
import argparse
import hashlib
import json
import os
import platform
import sqlite3
import sys
from pathlib import Path

from .checkpoints import run_checkpointed
from .core_commands import register_core_commands, run_core_command
from .io_helpers import read_json as _read, json_bytes as _json_bytes, open_private
from .identity import engine_fingerprint as _source_fingerprint
from .intelligence_commands import register_intelligence_commands, run_intelligence_command
from .public_commands import register_public_commands, run_public_command
from .scenario_commands import register_scenario_commands, run_scenario_command
from .choice_commands import register_choice_commands, run_choice_command
from .agent_commands import register_agent_commands, run_agent_command
from .decision_commands import register_decision_commands, run_decision_command
from .jev_commands import register_jev_commands, run_jev_command
from .strategic_commands import register_strategic_commands, run_strategic_command
from .social_commands import register_social_commands, run_social_command
from .journey_commands import register_journey_commands,run_journey_command
from .case_commands import register_case_commands, run_case_command
from .timeline_commands import register_timeline_commands, run_timeline_command
from .campaign_commands import register_campaign_commands, run_campaign_command
from .evidence_commands import register_evidence_commands, run_evidence_command
from .policy_bundles import compile_bundle
from .policy_preparation import import_response, prepare_request
from .simulation import compare_plans, default_scenario, load_pool, simulate


def main(argv=None):
    parser = argparse.ArgumentParser(description="Boyun decision lab; offline synthetic worlds, not a calibrated forecast.")
    commands = parser.add_subparsers(dest="command", required=True)
    mcp = commands.add_parser('mcp', help='Offline-only MCP stdio server for external agents (optional mcp extra)')
    mcp.add_argument('--workspace', required=True, help='Explicit private mode-0700 workspace; tools accept opaque IDs, never paths')
    run = commands.add_parser("run")
    run.add_argument("--scenario", help="Explicit synthetic JSON; uses built-in fixture when omitted")
    run.add_argument("--pool", help="Reviewed original persona library JSON")
    run.add_argument("--policy-bundle", help="Inert JSON strategy proposal; validated before execution")
    run.add_argument("--worlds", type=int, default=100)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--output", required=True)
    run.add_argument("--compare", action="store_true")
    run.add_argument("--checkpoint", help="Private completed-world checkpoint; compare is unsupported")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--max-new-worlds", type=int, help="Pause after this many newly completed worlds")
    serve = commands.add_parser("serve", help="Local product and lab; live routes require explicit server flags and user execution")
    serve.add_argument("--host", default="127.0.0.1", help="Only 127.0.0.1 is supported")
    serve.add_argument("--port", type=int, default=8769)
    serve.add_argument("--container-bind", action="store_true",
                       help="Bind every interface so a published container port is reachable; "
                            "the loopback Host and Origin checks stay enforced")
    serve.add_argument("--acknowledge-host-access", action="store_true",
                       help="You knowingly run this app where a machine operator could read stored "
                             "scenarios and imported keys; shows the in-product host-trust notice")
    serve.add_argument("--output-dir", default="engine/output/workbench")
    serve.add_argument("--policy-bundle", help="Explicit local imported-policy bundle for comparison")
    serve.add_argument("--policy-evidence", help="Optional local pilot evidence; never exposed as raw logs")
    serve.add_argument("--wallet-observations", action="append", default=[], help="Explicit local observed-wallet snapshot; can repeat for separate networks")
    serve.add_argument("--topic-observations", action="append", default=[], help="Explicit local news/social metadata snapshot")
    serve.add_argument("--public-archive", help="Explicit read-only forward public-history archive")
    from .cloud_configuration import add_cloud_arguments
    add_cloud_arguments(serve)
    serve.add_argument('--enable-gemini', action='store_true', help='Enable installed Antigravity author/actor route for explicitly public inputs')
    serve.add_argument('--gemini-model', default='gemini-3.8-flash-high')
    serve.add_argument('--model-timeout', type=int, default=180)
    serve.add_argument('--typesafe-http-client',choices=('urllib','curl'),default='urllib',help='Explicit TypeSafe client; no transport fallback')
    serve.add_argument('--typesafe-model',default='jev-latest',help='Explicit native Jev model or alias; record resolved model')
    serve.add_argument('--enable-typesafe',action='store_true',help='Enable TypeSafe actor route using only the selected process key')
    serve.add_argument('--typesafe-api-key-env',help='Explicit selected key variable; default TYPESAFE_API_KEY')
    serve.add_argument('--typesafe-env-file', help='Explicit local dotenv path; read only TYPESAFE_API_KEY, never send to browser')
    serve.add_argument('--enable-internal-map',action='store_true',help='Local developer navigation map only; never enable on a reviewer backend')
    serve.add_argument('--near-registry-contract')
    serve.add_argument('--near-registry-code-hash')
    serve.add_argument('--near-relayer-credential-file',help='Owner-only fresh dedicated TESTNET demo credential; no inference or submit at startup')
    serve.add_argument('--near-relayer-output-dir',default='engine/output/near-relayer-submissions')
    serve.add_argument('--near-relayer-script',help='Installed Node testnet signing helper path')
    policy = commands.add_parser("policy", help="Prepare, validate, or explicitly request an inert proposal")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    compile_command = policy_commands.add_parser("compile")
    compile_command.add_argument("--input", required=True)
    compile_command.add_argument("--pool")
    compile_command.add_argument("--output", required=True)
    prepare = policy_commands.add_parser("prepare", help="Export exact model messages; no request is sent")
    prepare.add_argument("--scenario")
    prepare.add_argument("--pool")
    prepare.add_argument("--model", required=True, help="Declared provider/model identifier; availability unverified")
    prepare.add_argument("--template", action="append", required=True, dest="template_ids")
    prepare.add_argument("--fallback", choices=("baseline", "abstain"), default="baseline")
    prepare.add_argument("--max-output-tokens", type=int, default=4096)
    prepare.add_argument("--output", required=True)
    ingest = policy_commands.add_parser("import", help="Validate caller-supplied model output and record provenance")
    ingest.add_argument("--request", required=True)
    ingest.add_argument("--response", required=True)
    ingest.add_argument("--pool")
    ingest.add_argument("--bundle-id", required=True)
    ingest.add_argument("--output", required=True)
    register_core_commands(commands, policy_commands)
    register_intelligence_commands(commands)
    register_public_commands(commands)
    register_scenario_commands(commands)
    register_choice_commands(commands)
    register_agent_commands(commands)
    register_decision_commands(commands)
    register_jev_commands(commands)
    register_strategic_commands(commands)
    register_social_commands(commands)
    register_journey_commands(commands)
    register_case_commands(commands)
    register_timeline_commands(commands)
    register_campaign_commands(commands)
    register_evidence_commands(commands)
    args = parser.parse_args(argv)
    if args.command == 'mcp':
        from .mcp_server import run_stdio
        return run_stdio(args.workspace)
    for handler in (run_evidence_command,run_journey_command,run_jev_command,run_strategic_command,run_social_command,run_case_command,run_timeline_command,run_campaign_command):
        result=handler(args)
        if result is not None:return result
    decision_result = run_decision_command(args)
    if decision_result is not None:
        return decision_result
    agent_result = run_agent_command(args)
    if agent_result is not None:
        return agent_result
    world_result = run_choice_command(args)
    if world_result is not None:
        return world_result
    scenario_result = run_scenario_command(args)
    if scenario_result is not None:
        return scenario_result
    if args.command == "serve":
        if args.host != "127.0.0.1" or not 0 <= args.port <= 65535:
            print("Workbench requires 127.0.0.1 and a valid local port.", file=sys.stderr)
            return 2
        from .web_server import create_server
        try:
            author=None; actors={}; route_status={}
            if not 1 <= args.model_timeout <= 300:
                raise ValueError('model timeout outside bounds')
            if args.enable_gemini:
                import shutil
                from .agent_models import AgyTextModel
                binary=shutil.which('agy')
                if not binary:raise ValueError('installed Antigravity CLI unavailable')
                author=AgyTextModel(model=args.gemini_model,binary=binary,public_input=True,timeout_seconds=args.model_timeout)
                from .gemini_decisions import GeminiDecisions
                actors['gemini']=GeminiDecisions(author)
            if args.typesafe_env_file or args.enable_typesafe:
                from .env_config import load_env_key
                from .jev import TypeSafeClient
                name=args.typesafe_api_key_env or ('TYPESAFE_API_KEY'if args.typesafe_env_file else'TYPESAFE_API_KEY')
                import re
                if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}',name):raise ValueError('explicit key name required')
                key=load_env_key(args.typesafe_env_file,name=name)if args.typesafe_env_file else os.environ.get(name,'')
                actors['typesafe']=TypeSafeClient(api_key=key,model=args.typesafe_model,
                    timeout_seconds=args.model_timeout,http_client=args.typesafe_http_client)
                route_status['typesafe']='Key configured locally. Use the explicit model-catalog check to verify access; no inference at startup.'
            from .cloud_configuration import configured_author
            cloud=configured_author(args)
            if cloud is not None:author=cloud
            near=None
            if args.near_relayer_credential_file:
                from .near_registry import NearRegistryClient,NearRegistryRelayer
                near=NearRegistryRelayer(NearRegistryClient(contract_id=args.near_registry_contract,expected_code_hash=args.near_registry_code_hash),
                    credential_file=args.near_relayer_credential_file,output_dir=args.near_relayer_output_dir,script_path=args.near_relayer_script)
            elif args.near_registry_contract or args.near_registry_code_hash or args.near_relayer_script:raise ValueError('explicit testnet relay credential required')
            server = create_server(host=args.host, port=args.port, output_dir=args.output_dir,
                                   policy_bundle_path=args.policy_bundle, policy_evidence_path=args.policy_evidence,
                                   wallet_observation_paths=args.wallet_observations, topic_observation_paths=args.topic_observations,
                                   public_archive_path=args.public_archive, product_author_client=author,
                                   product_actor_clients=actors, product_route_status=route_status,product_near_relayer=near,enable_internal_map=args.enable_internal_map,
                                   container_bind=args.container_bind, hosted=args.acknowledge_host_access)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
            print("Cannot start workbench: invalid configuration or unavailable local resources.", file=sys.stderr)
            return 2
        print(f"Boyun Lab: http://127.0.0.1:{server.server_address[1]} (local product; model calls only on explicit execution)", flush=True)
        if args.container_bind:
            print("Container bind is active: publish this port only on the host's own loopback, "
                  "and never on a shared network or public interface.", file=sys.stderr, flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    public_result = run_public_command(args)
    if public_result is not None:
        return public_result
    intelligence_result = run_intelligence_command(args)
    if intelligence_result is not None:
        return intelligence_result
    core_result = run_core_command(args)
    if core_result is not None:
        return core_result
    created = []
    try:
        output = Path(args.output)
        if args.command == "policy":
            if output.exists():
                raise ValueError("output already exists")
            pool = _read(args.pool) if args.pool else load_pool()
            if args.policy_command == "compile":
                bundle = compile_bundle(_read(args.input), pool)
                artifacts = [(output, _json_bytes(bundle.as_dict()))]
                notice = "Validated policy structure; provenance and behavioral accuracy remain unverified. 0 model calls."
            elif args.policy_command == "prepare":
                scenario = _read(args.scenario) if args.scenario else default_scenario()
                request = prepare_request(scenario, pool, model=args.model, template_ids=args.template_ids,
                                          fallback=args.fallback, max_output_tokens=args.max_output_tokens)
                artifacts = [(output, _json_bytes(request))]
                notice = "Saved private local policy request. No request sent; model availability unverified. 0 model calls."
            else:
                receipt_path = output.with_suffix(".preparation.json")
                if receipt_path == output or receipt_path.exists():
                    raise ValueError("preparation receipt already exists or conflicts with output")
                bundle, receipt = import_response(_read(args.request), _read(args.response), pool,
                                                  bundle_id=args.bundle_id)
                artifacts = [(output, _json_bytes(bundle)), (receipt_path, _json_bytes(receipt))]
                notice = "Validated imported policy and saved preparation receipt. Source/usage unverified; cost unknown. 0 local model calls."
            output.parent.mkdir(parents=True, exist_ok=True)
            for path, data in artifacts:
                with path.open("xb") as handle:
                    info = os.fstat(handle.fileno())
                    created.append((path, info.st_dev, info.st_ino))
                    os.fchmod(handle.fileno(), 0o600)
                    handle.write(data)
            print(notice)
            return 0
        manifest_path = output.with_suffix(".manifest.json")
        if (args.resume or args.max_new_worlds is not None) and not args.checkpoint:
            raise ValueError("resume and max-new-worlds require --checkpoint")
        if args.compare and args.checkpoint:
            raise ValueError("checkpoint comparison is unsupported")
        if args.checkpoint:
            checkpoint = Path(args.checkpoint)
            lock = checkpoint.with_name(checkpoint.name + ".lock")
            if any(path.resolve() == other.resolve() for path in (output, manifest_path) for other in (checkpoint, lock)):
                raise ValueError("checkpoint conflicts with result or manifest")
        if output == manifest_path or output.exists() or manifest_path.exists():
            raise ValueError("output or manifest already exists")
        scenario = _read(args.scenario) if args.scenario else default_scenario()
        pool = _read(args.pool) if args.pool else load_pool()
        proposal = _read(args.policy_bundle) if args.policy_bundle else None
        action = compare_plans if args.compare else simulate
        if args.checkpoint:
            report = run_checkpointed(scenario, pool, checkpoint_path=args.checkpoint, worlds=args.worlds,
                                      seed=args.seed, policy_bundle=proposal, resume=args.resume,
                                      max_new_worlds=args.max_new_worlds)
            if report is None:
                print("Saved completed-world checkpoint; run paused. Resume explicitly with --checkpoint and --resume. No final report or manifest written.")
                return 0
        else:
            report = action(scenario, pool, args.worlds, args.seed, policy_bundle=proposal)
        primary = report["plans"]["launch_now"] if args.compare else report
        encoded = _json_bytes(report)
        manifest = {
            "schema_version": "run-manifest.v1", "source_mode": "synthetic",
            "world_count": args.worlds, "seed": args.seed,
            "scenario_sha256": primary["scenario_sha256"], "policy_version": primary["policy_version"],
            "policy_bundle": primary["policy_bundle"],
            "policy_bundle_sha256": primary["policy_bundle_sha256"],
            "persona_pool_sha256": hashlib.sha256(_json_bytes(pool)).hexdigest(),
            "engine_source_sha256": _source_fingerprint(),
            "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation()},
            "scenario": scenario,
            "result_sha256": hashlib.sha256(encoded).hexdigest(),
            "model_rollout_calls": 0, "comparison": args.compare,
            "reproduction": "Retain the persona pool and engine matching these hashes. Use the saved scenario, seed, world count and Python runtime. This local manifest can contain confidential inputs; do not publish it by default.",
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects previous work, including a race with a
        # second writer. Roll back only the paths this invocation created.
        for path, data in ((output, encoded), (manifest_path, _json_bytes(manifest))):
            with open_private(path) as handle:
                info = os.fstat(handle.fileno())
                created.append((path, info.st_dev, info.st_ino))
                handle.write(data)
    except (ValueError, OSError, KeyError, TypeError) as error:
        for path, device, inode in created:
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (device, inode):
                    path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
        if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError):
            print(f"Cannot run synthetic experiment: {error}", file=sys.stderr)
        else:
            print("Cannot run synthetic experiment: invalid input or inaccessible output.", file=sys.stderr)
        return 2
    print(f"Saved synthetic result: {args.worlds} worlds; 0 model calls. Not calibrated real-world odds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
