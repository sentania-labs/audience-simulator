type Send = (event: Record<string, unknown> | ArrayBuffer) => void;

export class MeetingAudio {
  ctx: AudioContext | null = null;
  stream: MediaStream | null = null;
  node: AudioWorkletNode | null = null;
  sources = new Set<AudioBufferSourceNode>();
  muted = false;
  floor = 0;
  active = -1;
  nextTime = 0;
  voicedAt = 0;
  lastEnergy = 0;
  talking = false;
  lastSpeechEnd = 0;
  firstAudio = new Set<number>();
  completed = new Set<number>();
  outputMuted = false;
  gain: GainNode | null = null;

  constructor(private send: Send, private state: (speaking: boolean) => void) {}

  async open() {
    this.stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
    this.ctx = new AudioContext({sampleRate: 48000});
    await this.ctx.resume();
    this.ctx.onstatechange = () => this.reportState();
    await this.ctx.audioWorklet.addModule('/mic-worklet.js');
    this.gain = this.ctx.createGain();
    this.gain.connect(this.ctx.destination);
    this.node = new AudioWorkletNode(this.ctx, 'microphone-pcm');
    const source = this.ctx.createMediaStreamSource(this.stream);
    source.connect(this.node);
    const silent = this.ctx.createGain(); silent.gain.value = 0;
    this.node.connect(silent).connect(this.ctx.destination);
    this.node.port.onmessage = ({data}: MessageEvent<{pcm:ArrayBuffer;rms:number}>) => {
      if (this.muted) return;
      const now = performance.now();
      if (data.rms > .025) {
        this.lastEnergy = now;
        if (!this.voicedAt) this.voicedAt = now;
        if (!this.talking && now - this.voicedAt >= 120) {
          this.talking = true;
          this.send({type:'speech_activity'});
        }
      } else {
        this.voicedAt = 0;
        if (this.talking && now - this.lastEnergy > 500) {
          this.talking = false;
          this.lastSpeechEnd = now;
          this.send({type:'speech_end'});
        }
      }
      this.send(data.pcm);
    };
    return this.ctx.sampleRate;
  }

  reportState() {
    this.send({type:'audio_state', context_state:this.ctx?.state ?? 'unavailable',
      output_muted:this.outputMuted, gain:this.gain?.gain.value ?? 0, queued_sources:this.sources.size});
  }

  setMute(value: boolean) {
    this.muted = value;
    this.stream?.getAudioTracks().forEach(t => {t.enabled = !value;});
    if (value && this.talking) {
      this.talking = false;
      this.send({type:'speech_end'});
    }
  }

  setOutputMute(value: boolean) {
    this.outputMuted = value;
    if (this.gain) this.gain.gain.value = value ? 0 : 1;
    this.reportState();
  }

  stop(nextId?: number) {
    const hadAudio = this.sources.size > 0;
    const old = this.active;
    this.floor = Math.max(this.floor, nextId ?? this.active + 1);
    this.active = -1;
    for (const source of this.sources) {source.onended = null; source.stop(); source.disconnect();}
    this.sources.clear();
    this.nextTime = 0;
    this.state(false);
    if (hadAudio) this.send({type:'playback_stopped',response_id:old});
  }

  play(pcm: string, rid: number) {
    if (!this.ctx || !this.gain || rid < this.floor) return;
    if (rid !== this.active) {this.active = rid; this.state(true);}
    const raw = atob(pcm);
    const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
    const samples = new DataView(bytes.buffer);
    const buffer = this.ctx.createBuffer(1, bytes.length / 2, 24000);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < channel.length; i++) channel[i] = samples.getInt16(i*2,true) / 32768;
    const source = this.ctx.createBufferSource(); source.buffer = buffer; source.connect(this.gain);
    const when = Math.max(this.ctx.currentTime + .04, this.nextTime);
    this.nextTime = when + buffer.duration;
    this.sources.add(source);
    source.onended = () => {
      this.sources.delete(source); source.disconnect();
      if (!this.sources.size && this.completed.has(rid)) {
        this.state(false); this.active = -1;
        this.send({type:'playback_ended',response_id:rid});
      }
    };
    source.start(when);
    if (!this.firstAudio.has(rid)) {
      this.firstAudio.add(rid);
      const scheduledDelay = (when - this.ctx.currentTime) * 1000;
      this.reportState();
      this.send({type:'playback_started',response_id:rid});
      if (this.lastSpeechEnd) this.send({type:'browser_metric',stage:'estimated_first_playback_after_silence',response_id:rid,
        value_ms:performance.now()-this.lastSpeechEnd+scheduledDelay});
      this.lastSpeechEnd = 0;
    }
  }

  done(rid: number) {
    this.completed.add(rid);
    if (!this.sources.size && this.active === rid) {
      this.active = -1; this.state(false);
      this.send({type:'playback_ended',response_id:rid});
    }
  }

  async close() {
    this.muted = true;
    this.stop();
    if (this.node) this.node.port.onmessage = null;
    this.node?.disconnect();
    this.node = null;
    this.stream?.getTracks().forEach(t => t.stop());
    this.stream = null;
    const context = this.ctx;
    this.ctx = null;
    this.gain = null;
    if (context) {
      context.onstatechange = null;
      if (context.state !== 'closed') await context.close();
    }
  }
}
