from copy import deepcopy
import json
import pytest
from decision_lab.agent_models import ModelFailure
from decision_lab.agent_worlds import digest


def questions():
    return {'action':{'type':'choice','instructions':'Choose the affordable action.',
                      'criteria':{'wait':'Keep cash','pilot':'Fund a small pilot'}},
            'ready':{'type':'noul','instructions':'Is there verified evidence of readiness?'}}


class TextModel:
    model='gemini-test'; timeout=30; binary='fixture'
    def __init__(self):self.calls=[]
    def generate(self,messages):
        self.calls.append(deepcopy(messages))
        return {'value':{'answers':{'action':{'type':'choice','choice':'pilot','confidence':.8,
                    'probabilities':{'wait':.25,'pilot':.75}},'ready':{'type':'noul','noul':.2}}},
                'receipt':{'model_declared':self.model,'transport':'fixture_gemini',
                           'usage':{'total_tokens':100},'cost_usd':None,'request_attempts':1}}


def test_gemini_uses_exact_jev_state_questions_contract_and_actual_identity():
    from decision_lab.gemini_decisions import GeminiDecisions
    model=TextModel();client=GeminiDecisions(model)
    state={'actor':{'motivation':'preserve runway'},'private':'own information'}
    result=client.evaluate(state=state,questions=questions())
    data=json.loads(model.calls[0][1]['content'])
    assert data=={'state':state,'questions':questions()}
    assert result['answers']['action']['probabilities']=={'wait':.25,'pilot':.75}
    receipt=result['receipt']
    assert receipt['model_declared']=='gemini-test' and receipt['transport']=='fixture_gemini'
    assert receipt['decision_contract']=='jev-choice-noul.v1' and receipt['actual_provider']=='gemini'
    assert receipt['structured_request_sha256']==digest(data)
    assert 'Jev was not called' in receipt['limitations']
    assert len(model.calls)==1


def test_bad_primitive_or_distribution_is_single_attempt_no_fallback():
    from decision_lab.gemini_decisions import GeminiDecisions
    class Bad(TextModel):
        def generate(self,messages):
            value=super().generate(messages);value['value']['answers']['action']['probabilities']['wait']=.8;return value
    model=Bad()
    with pytest.raises(ModelFailure) as error:GeminiDecisions(model).evaluate(state='context',questions=questions())
    assert error.value.code=='gemini_decision_invalid_response' and len(model.calls)==1
    model=TextModel();q=questions();q['action']['criteria']={'only':'Only one'}
    with pytest.raises(ValueError):GeminiDecisions(model).evaluate(state='context',questions=q)
    assert not model.calls
    model.model='different-provider'
    with pytest.raises(ValueError):GeminiDecisions(model)


def test_gemini_adapter_drives_same_strategic_choice_menu():
    from decision_lab.gemini_decisions import GeminiDecisions
    from decision_lab.strategic_models import decide
    from decision_lab.strategic_worlds import StrategicWorld
    from decision_lab.product_api import examples
    class Menu(TextModel):
        def generate(self,messages):
            self.calls.append(messages);data=json.loads(messages[1]['content'])
            q=data['questions']['action'];ids=list(q['criteria'])
            return {'value':{'answers':{'action':{'type':'choice','choice':ids[1],'confidence':.8,
                'probabilities':{key:(.8 if key==ids[1] else .2/(len(ids)-1)) for key in ids}}}},
                'receipt':{'model_declared':self.model,'transport':'fixture_gemini','limitations':'fixture'}}
    model=Menu();client=GeminiDecisions(model)
    obs=next(iter(StrategicWorld(examples()[0]['world']).observations().values()))
    answer=decide(client,obs)
    assert answer['action_id']=='pilot' and answer['probabilities']['pilot']==.8
    assert json.loads(model.calls[0][1]['content'])['state']==obs
    assert answer['receipt']['actual_provider']=='gemini'


def test_author_question_recommendations_are_validated_not_fabricated():
    from decision_lab.strategic_models import validate_proposal
    p={'schema_version':'strategic-proposal.v1','context_sha256':'a'*64,'summary':'Choose a priority',
       'questions':[{'id':'goal','prompt':'Which goal?','choices':['Runway','Attention'],'required':True,
          'recommendation':{'choice':'Runway','confidence':.7,'probabilities':{'Runway':.7,'Attention':.3},'reason':'Lower initial spending suits the stated budget.'}}],
       'world':None,'limitations':['Scores are setup suggestions, not outcome odds.']}
    assert validate_proposal(p,'a'*64)==p
    bad=deepcopy(p);bad['questions'][0]['recommendation']['probabilities']['Runway']=.9
    with pytest.raises(ValueError):validate_proposal(bad,'a'*64)
    p['questions'][0].pop('recommendation')
    assert validate_proposal(p,'a'*64)==p
