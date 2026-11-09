import random
from selective_verify.core import risk, selected, verdict, save_trace

def test_risk_and_policy():
    r=risk('cancel_pending_order')
    assert 0 <= r.score <= 1
    assert selected('exhaustive',r.score,random.Random(1))
    assert not selected('none',r.score,random.Random(1))
    assert selected('risk',r.score,random.Random(1),threshold=0)

def test_risk_weights_are_configurable_and_normalized():
    impact_only=risk('cancel_pending_order',weights=(1,0,0,0))
    uncertainty_only=risk('cancel_pending_order',weights=(0,0,0,5))
    assert impact_only.score==impact_only.impact
    assert uncertainty_only.score==uncertainty_only.uncertainty

def test_verdict_intent_not_args():
    evidence={'address':{'address1':'999 Wrong Road','zip':'94305'}}
    assert verdict('modify_pending_order_address', {'address1':'999 Wrong Road'},evidence,'Please send to 123 Main Street, 94305')[0]=='FAIL'
    assert verdict('modify_pending_order_address', {},None,'anything')[0]=='INCONCLUSIVE'

def test_trace_roundtrip(tmp_path):
    p=tmp_path/'trace.json'; save_trace(p,{'events':[{'tool':'x'}]})
    assert 'events' in p.read_text()

def test_correct_arguments_do_not_excuse_wrong_persisted_state():
    evidence={'address':{'address1':'999 Wrong Road','zip':'94305'}}
    status,_=verdict('modify_pending_order_address',{'address1':'123 Main Street'},evidence,'Please change to 123 Main Street, 94305')
    assert status=='FAIL'

def test_missing_intent_cannot_pass():
    evidence={'address':{'address1':'123 Main Street','zip':'94305'}}
    assert verdict('modify_pending_order_address',{'address1':'123 Main Street'},evidence,'Please change my address')[0]=='INCONCLUSIVE'

def test_random_policy_is_seeded():
    assert [selected('random', .7, random.Random(5), random_rate=.4) for _ in range(3)] == [False]*3
    a=random.Random(5); b=random.Random(5)
    assert [selected('random', .7, a, random_rate=.4) for _ in range(20)] == [selected('random', .7, b, random_rate=.4) for _ in range(20)]

def test_random_stream_depends_on_task_id():
    class Task: pass
    class Dummy:
        def __init__(self, task_id):
            self.task=Task(); self.task.id=task_id
    from selective_verify.core import VerificationOrchestratorMixin
    streams=[]
    for task_id in ('34','22','72','41','87'):
        obj=Dummy(task_id)
        VerificationOrchestratorMixin.configure_verification(obj,'random',seed=42)
        streams.append(tuple(round(obj.rng.random(),6) for _ in range(4)))
    assert len(set(streams))==5

def test_no_oracle_fields_in_runtime_module():
    from pathlib import Path
    code=Path('selective_verify/core.py').read_text()
    assert 'evaluation_criteria' not in code
    assert 'reward_info' not in code
    assert 'task.user_scenario' not in code

def test_product_quantity_is_not_mistaken_for_street():
    intent=('I want the 500 pieces, art theme, beginner puzzle. '
            'The correct shipping address is 445 Maple Drive, Suite 394, Fort Worth, Texas, 76165.')
    observed={'address':{'address1':'445 Maple Drive','zip':'76165'}}
    assert verdict('modify_pending_order_address',{'address1':'445 Maple Drive'},observed,intent)[0]=='PASS'

def test_multiple_streets_uses_latest_user_target():
    intent='Please change to 123 Main Street. Actually, use 445 Maple Drive instead.'
    observed={'address':{'address1':'445 Maple Drive','zip':'76165'}}
    assert verdict('modify_pending_order_address',{},observed,intent)[0]=='PASS'
