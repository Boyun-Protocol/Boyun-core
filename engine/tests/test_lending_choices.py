"""Observation isolation, feasibility and explicit client receipts."""
from copy import deepcopy

import pytest

from decision_lab.lending_choices import lending_request, decide_lending, settle_lending_choice
from test_lending import pool, fund


class Client:
    def __init__(self,choice):
        self.choice = choice
        self.calls = 0

    def evaluate(self, *, state, questions):
        self.calls += 1
        ids = questions['action']['criteria']
        return {'answers':{'action':{'type':'choice','choice':self.choice,'confidence':1,
            'probabilities':{k:int(k==self.choice) for k in ids}}},
            'receipt':{'model':'test_client_only_not_laya'}}


def test_menu_cannot_see_other_wallets_or_future_or_overspend():
    p = pool(); fund(p)
    before = p.snapshot()
    request = lending_request(p,'borrower','borrower',news='Public launch occurred.',step_usdc=5000)
    assert p.snapshot() == before
    assert request['actions']['borrow']['payload']['usdc'] == 1000
    assert 'bob' not in str(request['state'])
    assert 'liquidator' not in str(request['state'])
    assert request['state']['news'] == 'Public launch occurred.'
    client = Client('borrow')
    record = decide_lending(p,request,client)
    assert p.snapshot() == before  # evaluation does not settle
    assert record['response']['receipt']['model'] == 'test_client_only_not_laya'
    settle_lending_choice(p,record,'model-borrow')
    assert p.principal() == 1000
    assert client.calls == 1


def test_forced_wait_uses_no_client_and_stale_request_is_rejected():
    p = pool(); fund(p)
    # Alice supplied all her cash but has an affordable withdrawal, so not forced.
    request = lending_request(p,'alice','supplier')
    assert 'withdraw' in request['actions']
    p.apply('all-cash','borrow',actor='borrower',usdc=1000)
    with pytest.raises(ValueError,match='different lending state'):
        decide_lending(p,request,Client('withdraw'))
    # A new actor with no supply and no funds cannot do anything.
    q = pool()
    q.apply('all','supply',actor='alice',usdc=600)
    q.apply('price','oracle',near_usd=1,usdc_usd=1,observed_second=0)
    q.apply('collateral','post_collateral',actor='borrower',near=2000)
    q.apply('borrow','borrow',actor='borrower',usdc=600)
    q.apply('queue','withdraw',actor='alice',usdc=600)
    req = lending_request(q,'alice','supplier')
    assert req['questions'] is None
    client = Client('wait')
    record = decide_lending(q,req,client)
    assert not client.calls
    assert not record['model_used']
    settle_lending_choice(q,record,'forced')


def test_response_tampering_and_state_changes_do_not_settle():
    p = pool(); fund(p)
    request = lending_request(p,'borrower','borrower')
    record = decide_lending(p,request,Client('borrow'))
    before = p.snapshot()
    bad = deepcopy(record); bad['choice']='wait'
    with pytest.raises(ValueError,match='differs'):
        settle_lending_choice(p,bad,'bad')
    assert p.snapshot() == before
    bad = deepcopy(record); bad['request']['actions']['borrow']['payload']['usdc']=99999
    with pytest.raises(ValueError,match='altered request'):
        settle_lending_choice(p,bad,'bad')
    assert p.snapshot() == before
    p.apply('news-time','advance',second=1)
    with pytest.raises(ValueError,match='stale lending state'):
        settle_lending_choice(p,record,'stale')


def test_private_profile_is_bounded_and_only_in_own_request():
    p = pool(); fund(p)
    request = lending_request(p,'borrower','borrower',profile='Needs working capital; avoids selling NEAR.')
    assert request['state']['profile'] == 'Needs working capital; avoids selling NEAR.'
    assert 'profile' not in lending_request(p,'alice','supplier')['state']
    with pytest.raises(ValueError):
        lending_request(p,'borrower','borrower',profile='x'*161)
