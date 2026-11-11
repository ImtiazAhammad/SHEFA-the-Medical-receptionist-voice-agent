import { DEFAULT_AGENT_NAME } from "@/constants/call";

export interface SupabasePublicConfig {
  url: string;
  anonKey: string;
}

export interface LiveKitServerConfig {
  serverUrl: string;
  apiKey: string;
  apiSecret: string;
  agentName: string;
}

export interface AgentApiConfig {
  baseUrl: string;
  internalToken: string;
}

function present(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

export function getSupabasePublicConfig(): SupabasePublicConfig | null {
  const url = present(process.env.NEXT_PUBLIC_SUPABASE_URL);
  const anonKey = present(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
  return url && anonKey ? { url, anonKey } : null;
}

export function getLiveKitServerConfig(): LiveKitServerConfig | null {
  const serverUrl = present(process.env.LIVEKIT_URL);
  const apiKey = present(process.env.LIVEKIT_API_KEY);
  const apiSecret = present(process.env.LIVEKIT_API_SECRET);
  if (!serverUrl || !apiKey || !apiSecret) {
    return null;
  }
  return { serverUrl, apiKey, apiSecret, agentName: present(process.env.LIVEKIT_AGENT_NAME) ?? DEFAULT_AGENT_NAME };
}

export function getAgentApiConfig(): AgentApiConfig | null {
  const baseUrl = present(process.env.AGENT_API_URL);
  const internalToken = present(process.env.INTERNAL_API_TOKEN);
  return baseUrl && internalToken ? { baseUrl: baseUrl.replace(/\/+$/, ""), internalToken } : null;
}

export function getVisitorKeySecret(): string | null {
  return present(process.env.INTERNAL_API_TOKEN);
}
