"""Freeze public NEAR observations into an explicitly hypothetical decision game.

This module only reads the forward archive and writes new local artifacts. It
has no author, wallet, registry, inference or transaction route.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
import json
from pathlib import Path

from .io_helpers import json_bytes, write_artifacts
from .public_archive import PublicArchive
from .strategic_worlds import StrategicWorld, validate_strategic_world
from .wallet_evidence import analyze_wallets


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _template():
    examples = json.loads(files('decision_lab').joinpath('data/strategic_examples.json').read_text())
    world = next(item['world'] for item in examples if item['id'] == 'near-launch-coordination')
    world['id'] = 'near-pilot-decision'
    world['title'] = 'NEAR: a bounded pilot or a larger commitment?'
    world['description'] = (
        'A creator with an assumed $10,000 budget compares waiting, a $500 pilot and a $5,000 larger commitment. '
        'A reviewer independently chooses review, caution or waiting. Public NEAR swap observations supply '
        'a dated context and coverage limits; they do not calibrate these roles, costs, effects or preferences. '
        'This is a conditional decision rehearsal, with no token-price or profit forecast.')
    creator = world['actors'][0]
    creator['goal'] = 'Preserve runway; expand only after a bounded pilot has verifiable delivery and independent review.'
    creator['information'] = (
        'The $10,000 budget is an author assumption, not any observed address balance. '
        'The $500 pilot includes at most $100 of incentives; the $5,000 commitment includes at most $1,000. '
        'These caps are already inside action costs. Incentives buy participation effort, not endorsement or demand.')
    pilot, commitment = creator['actions'][1:]
    pilot['description'] = (
        'Spend an assumed $500 total, including at most $100 incentives, on a bounded deliverable and a public '
        'measurement log. Proceed only with a defined acceptance test, owner and stop date. No return is promised.')
    commitment.update(id='commit', label='Make a larger commitment', cost_cents=500000,
        description='Spend an assumed $5,000 total, including at most $1,000 incentives. Consider only after pilot delivery, '
                    'independent review and a separate budget approval. Sampled swaps alone never satisfy this gate.',
        message='A larger project budget was committed under stated assumptions; there is no demand or return guarantee.')
    for interaction in world['interactions']:
        if interaction['when']['creator'] == 'announce':
            interaction['when']['creator'] = 'commit'
            interaction['description'] = 'Assumed tension: a larger commitment while review flags unresolved uncertainty increases execution exposure.'
    world['assumptions'].append(
        'Budget units are USD cents: creator 1000000; reviewer 50000; pilot cost 50000; larger commitment cost 500000. '
        'Incentive caps of 10000 and 100000 cents are included in those costs. No observed address funds either actor.')
    world['limitations'] = [item for item in world['limitations'] if 'No live news' not in item]
    return world


def build_near_demo(evidence, base_world=None):
    """Build a reviewable world from validated wallet-observations.v1 NEAR data.

    The canonical input hash identifies the supplied snapshot, not source truth.
    A caller-supplied base world retains all its authored economic assumptions.
    Raw public addresses remain in the separate frozen snapshot, never actors.
    """
    if type(evidence) is not dict or evidence.get('network') != 'near':
        raise ValueError('NEAR wallet-observations.v1 evidence required')
    analyzed = analyze_wallets(evidence)
    if not analyzed['summary']['accepted_trades']:
        raise ValueError('at least one accepted observed NEAR swap required')
    snapshot_hash = sha256(_json(evidence).encode()).hexdigest()
    metadata = analyzed['source_metadata']
    sources = deepcopy(metadata['sources'])
    units = {
        'observed_notional_cents': 'USD cents; provider-declared swap notional, not capital or profit',
        'initial_cash_cents': 'USD cents; authored budget assumption',
        'metric_effects': 'hypothetical points; not fitted to observations',
        'timestamps': 'UTC ISO 8601; provider declarations, not RPC attestations',
    }
    frozen = {
        'schema_version': 'near-demo-evidence.v1', 'network': 'near',
        'network_verification': metadata['network_reliability'],
        'verification': metadata['verification'], 'snapshot_sha256': snapshot_hash,
        'captured_at': metadata['captured_at'], 'sources': sources,
        'target_window': deepcopy(analyzed['target_window']),
        'coverage': deepcopy(analyzed['coverage']), 'summary': deepcopy(analyzed['summary']),
        'units': units, 'snapshot': deepcopy(evidence),
        'limitations': deepcopy(analyzed['limitations']),
    }
    world = validate_strategic_world(base_world) if base_world is not None else _template()
    context = {
        'schema_version': 'near-demo-context.v1', 'network': 'near',
        'snapshot_sha256': snapshot_hash, 'captured_at': frozen['captured_at'],
        'verification': frozen['verification'], 'network_verification': frozen['network_verification'],
        'target_window': frozen['target_window'], 'complete_target_window': False,
        'summary': frozen['summary'], 'units': units,
    }
    world['assumptions'].append('Frozen NEAR source context: ' + _json(context))
    for source, coverage in zip(sources, analyzed['coverage']['pools']):
        world['assumptions'].append('Frozen NEAR source: ' + _json({**source,
            'earliest_observed_at': coverage['earliest_observed_at'],
            'latest_observed_at': coverage['latest_observed_at']}))
    world['assumptions'].append(
        'Observed addresses can be routers, bots or custodians. Identity, motives, balances, holdings, common funding '
        'and future demand remain unknown. Public swaps assign no actor, capital, utility, action effect or success probability.')
    world['limitations'].append(
        'Frozen source metadata survives review and export, but a hash proves snapshot identity only. '
        'The bounded forward archive is incomplete; provider-declared network, sender, timestamps and USD values are unverified. '
        'Rebuild explicitly to refresh; this world does not silently update.')
    # Assumptions/provenance are review artifacts, not part of an actor's
    # permitted observation. An explicit public event makes the bounded factual
    # context available to personas without exposing raw wallet addresses.
    identifier='near-source-context'
    if any(e['id']==identifier for e in world['events']):raise ValueError('source context event already exists')
    world['events'].append({'id':identifier,'round':1,
        'text':('Public NEAR observation, captured '+str(frozen['captured_at'])+'. '
            +str(analyzed['summary']['accepted_trades'])+' sampled swaps across '
            +str(analyzed['summary']['observed_wallets'])+' observed addresses. '
            'USD notional is provider-declared, not participant capital. '
            'Partial forward coverage; identities, motives and future demand remain unknown. '
            'Action effects and utilities are authored assumptions, not calibrated. Snapshot SHA256 '+snapshot_hash),
        'effects':{},'visible_to':[a['id']for a in world['actors']],
        'provenance':{'status':'estimated','rationale':'Bounded public source summary from a frozen provider-declared snapshot; no numeric effect or persona inference.','source_refs':[]}})
    refs = ['urn:sha256:' + snapshot_hash] + [source['source_url'] for source in sources]
    nodes = world['metrics'] + world['actors'] + world['events'] + world['interactions']
    nodes += [action for actor in world['actors'] for action in actor['actions']]
    for node in nodes:
        provenance = node['provenance']
        provenance['source_refs'] = list(dict.fromkeys(refs + provenance['source_refs']))
        provenance['rationale'] += ' NEAR observations are context only; this rule remains an authored assumption, not empirical calibration.'
    return {
        'schema_version': 'near-demo.v1', 'world': validate_strategic_world(world), 'evidence': frozen,
        'model_requests': 0, 'review_status': 'human_review_required',
        'decision_brief': {
            'question': 'Under what conditions should a NEAR creator fund a bounded pilot or a larger commitment?',
            'pilot_if': 'A deliverable, owner, acceptance test, incentive cap and stop date are agreed within the stated pilot budget.',
            'larger_commitment_if': 'Pilot delivery and independent review are documented, unresolved issues are addressed, '
                                    'and the larger budget receives a separate explicit approval.',
            'wait_or_stop_if': 'Coverage is inadequate for the decision, delivery cannot be verified, incentive costs exceed the cap, '
                               'or independent review raises unresolved concerns.',
            'evidence_can_support': 'A reproducible dated description of sampled NEAR swap activity and its coverage limits.',
            'evidence_cannot_support': 'Verified participant identities, motives, project demand, actor capital, profitability or a go/no-go forecast.',
            'external_authoring': 'No author is called. Review the exact frozen world and public inputs before explicitly approving any external author request.',
        },
    }


def rehearse_near_demo(demo):
    """Execute four declared local action paths; frequencies are not forecasts."""
    world = validate_strategic_world(demo['world'])
    actor_ids = {actor['id'] for actor in world['actors']}
    if actor_ids != {'creator', 'reviewer'}:
        raise ValueError('rehearsal requires the NEAR creator/reviewer cast')
    paths = [('wait', 'wait'), ('pilot', 'review'), ('commit', 'review'), ('commit', 'caution')]
    branches = []
    for creator, reviewer in paths:
        engine = StrategicWorld(world)
        while observations := engine.observations():
            decisions = {actor: {'action_id': ({'creator': creator, 'reviewer': reviewer}[actor]
                if engine.round == 1 else 'wait'), 'observation_sha256': obs['observation_sha256']}
                for actor, obs in observations.items()}
            engine.advance(decisions)
        branches.append({'first_round_actions': {'creator': creator, 'reviewer': reviewer}, 'result': engine.report()})
    return {'schema_version': 'near-demo-rehearsal.v1', 'model_requests': 0, 'branches': branches,
        'meaning': 'Declared action paths under hypothetical rules. Cash tracks costs; utility is not profit. '
                   'Branch counts are neither event odds nor recommendations. Later rounds wait; no automatic escalation.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path, help='Existing public forward archive; opened read-only')
    parser.add_argument('--output', required=True, type=Path, help='New local directory; existing paths are refused')
    parser.add_argument('--as-of', help='Explicit UTC ISO 8601 snapshot cutoff; defaults to current time')
    parser.add_argument('--limit', type=int, default=1000, help='Maximum newest observed rows, 1 to 1000')
    parser.add_argument('--rehearse', action='store_true', help='Also replay declared local decision paths; no model calls')
    args = parser.parse_args(argv)
    output = args.output.expanduser().absolute()
    for candidate in (output, *output.parents):
        if candidate.is_symlink():
            raise ValueError('symlinked output path refused')
    if output.exists():
        raise FileExistsError('output must be a new directory')
    with PublicArchive(args.archive, read_only=True) as archive:
        snapshot = archive.export_snapshot('near', limit=args.limit, as_of=args.as_of)
    demo = build_near_demo(snapshot)
    artifacts = {'demo.json': demo, 'world.json': demo['world'], 'evidence.json': demo['evidence']}
    if args.rehearse:
        artifacts['rehearsal.json'] = rehearse_near_demo(demo)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    write_artifacts([(output / name, json_bytes(value)) for name, value in artifacts.items()])
    print(json.dumps({'output': str(output), 'snapshot_sha256': demo['evidence']['snapshot_sha256'],
                      'summary': demo['evidence']['summary'], 'model_requests': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
