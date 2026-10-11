import { useState } from 'react';
import { CallStatus } from './CallStatus';
import type { CallPhase } from './orb';

const PHASES: CallPhase[] = ['idle', 'connecting', 'listening', 'thinking', 'speaking', 'ended'];

const BN: Record<CallPhase, string> = {
  idle: 'নিষ্ক্রিয়',
  connecting: 'যুক্ত হচ্ছে',
  listening: 'শুনছে',
  thinking: 'ভাবছে',
  speaking: 'বলছে',
  ended: 'শেষ',
};

export default function App() {
  const [phase, setPhase] = useState<CallPhase>('idle');

  return (
    <main className="app">
      <h1>শেফা — কনসোল</h1>
      <p className="lede">কলের অবস্থা অনুযায়ী অরবের অবস্থা বদলায়।</p>

      <CallStatus phase={phase} />

      <div className="phase-bar" role="group" aria-label="কলের অবস্থা বেছে নিন">
        {PHASES.map((p) => (
          <button
            key={p}
            type="button"
            className="phase-btn"
            aria-pressed={phase === p}
            onClick={() => setPhase(p)}
          >
            {BN[p]}
          </button>
        ))}
      </div>
    </main>
  );
}