"""Run each archived MACRON path sequentially; preserve failures and resumable outputs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'engine/output/cases/macron-solana-2026-10-29/lifecycle-matrix-2026-11-02/native-jev'
OUTPUT = ROOT/'engine/output/macron-laya-continuation-2026-11-04'
OUTPUT.mkdir(parents=True, exist_ok=True)
paths = sorted(SOURCE.glob('macron-*/*/manifest.json'), key=lambda p: (
    'p5000-c5000' not in str(p), 'pause-and-observe' not in str(p), str(p)))
status = {'status':'running', 'started_unix':time.time(), 'total_paths':len(paths), 'paths':[]}

def save():
    tmp=OUTPUT/'batch-status.tmp'
    tmp.write_text(json.dumps(status,indent=2))
    os.replace(tmp,OUTPUT/'batch-status.json')

save()
for item in paths:
    source=item.parent
    name=source.parent.name.removeprefix('macron-')+'-'+('pause' if source.name=='pause-and-observe' else source.name)
    output=OUTPUT/name
    row={'name':name,'source':str(source),'output':str(output),'status':'running'}
    status['paths'].append(row)
    save()
    with (OUTPUT/(name+'.log')).open('a') as log:
        result=subprocess.run([sys.executable, '-u', str(ROOT/'engine/tools/continue_laya_lifecycle.py'),
                               '--source',str(source),'--output',str(output)], stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
    row['exit_code']=result.returncode
    row['status']='completed' if result.returncode==0 else 'failed'
    save()
status['status']='completed' if all(x['status']=='completed' for x in status['paths']) else 'finished_with_failures'
status['finished_unix']=time.time()
save()
