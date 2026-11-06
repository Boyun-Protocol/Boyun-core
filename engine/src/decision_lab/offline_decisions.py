"""Disclosed local baseline; no language model, network, learned odds or lookahead."""
from .agent_worlds import digest


class OfflineDecisions:
    model='local-myopic-utility-v1'
    protocol='local-rule-choice.v1'
    endpoint=None
    timeout=None

    def evaluate(self,*,state,questions):
        if set(questions)!={'action'}:raise ValueError('local action question required')
        weights=state['actor']['utility_weights']
        bounds={m['id']:m for m in state['world']['metric_definitions']}
        def score(action):
            delta=0
            for metric,weight in weights.items():
                if metric=='cash_cents':delta-=weight*action['cost_cents']
                else:
                    old=state['metrics'][metric];spec=bounds[metric]
                    after=max(spec['min'],min(spec['max'],old+action['effects'].get(metric,0)))
                    delta+=weight*(after-old)
            return delta
        scores=[score(a)for a in state['actions']]
        best=max(scores);winners=[i for i,v in enumerate(scores)if v==best]
        # Stable menu order breaks ties. This is not uncertainty estimation.
        selected=winners[0];keys=list(questions['action']['criteria'])
        if len(keys)!=len(scores):raise ValueError('local menu mismatch')
        probabilities={key:float(i==selected)for i,key in enumerate(keys)}
        return {'answers':{'action':{'type':'choice','choice':keys[selected],'confidence':1.0,'probabilities':probabilities}},
            'receipt':{'actual_provider':'local_rules','local_decision':True,'model_requests':0,
                'policy':self.model,'request_sha256':digest({'state':state,'questions':questions}),
                'cost_usd':0,'limitations':'Deterministic myopic own-action utility delta; ties use menu order. Ignores narrative motivations, peer messages, joint responses and future events. One-hot policy is not confidence or event odds.'}}
