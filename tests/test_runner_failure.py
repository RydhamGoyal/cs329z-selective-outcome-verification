"""A model failure should leave an explicit failed trace, never a reward row."""
import json
from types import SimpleNamespace

import pytest


def test_model_timeout_records_failed_trace(tmp_path, monkeypatch):
    import selective_verify.run as runner

    task=SimpleNamespace(id='34')
    env=SimpleNamespace(get_tools=lambda: [], get_policy=lambda: 'policy')
    monkeypatch.setattr(runner, 'get_tasks', lambda *a, **k: [task])
    monkeypatch.setattr(runner, 'build_environment', lambda *a, **k: env)
    monkeypatch.setattr(runner, 'LLMAgent', lambda **k: object())
    monkeypatch.setattr(runner, 'build_user', lambda *a, **k: object())
    class FakeOrchestrator:
        def __init__(self, **kwargs):
            self.events=[]
        def configure_verification(self, *a, **k):
            pass
    monkeypatch.setattr(runner, 'CheckedOrchestrator', FakeOrchestrator)
    monkeypatch.setattr(runner, 'run_simulation', lambda *a: (_ for _ in ()).throw(TimeoutError('model timeout')))
    path=tmp_path/'failed.json'
    with pytest.raises(TimeoutError):
        runner.run('34','none','openrouter/openai/gpt-4.1-mini',42,path)
    data=json.loads(path.read_text())
    assert 'model timeout' in data['error']
    assert data.get('reward') is None
