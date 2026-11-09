"""Key-free tests of the exact execution hook used by the tau2 subclass."""
import json
import sys
import types
from dataclasses import dataclass
from types import SimpleNamespace
from selective_verify.core import VerificationOrchestratorMixin

@dataclass
class Call:
    name: str
    arguments: dict
    id: str = ''
    requestor: str = 'assistant'

@dataclass
class System:
    role: str
    content: str

@dataclass
class ToolMessage:
    id: str
    role: str
    requestor: str
    content: str
    error: bool
    execution_status: str

def mock_tau_messages(monkeypatch):
    module=types.ModuleType('tau2.data_model.message')
    module.ToolCall=Call; module.SystemMessage=System; module.ToolMessage=ToolMessage
    simulation=types.ModuleType('tau2.data_model.simulation')
    simulation.TerminationReason=SimpleNamespace(AGENT_ERROR='agent_error')
    monkeypatch.setitem(sys.modules,'tau2',types.ModuleType('tau2'))
    monkeypatch.setitem(sys.modules,'tau2.data_model',types.ModuleType('tau2.data_model'))
    monkeypatch.setitem(sys.modules,'tau2.data_model.message',module)
    monkeypatch.setitem(sys.modules,'tau2.data_model.simulation',simulation)

class Environment:
    def __init__(self):
        self.state = {'address': {'address1':'123 Main Street','zip':'94305'}}
        self.calls=[]
        self.tools=SimpleNamespace(tool_mutates_state=lambda n:n=='modify_pending_order_address')
    def get_response(self, call):
        self.calls.append(call.name)
        if call.name=='modify_pending_order_address':
            self.state={'address': {'address1':call.arguments['address1'],'zip':'94305'}}
        return SimpleNamespace(error=False,content=json.dumps(self.state))

class Harness(VerificationOrchestratorMixin):
    def __init__(self, intent):
        self.environment=Environment()
        self.agent_state=SimpleNamespace(system_messages=[])
        self.num_errors=0
        self.intent=intent
        self.configure_verification('exhaustive')
    def get_trajectory(self):
        return [SimpleNamespace(role='user',content=self.intent)]

def test_hook_reads_independent_state_and_triggers_one_correction(monkeypatch):
    mock_tau_messages(monkeypatch)
    h=Harness('Please change to 123 Main Street, 94305')
    for _ in range(2):
        h._execute_tool_calls([Call('modify_pending_order_address',{'order_id':'#1','address1':'999 Wrong Road'})])
    assert h.environment.calls==['get_order_details','modify_pending_order_address','get_order_details']*2
    assert [e['verification']['verdict'] for e in h.events]==['FAIL','FAIL']
    assert len(h.agent_state.system_messages)==1
    assert h.corrections==1
    assert h.events[-1]['escalated']
    assert '999 Wrong Road' in h.events[0]['verification']['evidence']['address']['address1']

def test_no_verification_has_no_read_overhead(monkeypatch):
    mock_tau_messages(monkeypatch)
    h=Harness('Please change to 123 Main Street, 94305')
    h.configure_verification('none')
    h._execute_tool_calls([Call('modify_pending_order_address',{'order_id':'#1','address1':'123 Main Street'})])
    assert h.environment.calls==['modify_pending_order_address']
    assert not h.events[0]['checkpoint']

def test_failed_checkpoint_rejects_later_bundled_write(monkeypatch):
    mock_tau_messages(monkeypatch)
    h=Harness('Please change to 123 Main Street, 94305')
    results=h._execute_tool_calls([
        Call('modify_pending_order_address',{'order_id':'#1','address1':'999 Wrong Road'},id='a'),
        Call('modify_pending_order_address',{'order_id':'#2','address1':'123 Main Street'},id='b'),
    ])
    assert h.environment.calls==['get_order_details','modify_pending_order_address','get_order_details']
    assert len(results)==2
    assert results[1].execution_status=='rejected'
    assert h.events[1]['executed'] is False
    assert 'OUTCOME VERIFICATION FAILED' in h.agent_state.system_messages[0].content
    assert 'OUTCOME VERIFICATION FAILED' not in results[0].content

def test_irreversible_failed_checkpoint_stops_without_repair(monkeypatch):
    mock_tau_messages(monkeypatch)
    h=Harness('Please cancel order #1')
    h.environment.tools=SimpleNamespace(tool_mutates_state=lambda n:n=='cancel_pending_order')
    h.environment.get_response=lambda call: SimpleNamespace(error=False,content=json.dumps({'status':'pending'}))
    h._execute_tool_calls([Call('cancel_pending_order',{'order_id':'#1'})])
    assert h.events[0]['verification']['verdict']=='FAIL'
    assert h.events[0]['escalated']
    assert h.done
    assert h.corrections==0

def test_readback_timeout_is_inconclusive(monkeypatch):
    mock_tau_messages(monkeypatch)
    h=Harness('Please change to 123 Main Street, 94305')
    def response(call):
        if call.name=='get_order_details':
            raise TimeoutError('read timeout')
        return SimpleNamespace(error=False,content='{}')
    h.environment.get_response=response
    h._execute_tool_calls([Call('modify_pending_order_address',{'order_id':'#1','address1':'123 Main Street'})])
    assert h.events[0]['verification']['verdict']=='INCONCLUSIVE'
    assert h.corrections==0
