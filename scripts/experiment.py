"""Small, sequential tau2 retail experiment runner. No automatic costly batch."""
import argparse
import csv
import json
from pathlib import Path

SUITES = {'dev': ['34', '22', '72', '41', '87'], 'heldout': ['17', '42', '71', '97', '102']}
POLICIES = ['none', 'final-only', 'exhaustive', 'random', 'risk']

def summarize(trace):
    events = trace['events']
    verifications=[e.get('verification') for e in events if e.get('verification')]
    return {'suite':trace.get('suite',''), 'task_id':trace['task_id'], 'seed':trace['seed'],
            'policy':trace['policy'], 'reward':trace['reward'],
            'write_calls':sum(e['mutating'] and e.get('executed', True) for e in events),
            'verification_calls':len(verifications),
            'readback_calls':sum(v['read_calls'] for v in verifications),
            'fails':sum(v['verdict']=='FAIL' for v in verifications),
            'inconclusive':sum(v['verdict']=='INCONCLUSIVE' for v in verifications),
            'correction_opportunities':sum(bool(e.get('correction_opportunity')) for e in events),
            'elapsed_seconds':trace['elapsed_seconds'],
            'total_model_tokens':trace.get('total_model_tokens'),
            'reported_model_cost_usd':trace.get('reported_model_cost_usd'),
            'estimated_model_cost_usd':trace.get('estimated_model_cost_usd')}

def main():
    from selective_verify.run import run
    p=argparse.ArgumentParser()
    p.add_argument('--suite',choices=SUITES,default='dev')
    p.add_argument('--policies',nargs='+',choices=POLICIES,default=['none'])
    p.add_argument('--model',default='openai/gpt-4.1-mini')
    p.add_argument('--seeds',nargs='+',type=int,default=[42])
    p.add_argument('--max-runs',type=int,default=1)
    p.add_argument('--random-rate',type=float,default=.5)
    p.add_argument('--threshold',type=float,default=.55)
    p.add_argument('--output-dir',default='outputs/benchmark')
    a=p.parse_args()
    out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    jobs=[(task,seed,policy) for task in SUITES[a.suite] for seed in a.seeds for policy in a.policies]
    if len(jobs)>a.max_runs:
        raise SystemExit(f'{len(jobs)} runs requested; raise --max-runs explicitly after reviewing API cost')
    rows=[]
    for task,seed,policy in jobs:
        path=out/f'{a.suite}_task{task}_seed{seed}_{policy}.json'
        if path.exists():
            trace=json.loads(path.read_text())
        else:
            trace=run(task,policy,a.model,seed,path,a.threshold,a.random_rate)
            trace['suite']=a.suite
            path.write_text(json.dumps(trace,indent=2))
        rows.append(summarize(trace))
        print(rows[-1],flush=True)
    with (out/'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
if __name__=='__main__':main()
