import { useEffect, useState } from 'react';
import { ThinkingOrb } from 'thinking-orbs';
import type { OrbState } from 'thinking-orbs';
import { MOTION_PREF_KEY, ORB_STATE, motionAllowed, setMotion } from './orb';
import type { CallPhase } from './orb';
import './orb.css';

const PHASE_LABEL: Record<CallPhase, string> = {
  idle: 'কল শুরু করুন',
  connecting: 'যুক্ত হচ্ছে',
  listening: 'শুনছে',
  thinking: 'ভাবছে',
  speaking: 'বলছে',
  ended: 'কল শেষ',
};

const LIVE_LABEL: Partial<Record<CallPhase, string>> = {
  connecting: 'agent status: connecting',
  listening: 'agent status: listening',
  thinking: 'agent status: thinking',
  speaking: 'agent status: speaking',
};

export function CallStatus({ phase }: { phase: CallPhase }) {
  const [motion, setMotionState] = useState(motionAllowed);
  const prefersReduce = usePrefersReducedMotion();

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === MOTION_PREF_KEY) setMotionState(motionAllowed());
    };
    addEventListener('storage', onStorage);
    return () => removeEventListener('storage', onStorage);
  }, []);

  const live = phase !== 'idle' && phase !== 'ended';
  // While reduced motion is on we hold a single frame instead of unmounting:
  // the operator still needs to see that an orb stands for the agent at all.
  const orbState: OrbState = PHASE_LABEL[phase] && live ? ORB_STATE[phase as keyof typeof ORB_STATE] : 'breathing';

  return (
    <section className="call-status" aria-labelledby="call-status-h">
      <h2 id="call-status-h" className="sr-only">
        কলের অবস্থা
      </h2>

      <div className="call-status-row">
        <div className="orb-slot" data-live={live}>
          <ThinkingOrb
            state={orbState}
            size={64}
            theme="light"
            speed={1}
            paused={!motion || !live}
            aria-label={LIVE_LABEL[phase] ?? 'agent idle'}
          />
        </div>

        <div className="call-status-text">
          <p className="call-phase" aria-live="polite">
            {PHASE_LABEL[phase]}
          </p>
          <p className="call-phase-en">{phase}</p>
        </div>

        <button
          type="button"
          className="motion-toggle"
          onClick={() => {
            const next = !motion;
            setMotion(next);
            setMotionState(next);
          }}
        >
          {motion ? 'অ্যানিমেশন বন্ধ করুন' : 'অ্যানিমেশন চালু করুন'}
        </button>
      </div>

      {prefersReduce && (
        <p className="call-note">
          আপনার ডিভাইসে কম অ্যানিমেশন চালু আছে, তাই অ্যানিমেশন বন্ধ রাখা হয়েছে।
        </p>
      )}
    </section>
  );
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}