import csv
import sys
from pathlib import Path
from scripts import run_dev_suite

def test_dev_suite_calibrates_random_from_risk_only(tmp_path,monkeypatch):
    calls=[]
    def fake_run(task,policy,model,seed,path,random_rate):
        calls.append((policy,task,random_rate))
        checkpoint=policy in ('risk','exhaustive','final-only')
        return {'task_id':task,'seed':seed,'policy':policy,'reward':1.0,
                'elapsed_seconds':1.0,'estimated_model_cost_usd':.01,
                'total_model_tokens':100,
                'events':[{'mutating':True,'checkpoint':checkpoint,
                           'verification':{'verdict':'PASS','read_calls':1} if checkpoint else None}]}
    monkeypatch.setattr(run_dev_suite,'run',fake_run)
    monkeypatch.setattr(sys,'argv',['run_dev_suite','--output-dir',str(tmp_path)])
    run_dev_suite.main()
    assert len(calls)==25
    assert all(rate==1.0 for policy,_,rate in calls if policy=='random')
    with (tmp_path/'comparison.csv').open() as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==25

def test_dev_suite_stops_at_cost_guard(tmp_path,monkeypatch):
    calls=[]
    def fake_run(task,policy,model,seed,path,random_rate):
        calls.append(task)
        return {'task_id':task,'seed':seed,'policy':policy,'reward':1.0,
                'elapsed_seconds':1.0,'estimated_model_cost_usd':.1,
                'events':[{'mutating':True,'checkpoint':True,'verification':{'verdict':'PASS','read_calls':1}}]}
    monkeypatch.setattr(run_dev_suite,'run',fake_run)
    monkeypatch.setattr(sys,'argv',['run_dev_suite','--output-dir',str(tmp_path),'--max-estimated-usd','.3'])
    run_dev_suite.main()
    assert len(calls)==1

def test_pinned_suite_needs_no_external_nl_judge():
    import json
    from pathlib import Path
    from scripts.experiment import SUITES
    data=Path(__file__).resolve().parents[2]/'tau2-bench/data/tau2/domains/retail/tasks.json'
    if not data.exists():
        import pytest
        pytest.skip('pinned tau2 checkout not installed adjacent to project')
    tasks={x['id']:x for x in json.loads(data.read_text())}
    split_data=json.loads((data.parent/'split_tasks.json').read_text())
    for split in ('dev','heldout'):
        for task_id in SUITES[split]:
            assert not tasks[task_id]['evaluation_criteria'].get('nl_assertions')
            assert task_id in split_data['train' if split=='dev' else 'test']

def test_reuse_consistent_trace_without_paid_run(tmp_path,monkeypatch):
    import json
    from scripts.experiment import SUITES
    source=tmp_path/'source';source.mkdir()
    for policy in run_dev_suite.POLICIES:
        for task in SUITES['dev']:
            trace={'task_id':task,'seed':42,'policy':policy,'reward':1.0,
                   'elapsed_seconds':1.0,'estimated_model_cost_usd':.01,
                   'random_rate':1.0,'random_seed_scheme':'task-specific-v1','events':[{'tool':'modify_pending_order_items','arguments':{},'error':False,'mutating':True,'checkpoint':policy!='none',
                     'verification':{'verdict':'INCONCLUSIVE','reason':'test','evidence':None,'read_calls':0} if policy!='none' else None}],
                   'messages':[{'role':'user','content':'hello'},{'role':'tool','content':'{}'}]}
            (source/f'dev_task{task}_seed42_{policy}.json').write_text(json.dumps(trace))
    monkeypatch.setattr(run_dev_suite,'run',lambda *a,**k: (_ for _ in ()).throw(AssertionError('paid run must not start')))
    dest=tmp_path/'verified'
    monkeypatch.setattr(sys,'argv',['run_dev_suite','--output-dir',str(dest),'--reuse-source',str(source)])
    run_dev_suite.main()
    assert len(list(dest.glob('*.json')))==25
