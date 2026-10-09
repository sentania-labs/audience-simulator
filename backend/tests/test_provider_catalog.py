import json
import httpx
import pytest
from cryptography.fernet import Fernet
from test_api import client
from test_management import admin, ORIGIN, valid_config
from app import provider_catalog as catalog, runtime
from app.main import control
from app.management import provider_store
from app.providers import Endpoint, generation_limits, AnthropicDialogue, AnthropicVision
from app.diagnostics import provider_message


def test_provider_store_encrypts_keys_preserves_history_and_enforces_models(client, monkeypatch):
    admin(client)
    monkeypatch.setenv('PROVIDER_ENCRYPTION_KEY', Fernet.generate_key().decode())
    async def discover(*args):
        return [{'id':'gpt-6-luna','stages':['dialogue','vision']}], 'Verified'
    monkeypatch.setattr(catalog, 'discover', discover)
    body = dict(name='OpenAI practice',kind='openai',key='private-provider-secret')
    assert client.post('/api/admin/providers',json=body).status_code == 403
    r=client.post('/api/admin/providers',json=body,headers=ORIGIN)
    assert r.status_code == 200
    pid=r.json()['id']
    assert 'private-provider-secret' not in client.get('/api/admin/providers').text
    assert b'private-provider-secret' not in open(control().path,'rb').read()
    value=valid_config();value['dialogue']={'connection':pid,'model':'gpt-6-luna'}
    assert runtime.resolve(value).dialogue.key == body['key']
    original=runtime.resolve(value)
    new=provider_store().save('Replacement','openai',catalog.BASES['openai'],'replacement-key',[{'id':'gpt-6-luna','stages':['dialogue']}])
    assert original.dialogue.key == body['key'] and new != pid
    value['dialogue']['model']='not-advertised'
    assert client.post('/api/admin/runtime',json={'expected_revision':0,'config':value},headers=ORIGIN).status_code==422
    monkeypatch.setenv('PROVIDER_ENCRYPTION_KEY',Fernet.generate_key().decode())
    with pytest.raises(ValueError,match='cannot be unlocked'):
        provider_store().connection(pid)
    # Admin remains reachable for recovery without decrypting every stored key.
    assert client.get('/api/admin/providers').status_code==200


def test_provider_validation_does_not_echo_keys_or_store_failures(client,monkeypatch):
    admin(client)
    body=dict(name='Test',kind='openai',key='do-not-echo-this',extra='not-allowed')
    r=client.post('/api/admin/providers',json=body,headers=ORIGIN)
    assert r.status_code==422 and body['key'] not in r.text
    monkeypatch.setenv('PROVIDER_ENCRYPTION_KEY',Fernet.generate_key().decode())
    async def fail(*args): raise ValueError('upstream echoes do-not-echo-this')
    monkeypatch.setattr(catalog,'discover',fail)
    del body['extra']
    r=client.post('/api/admin/providers',json=body,headers=ORIGIN)
    assert r.status_code==422 and body['key'] not in r.text
    assert provider_store().rows()==[]
    for url in ['https://user:secret@example.org/v1','http://169.254.169.254','http://metadata.google.internal','file:///etc/passwd','https://example.org/v1?key=secret']:
        with pytest.raises(ValueError): catalog.validate('compatible',url,'key')
    assert catalog.validate('compatible','http://192.168.1.2:8000/v1/','key').endswith('/v1')


@pytest.mark.asyncio
async def test_anthropic_discovery_pagination_and_auth(monkeypatch):
    requests=[]
    def respond(request):
        requests.append(request)
        assert request.headers['x-api-key']=='test-key'
        assert request.headers['anthropic-version']=='2023-06-01'
        assert 'authorization' not in request.headers
        second='after_id' in request.url.params
        return httpx.Response(200,json={'data':[{'id':'claude-second' if second else 'claude-first'}],'has_more':not second,'last_id':'claude-first'})
    original=httpx.AsyncClient
    monkeypatch.setattr(catalog.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    models,_=await catalog.discover('anthropic',catalog.BASES['anthropic'],'test-key')
    assert len(models)==2 and len(requests)==2
    assert requests[1].url.params['after_id']=='claude-first'


@pytest.mark.asyncio
async def test_anthropic_adapters_stream_text_and_convert_images(monkeypatch):
    bodies=[]
    def respond(request):
        body=json.loads(request.content);bodies.append(body)
        assert request.url.path=='/v1/messages'
        assert request.headers['x-api-key']=='test-key'
        assert all('name' not in m for m in body['messages'])
        if body.get('stream'):
            return httpx.Response(200,text='data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello."}}\n\n')
        return httpx.Response(200,json={'content':[{'type':'text','text':'A diagram.'}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    ep=Endpoint(catalog.BASES['anthropic'],'claude-test','test-key','anthropic')
    assert ''.join([s async for s in AnthropicDialogue(ep).stream([{'role':'system','content':'Be brief.'},{'role':'user','content':'Hi','name':'Scott'}])])=='Hello.'
    assert await AnthropicVision(ep).observe('abc')=='A diagram.'
    assert bodies[1]['messages'][0]['content'][1]['source']['data']=='abc'


def test_luna_request_and_error_explain_rejection_instead_of_timeout():
    ep=Endpoint(catalog.BASES['openai'],'gpt-6-luna','key')
    assert generation_limits(ep,300)=={'max_completion_tokens':300,'reasoning_effort':'none'}
    assert generation_limits(Endpoint('https://local.invalid/v1','custom','key'),300)=={'max_tokens':300}
    error=httpx.HTTPStatusError('secret',request=httpx.Request('POST','https://example.org'),response=httpx.Response(400))
    assert 'rejected' in provider_message(error) and 'timeout' not in provider_message(error)
    assert 'secret' not in provider_message(error)


def test_catalog_filters_and_model_specific_voices():
    assert catalog.model_stages('gemini','gemini-2.5-flash')==['dialogue','vision']
    assert catalog.model_stages('gemini','gemini-2.5-flash-preview-tts')==[]
    assert catalog.model_stages('openai','gpt-4o-transcribe')==[]
    assert 'coral' in catalog.voices('openai','gpt-4o-mini-tts')
    assert 'marin' not in catalog.voices('openai','tts-1')
    assert catalog.voices('compatible','local-tts')==[]


def test_catalog_refresh_does_not_break_an_activated_configuration(client,monkeypatch):
    admin(client)
    monkeypatch.setenv('PROVIDER_ENCRYPTION_KEY',Fernet.generate_key().decode())
    ps=provider_store()
    pid=ps.save('Original','openai',catalog.BASES['openai'],'test-key',[{'id':'gpt-6-luna','stages':['dialogue','vision']}])
    value=valid_config();value['dialogue']={'connection':pid,'model':'gpt-6-luna'}
    assert client.post('/api/admin/runtime',json={'expected_revision':0,'config':value},headers=ORIGIN).status_code==200
    before=client.get('/api/config').json()
    ps.refresh(pid,ps.connection(pid),[{'id':'gpt-4o-mini-tts','stages':['tts']}])
    after=client.get('/api/config')
    assert after.status_code==200
    assert after.json()['consent_revision']==before['consent_revision']
    assert after.json()['revision']==1
    assert client.post('/api/admin/runtime',json={'expected_revision':1,'config':value},headers=ORIGIN).status_code==422


def test_chart_upgrade_retains_legacy_seed_models():
    from pathlib import Path
    import yaml
    from app.config import Settings
    chart=yaml.safe_load(Path('charts/audience-simulator/values.yaml').read_text())
    assert chart['config']['DIALOGUE_MODEL']=='gpt-4.1-mini'
    assert chart['config']['VISION_MODEL']=='gpt-4.1-mini'
    assert chart['config']['TTS_MODEL']=='gpt-4o-mini-tts'
    assert chart['config']['TTS_VOICES']=='coral,ash,sage,echo'
