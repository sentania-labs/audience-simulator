import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {MeetingAudio} from './audio';
import {SharedScreen} from './screen';
import './style.css';

type Event = {type:string;t_ms?:number;[key:string]:unknown};
type Config = {mode:string;missing:string[];providers:Record<string,string>;retention:string};
const defaultPersona = {name:'Morgan',role:'Enterprise infrastructure architect',expertise:'VCF, networking, virtualization and platform operations',style:'Technically precise, curious and candid',objective:''};
const stamp = (ms: unknown) => {const seconds=Math.floor(Number(ms||0)/1000);return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;};

function App() {
  const [config,setConfig]=useState<Config|null>(null);
  const [persona,setPersona]=useState(defaultPersona);
  const [consent,setConsent]=useState(false);
  const [status,setStatus]=useState('Ready to rehearse');
  const [joined,setJoined]=useState(false);
  const [connecting,setConnecting]=useState(false);
  const [ended,setEnded]=useState(false);
  const [muted,setMuted]=useState(false);
  const [outputMuted,setOutputMuted]=useState(false);
  const [speaking,setSpeaking]=useState(false);
  const [sharing,setSharing]=useState(false);
  const [events,setEvents]=useState<Event[]>([]);
  const [partial,setPartial]=useState('');
  const [tab,setTab]=useState('Transcript');
  const [testText,setTestText]=useState('Explain the current shared view.');
  const ws=useRef<WebSocket|null>(null);
  const audio=useRef<MeetingAudio|null>(null);
  const screen=useRef<SharedScreen|null>(null);
  const preview=useRef<HTMLVideoElement|null>(null);
  const base=useRef(0);
  const endedRef=useRef(false);
  const [spokenText,setSpokenText]=useState('');
  useEffect(()=>{fetch('/api/config').then(r=>r.json()).then(setConfig).catch(()=>setStatus('Backend unavailable. Start FastAPI.'));return()=>{ws.current?.close();void audio.current?.close();screen.current?.stop();};},[]);
  function send(value: Record<string,unknown>|ArrayBuffer) {
    if(ws.current?.readyState!==WebSocket.OPEN)return;
    if(ws.current.bufferedAmount>256000 && (value instanceof ArrayBuffer || value.type==='frame')){setStatus('Connection is falling behind. Audio/frame data dropped.');return;}
    ws.current.send(value instanceof ArrayBuffer?value:JSON.stringify(value));
  }
  function stopShare(notify=true) {
    screen.current?.stop();screen.current=null;setSharing(false);
    if(notify)send({type:'share',enabled:false});
  }
  async function join() {
    setConnecting(true);setEvents([]);setEnded(false);endedRef.current=false;base.current=0;
    setStatus('Connecting microphone and providers');
    try {
      audio.current=new MeetingAudio(send,setSpeaking);
      const sampleRate=await audio.current.open();
      audio.current.setMute(false);setMuted(false);setOutputMuted(false);
      const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/meeting`);
      ws.current=socket;
      socket.onopen=()=>send({type:'join',persona,consent,sample_rate:sampleRate});
      socket.onmessage=({data})=>{
        const e=JSON.parse(data) as Event;
        if(e.type==='audio'){audio.current?.play(String(e.pcm),Number(e.response_id));return;}
        if(e.type==='partial'){setPartial(String(e.text));return;}
        if(e.type==='speaking_text'){setSpokenText(String(e.text));return;}
        if(e.type==='cancel'){audio.current?.stop(Number(e.next_id));setSpokenText('');}
        if(e.type==='response_done')audio.current?.done(Number(e.response_id));
        if(e.type==='joined'){
          base.current=performance.now()-Number(e.t_ms);setJoined(true);setConnecting(false);setStatus('Meeting live');
        }
        if(e.type==='transcript')setPartial('');
        if(e.type==='error')setStatus(String(e.message));
        if(e.type==='summary'){endedRef.current=true;setEnded(true);setTab('Summary');setStatus('Session ended');}
        setEvents(previous=>[...previous,e].slice(-3000));
      };
      socket.onclose=()=>{
        setJoined(false);setConnecting(false);stopShare(false);void audio.current?.close();
        if(!endedRef.current){if(base.current)setEnded(true);setStatus('Connection closed. Download the retained review; summary may be unavailable.');}
      };
      socket.onerror=()=>setStatus('Meeting connection failed. Check backend configuration.');
    } catch(error) {
      setConnecting(false);setStatus(error instanceof Error?error.message:'Microphone unavailable');
      await audio.current?.close();
    }
  }
  async function share() {
    try {
      if(sharing)stopShare();
      const capture=new SharedScreen((jpeg,changed)=>send({type:'frame',jpeg,changed,captured_ms:Math.round(performance.now()-base.current)}),()=>stopShare());
      screen.current=capture;
      await capture.start();
      if(ws.current?.readyState!==WebSocket.OPEN){capture.stop();return;}
      send({type:'share',enabled:true});setSharing(true);
      if(preview.current){preview.current.srcObject=capture.stream;await preview.current.play();}
      capture.sample();
    }catch(error){stopShare(false);setStatus(error instanceof Error?error.message:'Screen capture unavailable');}
  }
  function interrupt() {audio.current?.stop();send({type:'interrupt'});send({type:'speech_end'});setSpokenText('');}
  async function end() {
    stopShare();audio.current?.stop();audio.current?.setMute(true);send({type:'end'});
    setStatus('Ending session');
  }
  function download() {
    const payload={persona,profile:config?.mode,events,retention:config?.retention};
    const link=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    link.href=url;link.download='audience-session.json';link.click();URL.revokeObjectURL(url);
  }
  const observations=events.filter(e=>e.type==='observation');
  const summary=events.findLast(e=>e.type==='summary');
  return <div className="app">
    <header><a className="brand" href="/">◉ <span>Audience<span className="soft"> / simulator</span></span></a><div className="headerStatus"><span className={`dot ${joined?'live':''}`}/>{status}</div></header>
    <main>
      {!joined&&!ended&&<section className="setup">
        <div><p className="eyebrow">A ROOM TO THINK OUT LOUD</p><h1>Your presentation.<br/>A curious audience.</h1><p className="intro">Practice with one participant who listens, questions, and follows what you share.</p>
          <div className="profile"><span className="avatar small">{persona.name[0]||'M'}</span><div><strong>{persona.name||'Your participant'}</strong><p>{persona.role}</p></div></div>
          <div className="notice"><strong>{config?.mode==='mock'?'Mock wiring mode':'Provider data flow'}</strong><p>{config?.mode==='mock'?'Test tones and fixed observations only. This mode does not recognize speech or understand screens.':`Microphone audio → ${config?.providers.stt||'STT'}; transcript and observations → ${config?.providers.dialogue||'dialogue'}; sampled images → ${config?.providers.vision||'vision'}; reply text → ${config?.providers.tts||'TTS'}.`}</p><p>{config?.retention} Provider-side retention follows your provider agreements.</p></div>
        </div>
        <form onSubmit={e=>{e.preventDefault();void join();}} className="config"><p className="eyebrow">MEET YOUR PARTICIPANT</p><h2>Set the conversation</h2>
          {Object.entries(persona).map(([key,value])=><label key={key}>{({name:'Name',role:'Role',expertise:'Expertise',style:'Conversational style',objective:'Meeting objective (optional)'} as Record<string,string>)[key]}<input value={value} maxLength={key==='name'?80: key==='objective'?1000:300} onChange={e=>setPersona({...persona,[key]:e.target.value})}/></label>)}
          <label className="check"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>I permit the configured providers to process audio, text, and explicitly shared screen samples.</span></label>
          {!!config?.missing.length&&<p className="error">Missing server configuration: {config.missing.join(', ')}</p>}
          <button className="primary" disabled={!config||!!config.missing.length||!consent||connecting}>{connecting?'Connecting…':'Join meeting →'}</button><p className="hint">Microphone permission required. Headphones recommended.</p>
        </form>
      </section>}
      {(joined||ended)&&<div className="meeting">
        <section className="stage"><div className="stageHeader"><span className="eyebrow">{ended?'SESSION REVIEW':'PRACTICE ROOM'}</span><span className="badge">1 AI participant</span></div>
          <div className={`shareArea ${sharing?'visible':''}`}><video ref={preview} muted autoPlay playsInline/><div className="shareLabel">● Your screen is being sampled</div></div>
          {!sharing&&<div className="participant"><span className={`avatar ${speaking?'speaking':''}`}>{persona.name[0]||'M'}</span><h2>{persona.name}</h2><p>{persona.role}</p><span className="badge">{ended?'Meeting ended':speaking?'Speaking':'Listening'}</span><p className="spoken">{speaking?spokenText:'Share a slide or demo to add visual context.'}</p></div>}
          {sharing&&<div className="profile"><span className="avatar small">{persona.name[0]}</span><div><strong>{persona.name}</strong><p>{speaking?'Speaking':'Listening'}</p></div></div>}
          <div className="controls"><button disabled={ended} className={muted?'active':''} onClick={()=>{const value=!muted;setMuted(value);audio.current?.setMute(value);send({type:'mute',enabled:value});}}>{muted?'Unmute mic':'Mute mic'}</button><button disabled={ended} onClick={()=>{const value=!outputMuted;setOutputMuted(value);audio.current?.setOutputMute(value);}}>{outputMuted?'Enable speaker':'Mute speaker'}</button><button disabled={ended} onClick={()=>void share()}>{sharing?'Switch share':'Share screen'}</button>{sharing&&<button onClick={()=>stopShare()}>Stop sharing</button>}<button disabled={ended} onClick={interrupt}>Interrupt</button><button className="danger" disabled={ended} onClick={()=>void end()}>End meeting</button></div>
          {config?.mode==='mock'&&!ended&&<form className="mockTurn" onSubmit={e=>{e.preventDefault();send({type:'mock_turn',text:testText});}}><label>Mock turn (no speech recognition)<input value={testText} onChange={e=>setTestText(e.target.value)}/></label><button>Send test turn</button></form>}
          <p className="hint">{config?.mode==='mock'?'MOCK: synthetic tones, fixed observations, no actual understanding.':'Screen capture starts only when you choose a surface. No camera or raw media storage.'}</p>
        </section>
        <aside className="review"><nav>{['Transcript','Observations','Metrics','Summary'].map(name=><button key={name} className={tab===name?'selected':''} onClick={()=>setTab(name)}>{name}</button>)}</nav>
          <div className="reviewBody" aria-live="polite">
            {tab==='Transcript'&&<>{events.filter(e=>e.type==='transcript').map((e,i)=><article key={i}><div className="entryHead"><strong>{String(e.speaker)}</strong><time>{stamp(e.t_ms)}</time></div><p>{String(e.text)}</p>{e.final===false&&<small>Interrupted; may be partly unheard</small>}</article>)}{partial&&<p className="partial">{partial}</p>}{!events.some(e=>e.type==='transcript')&&<p className="empty">Your conversation will appear here.</p>}</>}
            {tab==='Observations'&&<>{observations.map((e,i)=><article key={i}><div className="entryHead"><strong>Shared view {i+1}</strong><time>{stamp(e.captured_ms)}</time></div><p>{String(e.text)}</p><small>Observed at {stamp(e.observed_ms)}. Earlier views are historical evidence.</small></article>)}{!observations.length&&<p className="empty">Share a screen to add visible evidence.</p>}</>}
            {tab==='Metrics'&&<><p className="hint">Observed in this session. Mock timings measure wiring only. Playback timing is scheduled, not acoustically measured.</p>{events.filter(e=>e.type==='metric'||e.type==='browser_metric').map((e,i)=><article className="metric" key={i}><span>{String(e.stage).replaceAll('_',' ')}</span><strong>{Math.round(Number(e.value_ms))} ms</strong></article>)}</>}
            {tab==='Summary'&&(summary?<><h3>Session recap</h3><p className="hint">Extracted from recorded evidence; not coaching.</p><h4>Presenter topics</h4>{(summary.topics as string[]).map((s,i)=><p key={i}>{s}</p>)}<h4>Participant questions</h4>{(summary.questions as string[]).map((s,i)=><p key={i}>{s}</p>)}<h4>Visual moments</h4>{(summary.visual_moments as {text:string;captured_ms:number}[]).map((s,i)=><p key={i}>{stamp(s.captured_ms)} · {s.text}</p>)}<h4>Limitations</h4>{(summary.limitations as string[]).map((s,i)=><p key={i}>{s}</p>)}</>:<p className="empty">End the meeting to prepare your recap.</p>)}
          </div><footer><span>{events.length} timeline events</span><button onClick={download}>Download session</button></footer>
        </aside>
      </div>}
    </main><div className="bottom"><span>Audience Simulator · MVP feasibility candidate</span><span>One persona. Your voice. Shared context.</span></div>
  </div>;
}

createRoot(document.getElementById('root')!).render(<App/>);
