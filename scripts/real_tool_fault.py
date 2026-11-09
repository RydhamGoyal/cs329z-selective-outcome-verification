"""Controlled fault injection through official tau2 retail tools; no model or reward."""
from pathlib import Path
from types import SimpleNamespace
from tau2.runner import build_environment
from tau2.data_model.message import ToolCall
from selective_verify.core import VerificationOrchestratorMixin, save_trace

INTENT='Please change the shipping address to 123 Main Street, Stanford CA 94305. Yes, I confirm.'

class FaultHook(VerificationOrchestratorMixin):
    def __init__(self, environment):
        self.environment=environment
        self.agent_state=SimpleNamespace(system_messages=[])
        self.num_errors=0
        self.configure_verification('risk')
    def get_trajectory(self):
        return [SimpleNamespace(role='user',content=INTENT)]

def main():
    env=build_environment('retail')
    order=next(o for o in env.tools.db.orders.values() if str(o.status).lower()=='pending')
    hook=FaultHook(env)
    call=ToolCall(name='modify_pending_order_address',arguments={
        'order_id':order.order_id,'address1':'999 Wrong Road','address2':'',
        'city':'Stanford','state':'CA','country':'USA','zip':'94305'})
    result=hook._execute_tool_calls([call])[0]
    data={'kind':'deterministic_fault_injection_in_official_tau2_retail_environment',
          'benchmark_commit':'033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f',
          'user_objective':INTENT,'policy':'risk','task_id':None,'seed':42,
          'official_reward':None,'events':hook.events,
          'messages':[{'role':'user','content':INTENT},
                      {'role':'assistant','tool_calls':[call.model_dump(mode='json')]},
                      {'role':'tool','content':result.content}]}
    path=Path('outputs/real_retail_fault.json');save_trace(path,data)
    print({'trace':str(path),'verdict':hook.events[0]['verification']['verdict'],
           'read_calls':hook.events[0]['verification']['read_calls']})
if __name__=='__main__':main()
