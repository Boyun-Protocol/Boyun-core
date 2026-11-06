"""Independent replay: rebuild each continuation from package + recorded choices; re-derive sampled choices from saved Laya scores."""
import json, sys
from pathlib import Path
from decision_lab.agent_worlds import canonical, digest
from decision_lab.launch_lifecycle import LaunchLifecycle
from decision_lab.lifecycle_runs import lifecycle_request, sampled_choice
def j(p): return json.loads(p.read_text())
d=Path(sys.argv[1]); m=j(d/'manifest.json'); src=Path(m['identity']['source']); old=j(src/'manifest.json')
eng=LaunchLifecycle(j(src/'package.json'), old['seed'], old['response_policy'])
ss=m['identity']['source_steps']; calls=0
for i in range(ss+m['new_steps']):
    s=j((src if i<ss else d)/f'step-{i:05d}.json'); eng.prepare()
    if i>=ss:
        for a,e in s['decision_evidence'].items():
            if 'decision_file' not in e:
                assert len(eng.menu(a))==1; continue
            r=j(d/e['decision_file']); req=lifecycle_request(eng,a,'jev-1.14.0'); req['model']=m['identity']['model']
            assert digest(req)==r['request_sha256'], ('request',i,a)
            sel,meta=sampled_choice(r['answers']['action'],eng,a)
            assert sel==s['checkpoint']['choices'][a] and meta==e['sampling'], ('choice',i,a); calls+=1
    c=eng.advance(s['checkpoint']['choices']); assert canonical(c)==canonical(s['checkpoint']), ('checkpoint',i)
assert eng.summary()==m['summary'] and calls==m['model_calls']
print(d.name,'OK steps',ss+m['new_steps'],'laya calls verified',calls)
