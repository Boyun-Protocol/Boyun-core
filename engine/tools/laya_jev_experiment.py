"""Optional head-only Laya imitation experiment, separate from live continuations."""
import argparse
import json
import os
import random
from pathlib import Path
from types import SimpleNamespace

from decision_lab.agent_worlds import digest
from decision_lab.laya_choices import LayaChoiceClient

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'engine/output/cases/macron-solana-2026-10-29/lifecycle-matrix-2026-11-02/native-jev'
OUT = ROOT/'engine/output/macron-laya-jev-experiment-2026-11-04'
MODEL='convaiinnovations/laya-typed-decisions'
REVISION='1a793eb568e6718f15941d08f85432581df534e3'
FILES=['rl_agent_config.json','model.safetensors','tokenizer/*','encoder/*']


def prepare():
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    from laya.agent import Agent
    path=Path(snapshot_download(MODEL,revision=REVISION,local_files_only=True,allow_patterns=FILES))
    cfg=json.loads((path/'rl_agent_config.json').read_text())
    tok=AutoTokenizer.from_pretrained(path/'tokenizer',local_files_only=True)
    probe=SimpleNamespace(tok=tok,cfg=cfg,_to_internal=Agent._to_internal)
    checker=LayaChoiceClient(MODEL,agent=probe)
    pools={'train':[],'holdout':[]}; seen=set(); rejected=0
    for regime in ('bull','bear'):
        root=SOURCE/f'macron-{regime}-p5000-c5000'/'pause-and-observe'
        old=json.loads((root/'manifest.json').read_text())
        for i in range(old['completed_steps']):
            step=json.loads((root/f'step-{i:05d}.json').read_text())
            hour=step['checkpoint']['second']/3600
            part='train' if hour<=48 else ('holdout' if hour>=96 else None)
            if not part: continue
            for actor,entry in step['decision_evidence'].items():
                prefix=entry.get('call_prefix')
                if not prefix or 'answers' not in entry: continue
                req_path=root/(prefix+'.request.json')
                if not req_path.is_file(): continue
                req=json.loads(req_path.read_text())
                key=digest({'state':req['state'],'questions':req['questions']})
                if key in seen: continue
                seen.add(key)
                try: checker._check_input(req['state'],req['questions'])
                except ValueError:
                    rejected+=1;continue
                row={'state':req['state'],'questions':req['questions'],'gold':entry['answers']}
                pools[part].append({'row':row,'regime':regime,'actor':actor,'hour':hour,'request_sha256':key,'source':str(req_path)})
    rng=random.Random(1729)
    OUT.mkdir(parents=True,exist_ok=False)
    stats={'training_window_hours':'0–48','held_out_window_hours':'96+','rejected_truncation':rejected,'selection_seed':1729,
           'limitations':'One simulated scenario; temporally separated observations still correlated. Matching Jev is imitation, not truth or market calibration.'}
    for part,limit in [('train',64),('holdout',32)]:
        rng.shuffle(pools[part]); selected=pools[part][:limit]
        (OUT/(part+'.jsonl')).write_text(''.join(json.dumps(x['row'])+'\n' for x in selected))
        (OUT/(part+'-provenance.json')).write_text(json.dumps([{k:v for k,v in x.items() if k!='row'} for x in selected],indent=2))
        stats[part]={'eligible':len(pools[part]),'selected':len(selected)}
    (OUT/'dataset.json').write_text(json.dumps(stats,indent=2))
    print(json.dumps(stats),flush=True)


def train():
    from huggingface_hub import snapshot_download
    from laya.train import TrainConfig,finetune
    import torch
    torch.set_num_threads(1)
    snapshot=snapshot_download(MODEL,revision=REVISION,local_files_only=True,allow_patterns=FILES)
    cfg=TrainConfig(epochs=1,micro_batch=2,grad_accum=4,freeze_encoder=True,loss='soft-ce',
                    eval_data=str(OUT/'holdout.jsonl'),seed=1729,calib_frac=.15,log_every=10)
    result=finetune(str(OUT/'train.jsonl'),snapshot,str(OUT/'checkpoint'),config=cfg,device='cpu')
    (OUT/'training-result.json').write_text(json.dumps(result,indent=2,default=str))
    print('Training finished. Check held-out metrics before any use.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','train']);args=parser.parse_args()
    (prepare if args.action=='prepare' else train)()
