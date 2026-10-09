import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {transformSync} from 'esbuild';
const code=transformSync(readFileSync(new URL('../src/audio.ts',import.meta.url),'utf8'),{loader:'ts',format:'esm'}).code;
const {MeetingAudio}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
class FakeNode {
  gain={value:1}; stopped=false; onended=null;
  connect(target){return target;} disconnect(){} stop(){this.stopped=true;} start(time){this.startedAt=time;}
}
class FakeContext {
  state='running'; currentTime=1; sampleRate=48000; destination={}; audioWorklet={addModule:async()=>{}};
  resume=async()=>{}; close=async()=>{};
  createGain(){return new FakeNode();} createMediaStreamSource(){return new FakeNode();}
  createBufferSource(){return new FakeNode();}
  createBuffer(channels,size,rate){return {duration:size/rate,getChannelData:()=>new Float32Array(size)};}
}
const pcm=Buffer.from([1,0,2,0]).toString('base64');

test('interrupt stops queued sources and rejects late chunks from cancelled response',()=>{
  const events=[];const states=[];const audio=new MeetingAudio(e=>events.push(e),s=>states.push(s));
  audio.ctx=new FakeContext();audio.gain=new FakeNode();
  audio.play(pcm,4);const source=[...audio.sources][0];
  assert.equal(audio.sources.size,1);
  audio.stop(5);
  assert.equal(source.stopped,true);assert.equal(audio.sources.size,0);
  audio.play(pcm,4);assert.equal(audio.sources.size,0);
  audio.play(pcm,5);assert.equal(audio.sources.size,1);
  assert(events.some(e=>e.type==='playback_stopped'&&e.response_id===4));
  assert(states.includes(false));
});

test('microphone mute disables track and prevents audio transmission; sustained energy reports activity without cancelling playback',async()=>{
  const events=[];const track={enabled:true,stop(){}};
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:async()=>({getAudioTracks:()=>[track],getTracks:()=>[track]})}}});
  globalThis.AudioContext=FakeContext;
  globalThis.AudioWorkletNode=class extends FakeNode {port={onmessage:null};};
  let now=100;
  const originalPerformance=globalThis.performance;
  Object.defineProperty(globalThis,'performance',{configurable:true,value:{now:()=>now}});
  try {
    const audio=new MeetingAudio(e=>events.push(e),()=>{});
    assert.equal(await audio.open(),48000);
    const message={data:{pcm:new ArrayBuffer(4),rms:.06}};
    audio.setMute(true);audio.node.port.onmessage(message);
    assert.equal(track.enabled,false);assert.equal(events.length,0);
    audio.setMute(false);audio.node.port.onmessage(message);now=250;audio.node.port.onmessage(message);
    assert.equal(track.enabled,true);assert(events.some(e=>e.type==='speech_activity'));
    assert(!events.some(e=>e.type==='interrupt'));
    now=900;audio.node.port.onmessage({data:{pcm:new ArrayBuffer(4),rms:0}});
    assert(events.some(e=>e.type==='speech_end'));
    audio.setOutputMute(true);assert.equal(audio.gain.gain.value,0);
    assert(events.some(e=>e.type==='audio_state' && e.output_muted===true && e.gain===0 && e.context_state==='running'));
    await audio.close();
  } finally {Object.defineProperty(globalThis,'performance',{configurable:true,value:originalPerformance});}
});

test('completion after PCM drains emits exactly one playback ended receipt',()=>{
  const events=[];const audio=new MeetingAudio(e=>events.push(e),()=>{});
  audio.ctx=new FakeContext();audio.gain=new FakeNode();
  audio.play(pcm,9);
  [...audio.sources][0].onended();
  assert.equal(audio.sources.size,0);
  assert.equal(events.filter(e=>e.type==='playback_ended').length,0);
  audio.done(9);audio.done(9);
  assert.equal(events.filter(e=>e.type==='playback_ended'&&e.response_id===9).length,1);
  assert.equal(audio.active,-1);
});

test('concurrent teardown closes the audio context once and releases the microphone',async()=>{
  const audio=new MeetingAudio(()=>{},()=>{});
  let closes=0,stops=0;
  audio.ctx=new FakeContext();
  audio.ctx.close=async()=>{closes++;if(closes>1)throw new Error('Already closing');await Promise.resolve();};
  audio.stream={getTracks:()=>[{stop(){stops++;}}]};
  await Promise.all([audio.close(),audio.close()]);
  assert.equal(closes,1);
  assert.equal(stops,1);
  assert.equal(audio.ctx,null);
  assert.equal(audio.stream,null);
});
