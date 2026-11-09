from scripts.audit_verdicts import audit

def test_audit_uses_intent_available_before_tool_result():
    trace={'messages':[{'role':'user','content':'Ship to 445 Maple Drive.'},
                       {'role':'tool','content':'{}'},
                       {'role':'user','content':'Actually 123 Main Street.'}],
           'events':[{'tool':'modify_pending_order_address','arguments':{},'error':False,
                      'verification':{'verdict':'PASS','evidence':{'address':{'address1':'445 Maple Drive'}}}}]}
    assert audit(trace)==[]

def test_audit_detects_false_alarm():
    trace={'messages':[{'role':'user','content':'Use 445 Maple Drive, not 500 pieces.'},
                       {'role':'tool','content':'{}'}],
           'events':[{'tool':'modify_pending_order_address','arguments':{},'error':False,
                      'verification':{'verdict':'FAIL','evidence':{'address':{'address1':'445 Maple Drive'}}}}]}
    issues=audit(trace)
    assert issues[0]['saved']=='FAIL' and issues[0]['recomputed']=='PASS'
