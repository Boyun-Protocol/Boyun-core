"""Local, data-derived reports. No inference, web assets or executable markup."""
from copy import deepcopy
from html import escape
from importlib.resources import files
from io import BytesIO
from pathlib import Path
import re
from statistics import mean,median
from .product_insights import build_insights, DECISION_RECORD_SCOPE


def pdf_available():
    try:import reportlab  # noqa: F401
    except ImportError:return False
    return True


def report_data(snapshot,accounting=None):
    world=snapshot['proposal']['world'];results=snapshot['results']
    decision_insights=build_insights(snapshot)
    metrics=[]
    for m in world['metrics']:
        values=[r['result']['final_metrics'][m['id']]for r in results]
        metrics.append({'label':m['label'],'unit':m['unit'],'mean':mean(values)if values else None,
            'median':median(values)if values else None,'min':min(values)if values else None,'max':max(values)if values else None,
            'paths':[[m['initial']]+[step['metrics_after'][m['id']]for step in r['result']['rounds']]for r in results]})
    requested=(snapshot.get('review')or{}).get('worlds')or(snapshot.get('summary')or{}).get('requested_worlds')
    scenarios=[]
    for r in results:
        scenarios.append({'world':r['world_index']+1,'action_cost_cents':str(r['result']['total_cost_cents']),
            'actions':[f"Round {step['round']}: "+', '.join(f"{actor}: {decision['action_id']}"for actor,decision in step['decisions'].items())for step in r['result']['rounds']]})
    return {'title':world['title'],'description':world['description'],'question':snapshot.get('question'),
        'policy':(snapshot.get('review')or{}).get('mode','Not recorded'),
        'status':snapshot['status'],'completed':len(results),'requested':requested,'metrics':metrics,'scenarios':scenarios,
        'actors':[{k:deepcopy(a[k])for k in ('name','role','motivation','goal','initial_cash_cents')}for a in world['actors']],
        'rounds':world['rounds'],'assumptions':world['assumptions'],'limitations':world['limitations'],
        'accounting':deepcopy(accounting or{}),'decision_insights':decision_insights,'private':True}


def _insight_paragraphs(data):
    """Shared bounded plain text for Markdown and PDF; renderers escape it."""
    insights=data.get('decision_insights')
    if not insights:return []
    resource=insights['resources'];game=insights['strategic'];lines=[DECISION_RECORD_SCOPE]
    if resource['status']=='computed':
        for row in resource['worlds']:
            lines.append(f"World {row['world_index']+1} cash: {row['initial_cash_cents']} - {row['action_cost_cents']} = {row['remaining_cash_cents']} cents (initial - action expenses = remaining). Reconciled.")
        total=resource['aggregate']
        lines.append(f"Across completed alternative runs: {total['initial_cash_cents']} - {total['action_cost_cents']} = {total['remaining_cash_cents']} cents. These totals sum alternative runs, not a pooled portfolio.")
    else:lines.append(resource['reason'])
    lines.append(resource['meaning'])
    if game['status']!='computed':
        lines.append('Static strategic analysis not computed: '+game['reason'])
        opening=insights.get('opening_game')
        if opening and opening['status']=='computed':
            lines.append('Opening game diagnostic (separate from full-world analysis).')
            game=opening
        elif opening and opening['reason']!=game['reason']:
            lines.append('Opening game diagnostic not computed: '+opening['reason'])
    if game['status']=='computed':
        lines.append(game['scope'])
        profiles=game['pure_nash_profiles'];dominated=game['strictly_dominated_actions']
        lines.append(f"Exact affordable joint profiles checked: {game['profile_count']}. Pure Nash profiles: {len(profiles)}. Strictly dominated actions: {len(dominated)}.")
        for profile in profiles[:8]:lines.append('Pure Nash profile: '+', '.join(f'{actor}: {action}'for actor,action in profile.items()))
        if len(profiles)>8:lines.append(f'Showing first 8 of {len(profiles)} pure Nash profiles; complete profiles are in presentation JSON.')
        for row in dominated[:8]:lines.append(f"Strictly dominated: {row['player_id']}: {row['action_id']}; dominated by "+', '.join(row['dominating_action_ids']))
        if len(dominated)>8:lines.append(f'Showing first 8 of {len(dominated)} dominated actions; complete actions are in presentation JSON.')
        improvements=[]
        for observed in game['observed_profiles']:
            for actor in observed['actors']:
                if int(actor['unilateral_improvement_utility'])>0:
                    improvements.append(f"World {observed['world_index']+1}, {actor['id']}, selected {actor['selected_action_id']}: unilateral improvement: {actor['unilateral_improvement_utility']} utility points by choosing "+', '.join(actor['best_response_action_ids'])+' with recorded opponents fixed.')
        lines.extend(improvements or ['No strictly improving unilateral deviation in the recorded profiles under this static table.'])
    lines.extend(game['limitations'])
    return lines


def _md(value):
    # A report is data. Prevent supplied HTML, headings and table pipes from
    # becoming active markup in Markdown viewers.
    value=escape(str(value),quote=False).replace('\r',' ').replace('\n',' ')
    return re.sub(r'([\\`*_{}\[\]()#+.!|>\-])',r'\\\1',value)


def markdown(data):
    lines=['# Boyun report','',f"## {_md(data['title'])}",'',_md(data['description']),'',
        'User question: '+_md(data['question']or'Not recorded'),'',
        f"Status: {_md(data['status'])}. Completed worlds: {data['completed']} / {data['requested'] if data['requested']is not None else 'unknown requested'}. Rounds: {data['rounds']}.",'',
        '**Private report.** Includes scenario and persona details. No imported provider key is included.',
        'Conditional model/rule runs are not calibrated real-world probabilities. Utility points and action spending are not net financial profit.','',
        'Decision selection: '+_md(data['policy']),
        'Offline route, when selected: deterministic immediate own-action utility including clamps/cash costs; menu-order ties. Ignores narrative motivations, messages, joint responses and future events. One-hot weights are policy, not confidence.','',
        '## Outcome metrics','', '| Metric | Unit | Mean | Median | Min | Max |','| --- | --- | ---: | ---: | ---: | ---: |']
    for m in data['metrics']:lines.append('| '+' | '.join(_md(m[k]if m[k]is not None else 'No completed world')for k in ('label','unit','mean','median','min','max'))+' |')
    lines+=['','## Recorded scenarios','']
    if not data['scenarios']:lines+=['No complete world. Do not treat failed or unattempted worlds as outcomes.','']
    for s in data['scenarios']:
        lines += [f"### World {s['world']}",'',f"Modeled action cost: {s['action_cost_cents']} cents.",'']+['- '+_md(a)for a in s['actions']]+['']
    paragraphs=_insight_paragraphs(data)
    if paragraphs:lines+=['## Decision insights','']+sum(([_md(text),'']for text in paragraphs),[])
    lines+=['## Personas','']
    for a in data['actors']:
        lines += [f"### {_md(a['name'])}",'',_md(a['role']),f"Starting cash: {a['initial_cash_cents']} cents.",f"Motivation: {_md(a['motivation'])}",f"Goal: {_md(a['goal'])}",'']
    lines+=['## Run accounting','']+['- '+_md(k.replace('_',' '))+': '+_md(v)for k,v in data['accounting'].items()]+['',
        'Accounting covers this recorded run, including saved responses in incomplete worlds. Missing responses have unknown remote outcome/billing; no refunded or zero-cost outcome is invented. Authoring is separate.','',
        '## Assumptions and limits','']+['- '+_md(v)for v in data['assumptions']+data['limitations']]
    return ('\n'.join(lines)+'\n').encode('utf-8')


def pdf(data):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
        from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.graphics.shapes import Drawing,Line,String,PolyLine
    except ImportError:raise ValueError('PDF extra unavailable; install decision-lab-engine[pdf] or use Markdown')from None
    font='ScenarioManrope'
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font,BytesIO(files('decision_lab').joinpath('resources/fonts/manrope.ttf').read_bytes())))
    styles=getSampleStyleSheet()
    for style in styles.byName.values():style.fontName=font;style.textColor=colors.HexColor('#263f50')
    styles['Title'].fontSize=26;styles['Title'].leading=33;styles['BodyText'].fontSize=9;styles['BodyText'].leading=14
    small=ParagraphStyle('Small',parent=styles['BodyText'],fontSize=8,leading=11)
    story=[]
    def p(text,style='BodyText'):
        return Paragraph(escape(str(text)),styles[style])
    def add(text,style='BodyText'):story.extend([p(text,style),Spacer(1,9)])
    def table(rows,widths):
        cells=[[Paragraph(escape(str(v)),small)for v in row]for row in rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eff4')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d0dde6'))]))
        story.extend([t,Spacer(1,14)])
    add('BOYUN · PRIVATE REPORT','Heading3');add(data['title'],'Title');add(data['description'])
    if data['question']:add('User question: '+data['question'])
    add(f"{data['completed']} completed / {data['requested'] if data['requested']is not None else 'unknown requested'} worlds | {data['rounds']} rounds | Status: {data['status']}")
    add('Conditional runs, not calibrated event odds. Utility points and modeled spending are not net profit. Scenario and persona details below are private.')
    add('Decision selection: '+data['policy'])
    if data['accounting'].get('route')=='offline':add('Offline policy: deterministic immediate own-action utility with clamps/cash costs and menu-order ties. Ignores narrative motivations, messages, joint responses and future events. One-hot weights are policy, not confidence.')
    add('Outcome metrics','Heading1')
    table([['Metric / unit','Mean','Median','Range']]+[[m['label']+' / '+m['unit'],m['mean']if m['mean']is not None else 'N/A',m['median']if m['median']is not None else 'N/A',f"{m['min']} to {m['max']}"if m['min']is not None else 'No completed world']for m in data['metrics']],[222,72,72,133])
    for m in data['metrics']:
        if not m['paths']:continue
        drawing=Drawing(490,150);allv=[v for path in m['paths']for v in path];lo,hi=min(allv),max(allv);span=hi-lo or 1
        drawing.add(Line(45,25,480,25,strokeColor=colors.HexColor('#ccd8d1')))
        for path in m['paths']:
            points=[]
            for i,v in enumerate(path):points.extend([45+i*435/max(1,len(path)-1),30+(v-lo)*100/span])
            drawing.add(PolyLine(points,strokeColor=colors.HexColor('#8fb8a4'),strokeWidth=1.2))
        avg=[mean(path[i]for path in m['paths'])for i in range(len(m['paths'][0]))];points=[]
        for i,v in enumerate(avg):points.extend([45+i*435/max(1,len(avg)-1),30+(v-lo)*100/span])
        drawing.add(PolyLine(points,strokeColor=colors.HexColor('#245f4e'),strokeWidth=2.4))
        for x,y,text in ((4,125,str(hi)),(4,29,str(lo)),(45,9,'Initial'),(440,9,'Final')):drawing.add(String(x,y,text,fontName=font,fontSize=8))
        story.append(KeepTogether([p(m['label']+' - paths and mean','Heading2'),drawing,Spacer(1,10)]))
    add('Recorded scenarios','Heading1')
    if not data['scenarios']:add('No complete world. Failed and unattempted worlds remain outside outcome statistics.')
    for s in data['scenarios']:
        add(f"World {s['world']} - modeled action cost {s['action_cost_cents']} cents",'Heading2')
        for a in s['actions']:add(a)
    paragraphs=_insight_paragraphs(data)
    if paragraphs:
        add('Decision insights','Heading1')
        for text in paragraphs:add(text)
    story.append(PageBreak());add('Persona motivations and goals','Heading1')
    for a in data['actors']:
        add(a['name'],'Heading2');add(a['role']);add(f"Starting cash: {a['initial_cash_cents']} cents")
        add('Motivation: '+a['motivation']);add('Goal: '+a['goal'])
    add('Run accounting','Heading1')
    table([['Recorded item','Value']]+[[k.replace('_',' '),v]for k,v in data['accounting'].items()],[210,289])
    add('Includes saved run responses from incomplete worlds; missing responses have unknown remote outcome and billing. Authoring is separate.')
    add('Assumptions and limitations','Heading1')
    for text in data['assumptions']+data['limitations']:add(text)
    output=BytesIO()
    def footer(c,doc):
        c.setFont(font,8);c.setFillColor(colors.HexColor('#536a7a'));c.drawString(48,28,'Private - hypothetical scenario analysis');c.drawRightString(547,28,str(doc.page))
    SimpleDocTemplate(output,pagesize=(595,842),leftMargin=48,rightMargin=48,topMargin=44,bottomMargin=48,title='Boyun private report',author='Boyun').build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()


def render_report(snapshot,format,accounting=None):
    data=report_data(snapshot,accounting)
    if format=='md':return markdown(data)
    if format=='pdf':return pdf(data)
    raise ValueError('report format must be md or pdf')
