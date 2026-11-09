"""Run the frozen held-out retail suite with a development-calibrated random rate."""
import argparse
import csv
import json
from pathlib import Path

from scripts.audit_verdicts import audit
from scripts.experiment import SUITES, summarize
from selective_verify.run import run

MODEL = 'openrouter/openai/gpt-4.1-mini'
POLICIES = ('risk', 'none', 'final-only', 'exhaustive', 'random')


def development_rate(directory: Path, seed: int) -> float:
    rows = []
    for task in SUITES['dev']:
        path = directory / f'dev_task{task}_seed{seed}_risk.json'
        if not path.exists():
            raise ValueError(f'Missing development risk trace: {path}')
        trace = json.loads(path.read_text())
        if trace.get('error') or trace.get('reward') is None or audit(trace):
            raise ValueError(f'Invalid development risk trace: {path}')
        if trace.get('model') != MODEL or trace.get('threshold') != .55:
            raise ValueError(f'Development configuration mismatch: {path}')
        rows.append(summarize(trace))
    writes = sum(row['write_calls'] for row in rows)
    return sum(row['verification_calls'] for row in rows) / writes if writes else 0.0


def write_rows(path: Path, rows: list[dict]) -> None:
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--development-dir', type=Path, default=Path('outputs/benchmark_final_dev'))
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/benchmark_heldout'))
    parser.add_argument('--max-estimated-usd', type=float, default=5.0)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    if not 0 < args.max_estimated_usd <= 10:
        raise SystemExit('Cost cap must be above 0 and at most $10')
    rate = development_rate(args.development_dir, args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {'suite': 'heldout', 'benchmark_commit': '033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f',
                'model': MODEL, 'seed': args.seed, 'threshold': .55,
                'random_rate_from_development': rate, 'development_dir': str(args.development_dir),
                'tasks': SUITES['heldout'], 'policies': POLICIES}
    manifest_path = args.output_dir / 'run_config.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise SystemExit('Existing held-out run configuration differs; use a new output directory')
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f'Frozen random checkpoint probability from development: {rate:.4f}', flush=True)
    rows = []
    spent = 0.0
    for policy in POLICIES:
        for task in SUITES['heldout']:
            path = args.output_dir / f'heldout_task{task}_seed{args.seed}_{policy}.json'
            if path.exists():
                trace = json.loads(path.read_text())
                if trace.get('error') or trace.get('reward') is None or audit(trace):
                    raise SystemExit(f'Invalid existing trace: {path}')
            else:
                # Reserve enough room for one trial's typical cost; the tau2
                # orchestrator also enforces 40 steps and a 180-second timeout.
                if spent + .25 > args.max_estimated_usd:
                    print('Stopping before next trial: estimated spend guard reached', flush=True)
                    break
                trace = run(task, policy, MODEL, args.seed, path, random_rate=rate)
                trace['suite'] = 'heldout'
                path.write_text(json.dumps(trace, indent=2))
            row = summarize(trace)
            rows.append(row)
            spent += trace.get('estimated_model_cost_usd') or 0
            write_rows(args.output_dir / 'comparison.csv', rows)
            print(f"completed {policy} task {task}: reward={row['reward']} estimated_cumulative_usd={spent:.4f}", flush=True)
        if len(rows) < (POLICIES.index(policy)+1) * len(SUITES['heldout']):
            break
    print(f'finished_rows={len(rows)} estimated_model_usd={spent:.4f}', flush=True)


if __name__ == '__main__':
    main()
