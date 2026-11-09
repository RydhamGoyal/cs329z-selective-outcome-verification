"""Offline checks for result aggregation and frozen held-out calibration."""
import json

import pytest

from scripts.experiment import SUITES
from scripts.run_heldout_suite import development_rate, MODEL
from scripts.summarize_comparison import summarize_directory
from scripts.validate_traces import validate


def test_heldout_random_rate_is_frozen_from_development_only(tmp_path):
    for index, task in enumerate(SUITES['dev']):
        checked = index < 2
        trace = {
            'benchmark': 'tau2 retail', 'task_id': task, 'seed': 42,
            'policy': 'risk', 'model': MODEL, 'threshold': .55, 'reward': 1.0,
            'elapsed_seconds': 1.0, 'total_model_tokens': 100,
            'estimated_model_cost_usd': .01,
            'messages': [{'role': 'user', 'content': 'hello'}, {'role': 'tool', 'content': '{}'}],
            'events': [{
                'tool': 'modify_pending_order_items', 'arguments': {}, 'error': False,
                'mutating': True, 'checkpoint': checked,
                'verification': {'verdict': 'INCONCLUSIVE', 'evidence': None, 'read_calls': 0} if checked else None,
            }],
        }
        (tmp_path / f'dev_task{task}_seed42_risk.json').write_text(json.dumps(trace))
    assert development_rate(tmp_path, 42) == pytest.approx(2/5)


def test_heldout_refuses_missing_development_trace(tmp_path):
    with pytest.raises(ValueError, match='Missing development risk trace'):
        development_rate(tmp_path, 42)


def test_summary_excludes_fault_and_failed_runs(tmp_path):
    complete = {'benchmark': 'tau2 retail', 'task_id': '34', 'seed': 42,
                'policy': 'none', 'reward': 1.0, 'events': [],
                'elapsed_seconds': 2.0, 'total_model_tokens': 10,
                'estimated_model_cost_usd': .01}
    (tmp_path / 'dev_task34_seed42_none.json').write_text(json.dumps(complete))
    (tmp_path / 'dev_task34_seed42_risk.json').write_text(json.dumps({**complete, 'reward': None, 'policy': 'risk'}))
    (tmp_path / 'dev_task34_seed42_random.json').write_text(json.dumps({**complete, 'benchmark': 'fault', 'policy': 'random'}))
    rows, aggregate = summarize_directory(tmp_path)
    assert len(rows) == len(aggregate) == 1
    assert aggregate[0]['official_successes'] == 1


def test_trace_validator_detects_missing_tool_observation(tmp_path):
    trace={'benchmark':'tau2 retail','reward':1.0,'messages':[
        {'role':'user','content':'hello'}, {'role':'tool','content':'{}'}], 'events':[]}
    path=tmp_path/'dev_task34_seed42_none.json'
    path.write_text(json.dumps(trace))
    assert any('count' in issue for issue in validate(path))
