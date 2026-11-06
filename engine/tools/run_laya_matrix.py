"""Run every MACRON matrix world with Laya from hour 0; resumable, parallel, honest status."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'engine/output/cases/macron-solana-2026-10-29/lifecycle-matrix-2026-11-02/native-jev'
DEFAULT_OUTPUT = ROOT/'engine/output/macron-laya-from-start-2026-11-04'
THREADS_PER_WORKER = '2'


def path_name(source):
    policy = 'pause' if source.name == 'pause-and-observe' else source.name
    return source.parent.name.removeprefix('macron-') + '-' + policy


def ordered_sources():
    manifests = SOURCE.glob('macron-*/*/manifest.json')
    return sorted((m.parent for m in manifests), key=lambda s: (
        'p5000-c5000' not in str(s), 'pause-and-observe' != s.name, str(s)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--only', nargs='*', help='Path names to run, e.g. bull-p5000-c5000-pause')
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error('--workers must be between 1 and 8')
    sources = ordered_sources()
    if args.only:
        sources = [s for s in sources if path_name(s) in set(args.only)]
        missing = set(args.only) - {path_name(s) for s in sources}
        if missing:
            parser.error('unknown path names: %s' % ', '.join(sorted(missing)))
    args.output.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    status = {'status': 'running', 'mode': 'laya_from_start', 'runner_pid': os.getpid(),
              'started_unix': time.time(), 'total_paths': len(sources),
              'paths': [{'name': path_name(s), 'source': str(s), 'output': str(args.output/path_name(s)),
                         'status': 'queued'} for s in sources]}

    def save():
        temporary = args.output/'batch-status.tmp'
        temporary.write_text(json.dumps(status, indent=2))
        os.replace(temporary, args.output/'batch-status.json')

    def run(row):
        env = {**os.environ, 'OMP_NUM_THREADS': THREADS_PER_WORKER, 'MKL_NUM_THREADS': THREADS_PER_WORKER,
               'PYTHONPATH': str(ROOT/'engine/src')}
        command = [sys.executable, '-u', str(ROOT/'engine/tools/continue_laya_lifecycle.py'), '--from-start',
                   '--source', row['source'], '--output', row['output']]
        with (args.output/(row['name'] + '.log')).open('a') as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, env=env)
            with lock:
                row.update(status='running', pid=process.pid, started_unix=time.time())
                save()
            code = process.wait()
        with lock:
            row.update(status='completed' if code == 0 else 'failed', exit_code=code, finished_unix=time.time())
            save()

    with lock:
        save()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run, status['paths']))
    status['status'] = 'completed' if all(r['status'] == 'completed' for r in status['paths']) else 'finished_with_failures'
    status['finished_unix'] = time.time()
    save()


if __name__ == '__main__':
    main()
