"""Summarize completed official tau2 traces without treating faults as benchmark runs."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from scripts.experiment import summarize


def summarize_directory(directory: Path):
    traces = []
    for path in sorted(directory.glob('*_task*_seed*_*.json')):
        trace = json.loads(path.read_text())
        if trace.get('benchmark') != 'tau2 retail' or trace.get('reward') is None:
            continue
        traces.append(trace)
    rows = [summarize(trace) for trace in traces]
    groups = defaultdict(list)
    for row in rows:
        groups[row['policy']].append(row)
    aggregate = []
    for policy, items in sorted(groups.items()):
        checks = sum(x['verification_calls'] for x in items)
        inconclusive = sum(x['inconclusive'] for x in items)
        aggregate.append({
            'policy': policy,
            'tasks': len(items),
            'official_successes': sum(x['reward'] == 1 for x in items),
            'success_rate': sum(x['reward'] == 1 for x in items) / len(items),
            'writes': sum(x['write_calls'] for x in items),
            'checkpoints': checks,
            'readback_calls': sum(x['readback_calls'] for x in items),
            'inconclusive': inconclusive,
            'actionable_verdicts': checks - inconclusive,
            'fail_verdicts': sum(x['fails'] for x in items),
            'correction_opportunities': sum(x['correction_opportunities'] for x in items),
            'total_model_tokens': sum(x['total_model_tokens'] or 0 for x in items),
            'estimated_model_cost_usd': round(sum(x['estimated_model_cost_usd'] or 0 for x in items), 6),
            'mean_elapsed_seconds': round(sum(x['elapsed_seconds'] for x in items) / len(items), 3),
        })
    return rows, aggregate


def write_csv(path: Path, rows):
    if not rows:
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    rows, aggregate = summarize_directory(args.directory)
    if not rows:
        raise SystemExit('No completed official tau2 traces found')
    write_csv(args.directory / 'comparison_rebuilt.csv', rows)
    write_csv(args.directory / 'policy_summary.csv', aggregate)
    for item in aggregate:
        print(item)


if __name__ == '__main__':
    main()
