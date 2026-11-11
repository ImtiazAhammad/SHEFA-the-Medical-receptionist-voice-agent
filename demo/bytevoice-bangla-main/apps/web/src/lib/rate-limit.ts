export interface RateLimitDecision {
  allowed: boolean;
  retryAfterSeconds: number;
}

export interface RateLimiter {
  consume: (key: string) => RateLimitDecision;
}

const MAX_TRACKED_KEYS = 5_000;

export function createSlidingWindowRateLimiter(maxRequests: number, windowMilliseconds: number): RateLimiter {
  const requestLog = new Map<string, number[]>();

  function prune(now: number): void {
    if (requestLog.size <= MAX_TRACKED_KEYS) {
      return;
    }
    for (const [key, timestamps] of requestLog) {
      if (timestamps.every((timestamp) => now - timestamp >= windowMilliseconds)) {
        requestLog.delete(key);
      }
    }
  }

  return {
    consume(key: string): RateLimitDecision {
      const now = Date.now();
      prune(now);
      const recent = (requestLog.get(key) ?? []).filter((timestamp) => now - timestamp < windowMilliseconds);
      if (recent.length >= maxRequests) {
        requestLog.set(key, recent);
        const oldest = recent[0] ?? now;
        return { allowed: false, retryAfterSeconds: Math.max(1, Math.ceil((oldest + windowMilliseconds - now) / 1000)) };
      }
      recent.push(now);
      requestLog.set(key, recent);
      return { allowed: true, retryAfterSeconds: 0 };
    },
  };
}

export function clientAddressFromHeaders(headers: Headers): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) {
      return first;
    }
  }
  return headers.get("x-real-ip")?.trim() || "unknown";
}
