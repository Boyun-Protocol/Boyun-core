"""Campaign-specific target inventory for the domain-neutral evidence audit."""
from datetime import datetime

from .agent_worlds import digest
from .simulation_evidence import audit_evidence, numeric_targets


def campaign_evidence_context(package, *, commitments=None, stress=None, sample_actions=True):
    return {'package': package, 'committed_plan': commitments, 'stress_policy': stress,
            'sample_actions': sample_actions}


def campaign_evidence_targets(context):
    targets = numeric_targets(context)
    for target in targets:
        if target.rsplit('/', 1)[-1] in {'delivery_bps', 'occurrence_bps'}:
            targets[target] = 'probability'
    package = context['package']
    targets['/package/start_time'] = 'input'
    targets['/package/token/provenance'] = 'input'
    for collection, fields in (('actors', ('role', 'goal')), ('campaigns', ('public_text',)),
                               ('events', ('text',)), ('signals', ('text',))):
        for index, row in enumerate(package[collection]):
            for field in fields:
                targets[f'/package/{collection}/{index}/{field}'] = 'input'
    for index in range(len(package['assumptions'])):
        targets[f'/package/assumptions/{index}'] = 'input'
    for collection, field in (('actors', 'campaign_ids'), ('campaigns', 'audience'),
                              ('events', 'audience'), ('signals', 'recipients')):
        for index, row in enumerate(package[collection]):
            for item_index in range(len(row[field])):
                targets[f'/package/{collection}/{index}/{field}/{item_index}'] = 'input'
    for index in range(len(package['signals'])):
        targets[f'/package/signals/{index}/sender'] = 'input'
    for index in range(len(context['committed_plan'] or [])):
        targets[f'/committed_plan/{index}/payer'] = 'input'
        targets[f'/committed_plan/{index}/campaign_id'] = 'input'
    targets.update({'probability:actor_choices': 'probability', 'outcome:price': 'outcome',
                    'outcome:executed_turnover': 'outcome', 'outcome:controlled_cash': 'outcome'})
    return targets


def review_campaign_evidence(register, context):
    if register is None:
        raise ValueError('campaign evidence register required before inference')
    result = audit_evidence(register, required_targets=campaign_evidence_targets(context), target_sha256=digest(context))
    cutoff = datetime.fromisoformat(register['as_of'].replace('Z', '+00:00'))
    start = datetime.fromisoformat(context['package']['start_time'].replace('Z', '+00:00'))
    if cutoff > start:
        raise ValueError('campaign evidence cutoff is after launch')
    if result['status'] == 'blocked':
        raise ValueError('campaign evidence audit blocked; inspect the offline audit before inference')
    return result
