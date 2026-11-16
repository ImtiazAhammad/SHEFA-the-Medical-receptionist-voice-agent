// Runs on the audio thread. Takes the microphone (any rate, usually 44.1 or 48 kHz), averages it
// down to 16 kHz mono, turns it into 16-bit numbers and hands them to the page in small chunks,
// plus a loudness reading about every 30 ms for the level meter.
// It is a separate same-origin file because the page's security policy forbids inline or blob scripts.

class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000; // input samples per output sample
    this.filled = 0; // how much of the current output sample has been averaged so far
    this.sum = 0;
    this.out = new Int16Array(4000); // 250 ms of output
    this.outLen = 0;
    this.sq = 0; this.peak = 0; this.seen = 0; // loudness window
    this.on = true;
    this.port.onmessage = (e) => {
      if (e.data === "stop") {
        this.level();
        if (this.outLen) this.port.postMessage({ pcm: this.out.slice(0, this.outLen) });
        this.port.postMessage({ done: true });
        this.on = false;
      }
    };
  }

  level() {
    if (this.seen) this.port.postMessage({ rms: Math.sqrt(this.sq / this.seen), peak: this.peak });
    this.sq = 0; this.peak = 0; this.seen = 0;
  }

  push(v) {
    const c = v > 1 ? 1 : v < -1 ? -1 : v;
    this.out[this.outLen++] = c < 0 ? c * 32768 : c * 32767;
    if (this.outLen === this.out.length) {
      this.port.postMessage({ pcm: this.out.slice() });
      this.outLen = 0;
    }
  }

  process(inputs) {
    if (!this.on) return false;
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      const x = ch[i];
      this.sq += x * x;
      const a = x < 0 ? -x : x;
      if (a > this.peak) this.peak = a;
      this.seen++;
      // Box-filter resampling: each input sample feeds the output sample it overlaps.
      let w = 1;
      while (w > 1e-9) {
        const room = this.ratio - this.filled;
        if (w < room) { this.sum += x * w; this.filled += w; w = 0; }
        else { this.sum += x * room; this.push(this.sum / this.ratio); w -= room; this.sum = 0; this.filled = 0; }
      }
    }
    if (this.seen >= 1536) this.level();
    return true;
  }
}

registerProcessor("shefa-capture", Capture);
