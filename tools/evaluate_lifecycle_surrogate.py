"""Evaluate a deliberately simple 20%-trained Jev score imitator, without calls.

This evaluates one-step scores on previously recorded states, not world forecasts.
"""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

from build_financial_casebook import load_bundle


def evaluate(bundle):
    ctx=load_bundle(bundle)
    paths={p['id']:p for p in ctx['data']['paths'] if p['mode']=='native'}
    rows=[];seen=set()
    for path_id,points in ctx['streams'].items():
        path=paths[path_id]
        for point in points:
            block=(path['case'],point['second']//21600)
            for actor,record in point['scores'].items():
                probs=record['probabilities'];request=record['request_sha256'];observation=record['observation_sha256']
                if not probs or not request or not observation:continue
                unique=(request,observation,tuple(ctx['seeds']))
                if unique in seen:continue
                seen.add(unique)
                feature=(path['regime'],actor,tuple(sorted(probs)))
                rows.append({'block':block,'feature':feature,'scores':probs,'provider':record['provider_choice'],
                             'sampled':record['sampled_choice']})
    block_folds={}
    for case in sorted({r['block'][0] for r in rows}):
        blocks=sorted({r['block'] for r in rows if r['block'][0]==case},key=lambda b:b[1])
        offset=int.from_bytes(sha256(case.encode()).digest()[:2],'big')%5
        block_folds.update({b:(i+offset)%5 for i,b in enumerate(blocks)})
    reports=[]
    for fold in range(5):
        training=[r for r in rows if block_folds[r['block']]==fold]
        testing=[r for r in rows if block_folds[r['block']]!=fold]
        sums=defaultdict(Counter);counts=Counter()
        for row in training:
            counts[row['feature']]+=1
            sums[row['feature']].update(row['scores'])
        matched=provider_matches=sampled_matches=0;tv=0.;by_role=defaultdict(Counter)
        for row in testing:
            n=counts[row['feature']]
            if not n:continue
            predicted={k:sums[row['feature']][k]/n for k in row['scores']}
            picked=max(predicted,key=predicted.get)
            distance=sum(abs(predicted[k]-v) for k,v in row['scores'].items())/2
            matched+=1;tv+=distance
            provider_matches+=picked==row['provider'];sampled_matches+=picked==row['sampled']
            by_role[row['feature'][1]]['count']+=1
            by_role[row['feature'][1]]['provider_matches']+=picked==row['provider']
        reports.append({'fold':fold,'training_unique_decisions':len(training),'held_out_unique_decisions':len(testing),
                        'supported_held_out':matched,'support_rate':matched/len(testing) if testing else None,
                        'provider_top_choice_agreement':provider_matches/matched if matched else None,
                        'sampled_action_agreement':sampled_matches/matched if matched else None,
                        'mean_score_total_variation':tv/matched if matched else None,
                        'by_actor':{key:dict(value) for key,value in by_role.items()}})
    return {'unique_confirmed_decisions':len(rows),'blocks':len(block_folds),'folds':reports,
            'method':'Train on one of five non-overlapping six-hour block folds and test on the other four; exact request/observation duplicates removed. Baseline predicts mean Jev scores for regime, actor and exact feasible menu.',
            'limitations':'Partial recorded states, one seed and dependent paths. Scores are uncalibrated model outputs. This does not test closed-loop rollouts or establish the trajectories of missing worlds; no new inference calls.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();target=Path(args.output)
    if target.exists():raise ValueError('Output must be new; preserve earlier results')
    result=evaluate(args.bundle);target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
