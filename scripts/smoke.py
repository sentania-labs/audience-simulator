"""Exercise the running artifact, not only its health endpoint. Mock providers only."""
import asyncio
import os
import json
import httpx
import websockets

base = os.getenv('SMOKE_URL', 'http://127.0.0.1:8000')
origin = 'http://localhost:8000'


async def main():
    async with httpx.AsyncClient(base_url=base) as client:
        assert (await client.get('/')).status_code == 200
        assert (await client.get('/api/config')).status_code == 401
        assert (await client.get('/api/admin')).status_code == 401
        assert (await client.post('/api/auth/meeting/login',headers={'origin':origin},
                                 json={'password':os.environ['MEETING_PASSWORD']})).status_code == 200
        cfg=(await client.get('/api/config')).json()
        assert cfg['mode']=='mock'
        assert (await client.get('/api/admin')).status_code==401
        cookie='; '.join(f'{k}={v}' for k,v in client.cookies.items())
        async with websockets.connect(base.replace('http','ws',1)+'/api/meeting',origin=origin,
                                      additional_headers={'Cookie':cookie}) as ws:
            await ws.send(json.dumps(dict(type='join',sample_rate=48000,consent=True,
                                         attendees=[{'name':'Morgan'},{'name':'Riley'}])))
            first=json.loads(await ws.recv())
            assert first['type']=='joined' and len(first['attendees'])==2
            await ws.send(json.dumps(dict(type='mock_turn',text='Riley, explain the demo.')))
            events=[]
            async with asyncio.timeout(15):
                while not any(e['type']=='transcript' and e.get('speaker')=='Riley' for e in events):
                    events.append(json.loads(await ws.recv()))
                assert any(e['type']=='audio' for e in events)
                await ws.send(json.dumps(dict(type='end')))
                while not any(e['type']=='summary' for e in events):
                    events.append(json.loads(await ws.recv()))
        assert (await client.post('/api/auth/admin/login',headers={'origin':origin},
                                 json={'password':os.environ['ADMIN_PASSWORD']})).status_code == 200
        assert (await client.get('/api/admin/feedback')).json()['reviews'] == []
        sid, token = first['session_id'], first['review_token']
        feedback = dict(token=token,rating=3,comment='Synthetic artifact smoke')
        assert (await client.post('/api/feedback/'+sid,headers={'origin':origin},json=feedback)).status_code == 200
        assert (await client.get('/api/admin/feedback')).json()['reviews'][0]['transcript'] is None
        assert (await client.get('/metrics')).status_code == 401
        metrics=await client.get('/metrics',headers={'Authorization':'Bearer '+os.environ['METRICS_TOKEN']})
        assert metrics.status_code == 200 and 'audience_latency_seconds_count' in metrics.text
        runtime=(await client.get('/api/admin/runtime')).json()
        for stage in ('dialogue','vision','tts','stt'):
            runtime['config'][stage]['model']='mock-model'
        changed=await client.post('/api/admin/runtime',headers={'origin':origin},json={'expected_revision':0,'config':runtime['config']})
        assert changed.status_code == 200 and changed.json()['revision'] == 1
        stats=(await client.get('/api/admin')).json()
        assert stats['meetings'] and stats['meetings'][0]['attendees']==2
        assert (await client.post('/api/admin/admission',headers={'origin':origin},json={'paused':True})).status_code==200
        assert (await client.get('/api/admin')).json()['paused']
        await client.post('/api/admin/admission',headers={'origin':origin},json={'paused':False})
    print('Artifact smoke passed: auth separation, two attendees, audio, recap, durable stats, opt-in feedback, runtime revision, metrics and admission.')

asyncio.run(main())
