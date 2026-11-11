/** Microphone in, agent voice out, over the demo WebSocket (16 kHz mono 16-bit PCM both ways). */
export type VoiceState = 'idle' | 'connecting' | 'live'
export type VoiceEnd = 'ended' | 'tooLong' | 'busy' | 'forbidden' | 'micBlocked' | 'micMissing' | 'failed'

export interface VoiceHandlers {
  onState: (state: VoiceState) => void
  onTurn: (role: 'user' | 'assistant', text: string) => void
  onEnd: (why: VoiceEnd) => void
}

// Downsamples the microphone to 16 kHz in chunks of 640+ samples, off the main thread.
const WORKLET = `class P extends AudioWorkletProcessor{constructor(){super();this.b=[];this.r=sampleRate/16000}
process(i){const c=i[0][0];if(!c)return true;for(let k=0;k<c.length;k++){this.b.push(c[k])}
const need=Math.floor(this.b.length/this.r);if(need>=640){const o=new Int16Array(need);for(let j=0;j<need;j++){let a=0,s=Math.floor(j*this.r),e=Math.floor((j+1)*this.r);for(let k=s;k<e;k++)a+=this.b[k];a/=Math.max(1,e-s);o[j]=Math.max(-1,Math.min(1,a))*32767}
this.b=this.b.slice(Math.floor(need*this.r));this.port.postMessage(o.buffer,[o.buffer])}return true}}registerProcessor('p',P);`

export class VoiceCall {
  private ws: WebSocket | null = null
  private ctx: AudioContext | null = null
  private mic: MediaStream | null = null
  private node: AudioWorkletNode | null = null
  private playAt = 0
  private agentUntil = 0
  private quietTimer: number | undefined
  private finished = false

  private readonly h: VoiceHandlers

  constructor(handlers: VoiceHandlers) {
    this.h = handlers
  }

  async start(): Promise<void> {
    if (this.ws) return
    this.finished = false
    if (!navigator.mediaDevices?.getUserMedia) return this.fail('micMissing')
    this.h.onState('connecting')
    try {
      this.mic = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
    } catch {
      return this.fail('micBlocked')
    }
    try {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      this.ctx = new Ctx()
      await this.ctx.resume()
      const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
      await this.ctx.audioWorklet.addModule(url)
      this.node = new AudioWorkletNode(this.ctx, 'p')
      this.ctx.createMediaStreamSource(this.mic).connect(this.node)
    } catch {
      return this.fail('failed')
    }
    const scheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://'
    const ws = new WebSocket(`${scheme}${window.location.host}/ws/demo-call`)
    ws.binaryType = 'arraybuffer'
    this.ws = ws
    ws.onopen = () => this.h.onState('live')
    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        const message = JSON.parse(event.data) as { type: string; role?: 'user' | 'assistant'; text?: string }
        if (message.type === 'turn' && message.role && message.text) this.h.onTurn(message.role, message.text)
        else if (message.type === 'hangup') this.hangUpWhenQuiet()
        return
      }
      this.play(event.data as ArrayBuffer)
    }
    ws.onclose = (event) => {
      const why: VoiceEnd =
        event.code === 4408 ? 'tooLong' : event.code === 4429 ? 'busy' : event.code === 4403 ? 'forbidden' : 'ended'
      this.cleanup(why)
    }
    ws.onerror = () => this.cleanup('failed')
    this.node.port.onmessage = (event) => {
      if (ws.readyState !== WebSocket.OPEN || !this.ctx) return
      // Half duplex: while the agent speaks, send silence so it cannot hear itself.
      ws.send(this.ctx.currentTime < this.agentUntil ? new Int16Array(event.data.byteLength / 2).buffer : event.data)
    }
  }

  stop(): void {
    this.cleanup('ended')
  }

  private play(buffer: ArrayBuffer): void {
    if (!this.ctx) return
    const samples = new Int16Array(buffer)
    const floats = new Float32Array(samples.length)
    for (let i = 0; i < samples.length; i++) floats[i] = samples[i] / 32768
    const audio = this.ctx.createBuffer(1, floats.length, 16000)
    audio.copyToChannel(floats, 0)
    const source = this.ctx.createBufferSource()
    source.buffer = audio
    source.connect(this.ctx.destination)
    this.playAt = Math.max(this.playAt, this.ctx.currentTime + 0.05)
    source.start(this.playAt)
    this.playAt += audio.duration
    this.agentUntil = this.playAt
  }

  /** The agent ended the call: hang up once its last words have played out. */
  private hangUpWhenQuiet(): void {
    window.clearInterval(this.quietTimer)
    this.quietTimer = window.setInterval(() => {
      if (!this.ctx || this.ctx.currentTime >= this.agentUntil) {
        window.clearInterval(this.quietTimer)
        this.cleanup('ended')
      }
    }, 200)
  }

  private fail(why: VoiceEnd): void {
    this.cleanup(why)
  }

  private cleanup(why: VoiceEnd): void {
    if (this.finished) return
    this.finished = true
    window.clearInterval(this.quietTimer)
    try {
      this.ws?.close()
    } catch {
      /* already closed */
    }
    this.ws = null
    this.node?.disconnect()
    this.mic?.getTracks().forEach((track) => track.stop())
    void this.ctx?.close()
    this.ctx = null
    this.node = null
    this.mic = null
    this.playAt = this.agentUntil = 0
    this.h.onState('idle')
    this.h.onEnd(why)
  }
}
