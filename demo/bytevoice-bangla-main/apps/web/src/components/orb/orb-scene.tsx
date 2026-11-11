"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, type RefObject } from "react";
import { AdditiveBlending, Color, type Group, type ShaderMaterial } from "three";
import {
  ORB_FRAGMENT_SHADER,
  ORB_VERTEX_SHADER,
  RING_FRAGMENT_SHADER,
  RING_VERTEX_SHADER,
} from "@/components/orb/orb-shaders";
import type { OrbMode, OrbSignal } from "@/types/call";

interface ModeTarget {
  amplitude: number;
  volumeGain: number;
  frequency: number;
  ripple: number;
  speed: number;
  spin: number;
  pulse: number;
  glowStrength: number;
  saturation: number;
  scale: number;
  core: string;
  surface: string;
  glow: string;
  ring: string;
  ringOpacity: number;
}

const MODE_TARGETS: Record<OrbMode, ModeTarget> = {
  idle: {
    amplitude: 0.06, volumeGain: 0, frequency: 1.0, ripple: 0.006, speed: 0.35, spin: 0.12, pulse: 0.2,
    glowStrength: 1.35, saturation: 1, scale: 1,
    core: "#0b5a51", surface: "#36d1bc", glow: "#b4f2e8", ring: "#8fe6d9", ringOpacity: 0.75,
  },
  connecting: {
    amplitude: 0.13, volumeGain: 0, frequency: 1.6, ripple: 0.02, speed: 1.3, spin: 0.9, pulse: 1,
    glowStrength: 1.5, saturation: 1, scale: 0.96,
    core: "#0a4a43", surface: "#3fd0bc", glow: "#f4c67a", ring: "#f4c67a", ringOpacity: 0.8,
  },
  listening: {
    amplitude: 0.06, volumeGain: 0.7, frequency: 1.4, ripple: 0.015, speed: 0.7, spin: 0.3, pulse: 0.4,
    glowStrength: 1.4, saturation: 1, scale: 1.02,
    core: "#06403a", surface: "#38cdb9", glow: "#c3f5ec", ring: "#9be8dc", ringOpacity: 0.7,
  },
  speaking: {
    amplitude: 0.08, volumeGain: 0.9, frequency: 1.2, ripple: 0.025, speed: 0.95, spin: 0.45, pulse: 0.6,
    glowStrength: 1.7, saturation: 1, scale: 1.04,
    core: "#0b3f3a", surface: "#46cfae", glow: "#f4a63a", ring: "#f8c675", ringOpacity: 0.85,
  },
  ended: {
    amplitude: 0.04, volumeGain: 0, frequency: 1.1, ripple: 0.005, speed: 0.12, spin: 0.04, pulse: 0,
    glowStrength: 0.7, saturation: 0.25, scale: 0.94,
    core: "#1a2c2a", surface: "#4d6b66", glow: "#8aa39f", ring: "#6f8a86", ringOpacity: 0.3,
  },
};

const RING_POINT_COUNT = 1500;

function damp(current: number, target: number, rate: number, delta: number): number {
  return current + (target - current) * (1 - Math.exp(-rate * delta));
}

function OrbBody({ signalRef }: { signalRef: RefObject<OrbSignal> }) {
  const orbMaterial = useRef<ShaderMaterial>(null);
  const ringMaterial = useRef<ShaderMaterial>(null);
  const group = useRef<Group>(null);
  const clock = useRef({ orbTime: 0, ringTime: 0, level: 0 });

  const orbUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uAmplitude: { value: MODE_TARGETS.idle.amplitude },
      uFrequency: { value: MODE_TARGETS.idle.frequency },
      uRipple: { value: MODE_TARGETS.idle.ripple },
      uCoreColor: { value: new Color(MODE_TARGETS.idle.core) },
      uSurfaceColor: { value: new Color(MODE_TARGETS.idle.surface) },
      uGlowColor: { value: new Color(MODE_TARGETS.idle.glow) },
      uGlowStrength: { value: MODE_TARGETS.idle.glowStrength },
      uSaturation: { value: 1 },
    }),
    [],
  );

  const ringUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uSpin: { value: MODE_TARGETS.idle.spin },
      uPulse: { value: MODE_TARGETS.idle.pulse },
      uPointSize: { value: 13 },
      uColor: { value: new Color(MODE_TARGETS.idle.ring) },
      uOpacity: { value: MODE_TARGETS.idle.ringOpacity },
    }),
    [],
  );

  const ringGeometry = useMemo(() => {
    const positions = new Float32Array(RING_POINT_COUNT * 3);
    const seeds = new Float32Array(RING_POINT_COUNT);
    let state = 7;
    const random = () => {
      state = (state * 16807) % 2147483647;
      return (state - 1) / 2147483646;
    };
    for (let index = 0; index < RING_POINT_COUNT; index += 1) {
      const angle = random() * Math.PI * 2;
      const radius = 1.38 + Math.pow(random(), 1.6) * 0.34;
      positions[index * 3] = Math.cos(angle) * radius;
      positions[index * 3 + 1] = (random() - 0.5) * 0.12;
      positions[index * 3 + 2] = Math.sin(angle) * radius;
      seeds[index] = random();
    }
    return { positions, seeds };
  }, []);

  const targetColors = useMemo(
    () => ({ core: new Color(), surface: new Color(), glow: new Color(), ring: new Color() }),
    [],
  );

  useFrame((_state, rawDelta) => {
    const delta = Math.min(rawDelta, 0.05);
    const signal = signalRef.current;
    const target = MODE_TARGETS[signal.mode];
    const volume = signal.mode === "speaking" ? signal.agentVolume : signal.mode === "listening" ? signal.micVolume : 0;
    clock.current.level = damp(clock.current.level, Math.min(1, volume * 1.6), 14, delta);
    clock.current.orbTime += delta * (target.speed + clock.current.level * 1.2);
    clock.current.ringTime += delta;

    const orb = orbMaterial.current;
    if (orb) {
      orb.uniforms.uTime.value = clock.current.orbTime;
      orb.uniforms.uAmplitude.value = damp(
        orb.uniforms.uAmplitude.value,
        target.amplitude + clock.current.level * target.volumeGain * 0.5,
        6,
        delta,
      );
      orb.uniforms.uFrequency.value = damp(orb.uniforms.uFrequency.value, target.frequency, 3, delta);
      orb.uniforms.uRipple.value = damp(orb.uniforms.uRipple.value, target.ripple + clock.current.level * 0.05, 6, delta);
      orb.uniforms.uGlowStrength.value = damp(
        orb.uniforms.uGlowStrength.value,
        target.glowStrength + clock.current.level * 0.6,
        5,
        delta,
      );
      orb.uniforms.uSaturation.value = damp(orb.uniforms.uSaturation.value, target.saturation, 2, delta);
      const colorBlend = 1 - Math.exp(-3 * delta);
      orb.uniforms.uCoreColor.value.lerp(targetColors.core.set(target.core), colorBlend);
      orb.uniforms.uSurfaceColor.value.lerp(targetColors.surface.set(target.surface), colorBlend);
      orb.uniforms.uGlowColor.value.lerp(targetColors.glow.set(target.glow), colorBlend);
    }

    const ring = ringMaterial.current;
    if (ring) {
      ring.uniforms.uTime.value = clock.current.ringTime;
      ring.uniforms.uSpin.value = damp(ring.uniforms.uSpin.value, target.spin, 2, delta);
      ring.uniforms.uPulse.value = damp(ring.uniforms.uPulse.value, target.pulse + clock.current.level, 4, delta);
      ring.uniforms.uOpacity.value = damp(ring.uniforms.uOpacity.value, target.ringOpacity, 3, delta);
      ring.uniforms.uColor.value.lerp(targetColors.ring.set(target.ring), 1 - Math.exp(-3 * delta));
    }

    if (group.current) {
      const scale = damp(group.current.scale.x, target.scale + clock.current.level * 0.06, 6, delta);
      group.current.scale.setScalar(scale);
      group.current.rotation.y += delta * 0.08;
    }
  });

  return (
    <group ref={group}>
      <mesh>
        <icosahedronGeometry args={[1, 6]} />
        <shaderMaterial
          ref={orbMaterial}
          uniforms={orbUniforms}
          vertexShader={ORB_VERTEX_SHADER}
          fragmentShader={ORB_FRAGMENT_SHADER}
        />
      </mesh>
      <points rotation={[0.42, 0, 0.2]}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[ringGeometry.positions, 3]} />
          <bufferAttribute attach="attributes-aSeed" args={[ringGeometry.seeds, 1]} />
        </bufferGeometry>
        <shaderMaterial
          ref={ringMaterial}
          uniforms={ringUniforms}
          vertexShader={RING_VERTEX_SHADER}
          fragmentShader={RING_FRAGMENT_SHADER}
          transparent
          depthWrite={false}
          blending={AdditiveBlending}
        />
      </points>
    </group>
  );
}

interface OrbSceneProps {
  signalRef: RefObject<OrbSignal>;
  active: boolean;
  onReady: () => void;
}

export default function OrbScene({ signalRef, active, onReady }: OrbSceneProps) {
  return (
    <Canvas
      dpr={[1, 1.5]}
      frameloop={active ? "always" : "never"}
      camera={{ position: [0, 0, 5.5], fov: 38 }}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      onCreated={onReady}
      aria-hidden
    >
      <OrbBody signalRef={signalRef} />
    </Canvas>
  );
}
