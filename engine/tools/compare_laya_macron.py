"""Compare recorded Jev MACRON decisions with Laya on exactly the same observations."""
import argparse
import json
from pathlib import Path
from collections import Counter
from decision_lab.laya_choices import LayaChoiceClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    client = LayaChoiceClient('convaiinnovations/laya-typed-decisions')
    rows = []
    for regime in ('BULL', 'BEAR'):
        root = args.source / ('macron-' + regime.lower() + '-p5000-c5000') / 'pause-and-observe'
        manifest = json.loads((root / 'manifest.json').read_text())
        last = manifest['completed_steps'] - 1
        for index in sorted({0, min(25,last), min(75,last), min(120,last), last}):
            step = json.loads((root / f'step-{index:05d}.json').read_text())
            available = [(a,e) for a,e in step['decision_evidence'].items() if e.get('call_prefix') and e.get('answers')]
            # Select a founder and one independently reacting actor where possible.
            selected = sorted(available, key=lambda x:(x[0] != 'founder', x[0]))[:2]
            for actor, evidence in selected:
                row = {'regime':regime, 'step':index, 'second':step['checkpoint']['second'], 'actor':actor,
                       'source_run':str(root), 'source_call':evidence['call_prefix'],
                       'jev':evidence['answers']['action']}
                try:
                    request = json.loads((root / (evidence['call_prefix'] + '.request.json')).read_text())
                    response = client.evaluate(state=request['state'], questions=request['questions'])
                    row.update(status='completed', laya=response['answers']['action'], receipt=response['receipt'])
                except Exception as error:
                    row.update(status='failed', error=type(error).__name__, reason=str(error.__cause__ or error))
                rows.append(row)
                (args.output/'results.json').write_text(json.dumps({'rows':rows}, indent=2))
                print(regime, index, actor, row['status'], row.get('reason',''), flush=True)
    ok=[r for r in rows if r['status']=='completed']
    summary={'attempted':len(rows), 'completed':len(ok), 'failed':len(rows)-len(ok),
             'exact_top_choice_matches':sum(r['jev']['choice']==r['laya']['choice'] for r in ok),
             'jev_choices':dict(Counter(r['jev']['choice'] for r in ok)),
             'laya_choices':dict(Counter(r['laya']['choice'] for r in ok)),
             'limitations':'Small deliberately selected matched observations; no predictive accuracy or independent outcome validation.'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)

if __name__=='__main__': main()
