"""Reviewed persona emphasis, separate from world execution and market evidence."""
from copy import deepcopy
from .strategic_worlds import validate_strategic_world

FOCUSES=('balanced','retail','liquidity','team')
RETAIL=('balanced','degen','cautious')
TEAM=('balanced','marketing','liquidity')

def validate_options(value):
    if type(value)is not dict or set(value)!={'focus','retail_style','team_priority'}:raise ValueError('exact persona controls required')
    if value['focus']not in FOCUSES or value['retail_style']not in RETAIL or value['team_priority']not in TEAM:raise ValueError('reviewed persona option required')
    return deepcopy(value)


def adapt_personas(world,options):
    """Change profiles only. No inferred wallet identity, new money or execution."""
    world=deepcopy(validate_strategic_world(world));options=validate_options(options)
    if options=={'focus':'balanced','retail_style':'balanced','team_priority':'balanced'}:return world
    for index,actor in enumerate(world['actors']):
        # The first role owns the scenario plan; remaining roles are counterparties.
        # This is an explicit template convention, not an inferred real identity.
        if index==0:
            priority={'balanced':'Balance visibility, liquidity readiness and preserving runway.',
                'marketing':'Prioritize transparent marketing and audience discovery over liquidity work. Spend only on permitted actions; do not assume spending creates buyers.',
                'liquidity':'Prioritize liquidity readiness and market-making due diligence over promotion. There is no modeled market-maker execution, inventory or funded liquidity allocation unless explicitly present in the reviewed rules.'}[options['team_priority']]
            actor['motivation']=('User-selected team emphasis: '+priority+' '+actor['motivation'])[:1600]
            actor['goal']=(priority+' '+actor['goal'])[:1600]
        else:
            emphasis={'balanced':'Compare attention, evidence and preserving resources.',
                'degen':'Use a speculative, momentum-seeking retail viewpoint: favor timely exploration and social signals, while respecting the affordable menu. This is hypothetical behavior, not an observed trader identity.',
                'cautious':'Use a cautious retail viewpoint: require evidence, value downside protection, and consider waiting before exposure.'}[options['retail_style']]
            if options['focus']=='retail' or options['retail_style']!='balanced':
                actor['role']='Retail participant / user-selected scenario perspective'
                actor['motivation']=('User-selected audience emphasis: '+emphasis+' '+actor['motivation'])[:1600]
                actor['goal']=(emphasis+' '+actor['goal'])[:1600]
        if options['focus']=='liquidity':
            actor['goal']=(actor['goal']+' Inspect liquidity constraints, counterparty incentives and inventory risk within the supplied action menu.')[:1600]
        elif options['focus']=='team':
            actor['goal']=(actor['goal']+' Inspect delivery commitments and team/partner coordination.')[:1600]
        actor['provenance']={'status':'assumed','rationale':'User-selected reviewed persona emphasis. Cash, weights, actions, effects and peer links are unchanged; these are hypothetical preferences, not empirically fitted behavior.','source_refs':actor['provenance']['source_refs']}
    world['assumptions'].append('User-selected persona emphasis: '+str(options)+'. Priorities do not allocate or spend cash. Market making is not executed by the strategic engine.')
    return validate_strategic_world(world)
