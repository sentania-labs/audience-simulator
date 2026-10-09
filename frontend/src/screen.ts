export class SharedScreen {
  stream: MediaStream | null = null;
  video = document.createElement('video');
  timer = 0;
  previous: Uint8ClampedArray | null = null;
  lastFrame = 0;
  busy = false;
  constructor(private frame: (jpeg:string, changed:boolean) => void, private ended: () => void) {}
  async start() {
    this.stream = await navigator.mediaDevices.getDisplayMedia({video:{frameRate:5},audio:false});
    this.video.srcObject = this.stream; this.video.muted = true;
    await this.video.play();
    this.stream.getVideoTracks()[0].onended = this.ended;
    // Caller sends share_started before sampling the first frame.
  }
  sample() {
    void this.capture();
    this.timer = window.setInterval(() => void this.capture(), 2000);
  }
  async capture() {
    if (this.busy || !this.stream || !this.video.videoWidth) return;
    this.busy = true;
    try {
      const small = document.createElement('canvas'); small.width=32; small.height=18;
      const tiny = small.getContext('2d')!; tiny.drawImage(this.video,0,0,32,18);
      const pixels = tiny.getImageData(0,0,32,18).data;
      const delta = this.previous ? pixels.reduce((n,p,i)=> n + Math.abs(p-this.previous![i]),0) / pixels.length : 255;
      if (delta < 4 && performance.now()-this.lastFrame < 10000) return;
      this.previous = pixels; this.lastFrame = performance.now();
      const canvas = document.createElement('canvas');
      canvas.width = Math.min(1280,this.video.videoWidth);
      canvas.height = Math.round(canvas.width*this.video.videoHeight/this.video.videoWidth);
      canvas.getContext('2d')!.drawImage(this.video,0,0,canvas.width,canvas.height);
      this.frame(canvas.toDataURL('image/jpeg',.75).split(',')[1], delta >= 4);
    } finally {this.busy=false;}
  }
  stop() {
    clearInterval(this.timer);
    this.stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});
    this.stream=null; this.video.srcObject=null;
  }
}
