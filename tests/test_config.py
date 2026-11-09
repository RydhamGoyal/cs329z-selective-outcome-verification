from selective_verify.config import load_project_env

def test_explicit_project_env_path(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    path=tmp_path/'.env';path.write_text('OPENROUTER_API_KEY=test-only-placeholder\n')
    assert load_project_env(path)
    import os
    assert os.environ['OPENROUTER_API_KEY']=='test-only-placeholder'
