"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { REALTIME_REFRESH_DEBOUNCE_MILLISECONDS } from "@/constants/portal";
import { createLogger } from "@/lib/logger";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

const logger = createLogger("portal.realtime");

export interface RealtimeSubscription {
  table: "calls" | "transcript_turns" | "call_events";
  filter?: string;
}

interface RealtimeRefreshProps {
  channelName: string;
  subscriptions: RealtimeSubscription[];
}

export function RealtimeRefresh({ channelName, subscriptions }: RealtimeRefreshProps) {
  const router = useRouter();
  const [isConnected, setIsConnected] = useState(false);
  const timer = useRef<number | null>(null);
  const subscriptionKey = JSON.stringify(subscriptions);

  useEffect(() => {
    const client = getSupabaseBrowserClient();
    if (!client) {
      return;
    }
    const parsedSubscriptions = JSON.parse(subscriptionKey) as RealtimeSubscription[];
    const scheduleRefresh = () => {
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }
      timer.current = window.setTimeout(() => router.refresh(), REALTIME_REFRESH_DEBOUNCE_MILLISECONDS);
    };

    let channel = client.channel(channelName);
    for (const subscription of parsedSubscriptions) {
      channel = channel.on(
        "postgres_changes",
        { event: "*", schema: "public", table: subscription.table, filter: subscription.filter },
        scheduleRefresh,
      );
    }
    channel.subscribe((status, error) => {
      setIsConnected(status === "SUBSCRIBED");
      if (error) {
        logger.warn("Realtime subscription error", { status, error });
      }
    });

    return () => {
      if (timer.current !== null) {
        window.clearTimeout(timer.current);
      }
      void client.removeChannel(channel);
    };
  }, [channelName, router, subscriptionKey]);

  return (
    <span className="inline-flex items-center gap-2 text-xs text-slate" title={isConnected ? "Realtime updates on" : "Realtime connecting"}>
      <span aria-hidden className={`h-2 w-2 rounded-full ${isConnected ? "live-dot bg-teal" : "bg-line"}`} />
      {isConnected ? "Live updates" : "Connecting…"}
    </span>
  );
}
