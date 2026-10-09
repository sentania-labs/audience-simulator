import asyncio
import base64
import pytest

from app.providers import MockRecognition, MockDialogue, MockVision, MockSpeech
from app.session import Session


@pytest.fixture
def session():
    events = []
    async def send(event):
        events.append(event)
    s = Session(send, MockRecognition(), MockDialogue(), MockVision(), MockSpeech(), {'name': 'Morgan'}, True)
    return s, events


@pytest.mark.asyncio
async def test_spoken_pipeline_and_summary(session):
    s, events = session
    await s.user_turn('How does this architecture recover?')
    await s.reply_task
    assert any(e['type'] == 'audio' and base64.b64decode(e['pcm']) for e in events)
    assert any(e.get('stage') == 'tts_first_audio' for e in events)
    assert any(e.get('stage') == 'dialogue_first_token' for e in events)
    await s.end()
    summary = next(e for e in events if e['type'] == 'summary')
    assert summary['topics'] == ['How does this architecture recover?']
    assert [e['t_ms'] for e in s.events] == sorted(e['t_ms'] for e in s.events)


@pytest.mark.asyncio
async def test_cancellation_prevents_late_audio(session):
    s, events = session
    started = asyncio.Event()
    class SlowSpeech:
        async def stream(self, text):
            started.set()
            await asyncio.sleep(1)
            yield b'\x01\x00'
    s.tts = SlowSpeech()
    await s.user_turn('Begin')
    await started.wait()
    await s.interrupt()
    boundary = len(events)
    await asyncio.sleep(.05)
    assert not any(e['type'] == 'audio' for e in events[boundary:])
    assert any(e['type'] == 'transcript' and not e['final'] for e in events)


@pytest.mark.asyncio
async def test_changed_view_and_earlier_context_are_untrusted(session):
    s, events = session
    class EvidenceVision:
        async def observe(self, image):
            return {'slide': 'VCF architecture diagram: management domain connects to workload domain.',
                    'demo': 'VCF Automation: request status Pending approval.'}[image]
    s.vision = EvidenceVision()
    s.speech_active = True  # Presenter speaking, no automatic response.
    await s.share(True)
    await s.frame('slide', 0)
    await s.vision_task
    await s.frame('demo', 1)
    await s.vision_task
    assert len(s.observations) == 2
    assert 'Pending approval' in s.current['text']
    messages = s.messages('Refer back to the slide.')
    assert 'management domain' in messages[-1]['content']
    assert 'Pending approval' in messages[-1]['content']
    assert messages[-1]['role'] == 'user'
    assert 'management domain' not in messages[0]['content']
    await s.share(False)
    assert s.current is None
    assert len(s.observations) == 2


@pytest.mark.asyncio
async def test_latest_frame_queue_and_share_stop(session):
    s, events = session
    entered = asyncio.Event()
    release = asyncio.Event()
    seen = []
    class SlowVision:
        async def observe(self, frame):
            entered.set()
            await release.wait()
            seen.append(frame)
            return frame
    s.vision = SlowVision()
    s.speech_active = True
    await s.share(True)
    await s.frame('one', 0)
    await entered.wait()
    await s.frame('two', 1)
    await s.frame('three', 2)
    release.set()
    await s.vision_task
    assert seen == ['one', 'three']
    assert any(e['type'] == 'frame_dropped' for e in events)
    release.clear()
    await s.frame('four', 3)
    await asyncio.sleep(.01)
    await s.share(False)
    release.set()
    assert s.current is None
    assert not any(e.get('text') == 'four' for e in events)


@pytest.mark.asyncio
async def test_provider_failure_preserves_conversation(session):
    s, events = session
    class Broken:
        async def stream(self, messages):
            raise RuntimeError('secret provider payload')
            yield ''
    s.dialogue = Broken()
    await s.user_turn('hello')
    await s.reply_task
    assert any(e['type'] == 'error' for e in events)
    assert 'secret provider payload' not in str(events)
    assert s.history[0]['content'] == 'hello'


@pytest.mark.asyncio
async def test_failed_new_view_clears_current(session):
    s, events = session
    s.speech_active = True
    await s.share(True)
    await s.frame('slide', 0)
    await s.vision_task
    assert s.current is not None
    class FailedVision:
        async def observe(self, frame):
            raise RuntimeError('private body')
    s.vision = FailedVision()
    await s.frame('demo', 1)
    await s.vision_task
    assert s.current is None
    assert len(s.observations) == 1
    assert 'private body' not in str(events)


@pytest.mark.asyncio
async def test_refresh_does_not_evict_early_slide_or_ask(session):
    s, events = session
    class EchoVision:
        async def observe(self, frame):
            return frame
    s.vision = EchoVision()
    s.speech_active = True
    await s.share(True)
    await s.frame('original slide', 0)
    await s.vision_task
    await s.frame('demo', 1)
    await s.vision_task
    s.speech_active = False
    for i in range(65):
        await s.frame('demo refresh', 2 + i, changed=False)
        await s.vision_task
    assert len(s.observations) == 2
    assert 'original slide' in s.messages('Recall the slide')[-1]['content']
    assert not any(e['type'] == 'response_start' for e in events)
    s.speech_active = True
    for i in range(45):
        await s.frame('distinct screen ' + str(i), 100 + i)
        await s.vision_task
    assert len(s.observations) == 40
    assert s.observations[0]['text'] == 'original slide'


@pytest.mark.asyncio
async def test_visual_reply_cannot_race_user_turn(session):
    s, events = session
    cancelled = asyncio.Event()
    release = asyncio.Event()
    original_send = s.send
    async def pausing_send(event):
        if event['type'] == 'cancel' and event.get('source') == 'new_turn':
            cancelled.set()
            await release.wait()
        await original_send(event)
    s.send = pausing_send
    await s.share(True)
    turn = asyncio.create_task(s.user_turn('Presenter turn'))
    await cancelled.wait()
    await s.frame('frame', 0)
    await asyncio.sleep(.04)  # Vision completes while user turn owns cancellation.
    release.set()
    await turn
    await s.vision_task
    await s.reply_task
    starts = [e for e in events if e['type'] == 'response_start']
    assert len(starts) == 1
    assert len([e for e in events if e['type'] == 'transcript' and e['speaker'] == 'Morgan']) == 1

@pytest.mark.asyncio
async def test_noise_and_acknowledgment_do_not_cancel_reply(session):
    s, events = session
    await s.user_turn('Begin')
    rid = s.generation
    await s.recognition({'type': 'speech_started'})
    await s.recognition({'type': 'partial', 'text': 'Mm-hmm'})
    await s.recognition({'type': 'final', 'text': 'Mm-hmm'})
    assert s.generation == rid
    await s.reply_task


@pytest.mark.asyncio
async def test_confirmed_interruption_cancels_once(session):
    s, events = session
    await s.user_turn('Begin')
    rid = s.generation
    await s.recognition({'type': 'speech_started'})
    await s.recognition({'type': 'partial', 'text': 'Stop, let me clarify'})
    assert s.generation == rid + 1
    await s.recognition({'type': 'partial', 'text': 'Stop, let me clarify this'})
    assert s.generation == rid + 1
    await s.end()


@pytest.mark.asyncio
async def test_final_fragments_merge_before_reply(session):
    s, events = session
    s.turn_delay = .03
    await s.recognition({'type': 'final', 'text': 'Now here is information about'})
    await s.recognition({'type': 'partial', 'text': 'Deepgram'})
    await asyncio.sleep(.05)
    assert not any(e['type'] == 'response_start' for e in events)
    await s.recognition({'type': 'final', 'text': 'Deepgram.'})
    await asyncio.sleep(.06)
    assert s.history[0]['content'] == 'Now here is information about Deepgram.'
    await s.reply_task
    await s.end()


@pytest.mark.asyncio
async def test_old_vision_completion_cannot_restore_stale_current(session):
    s, events = session
    first = asyncio.Event()
    release_first = asyncio.Event()
    second = asyncio.Event()
    release_second = asyncio.Event()
    class SlowVision:
        async def observe(self, frame):
            if frame == 'old':
                first.set()
                await release_first.wait()
            else:
                second.set()
                await release_second.wait()
            return frame
    s.vision = SlowVision()
    s.speech_active = True
    await s.share(True)
    await s.frame('old', 1)
    await first.wait()
    await s.frame('new', 2)
    release_first.set()
    await second.wait()
    assert s.current is None
    release_second.set()
    await s.vision_task
    assert s.current['text'] == 'new'
    await s.end()

@pytest.mark.asyncio
async def test_observer_failure_never_changes_response(session):
    s, events = session
    class FailedJudge:
        async def evaluate(self, state):
            raise RuntimeError('private provider body')
    s.judge = FailedJudge()
    await s.user_turn('Hello')
    rid = s.generation
    s.shadow('interruption', 'Stop')
    await s.judge_task
    await s.reply_task
    if s.judge_task:
        await s.judge_task
    assert s.generation == rid
    assert any(e['type'] == 'audio' for e in events)
    assert any(e['type'] == 'judge_observation' and e['outcome'] == 'unavailable' for e in events)
    assert 'private provider body' not in str(events)
    await s.end()


@pytest.mark.asyncio
async def test_response_waits_for_pending_visual_evidence(session):
    s, events = session
    entered = asyncio.Event()
    release = asyncio.Event()
    class SlowVision:
        async def observe(self, frame):
            entered.set()
            await release.wait()
            return 'New screen: Blue project, seven servers'
    prompts = []
    class Dialogue:
        async def stream(self, messages):
            prompts.append(messages)
            yield 'Seven servers.'
    s.vision, s.dialogue = SlowVision(), Dialogue()
    await s.share(True)
    await s.frame('new', 1)
    await entered.wait()
    await s.user_turn('What is on the screen?')
    await asyncio.sleep(.02)
    assert not prompts
    release.set()
    await s.vision_task
    await s.reply_task
    assert 'seven servers' in prompts[0][-1]['content']
    await s.end()
