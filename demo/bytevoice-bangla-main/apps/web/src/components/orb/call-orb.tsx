"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState, type RefObject } from "react";
import { createLogger } from "@/lib/logger";
import type { OrbMode, OrbSignal } from "@/types/call";

const logger = createLogger("orb");

const OrbScene = dynamic(() => import("@/components/orb/orb-scene"), { ssr: false, loading: () => null });

function supportsWebGl(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch (error) {
    logger.debug("WebGL probe failed", { error });
    return false;
  }
}

interface CallOrbProps {
  signalRef: RefObject<OrbSignal>;
  mode: OrbMode;
}

export function CallOrb({ signalRef, mode }: CallOrbProps) {
  const container = useRef<HTMLDivElement>(null);
  const [shouldRender3d, setShouldRender3d] = useState(false);
  const [isVisible, setIsVisible] = useState(true);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion || !supportsWebGl()) {
      return;
    }
    if (typeof window.requestIdleCallback === "function") {
      const handle = window.requestIdleCallback(() => setShouldRender3d(true), { timeout: 2500 });
      return () => window.cancelIdleCallback(handle);
    }
    const timer = window.setTimeout(() => setShouldRender3d(true), 300);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const element = container.current;
    if (!element || typeof IntersectionObserver === "undefined") {
      return;
    }
    const observer = new IntersectionObserver(([entry]) => setIsVisible(Boolean(entry?.isIntersecting)), {
      rootMargin: "80px",
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={container} className="relative aspect-square w-full" data-mode={mode}>
      <div
        aria-hidden
        className={`absolute inset-[22%] transition-opacity duration-700 ${isReady ? "opacity-0" : "opacity-100"}`}
      >
        <div data-mode={mode} className="poster-orb poster-breathe h-full w-full rounded-full" />
      </div>
      {shouldRender3d ? (
        <div className={`absolute inset-0 transition-opacity duration-700 ${isReady ? "opacity-100" : "opacity-0"}`}>
          <OrbScene signalRef={signalRef} active={isVisible} onReady={() => setIsReady(true)} />
        </div>
      ) : null}
    </div>
  );
}
