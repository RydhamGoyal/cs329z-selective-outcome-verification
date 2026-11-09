"""Check completeness and verifier consistency of saved natural tau2 traces."""
import argparse
import json
from pathlib import Path

from scripts.audit_verdicts import audit


def validate(path: Path):
    trace = json.loads(path.read_text())
    issues = []
    if trace.get('benchmark') != 'tau2 retail' or trace.get('reward') is None:
        issues.append('missing official tau2 reward')
    if trace.get('controlled_fault_injection'):
        issues.append('controlled fault mixed with natural suite')
    messages = [m for m in trace.get('messages', []) if m.get('role') == 'tool']
    events = trace.get('events', [])
    if len(messages) != len(events):
        issues.append(f'tool message count {len(messages)} != event count {len(events)}')
    for index, (message, event) in enumerate(zip(messages, events)):
        if message.get('content') != event.get('response'):
            issues.append(f'event {index} response differs from tool message')
        if 'mutating' not in event or 'arguments' not in event or 'tool' not in event:
            issues.append(f'event {index} missing core fields')
        if event.get('mutating') and event.get('executed', True):
            risk = event.get('risk')
            if not isinstance(risk, dict) or not all(0 <= risk.get(k, -1) <= 1 for k in
                                                     ('impact', 'downstream', 'irreversibility', 'uncertainty', 'score')):
                issues.append(f'event {index} missing normalized risk')
            if bool(event.get('checkpoint')) != bool(event.get('verification')):
                issues.append(f'event {index} checkpoint/verdict mismatch')
    if audit(trace):
        issues.append('saved verifier verdict differs from replay audit')
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directories', nargs='+', type=Path)
    args = parser.parse_args()
    paths = [path for directory in args.directories
             for path in sorted(directory.glob('*_task*_seed*_*.json'))]
    if not paths:
        raise SystemExit('No natural benchmark traces found')
    errors = {str(path): problems for path in paths if (problems := validate(path))}
    print(f'validated_traces={len(paths)} errors={len(errors)}')
    for path, problems in errors.items():
        print(path, problems)
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
