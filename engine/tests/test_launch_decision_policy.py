import pytest

from decision_lab.launch_decision_policy import decision_schedule, volume_signal, response_branches, exit_deferred, HORIZON


def test_fourteen_days_include_every_hour_and_event_with_no_cutoff():
    steps = decision_schedule([12345, HORIZON])
    assert steps[0] == 0 and steps[-1] == 1209600
    assert all(hour * 3600 in steps for hour in range(337))
    assert all(minute * 60 in steps for minute in range(16))
    assert 12345 in steps and len(steps) == 353
    with pytest.raises(ValueError):
        decision_schedule([HORIZON + 1])


def test_six_hour_total_volume_uses_causal_reference_and_freezes_after_48h():
    trades = [{'second': 0, 'cash_cents': 10000}, {'second': 53*3600, 'cash_cents': 100000}]
    assert volume_signal(trades, 3600)['reference_status'] == 'warming_up'
    at_six = volume_signal(trades, 6*3600)
    assert at_six['current_volume_cents'] == at_six['peak_volume_cents'] == 10000
    assert at_six['funding_gate_open'] is True
    at_54 = volume_signal(trades, 54*3600)
    assert at_54['peak_volume_cents'] == 10000
    assert at_54['current_volume_cents'] == 100000
    assert at_54['reference_frozen'] is True
    assert volume_signal(trades, HORIZON)['exit_trigger'] is True


def test_future_trades_never_change_earlier_signal():
    prior = [{'second': 0, 'cash_cents': 10000}]
    future = prior + [{'second': 40*3600, 'cash_cents': 10**8}]
    assert volume_signal(prior, 10*3600) == volume_signal(future, 10*3600)


def test_zero_peak_remains_unknown_and_thresholds_are_inclusive():
    assert volume_signal([], 72*3600)['exit_trigger'] is None
    assert volume_signal([], 72*3600)['funding_gate_open'] is None
    trades = [{'second': 0, 'cash_cents': 10000}, {'second': 50*3600, 'cash_cents': 2500}]
    signal = volume_signal(trades, 54*3600)
    assert signal['exit_trigger'] is True and signal['funding_gate_open'] is False
    trades[-1]['cash_cents'] = 6000
    signal = volume_signal(trades, 54*3600)
    assert signal['funding_gate_open'] is True and signal['exit_trigger'] is False
    assert exit_deferred(signal, '10', '10') is True
    assert exit_deferred(signal, '9', '10') is False


def test_response_branches_preserve_over_horizon_tranches_and_no_choice():
    branches = response_branches(HORIZON - 60, decision_delay_seconds=0)
    assert {branch['id'] for branch in branches} == {'pause-and-observe', 'staged-exit'}
    assert branches[1]['tranches'][0]['status'] == 'within_horizon'
    assert branches[1]['tranches'][-1]['status'] == 'pending_after_horizon'
    delayed = response_branches(3600, decision_delay_seconds=900)
    assert delayed[1]['tranches'][0]['due_second'] == 4500
    with pytest.raises(ValueError):
        response_branches(3600, decision_delay_seconds=1800)
