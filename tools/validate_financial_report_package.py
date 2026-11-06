"""Check structural integrity of a locally generated financial report package.

This checks machine-readable packaging, not factual accuracy or visual quality.
"""
import argparse
import json
import math
from pathlib import Path


REQUIRED = {'World Creation', 'Bear Case', 'Bull Case', 'Technical Report', 'User and Agent Decision Record'}


def validate(root):
    root = Path(root)
    manifest = json.loads((root/'DATA'/'manifest.json').read_text())
    docs = manifest['documents']
    errors = []
    missing = REQUIRED - {doc['title'] for doc in docs}
    if missing:
        errors.append('Missing required documents: '+', '.join(sorted(missing)))
    count = 0
    for doc in docs:
        for extension in ('pdf', 'html', 'md'):
            if not (root/(doc['id']+'.'+extension)).is_file():
                errors.append(f"Missing {doc['id']}.{extension}")
        html = root/(doc['id']+'.html')
        if html.is_file() and '<nav aria-label="Contents">' not in html.read_text():
            errors.append(f"Missing HTML contents: {doc['id']}")
        for i in range(1, doc['figures']+1):
            identifier=f"{doc['id'].split('-')[0]}-F{i:02d}"
            data_path=root/'DATA'/(identifier+'.json')
            image_path=root/'FIGURES'/(identifier+'.svg')
            if not data_path.is_file() or not image_path.is_file():
                errors.append(f'Missing exhibit data or figure: {identifier}')
                continue
            exhibit=json.loads(data_path.read_text())
            if not all(exhibit.get(k) for k in ('title','finding','explanation','implication','source')):
                errors.append(f'Incomplete exhibit interpretation: {identifier}')
            for series in exhibit.get('series',[]):
                values=series['values']
                if len(values)!=len(exhibit['labels']) or any(v is not None and (type(v) not in (int,float) or not math.isfinite(v)) for v in values):
                    errors.append(f'Invalid series: {identifier}')
            count+=1
    return {'status':'failed' if errors else 'passed','documents':len(docs),'exhibits_checked':count,
            'errors':errors,'limitation':'Structural checks only; verify evidence and inspect PDF/phone layouts separately.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    result=validate(parser.parse_args().package)
    print(json.dumps(result,indent=2))
    raise SystemExit(1 if result['errors'] else 0)
