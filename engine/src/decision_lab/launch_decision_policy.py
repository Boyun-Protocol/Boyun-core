"""Causal six-hour volume signals and explicit comparative founder responses."""
from fractions import Fraction


HOUR = 3600
WINDOW = 6 * HOUR
REFERENCE_END = 48 * HOUR
HORIZON = 14 * 24 * HOUR


def decision_schedule(event_seconds=()):
    points = set(range(0, 16 * 60, 60)) | set(range(HOUR, HORIZON + 1, HOUR))
    for second in event_seconds:
        if type(second) is not int or not 0 <= second <= HORIZON:
            raise ValueError('event outside the fourteen-day horizon')
        points.add(second)
    return sorted(points)


def volume_signal(trades, now):
    if type(now) is not int or not 0 <= now <= HORIZON:
        raise ValueError('invalid simulation clock')
    for trade in trades:
        if (type(trade) is not dict or set(trade) != {'second', 'cash_cents'}
                or type(trade['second']) is not int or not 0 <= trade['second'] <= HORIZON
                or type(trade['cash_cents']) is not int or trade['cash_cents'] < 0):
            raise ValueError('executed trade timestamp and cash amount required')
    available = [trade for trade in trades if trade['second'] < now]
    total = lambda end: sum(trade['cash_cents'] for trade in available if end - WINDOW <= trade['second'] < end)
    result = {'elapsed_seconds': now, 'window_seconds': WINDOW, 'volume_basis': 'total_executed_cash_turnover',
              'window_boundary': '[now - 21600, now); pre-decision snapshot',
              'reference_sampling': 'hourly completed six-hour windows ending at hours 6 through 48',
              'reference_frozen': now >= REFERENCE_END, 'current_volume_cents': total(now) if now >= WINDOW else None,
              'peak_volume_cents': None, 'fraction_of_peak_exact': None,
              'exit_trigger': None, 'funding_gate_open': None,
              'reference_status': 'warming_up' if now < WINDOW else 'no_positive_reference'}
    if now < WINDOW:
        return result
    peak = max(total(end) for end in range(WINDOW, min(now, REFERENCE_END) + 1, HOUR))
    result['peak_volume_cents'] = peak
    if not peak:
        return result
    fraction = Fraction(result['current_volume_cents'], peak)
    result.update(reference_status='frozen' if now >= REFERENCE_END else 'running_reference',
                  fraction_of_peak_exact=str(fraction), exit_trigger=fraction <= Fraction(1, 4),
                  funding_gate_open=fraction >= Fraction(3, 5))
    return result


def exit_deferred(signal, price_now, price_one_hour_ago):
    if signal['fraction_of_peak_exact'] is None or price_now is None or price_one_hour_ago is None:
        return None
    current, previous = Fraction(str(price_now)), Fraction(str(price_one_hour_ago))
    if current <= 0 or previous <= 0:
        raise ValueError('positive token prices required')
    return Fraction(signal['fraction_of_peak_exact']) > Fraction(1, 4) and current >= previous


def response_branches(alert_second, *, decision_delay_seconds):
    if type(alert_second) is not int or not 0 <= alert_second <= HORIZON:
        raise ValueError('invalid alert time')
    if type(decision_delay_seconds) is not int or not 0 <= decision_delay_seconds < 1800:
        raise ValueError('explicit response delay must remain below thirty minutes')
    execution_start = alert_second + decision_delay_seconds
    return [
        {'id': 'pause-and-observe', 'new_discretionary_spending': 'paused',
         'decision_delay_seconds': decision_delay_seconds,
         'response': 'hold founder inventory pending recovery; other actors continue', 'tranches': []},
        {'id': 'staged-exit', 'new_discretionary_spending': 'paused',
         'decision_delay_seconds': decision_delay_seconds,
         'response': 'four equal tranches; later tranches defer only on recovered volume AND one-hour price hold',
         'tranches': [{'due_second': execution_start + offset * 60, 'status': 'within_horizon' if execution_start + offset * 60 <= HORIZON else 'pending_after_horizon'}
                      for offset in (0, 15, 30, 45)]}
    ]
