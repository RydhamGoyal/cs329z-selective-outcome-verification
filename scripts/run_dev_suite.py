"""One-command development comparison with a conservative API-spend stop."""
import argparse
import csv
import json
from pathlib import Path
from selective_verify.run import run
from scripts.experiment import SUITES, summarize
from scripts.audit_verdicts import audit

MODEL='openrouter/openai/gpt-4.1-mini'
POLICIES=('risk','none','final-only','exhaustive','random')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--max-estimated-usd',type=float,default=5.0)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--output-dir',default='outputs/benchmark')
    p.add_argument('--reuse-source',type=Path,default=None)
    args=p.parse_args()
    if not 0 < args.max_estimated_usd <= 10:
        raise SystemExit('Cost cap must be above 0 and at most $10')
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    rows=[];spent=0.0;rate=.5
    for policy in POLICIES:
        if policy=='random':
            risk_rows=[r for r in rows if r['policy']=='risk']
            writes=sum(r['write_calls'] for r in risk_rows)
            rate=sum(r['verification_calls'] for r in risk_rows)/writes if writes else 0.0
            print(f'Development-calibrated random checkpoint rate: {rate:.4f}',flush=True)
        for task in SUITES['dev']:
            path=out/f'dev_task{task}_seed{args.seed}_{policy}.json'
            if path.exists():
                trace=json.loads(path.read_text())
                if trace.get('error') or trace.get('reward') is None:
                    raise SystemExit(f'Incomplete trace exists: {path}; inspect it before retrying')
            else:
                source=(args.reuse_source / path.name) if args.reuse_source else None
                if source and source.exists():
                    candidate=json.loads(source.read_text())
                    reusable=(not candidate.get('error') and candidate.get('reward') is not None
                              and not audit(candidate)
                              and (policy!='random' or (candidate.get('random_seed_scheme')=='task-specific-v1'
                                                        and abs(candidate.get('random_rate',-.1)-rate)<1e-9)))
                    if reusable:
                        trace=candidate
                        trace['audit_provenance']={'reused_from':str(source),
                                                   'verdicts_recomputed_consistent':True}
                        path.write_text(json.dumps(trace,indent=2))
                        print(f'Reused audited trace {source}',flush=True)
                    else:
                        trace=None
                else:
                    trace=None
                if trace is None:
                    # Reserve $0.25 for the next single task. The model run is capped
                # at 40 steps / 180 seconds; stop before a new trial near the cap.
                    if spent + .25 > args.max_estimated_usd:
                        print('Stopping before next task: estimated spend guard reached',flush=True)
                        break
                    trace=run(task,policy,MODEL,args.seed,path,random_rate=rate)
                    trace['suite']='dev'
                    path.write_text(json.dumps(trace,indent=2))
            row=summarize(trace);rows.append(row)
            spent+=trace.get('estimated_model_cost_usd') or 0
            with (out/'comparison.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
            print(f"completed {policy} task {task}: reward={row['reward']} estimated_cumulative_usd={spent:.4f}",flush=True)
        if len(rows)<(POLICIES.index(policy)+1)*len(SUITES['dev']):
            break
    if rows:
        with (out/'comparison.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    print(f'finished_rows={len(rows)} estimated_model_usd={spent:.4f} comparison={out / "comparison.csv"}',flush=True)
if __name__=='__main__':main()
