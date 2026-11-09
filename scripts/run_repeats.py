"""Cost-bounded repeated held-out risk-versus-none trials at new paired seeds."""
import argparse
import csv
import json
from pathlib import Path

from scripts.audit_verdicts import audit
from scripts.experiment import SUITES, summarize
from selective_verify.run import run

MODEL = 'openrouter/openai/gpt-4.1-mini'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/benchmark_repeats'))
    parser.add_argument('--seeds', nargs='+', type=int, default=[43, 44])
    parser.add_argument('--max-estimated-usd', type=float, default=5.0)
    args = parser.parse_args()
    if not 0 < args.max_estimated_usd <= 10:
        raise SystemExit('Cost cap must be above 0 and at most $10')
    if any(seed == 42 for seed in args.seeds):
        raise SystemExit('Seed 42 is already in the main held-out comparison')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {'suite': 'heldout_repeats', 'model': MODEL, 'seeds': args.seeds,
                'tasks': SUITES['heldout'], 'policies': ['risk', 'none'], 'threshold': .55,
                'benchmark_commit': '033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f'}
    manifest_path = args.output_dir / 'run_config.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise SystemExit('Existing repeat configuration differs; use a new output directory')
    manifest_path.write_text(json.dumps(manifest, indent=2))
    rows = []
    spent = 0.0
    for seed in args.seeds:
        for task in SUITES['heldout']:
            for policy in ('risk', 'none'):
                path = args.output_dir / f'heldout_task{task}_seed{seed}_{policy}.json'
                if path.exists():
                    trace = json.loads(path.read_text())
                    if trace.get('error') or trace.get('reward') is None or audit(trace):
                        raise SystemExit(f'Invalid existing trace: {path}')
                else:
                    if spent + .25 > args.max_estimated_usd:
                        print('Stopping before next trial: estimated spend guard reached', flush=True)
                        return
                    trace = run(task, policy, MODEL, seed, path)
                    trace['suite'] = 'heldout_repeats'
                    path.write_text(json.dumps(trace, indent=2))
                rows.append(summarize(trace))
                spent += trace.get('estimated_model_cost_usd') or 0
                with (args.output_dir / 'comparison.csv').open('w', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"completed seed={seed} task={task} policy={policy} reward={trace['reward']} estimated_cumulative_usd={spent:.4f}", flush=True)
    print(f'finished_rows={len(rows)} estimated_model_usd={spent:.4f}', flush=True)


if __name__ == '__main__':
    main()
