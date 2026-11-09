import argparse
import time
from pathlib import Path
from selective_verify.config import load_project_env

load_project_env()

from tau2.agent import LLMAgent
from tau2.orchestrator.orchestrator import Orchestrator
from tau2.runner import build_environment, build_user, get_tasks, run_simulation
from selective_verify.core import VerificationOrchestratorMixin, save_trace

class CheckedOrchestrator(VerificationOrchestratorMixin, Orchestrator):
    pass

def run(task_id, policy, model, seed, out, threshold=.55, random_rate=.5,
        fault_address_once=False, risk_weights=(.35, .25, .2, .2)):
    task = get_tasks('retail', task_ids=[task_id])[0]
    env = build_environment('retail')
    if fault_address_once:
        from selective_verify.faults import WrongAddressOnce
        env = WrongAddressOnce(env)
    agent = LLMAgent(tools=env.get_tools(), domain_policy=env.get_policy(), llm=model, llm_args={'temperature':0, 'timeout':60})
    user = build_user('user_simulator', env, task, llm=model, llm_args={'temperature':0, 'timeout':60})
    orchestrator = CheckedOrchestrator(domain='retail', agent=agent, user=user, environment=env, task=task, max_steps=40, timeout=180, seed=seed)
    orchestrator.configure_verification(policy, seed=seed, threshold=threshold,
                                        random_rate=random_rate, weights=risk_weights)
    start = time.perf_counter()
    try:
        result = run_simulation(orchestrator)
    except Exception as exc:
        save_trace(Path(out), {'benchmark':'tau2 retail', 'task_id':task_id,
            'seed':seed, 'policy':policy, 'model':model,
            'controlled_fault_injection':fault_address_once,
            'benchmark_commit':'033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f',
            'error':repr(exc), 'events':orchestrator.events})
        raise
    if policy == 'final-only':
        from tau2.data_model.message import ToolCall
        from selective_verify.core import verdict, visible_intent
        intent = visible_intent(result.messages)
        for event in orchestrator.events:
            if event['mutating']:
                call = ToolCall(name=event['tool'], arguments=event['arguments'])
                evidence = orchestrator._readback(call)
                status, reason = verdict(call.name, call.arguments, evidence, intent, event['error'])
                event['checkpoint'] = True
                event['verification'] = {'verdict':status, 'reason':reason, 'evidence':evidence, 'read_calls':int(evidence is not None), 'timing':'final-only'}
    messages = [m.model_dump(mode='json') for m in (result.messages or [])]
    usage = [m for m in messages if isinstance(m.get('usage'), dict)]
    prompt_tokens = sum(m['usage'].get('prompt_tokens', 0) for m in usage)
    completion_tokens = sum(m['usage'].get('completion_tokens', 0) for m in usage)
    token_count = prompt_tokens + completion_tokens
    reported_costs = [m.get('cost') for m in messages if m.get('cost') is not None]
    reported_cost = sum(reported_costs) if any(c > 0 for c in reported_costs) else None
    # Public list-price estimate, not the account's actual charge or cache-adjusted bill.
    estimated_cost = (prompt_tokens * .40 + completion_tokens * 1.60) / 1_000_000 if model == 'openrouter/openai/gpt-4.1-mini' else None
    elapsed_seconds = time.perf_counter()-start
    fault_final_street = (env.tools.db.orders[env.faulted_order_id].address.address1
                          if fault_address_once and env.triggered and env.faulted_order_id else None)
    data = {'benchmark_commit':'033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f',
            'random_seed_scheme':'task-specific-v1',
            'controlled_fault_injection':fault_address_once,
            'fault_triggered':bool(fault_address_once and env.triggered),
            'faulted_order_id':env.faulted_order_id if fault_address_once else None,
            'fault_intended_street':env.intended_street if fault_address_once else None,
            'fault_injected_street':env.injected_street if fault_address_once else None,
            'fault_final_street':fault_final_street,
            'fault_recovered':(fault_final_street == env.intended_street if fault_address_once and env.triggered else None),
            'fault_reward_interpretation':('Official tau2 evaluator replays recorded tool arguments, so its reward does not score the injected persisted-state fault.'
                                           if fault_address_once else None),
            'prompt_tokens':prompt_tokens, 'completion_tokens':completion_tokens,
            'total_model_tokens':token_count,
            'reported_model_cost_usd':reported_cost,
            'estimated_model_cost_usd':estimated_cost,
            'benchmark':'tau2 retail', 'task_id':task_id, 'seed':seed, 'policy':policy, 'model':model,
            'threshold':threshold, 'random_rate':random_rate,
            'risk_weights':risk_weights,
            'elapsed_seconds':elapsed_seconds,
            'termination_reason':result.termination_reason,
            'reward':result.reward_info.reward if result.reward_info else None,
            'evaluation_details':result.reward_info.model_dump(mode='json') if result.reward_info else None,
            'messages':messages, 'events':orchestrator.events,
            'user_objective':str(task.user_scenario.instructions)}
    save_trace(Path(out), data)
    return data

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--task-id', required=True); p.add_argument('--policy', choices=['none','exhaustive','risk','random','final-only'], default='none')
    p.add_argument('--model', default='openai/gpt-4.1-mini'); p.add_argument('--seed', type=int, default=42); p.add_argument('--threshold', type=float, default=.55); p.add_argument('--random-rate', type=float, default=.5); p.add_argument('--out', default='outputs/trace.json')
    p.add_argument('--risk-weights', nargs=4, type=float, default=(.35, .25, .2, .2),
                   metavar=('IMPACT','DOWNSTREAM','IRREVERSIBILITY','UNCERTAINTY'))
    a=p.parse_args(); d=run(a.task_id,a.policy,a.model,a.seed,a.out,a.threshold,a.random_rate,
                            risk_weights=tuple(a.risk_weights))
    print({'reward':d['reward'],'events':len(d['events']),'out':a.out})
