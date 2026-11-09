"""One controlled model-backed fault trial, excluded from natural comparison."""
from pathlib import Path
import json

from selective_verify.run import run


def main():
    for policy in ('risk', 'none'):
        suffix = 'replay_safe' if policy == 'risk' else 'fault'
        out = Path(f'outputs/controlled_task41_{policy}_{suffix}.json')
        if out.exists():
            trace = json.loads(out.read_text())
            if trace.get('error') or trace.get('reward') is None:
                raise SystemExit(f'Existing fault trace is incomplete: {out}')
        else:
            trace = run('41', policy, 'openrouter/openai/gpt-4.1-mini', 42, out,
                        fault_address_once=True)
        verdicts = [e['verification']['verdict'] for e in trace['events'] if e.get('verification')]
        print({'trace': str(out), 'fault_triggered': trace['fault_triggered'],
               'verdicts': verdicts, 'replay_reward_not_fault_sensitive': trace['reward'],
               'persisted_state_recovered': trace.get('fault_recovered'),
               'estimated_model_cost_usd': trace['estimated_model_cost_usd']}, flush=True)
        if not trace['fault_triggered']:
            raise SystemExit(f'No address write occurred for {policy}; fault was not triggered')


if __name__ == '__main__':
    main()
