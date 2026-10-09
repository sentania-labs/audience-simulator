"""The registry preflight must distinguish absent tags from outages."""
import runpy
import sys
import httpx
import pytest


@pytest.mark.parametrize('status,expected', [(200,'true'),(404,'false'),(401,None),(429,None),(503,None)])
def test_registry_existence_fail_closed(monkeypatch, capsys, status, expected):
    monkeypatch.setenv('GITHUB_ACTOR','test-actor')
    monkeypatch.setenv('GH_TOKEN','test-token')
    monkeypatch.setattr(sys,'argv',['registry-exists.py','example/audience','v0.1.0'])
    def handler(request):
        if request.url.path=='/token':
            return httpx.Response(200,json={'token':'test-registry-token'})
        return httpx.Response(status)
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    if expected is None:
        with pytest.raises(httpx.HTTPStatusError):
            runpy.run_path('scripts/registry-exists.py',run_name='__main__')
        assert capsys.readouterr().out==''
    else:
        runpy.run_path('scripts/registry-exists.py',run_name='__main__')
        assert capsys.readouterr().out.strip()==expected
