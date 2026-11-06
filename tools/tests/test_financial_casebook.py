"""Financial exhibits must reconcile money, coverage and missingness."""
import importlib.util
import json
from pathlib import Path

import pytest
from reportlab.graphics.shapes import PolyLine, Rect


SPEC=importlib.util.spec_from_file_location('financial_casebook',Path(__file__).parents[1]/'build_financial_casebook.py')
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_actor_flow_uses_fills_not_choices_and_preserves_cash_direction():
    points=[{'settlements':[
        {'actor':'large-buyer','status':'executed','side':'buy','cash_cents':10000},
        {'actor':'large-buyer','status':'executed','side':'sell','cash_cents':6000},
        {'actor':'retail-patient','status':'rejected_slippage','side':'buy','cash_cents':900000},
        {'actor':'kol-a','status':'executed','side':'sell','cash_cents':2000}]}]
    flows=MODULE.flow_values(points)
    assert flows['Large buyer']=={'buy':100,'sell':60,'fills':2,'rejected':0}
    assert flows['Retail']=={'buy':0,'sell':0,'fills':0,'rejected':1}
    assert sum(r['buy']+r['sell']for r in flows.values())==180
    assert flows['Community']['fills']==0


def test_pair_alignment_excludes_later_endpoint_and_does_not_interpolate():
    pair={
        'pause-and-observe':{'rows':[{'second':0,'cash':0},{'second':3600,'cash':-100}]},
        'staged-exit':{'rows':[{'second':0,'cash':0},{'second':1800,'cash':-50},{'second':3600,'cash':-20},{'second':7200,'cash':1000}]}}
    joined=MODULE.common_rows(pair)
    assert [a['second']for a,b in joined]==[0,3600]
    assert joined[-1][1]['cash']-joined[-1][0]['cash']==80


def test_frozen_aggregate_tampering_is_rejected_before_run_inputs_are_read(tmp_path):
    (tmp_path/'reports').mkdir()
    (tmp_path/'reports/results.json').write_text(json.dumps({'paths':[],'market_context':None,'result_sha256':'tampered'}))
    with pytest.raises(ValueError,match='digest'):
        MODULE.load_bundle(tmp_path)


def test_missing_time_series_value_breaks_line_instead_of_bridging_gap():
    block=MODULE.chart('line','A',[0,1,2,3,4],
        [{'name':'cash','values':[1,2,None,4,5]}],'finding','explanation','implication','source')
    drawing=MODULE.draw_chart(block)
    lines=[x for x in drawing.contents if isinstance(x,PolyLine)]
    assert len(lines)==2
    assert all(len(x.points)==4 for x in lines)


def test_exhibits_reject_nonfinite_values_and_misaligned_series():
    with pytest.raises(ValueError,match='finite'):
        MODULE.chart('bar','A',['a'],[{'name':'cash','values':[float('inf')]}],'f','e','i','s')
    with pytest.raises(ValueError,match='length'):
        MODULE.chart('bar','A',['a','b'],[{'name':'cash','values':[1]}],'f','e','i','s')
    with pytest.raises(ValueError,match='increasing'):
        MODULE.chart('line','A',[1,1],[{'name':'cash','values':[1,2]}],'f','e','i','s')


def test_report_build_cannot_overwrite_an_earlier_edition(tmp_path):
    (tmp_path/'keep.txt').write_text('recorded evidence')
    with pytest.raises(ValueError,match='new directory'):
        MODULE.build(tmp_path/'unused-input',tmp_path)
    assert (tmp_path/'keep.txt').read_text()=='recorded evidence'


def test_dollar_stack_scales_to_total_and_preserves_each_component():
    block=MODULE.chart('stack','Budget',['world'],[
        {'name':'reserve','values':[10000]}, {'name':'position','values':[5000]},
        {'name':'expense','values':[5000]}, {'name':'other','values':[30000]}],
        'f','e','i','s',unit='USD')
    # Legend swatches (6x6) sit in their own band above the plot; count only the stacked bars.
    bars=[x for x in MODULE.draw_chart(block).contents if isinstance(x,Rect) and not (x.width==6 and x.height==6)]
    assert len(bars)==4
    assert all(r.x>=155 and r.x+r.width<=480.001 for r in bars)
    assert [round(r.width,2) for r in bars]==[65,32.5,32.5,195]


def test_hourly_price_and_activity_use_fills_and_last_saved_close():
    points=[{'second':0,'market_after':{'price_usd_exact':'1/100'},'settlements':[
        {'status':'executed','cash_cents':500}, {'status':'rejected_slippage','cash_cents':10000}]},
        {'second':120,'market_after':{'price_usd_exact':'1/50'},'settlements':[
        {'status':'executed','cash_cents':250}]},
        {'second':3600,'market_after':{'price_usd_exact':'1/25'},'settlements':[]}]
    rows=MODULE.hourly_market(points)
    assert [(r['hour'],r['price'],r['trades'],r['volume']) for r in rows]==[(0,.02,2,7.5),(1,.04,0,0)]


def test_final_activity_uses_only_executed_trades_in_final_six_hours():
    points=[{'second':0,'settlements':[{'status':'executed','side':'buy','cash_cents':9999}]},
            {'second':3600,'settlements':[{'status':'executed','side':'buy','cash_cents':1000}]},
            {'second':25200,'settlements':[{'status':'executed','side':'sell','cash_cents':600},
                                         {'status':'rejected_slippage','side':'buy','cash_cents':2000}],
             'market_after':{'phase':'pool'}}]
    ending=MODULE.end_activity(points)
    assert ending == {'start_second':3600,'end_second':25200,'filled_trades':2,'volume_usd':16,
                      'buys':1,'sells':1,'phase':'pool'}
