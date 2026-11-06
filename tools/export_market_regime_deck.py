import os
"""Export aggregate-only regime slides with the documented Presenton v3 API."""
from concurrent.futures import ThreadPoolExecutor
from html import escape
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def request(route, payload, folder, name):
    source=folder/(name+'.request.json')
    source.write_text(json.dumps(payload))
    result=subprocess.run(['curl','--fail-with-body','--silent','--show-error','--max-time','300',
                           '-H','Content-Type: application/json','--data-binary','@'+str(source),
                           'https://api.presenton.ai'+route],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(f'Presenton {name} failed; HTTP/transport request returned code {result.returncode}.')
    response=json.loads(result.stdout)
    if response.get('message'):
        print(response['message'],flush=True)
    return response


def deck(datasets):
    slides=[]
    charts=[]
    def page(title, content, kicker='MACRON / RECORDED SCENARIOS'):
        slides.append(f'<section class="relative h-[720px] w-[1280px] overflow-hidden bg-[#F8F5ED] px-[64px] py-[42px] font-[Manrope] text-[#252B29]"><p class="text-[15px] tracking-[2px] text-[#173F35]">{escape(kicker)}</p><h1 class="mt-[18px] mb-[28px] font-[\'DM_Serif_Display\'] text-[46px] leading-[1.1] text-[#173F35]">{escape(title)}</h1>{content}<p class="absolute bottom-[24px] left-[64px] text-[13px] text-[#173F35]">2 November 2026 · Four synthetic worlds per arm · Not a real-market forecast · {len(slides)+1}</p></section>')
    def paragraph(text):
        return f'<p class="mb-[20px] text-[22px] leading-[1.5]">{escape(text)}</p>'
    def figure(data, field, title, explanation):
        chart_id=f'chart-{len(charts)}'
        series=[{'label':f'World {world+1}', 'data':[{'x':row['hours'],'y':row[field]} for row in data['rows'] if row['world']==world],
                 'borderColor':['#173F35','#587A55','#91A38C','#252B29'][world], 'borderWidth':2,'pointRadius':0} for world in range(4)]
        config={'type':'line','data':{'datasets':series},'options':{'responsive':False,'animation':False,
                 'plugins':{'legend':{'labels':{'font':{'size':14,'family':'Manrope'}}}},
                 'scales':{'x':{'type':'linear','min':0,'max':48,'title':{'display':True,'text':'Hours after planned launch','font':{'size':15}}},
                           'y':{'title':{'display':True,'text':'USD (simulated)','font':{'size':15}},'ticks':{'font':{'size':13}}}}}}
        charts.append(f'new Chart(document.querySelector("#{chart_id}"),{json.dumps(config)});')
        page(title,f'<canvas id="{chart_id}" width="1152" height="295"></canvas><div class="mt-[22px] border-t border-[#A8C3A0] pt-[18px]">{paragraph(explanation)}</div>',data['label'])
    page('BULL / BEAR Market scenarios',paragraph('Two completed MACRON experiments. Each arm: 2,048 native Jev calls, eight actors, four 48-hour worlds and exact replay.')+
         (paragraph('MATCHED EXECUTED PLAN: each world pays $899 from its existing marketing sleeve for a launch post, Token Info and KOL order. Public delivery follows the saved delays and success draws; trading is never guaranteed.') if datasets[0].get('committed_plan') else '')+
         paragraph('BULL: deliberately increased trading activity. BEAR: unchanged defensive baseline. These are scenario labels selected for interpretation, not a diagnosis of today\'s market.')+
         '<div class="mt-[32px] rounded-[16px] bg-[#E8F0E5] p-[28px]"><p class="text-[25px]">The reader decides applicability using Bitcoin trend, spot participation, DEX activity and liquidity conditions.</p></div>')
    for data in datasets:
        worlds=data['worlds'];summary=data['summary'];label=data['label']
        buys=sum(world['buys'] for world in worlds);sells=sum(world['sells'] for world in worlds)
        page(label,paragraph(f'{buys:,} filled buys · {sells:,} filled sells · ${summary["executed_volume_cents"]/100:,.2f} simulated turnover across four worlds.')+
             paragraph('Activity stress uses 4× buy/sell sampling weights and 2× buy-ticket caps. Raw provider choices are preserved, while the stress policy samples another legal action.' if label.startswith('BULL') else
                       f'The provider policy is unchanged: {summary["provider_action_counts"].get("wait", 0):,} calls resulted in wait/review choices. Reported fills above record actual responses; a quiet pool is not evidence of a particular real-world market regime.')+
             paragraph('Turnover recycles finite actor cash. It is not new investor capital, revenue or founder profit. These four paths do not establish event probabilities.'))
        figure(data,'market_cap_usd','Market cap follows actual simulated fills',
               'Four recorded paths, not a forecast band. Market cap uses declared circulating supply and AMM price; it is not realizable sale proceeds. Both buys and sells are stressed, so BULL does not impose rising prices.')
        figure(data,'cumulative_volume_usd','Turnover accumulates only when trades fill',
               'Campaign spending does not directly generate volume or price uplift. Different slopes reflect independently selected actions, finite wallets and execution constraints. A flat BEAR path records zero trading, not measured exchange inactivity.')
        figure(data,'founder_cash_usd','Founder cash is only one part of the result',
               'The founder begins with $43,000 cash and 300M hypothetical token units. Cash change excludes remaining token value, LP recovery and separate marketing costs; it must not be labeled total economic profit.')
        depth = data.get('depth_analysis')
        if depth:
            cash = depth['controlled_cash_change_cents']
            page('Reconcile cash before judging success',
                 paragraph(f'Founder + marketing median liquid-cash change: ${cash["median"]/100:,.2f}. {depth["worlds_with_controlled_cash_loss"]} of {depth["n_worlds"]} worlds lose liquid cash on this consolidated scope.')+
                 paragraph(f'Observed range: ${cash["minimum"]/100:,.2f} to ${cash["maximum"]/100:,.2f}. Prepaid commitments and optional marketing expenses are included; remaining token value and LP recovery are not.')+
                 paragraph('This can reverse the impression from founder-only proceeds. It is still a cash-scope result, not total economic profit or causal campaign ROI.'), label)
            risk = depth['sampled_max_drawdown_fraction']
            page('Risk is more than the terminal price',
                 paragraph(f'Sampled maximum drawdown range: {risk["minimum"]:.1%}–{risk["maximum"]:.1%}. Rejected executions: {depth["rejected_trades"]} among {depth["trade_attempts"]} attempted trades.')+
                 paragraph('These drawdowns use saved pre/post decision barriers, so within-barrier extremes may be missed. With zero attempts, a rejection rate is undefined—not evidence of frictionless execution.')+
                 paragraph('The statistical unit is the world, not the actor call. Four worlds support descriptive ranges, not calibrated tail odds, p99 losses or market-probability claims.'), label)
    page('When the BULL scenario may be relevant',paragraph('Bitcoin: price above a rising 200-day average, improving 50-day trend and positive 30/90-day returns. Confirm with broad non-stablecoin participation, not Bitcoin alone.')+
         paragraph('Activity: compare 7-day mean CEX spot and DEX spot turnover with each series\' 90-day median. Prefer sustained participation on rising prices across multiple venues and chains.')+
         paragraph('Liquidity: expanding stablecoin supply and usable market depth, contained spreads and improving sentiment. These are exploratory screening ideas, not validated classification thresholds.'))
    page('When the BEAR scenario may be relevant',paragraph('Bitcoin: below a falling long-term trend; weak rebounds and poor breadth. High volume during a selloff can be bearish, so volume alone cannot select the regime.')+
         paragraph('Activity and liquidity: weak participation on rallies, contracting depth, wider spreads, or verified venue/chain disruptions. Compare spot activity separately from derivatives and aggregator routing.')+
         paragraph('BTC dominance and Fear & Greed are supporting context, not stand-alone rules. Mixed conditions can remain mixed. No current readings or Binance-incident explanation is established by these runs.'))
    page('What this comparison can and cannot tell you',paragraph('Both arms preserve the MACRON clock, narrative and hypothetical initial resources. The BULL arm changes several policy mechanics, so this is not a clean estimate of a real market-regime effect.')+
         paragraph('Missing: historical demand calibration, new-wallet arrival cohorts, real announcement schedules, bonding-curve graduation, MEV and LP withdrawal. Four worlds cannot support reliable 5M-market-cap odds.')+
         paragraph('Use the accompanying PDFs for interpretation, CSV/JSON for audit and the self-contained interactive explorer for actor-specific state and choices.'))
    if datasets[0].get('depth_analysis'):
        page('Edge cases: evidence versus coverage gaps',
             paragraph('Recorded and measurable: no-trade behavior after paid delivery, campaign delivery failures, attempted versus rejected trades, liquidity floors and concentrated turnover.')+
             paragraph('Not established by these runs: campaign-on/off causality, real regime effects, late-wallet arrival surges, coordinated venue outages, LP withdrawal, MEV and migration failure.')+
             paragraph('Untested cases are a research backlog, not simulated outcomes. Every future branch needs a trigger, feasible response, execution constraints, funding and recovery condition.'))
    page('Indicator sources and how to use the reports',
         '<p class="text-[20px] leading-[1.6]">CoinGecko global market data<br>https://docs.coingecko.com/reference/crypto-global<br><br>CoinGecko exchange data<br>https://docs.coingecko.com/reference/exchanges-id<br><br>DefiLlama metric definitions<br>https://docs.llama.fi/<br><br>Alternative.me Bitcoin sentiment methodology<br>https://alternative.me/crypto/fear-and-greed-index/</p>')
    head='''<!doctype html><html lang="en"><head><meta charset="utf-8"><script src="https://cdn.tailwindcss.com"></script><script src="https://cdn.jsdelivr.net/npm/chart.js"></script><link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet"></head><body class="m-0 p-0"><main id="presentation-slides-wrapper" class="m-0 w-[1280px] p-0">'''
    return head+''.join(slides)+'</main><script>'+''.join(charts)+'</script></body></html>',len(slides)


def main(directory):
    root=Path(directory)
    receipt=root/'presenton-export-receipts.json'
    if receipt.exists():
        raise ValueError('Export receipt already exists; inspect it before any repeated export.')
    datasets=json.loads((root/'results.json').read_text())
    state={'title':'MACRON BULL and BEAR Market scenarios' + (' — executed marketing plans' if datasets[0].get('committed_plan') else ''),'design_id':14,'design':'Sage Authority',
           'fonts':['DM Serif Display','Manrope'],'font_source':'https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Manrope:wght@400;500;600;700&display=swap',
           'exports':{},'status':'running','assets':'Aggregate simulated chart data only; no icons or user images.'}
    with tempfile.TemporaryDirectory(prefix='presenton-') as temporary:
        folder=Path(temporary)
        html,count=deck(datasets);state['slides']=count
        source=folder/'presentation.html';source.write_text(html)
        validation=subprocess.run([sys.executable,str(Path(os.environ.get('BOYUN_PRESENTON_SCRIPTS', 'presenton-scripts')).expanduser() / 'validate_html.py'),str(source)],capture_output=True,text=True)
        if validation.returncode:
            raise ValueError('Presenton HTML validation failed: '+validation.stdout+validation.stderr)
        receipt.write_text(json.dumps(state,indent=2))
        def export(format_name):
            return request('/api/v3/export/html-to-any',{'html':html,'format':format_name,'title':state['title'],'design_id':14},folder,format_name)
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures={format_name:pool.submit(export,format_name) for format_name in ('pptx','pdf','png')}
                for format_name,future in futures.items():
                    try:
                        value=future.result()
                        if type(value.get('id')) is not int or value['id']<1 or not value.get('url','').startswith(('https://','http://')):
                            raise ValueError('Invalid export receipt')
                        state['exports'][format_name]=value
                        print(format_name+': '+value['url'],flush=True)
                    except Exception as error:
                        state['exports'][format_name]={'error':str(error)}
                    receipt.write_text(json.dumps(state,indent=2))
            success=next((value for value in state['exports'].values() if value.get('id')),None)
            if success:
                state['preview']=request('/api/v3/export/html-to-any/create-preview',{'id':success['id']},folder,'preview')
            state['status']='completed' if all('url' in value for value in state['exports'].values()) and state.get('preview',{}).get('url') else 'partial_or_failed'
            inventory=subprocess.run([sys.executable,str(Path(os.environ.get('BOYUN_PRESENTON_SCRIPTS', 'presenton-scripts')).expanduser() / 'presenton_artifacts.py'),'list-fonts','--html',str(source)],capture_output=True,text=True)
            state['font_inventory']=inventory.stdout
        finally:
            receipt.write_text(json.dumps(state,indent=2))
    lines=['# MACRON presentation exports','',f'{state["slides"]} slides. Design: Sage Authority (14). Fonts: DM Serif Display and Manrope.','',
           'Aggregate simulated chart data only. BULL is activity stress; BEAR is unmodified low activity. These labels do not classify current market conditions.','',
           'Export/preview links expire after 24 hours. Locally saved analytical PDFs and HTML remain available.','']
    for format_name,value in state['exports'].items():
        lines.append(f'- {format_name.upper()}: [{format_name.upper()} download]({value["url"]})' if value.get('url') else f'- {format_name.upper()}: export failed; inspect the receipt.')
        if value.get('message'):lines.append(value['message'])
    if state.get('preview',{}).get('url'):lines.append(f'- [Shareable preview]({state["preview"]["url"]})')
    if state.get('preview',{}).get('message'):lines.append(state['preview']['message'])
    lines.extend(['','Fonts: '+state['font_source'],'',state.get('font_inventory','')])
    (root/'PRESENTATION-EXPORTS.md').write_text('\n'.join(lines))
    print('status:',state['status'],flush=True)


if __name__=='__main__':
    main(sys.argv[1])
