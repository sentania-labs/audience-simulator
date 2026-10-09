class MicrophonePCM extends AudioWorkletProcessor {
  constructor() { super(); this.parts = []; this.count = 0; }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;
    this.parts.push(new Float32Array(channel));
    this.count += channel.length;
    if (this.count >= 2048) {
      const pcm = new Int16Array(this.count);
      let index = 0, energy = 0;
      for (const part of this.parts) for (const sample of part) {
        energy += sample * sample;
        pcm[index++] = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
      }
      this.port.postMessage({pcm: pcm.buffer, rms: Math.sqrt(energy / this.count)}, [pcm.buffer]);
      this.parts = []; this.count = 0;
    }
    return true;
  }
}
registerProcessor('microphone-pcm', MicrophonePCM);
