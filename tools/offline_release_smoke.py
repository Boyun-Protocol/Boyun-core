#!/usr/bin/env python3
"""Run a public synthetic journey using the selected Python installation.

Use the installed venv's Python with -I and --installed-root to reject accidental
checkout imports. No private historical run, .env, provider or RPC is needed.
"""
import argparse
from argparse import Namespace
import hashlib
import json
from pathlib import Path
import socket
import sys


class NetworkForbidden(RuntimeError):
    pass


def deny_external_effects(event, args):
    if event in {
        'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.bind',
        'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.exec',
    }:
        raise NetworkForbidden('offline release check forbids network and child processes')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def smoke(output, format, installed_root=None):
    import decision_lab
    from decision_lab.journey_commands import journey
    from decision_lab.product_api import ProductManager
    from decision_lab.strategic_worlds import replay_strategic_world

    if installed_root is not None:
        require(Path(decision_lab.__file__).resolve().is_relative_to(installed_root.resolve()),
                'decision_lab was imported outside the installed environment')

    # These are explicit answers to the real CLI: first ready world, example
    # question, retail focus, momentum-seeking style, marketing motivation, two rounds,
    # two worlds, highest-score selection, and execution approval.
    answers = iter(['1', '', '2', '2', '2', '2', '2', '1', 'RUN'])
    options = Namespace(output_dir=str(output), offline=True, api_key_env=None,
                        format=format, world=None)
    require(journey(options, read=lambda _: next(answers), write=lambda _: None) == 0,
            'offline journey did not complete')
    product_root = output / 'product'
    sessions = list(product_root.glob('*/state.json'))
    require(len(sessions) == 1, 'expected one persisted session')
    identifier = sessions[0].parent.name
    manager = ProductManager(product_root)
    try:
        state = manager.snapshot(identifier)
        require(state['status'] == 'completed' and len(state['results']) == 2,
                'expected two completed worlds after reopening')
        for result in state['results']:
            require(replay_strategic_world(result['result']) == result['result'],
                    'world replay differs from the recorded execution')
        deck = manager.presentation(identifier)
        provider = deck['slides'][2]['provider']
        require(provider['recorded_model_calls'] == 0 and provider['models'] == [],
                'offline presentation unexpectedly contains model calls')
        require(provider['local_decision_turns'] == 8,
                'expected eight actual local decision turns')
        report = (output / 'scenario-report.md').read_bytes()
        require(manager.report(identifier, 'md', state['run_id']) == report,
                'reopened Markdown differs from journey export')
        if format == 'both':
            require((output / 'scenario-report.pdf').read_bytes().startswith(b'%PDF-'),
                    'PDF export missing or invalid')
    finally:
        manager.close()
    return {
        'fixture': 'public-synthetic-ready-world',
        'completed_worlds': 2,
        'local_decision_turns': provider['local_decision_turns'],
        'provider_calls': provider['recorded_model_calls'],
        'replay_exact': True,
        'reopened_markdown_identical': True,
        'markdown_sha256': hashlib.sha256(report).hexdigest(),
        'pdf_exported': format == 'both',
        'network_blocked': True,
        'installed_import_verified': installed_root is not None,
        'live_provider_verified': False,
        'live_wallet_verified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True, help='NEW private directory')
    parser.add_argument('--installed-root', type=Path, help='Require module import from this venv')
    parser.add_argument('--format', choices=('md', 'both'), default='both')
    args = parser.parse_args()
    sys.addaudithook(deny_external_effects)
    # Verify the guard before importing product code. No packet is sent.
    try:
        socket.create_connection(('127.0.0.1', 9), timeout=.01)
    except NetworkForbidden:
        pass
    else:
        raise RuntimeError('network guard did not intercept the probe')
    try:
        evidence = smoke(args.output_dir, args.format, args.installed_root)
    except Exception as error:
        # Do not print arbitrary scenario/provider exceptions or inherited keys.
        print(f'FAIL: offline release check ({type(error).__name__}); inspect local artifacts.',
              file=sys.stderr)
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
