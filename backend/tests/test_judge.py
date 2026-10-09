import httpx
import pytest
from app.judge import JevObserver


@pytest.mark.asyncio
async def test_judge_contract_and_invalid_output(monkeypatch):
    original = httpx.AsyncClient
    requests = []
    def handler(request):
        import json
        body = json.loads(request.content)
        requests.append(body)
        assert request.headers['Authorization'] == 'Bearer test-only'
        return httpx.Response(200, json={'answers': {'decision': {
            'choice': 'uncertain' if len(requests) == 1 else 'invalid', 'confidence': .8}}})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    judge = JevObserver('test-only')
    state = {'kind': 'interruption', 'presenter': '', 'persona_reply': 'Hello'}
    assert await judge.evaluate(state) == {'decision': 'uncertain', 'confidence': .8}
    assert requests[0]['model'] == 'jev-1.13.0'
    with pytest.raises(ValueError):
        await judge.evaluate(state)
