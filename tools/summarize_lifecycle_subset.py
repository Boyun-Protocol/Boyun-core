"""Create a self-contained report from a stopped, separately funded Jev path."""
import argparse
from collections import Counter
import json
from pathlib import Path

from decision_lab.lifecycle_runs import replay_lifecycle
from build_financial_casebook import chart, choice_values, end_activity, hourly_market, make_html, make_pdf, paragraph, section, table


def build(root,report_name='REPORT'):
    if not isinstance(report_name,str) or report_name in ('', '.', '..') or '/' in report_name or '\\' in report_name:
        raise ValueError('Report name must be a single directory name')
    root=Path(root).resolve();manifest=json.loads((root/'manifest.json').read_text())
    if manifest['status']=='running':raise ValueError('Wait for the path to stop before building its report')
    target=root/report_name
    if target.exists():raise ValueError('Report directory exists; preserve the earlier report')
    result=replay_lifecycle(root)
    points=[json.loads(p.read_text())['checkpoint'] for p in sorted(root.glob('step-*.json'))]
    if not points:raise ValueError('No completed barriers to summarize')
    market=hourly_market(points);choices=choice_values(points);summary=manifest['summary']
    budget=manifest.get('budget') or json.loads((root/'budget.json').read_text())
    ending=end_activity(points)
    if ending['filled_trades']:
        activity=f"Still active at the end of the recorded period: {ending['filled_trades']} executed trades ({ending['buys']} buys, {ending['sells']} sells) in the final observed { (ending['end_second']-ending['start_second'])/3600:g} hours."
    else:
        activity='No executed trades were recorded in the final observed six-hour window. The available record does not establish that the project has ended.'
    doc={'kind':'JEV-SUBSET','title':'Jev Subset Result','subtitle':'One representative native path; no inferred results for other worlds',
         'asof':'3 November 2026','result_sha256':summary['final_hash'],
         'highlights':[f"Recorded simulation duration: +{summary['last_second']/3600:g} hours.",
                       f"{budget['completed_calls']:,} confirmed calls; estimated usage ${budget['spent_estimate_micro_usd']/1e6:.6f}.",
                       activity,
                       'One BULL $10k position / $5k upfront staged-exit path; one seed.'],
         'sections':[
             section('1. Scope and status',paragraph('This is an independently funded representative path. It is not a continuation of the prior frozen matrix and does not establish the outcomes of the other worlds.'),
                 table(['Item','Value'],[['Recorded duration',f"+{summary['last_second']/3600:g} hours"],
                     ['Completed barriers',str(manifest['completed_steps'])],['Confirmed provider calls',str(budget['completed_calls'])],
                     ['Calls included in completed barriers',str(manifest['model_calls'])],
                     ['Estimated spend',f"${budget['spent_estimate_micro_usd']/1e6:.6f}"],['Uncertain reserved',f"${budget['uncertain_reserved_micro_usd']/1e6:.6f}"],
                     ['Market phase at last record',ending['phase']],['Last-window traded volume',f"${ending['volume_usd']:,.2f}"],
                     ['Exact replay',f"{result['verified_steps']} barriers; zero inference calls"]]),
                 paragraph(activity+' The recording endpoint does not by itself mean the project ended. Activity beyond that point was not observed.')),
             section('2. Recorded market progression',
                 chart('multi','Hourly simulated market path',[r['hour'] for r in market],[
                     {'name':'Price · USD / token','values':[r['price'] for r in market]},
                     {'name':'Filled trades / hour','values':[r['trades'] for r in market]},
                     {'name':'Executed USD / hour','values':[r['volume'] for r in market]}],
                     'Each panel shows a different metric with its own scale.',
                     'Price is the final saved marginal price in the hour. Trade and volume values count executed settlements; the last hour can be partial.',
                     'Use this one path as a conditional example, not a forecast or evidence for unrun paths.',
                     'Source: this path’s replay-verified checkpoint files.',unit='hours')),
             section('3. Actor choices and limitations',
                 table(['Recorded action','Count'],[[k,str(v)] for k,v in sorted(choices.items())]),
                 paragraph('Counts aggregate repeated decisions across sixteen simulated roles. They are not unique users or calibrated human behavior. A single sampled path cannot establish the probability of a world, and the unrun paths remain unknown.'))]}
    for s in doc['sections']:
        for b in s['blocks']:
            if b['kind']=='chart':b['figure_id']='S-F01'
    target.mkdir(mode=0o700);(target/'DATA').mkdir()
    for s in doc['sections']:
        for b in s['blocks']:
            if b['kind']=='chart':(target/'DATA'/(b['figure_id']+'.json')).write_text(json.dumps(b,indent=2)+'\n')
    make_pdf(doc,target/'JEV-SUBSET.pdf');(target/'index.html').write_text(make_html(doc))
    return {'report':str(target),'status':manifest['status'],'verified_steps':result['verified_steps']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run_directory');parser.add_argument('--report-name',default='REPORT',help='New folder under the run directory; earlier reports are never overwritten')
    args=parser.parse_args()
    print(json.dumps(build(args.run_directory,args.report_name),indent=2))
