"""Combine seed-42 held-out runs with two new paired seeds for risk vs none."""
import csv
import json
from collections import defaultdict
from pathlib import Path

from scripts.experiment import SUITES, summarize


def main():
    main_dir = Path('outputs/benchmark_heldout')
    repeat_dir = Path('outputs/benchmark_repeats')
    rows = []
    for seed in (42, 43, 44):
        directory = main_dir if seed == 42 else repeat_dir
        for task in SUITES['heldout']:
            for policy in ('risk', 'none'):
                path = directory / f'heldout_task{task}_seed{seed}_{policy}.json'
                if not path.exists():
                    raise SystemExit(f'Missing trace: {path}')
                trace = json.loads(path.read_text())
                if trace.get('reward') is None or trace.get('controlled_fault_injection'):
                    raise SystemExit(f'Invalid natural benchmark trace: {path}')
                rows.append(summarize(trace))
    out = Path('report/combined_heldout_risk_none.csv')
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_policy = defaultdict(list)
    by_pair = defaultdict(dict)
    for row in rows:
        by_policy[row['policy']].append(row)
        by_pair[(row['task_id'], row['seed'])][row['policy']] = row['reward']
    comparison = {}
    for policy, items in by_policy.items():
        comparison[policy] = {
            'trials': len(items),
            'successes': sum(x['reward'] == 1 for x in items),
            'readback_calls': sum(x['readback_calls'] for x in items),
            'fail_verdicts': sum(x['fails'] for x in items),
            'inconclusive_verdicts': sum(x['inconclusive'] for x in items),
            'estimated_model_cost_usd': round(sum(x['estimated_model_cost_usd'] or 0 for x in items), 6),
        }
    comparison['paired'] = {
        'risk_wins': sum(v['risk'] > v['none'] for v in by_pair.values()),
        'none_wins': sum(v['risk'] < v['none'] for v in by_pair.values()),
        'ties': sum(v['risk'] == v['none'] for v in by_pair.values()),
    }
    (out.parent / 'combined_heldout_summary.json').write_text(json.dumps(comparison, indent=2))
    print(json.dumps(comparison, indent=2))


if __name__ == '__main__':
    main()
