"""Runs against the pinned official tau2 retail environment when installed."""
from types import SimpleNamespace
import pytest

tau2 = pytest.importorskip('tau2')
from tau2.runner import build_environment
from tau2.data_model.message import AssistantMessage, ToolCall
from selective_verify.core import VerificationOrchestratorMixin
from selective_verify.faults import WrongAddressOnce

class Hook(VerificationOrchestratorMixin):
    def __init__(self, environment):
        self.environment=environment
        self.agent_state=SimpleNamespace(system_messages=[])
        self.num_errors=0
        self.configure_verification('exhaustive')
    def get_trajectory(self):
        return [SimpleNamespace(role='user', content='Please change the shipping address to 123 Main Street, Stanford CA 94305. Yes, I confirm.')]

def test_real_retail_write_readback_and_reset():
    env=build_environment('retail')
    order=next(o for o in env.tools.db.orders.values() if str(o.status).lower()=='pending')
    old_street=order.address.address1
    call=ToolCall(name='modify_pending_order_address',arguments={
        'order_id':order.order_id,'address1':'999 Wrong Road','address2':'',
        'city':'Stanford','state':'CA','country':'USA','zip':'94305'})
    hook=Hook(env)
    response=hook._execute_tool_calls([call])[0]
    assert not response.error
    assert hook.events[0]['verification']['verdict']=='FAIL'
    assert hook.events[0]['verification']['read_calls']==2
    assert hook.corrections==1
    assert env.tools.db.orders[order.order_id].address.address1=='999 Wrong Road'
    fresh=build_environment('retail')
    assert fresh.tools.db.orders[order.order_id].address.address1==old_street

def test_success_response_can_hide_wrong_persisted_address():
    raw=build_environment('retail')
    order=next(o for o in raw.tools.db.orders.values() if str(o.status).lower()=='pending')
    wrapped=WrongAddressOnce(raw)
    hook=Hook(wrapped)
    call=ToolCall(name='modify_pending_order_address',arguments={
        'order_id':order.order_id,'address1':'123 Main Street','address2':'',
        'city':'Stanford','state':'CA','country':'USA','zip':'94305'})
    response=hook._execute_tool_calls([call])[0]
    assert not response.error
    assert '123 Main Street' in response.content
    assert raw.tools.db.orders[order.order_id].address.address1=='999 Wrong Road'
    assert hook.events[0]['verification']['evidence']['address']['address1']=='999 Wrong Road'
    assert hook.events[0]['verification']['verdict']=='FAIL'
    # Tau2's strict evaluator replays the recorded call and exact tool result.
    # The replay succeeds but sees the intended write, demonstrating why its
    # official reward cannot score this injected storage fault.
    replay=build_environment('retail')
    replay.set_state(initialization_data=None, initialization_actions=None,
                     message_history=[AssistantMessage(role='assistant',tool_calls=[call]),response])
    assert replay.tools.db.orders[order.order_id].address.address1=='123 Main Street'

def test_real_retail_batch_stops_after_failed_checkpoint():
    env=build_environment('retail')
    order=next(o for o in env.tools.db.orders.values() if str(o.status).lower()=='pending')
    user=env.tools.db.users[order.user_id]
    old_user_street=user.address.address1
    order_call=ToolCall(name='modify_pending_order_address',arguments={
        'order_id':order.order_id,'address1':'999 Wrong Road','address2':'',
        'city':'Stanford','state':'CA','country':'USA','zip':'94305'})
    user_call=ToolCall(name='modify_user_address',arguments={
        'user_id':order.user_id,'address1':'123 Main Street','address2':'',
        'city':'Stanford','state':'CA','country':'USA','zip':'94305'})
    hook=Hook(env)
    results=hook._execute_tool_calls([order_call,user_call])
    assert results[1].execution_status=='rejected'
    assert env.tools.db.users[order.user_id].address.address1==old_user_street
    assert hook.events[1]['executed'] is False
    replay=build_environment('retail')
    replay.set_state(initialization_data=None, initialization_actions=None,
                     message_history=[AssistantMessage(role='assistant',tool_calls=[order_call,user_call]), *results])
    assert replay.tools.db.users[order.user_id].address.address1==old_user_street
