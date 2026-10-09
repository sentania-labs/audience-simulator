import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {MeetingAudio} from './audio';
import {SharedScreen} from './screen';
import './style.css';
import {MeetingFeedback} from './feedback';
import {Access, Admin, api} from './access';

type Event = {type:string;t_ms?:number;[key:string]:unknown};
type Config = {consent_revision:string;revision:number;mode:string;missing:string[];providers:Record<string,string>;retention:string;limits:{max_attendees:number;meeting_usd:number;daily_usd:number;max_minutes:number}};
type CastPerson={id:string;name:string;role:string;expertise:string;style:string;objective:string;history:string};
type Scenario={id:string;name:string;background:string;fiction_notice:string;source:string;cast:CastPerson[]};
const defaultPersona = {cast_id:'',name:'Morgan',role:'Enterprise infrastructure architect',expertise:'Networking, recovery, virtualization and platform operations',style:'Technically precise, curious and candid',objective:''};
const stamp = (ms: unknown) => {const seconds=Math.floor(Number(ms||0)/1000);return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;};

function App() {
  const [scenarios,setScenarios]=useState<Scenario[]>([]),[scenarioId,setScenarioId]=useState('');
  const [reviewAccess,setReviewAccess]=useState({sid:'',token:''});
  const scenario=scenarios.find(s=>s.id===scenarioId);
  const [config,setConfig]=useState<Config|null>(null);
  const [attendees,setAttendees]=useState([defaultPersona]);
  const [selected,setSelected]=useState(0);
  const persona=attendees[selected];
  function setPersona(p:typeof defaultPersona){setAttendees(a=>a.map((v,i)=>i===selected?p:v));}
  const [background,setBackground]=useState('');
  const [login,setLogin]=useState(false);
  const [speaker,setSpeaker]=useState('Morgan');
  const [usage,setUsage]=useState({meeting_usd:0,daily_usd:0,warning:false});
  const initialized=useRef(false);
  function loadConfig(){return api('/api/config').then(c=>{setConfig(c);setLogin(false);void api('/api/scenarios').then((list:Scenario[])=>{setScenarios(list);if(!initialized.current&&list.length){initialized.current=true;const first=list[0],p=first.cast[Math.floor(Math.random()*first.cast.length)];setScenarioId(first.id);setAttendees([{cast_id:p.id,name:p.name,role:p.role,expertise:p.expertise,style:p.style,objective:p.objective}]);}});}).catch(()=>setLogin(true));}
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
  const [previousReview,setPreviousReview]=useState<ReturnType<typeof review>|null>(null);
  const [partial,setPartial]=useState('');
  const [tab,setTab]=useState('Transcript');
  const [testText,setTestText]=useState('Explain the current shared view.');
  const ws=useRef<WebSocket|null>(null);
  const audio=useRef<MeetingAudio|null>(null);
  const screen=useRef<SharedScreen|null>(null);
  const preview=useRef<HTMLVideoElement|null>(null);
  const base=useRef(0);
  const endedRef=useRef(false);
  const endingRef=useRef(false);
  const [spokenText,setSpokenText]=useState('');
  useEffect(()=>{loadConfig();return()=>{ws.current?.close();void audio.current?.close();screen.current?.stop();};},[]);
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
    if(connecting||joined)return;
    setConnecting(true);setEvents([]);setReviewAccess({sid:'',token:''});setEnded(false);endedRef.current=false;base.current=0;
    endingRef.current=false;
    setStatus('Opening microphone');
    let failure='';
    let stage='microphone';
    const meetingAudio=new MeetingAudio(send,setSpeaking);
    audio.current=meetingAudio;
    try {
      const sampleRate=await meetingAudio.open();
      meetingAudio.setMute(false);setMuted(false);setOutputMuted(false);
      stage='connection';setStatus('Connecting to meeting server');
      const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/meeting`);
      ws.current=socket;
      let timer:ReturnType<typeof setTimeout>;
      const timeout=()=>{
        if(ws.current!==socket)return;
        failure=stage==='connection'?'Meeting connection timed out. Check your connection and try again.':'Meeting setup timed out. Try joining again.';
        setStatus(failure);socket.close();
      };
      timer=setTimeout(timeout,20000);
      socket.onopen=()=>{
        if(ws.current!==socket){socket.close();return;}
        stage='setup';setStatus('Connecting speech providers');clearTimeout(timer);timer=setTimeout(timeout,20000);
        send({type:'join',consent_revision:config?.consent_revision,configuration_revision:config?.revision,attendees,background,scenario_id:scenarioId,consent,sample_rate:sampleRate});
      };
      socket.onmessage=({data})=>{
        if(ws.current!==socket)return;
        const e=JSON.parse(data) as Event;
        if(e.type==='audio'){audio.current?.play(String(e.pcm),Number(e.response_id));return;}
        if(e.type==='response_start')setSpeaker(String(e.speaker||attendees[0].name));
        if(e.type==='usage')setUsage({meeting_usd:Number(e.meeting_usd),daily_usd:Number(e.daily_usd),warning:Boolean(e.warning)});
        if(e.type==='limit'){failure=String(e.message);setStatus(failure);stopShare(false);void meetingAudio.close();}
        if(e.type==='partial'){setPartial(String(e.text));return;}
        if(e.type==='speaking_text'){setSpokenText(String(e.text));return;}
        if(e.type==='cancel'){audio.current?.stop(Number(e.next_id));setSpokenText('');}
        if(e.type==='response_done')audio.current?.done(Number(e.response_id));
        if(e.type==='joined'){
          setReviewAccess({sid:String(e.session_id),token:String(e.review_token||'')});
          delete e.review_token;
          clearTimeout(timer);stage='meeting';
          audio.current?.reportState();
          base.current=performance.now()-Number(e.t_ms);setSpeaker(attendees[0].name);setJoined(true);setConnecting(false);setStatus('Meeting live');
        }
        if(e.type==='transcript')setPartial('');
        if(e.type==='error'){if(!base.current)failure=String(e.message);setStatus(String(e.message));}
        if(e.type==='summary'){endedRef.current=true;setEnded(true);setTab('Summary');setStatus('Session ended');}
        setEvents(previous=>[...previous,e].slice(-3000));
      };
      socket.onclose=(event)=>{
        clearTimeout(timer);
        if(ws.current!==socket)return;
        ws.current=null;
        setJoined(false);setConnecting(false);stopShare(false);void meetingAudio.close();
        setEvents(previous=>[...previous,{type:'connection_closed',stage,code:event.code,clean:event.wasClean}]);
        if(!endedRef.current){
          if(base.current)setEnded(true);
          setStatus(failure||(endingRef.current?'Meeting ended. The review is retained; the summary did not arrive.':base.current?'Connection lost. Your review is retained. Start a new meeting to reconnect.':`Could not connect to the meeting server (code ${event.code}). Try again. If it persists, use Feedback.`));
        }
      };
      socket.onerror=()=>{if(ws.current!==socket)return;failure||='Meeting connection failed. Check your connection and try again. If it persists, use Feedback.';setStatus(failure);};
    } catch(error) {
      setConnecting(false);setStatus(stage==='microphone'?`Microphone setup failed: ${error instanceof Error?error.message:'unavailable'}. Check microphone permission and try again.`:'Meeting connection could not start. Try again.');
      await meetingAudio.close();
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
    endingRef.current=true;
    stopShare();audio.current?.stop();audio.current?.setMute(true);send({type:'end'});
    setStatus('Ending session');
  }
  function review() {return {attendees,background,profile:config?.mode,events,retention:config?.retention};}
  function download(payload=review()) {
    const link=document.createElement('a');const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    link.href=url;link.download='audience-session.json';link.click();URL.revokeObjectURL(url);
  }
  async function newMeeting() {
    setPreviousReview(review());
    const socket=ws.current;ws.current=null;socket?.close();
    stopShare(false);await audio.current?.close();audio.current=null;
    setJoined(false);setEnded(false);setConnecting(false);setSpeaking(false);setPartial('');setSpokenText('');
    setTab('Transcript');setStatus('Ready for a new meeting. Your previous review is available below.');
    setConsent(false);setConfig(null);await loadConfig();
  }
  const observations=events.filter(e=>e.type==='observation');
  const summary=events.findLast(e=>e.type==='summary');
  if(login)return <Access role="meeting" onReady={loadConfig}/>;
  return <div className="app">
    <header><div className="brandBlock"><a className="brand" href="/">◉ <span>Audience<span className="soft"> / simulator</span></span></a>{config&&<a className="feedback" href="https://github.com/sentania-labs/audience-simulator/issues/new" target="_blank" rel="noopener noreferrer">Feedback <span>Open an issue ↗</span></a>}</div><div className="headerStatus"><span className={`dot ${joined?'live':''}`}/>{status}</div></header>
    <main>
      {!joined&&<div className="account"><a href="/?admin">Admin</a><button onClick={async()=>{await api("/api/auth/meeting/logout",{});setLogin(true);}}>Sign out</button></div>}
      {previousReview&&<div className="previousReview"><span>Previous meeting review</span><button onClick={()=>download(previousReview)}>Download previous review</button></div>}
      {!joined&&!ended&&<section className="setup">
        <div><p className="eyebrow">A ROOM TO THINK OUT LOUD</p><h1>Your presentation.<br/>A curious audience.</h1><p className="intro">Practice with an audience that listens, asks questions, and follows what you share.</p>
          <div className="profile"><span className="avatar small">{persona.name[0]||'M'}</span><div><strong>{persona.name||'Your participant'}</strong><p>{persona.role}</p></div></div>
          <div className="notice"><strong>{config?.mode==='mock'?'Mock wiring mode':'Provider data flow'}</strong><p>{config?.mode==='mock'?'Test tones and fixed observations only. This mode does not recognize speech or understand screens.':`Microphone audio → ${config?.providers.stt||'STT'}; transcript and observations → ${config?.providers.dialogue||'dialogue'}; sampled images → ${config?.providers.vision||'vision'}; reply text → ${config?.providers.tts||'TTS'}.${config?.providers.judge ? ` Conversation excerpts → ${config.providers.judge} for observation-only evaluation.` : ''}`}</p><p>{config?.retention} Provider-side retention follows your provider agreements.</p></div>
        </div>
        <form onSubmit={e=>{e.preventDefault();void join();}} className="config"><p className="eyebrow">MEET YOUR PARTICIPANT</p><h2>Set the conversation</h2>
          <label>Audience<select disabled={connecting} value={scenarioId} onChange={e=>{setScenarioId(e.target.value);setSelected(0);const next=scenarios.find(s=>s.id===e.target.value);if(next){const p=next.cast[0];setAttendees([{cast_id:p.id,name:p.name,role:p.role,expertise:p.expertise,style:p.style,objective:p.objective}]);}else setAttendees([defaultPersona]);}}><option value="">Custom meeting</option>{scenarios.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>{scenario&&<div className="notice"><p>{scenario.background}</p><p>{scenario.fiction_notice} {scenario.source&&<a href={scenario.source} target="_blank" rel="noopener noreferrer">Industry source</a>}</p></div>}
          <label>Attendees<select value={attendees.length} onChange={e=>{const count=Number(e.target.value);setAttendees(a=>{const next=a.slice(0,count);while(next.length<count){const i=next.length,available=scenario?.cast.filter(p=>!next.some(v=>v.cast_id===p.id)),p=available?.[Math.floor(Math.random()*available.length)];next.push(p?{cast_id:p.id,name:p.name,role:p.role,expertise:p.expertise,style:p.style,objective:p.objective}:{...defaultPersona,name:['Morgan','Riley','Casey','Jordan'][i],role:['Infrastructure architect','Platform operator','Engineering leader','Curious colleague'][i]});}return next;});setSelected(0);}}>{Array.from({length:config?.limits.max_attendees||4},(_,i)=><option key={i} value={i+1}>{i+1}</option>)}</select></label>
          <nav>{attendees.map((a,i)=><button type="button" className={i===selected?'selected':''} key={i} onClick={()=>setSelected(i)}>{a.name||'Attendee'}</button>)}</nav>
          {scenario?<label>Cast member<select value={persona.cast_id} onChange={e=>{const p=scenario.cast.find(p=>p.id===e.target.value)!;setPersona({cast_id:p.id,name:p.name,role:p.role,expertise:p.expertise,style:p.style,objective:p.objective});}}>{scenario.cast.map(p=><option key={p.id} value={p.id} disabled={attendees.some((a,i)=>i!==selected&&a.cast_id===p.id)}>{p.name} · {p.role}</option>)}</select><p className="hint">{scenario.cast.find(p=>p.id===persona.cast_id)?.history}</p></label>:<label>Baseline<select onChange={e=>{const presets=[defaultPersona,{...defaultPersona,role:'Platform operator',expertise:'Day-to-day operations, recovery and maintenance',style:'Practical and direct'},{...defaultPersona,role:'Engineering leader',expertise:'Business outcomes, delivery risk and investment',style:'Concise and outcome focused'}];setPersona({...presets[Number(e.target.value)],name:persona.name});}}><option value="0">Infrastructure architect</option><option value="1">Platform operator</option><option value="2">Engineering leader</option></select></label>}
          {scenario?<div className="notice"><strong>{persona.role}</strong><p>{persona.objective}</p><details><summary>Expertise and style</summary><p>{persona.expertise}</p><p>{persona.style}</p></details></div>:Object.entries(persona).filter(([key])=>key!=='cast_id').map(([key,value])=><label key={key}>{({name:'Name',role:'Role',expertise:'Expertise',style:'Conversational style',objective:'Meeting objective (optional)'} as Record<string,string>)[key]}<input readOnly={!!persona.cast_id} value={value} maxLength={key==='name'?80: key==='objective'?1000:300} onChange={e=>setPersona({...persona,[key]:e.target.value})}/></label>)}
          <label>Meeting background<textarea maxLength={4000} value={background} onChange={e=>setBackground(e.target.value)} placeholder="What should the audience know before you begin?"/></label>
          <p className="hint">Up to {config?.limits.max_minutes} minutes. Estimated spending allowance: ${config?.limits.meeting_usd.toFixed(2)} per meeting. Address someone by name to choose who replies; otherwise attendees take turns.</p>
          <label className="check"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>I permit the configured providers to process audio, text, and explicitly shared screen samples.</span></label>
          {!!config?.missing.length&&<p className="error">Missing server configuration: {config.missing.join(', ')}</p>}
          <button className="primary" disabled={!config||!!config.missing.length||!consent||connecting}>{connecting?'Connecting…':'Join meeting →'}</button><p className="hint">Microphone permission required. Headphones recommended.</p>
        </form>
      </section>}
      {(joined||ended)&&<div className="meeting">
        <section className="stage"><div className="stageHeader"><span className="eyebrow">{ended?'SESSION REVIEW':'PRACTICE ROOM'}</span><span className="badge">{attendees.length} AI attendees</span></div>
          <div className={`shareArea ${sharing?'visible':''}`}><video ref={preview} muted autoPlay playsInline/><div className="shareLabel">● Your screen is being sampled</div></div>
          {!sharing&&<div className="participant"><span className={`avatar ${speaking?'speaking':''}`}>{speaker[0]||'M'}</span><h2>{speaker}</h2><p>{attendees.find(p=>p.name===speaker)?.role}</p><span className="badge">{ended?'Meeting ended':speaking?'Speaking':'Listening'}</span><p className="spoken">{speaking?spokenText:'Share a slide or demo to add visual context.'}</p></div>}
          {sharing&&<div className="profile"><span className="avatar small">{speaker[0]}</span><div><strong>{speaker}</strong><p>{speaking?'Speaking':'Listening'}</p></div></div>}
          <div className="roster">{attendees.map(a=><span className="badge" key={a.name}>{a.name}{speaking&&speaker===a.name?' · Speaking':''}</span>)}</div>
          {ended&&<button className="primary newMeeting" onClick={()=>void newMeeting()}>New meeting</button>}
          <p className={usage.warning?'error':'hint'}>Estimated meeting spend: ${usage.meeting_usd.toFixed(3)} / ${config?.limits.meeting_usd.toFixed(2)}{usage.warning?' · Allowance nearly reached':''}</p>
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
          </div><footer><span>{events.length} timeline events</span><button onClick={()=>download()}>Download session</button></footer>
        </aside>
      </div>}
      {ended&&reviewAccess.token&&<MeetingFeedback key={reviewAccess.sid} sid={reviewAccess.sid} token={reviewAccess.token} lines={events.filter(e=>e.type==='transcript').map(e=>({speaker:String(e.speaker),text:String(e.text),t_ms:Number(e.t_ms||0),final:Boolean(e.final)}))}/>}
    </main><div className="bottom"><span>Audience Simulator · Peer preview</span><span>Your audience. Your voice. Shared context.</span></div>
  </div>;
}

createRoot(document.getElementById('root')!).render(location.search.includes('admin')?<Admin/>:<App/>);
