import { createServerClient } from "@supabase/ssr";
import type { User } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { getSupabasePublicConfig } from "@/lib/env";
import { createLogger } from "@/lib/logger";

const logger = createLogger("supabase.proxy");

export interface SessionRefreshResult {
  response: NextResponse;
  user: User | null;
  configured: boolean;
}

export async function refreshSession(request: NextRequest): Promise<SessionRefreshResult> {
  let response = NextResponse.next({ request });
  const config = getSupabasePublicConfig();
  if (!config) {
    return { response, user: null, configured: false };
  }
  try {
    const client = createServerClient(config.url, config.anonKey, {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          response = NextResponse.next({ request });
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
          for (const [headerName, headerValue] of Object.entries(headers ?? {})) {
            response.headers.set(headerName, headerValue);
          }
        },
      },
    });
    const { data } = await client.auth.getUser();
    return { response, user: data.user ?? null, configured: true };
  } catch (error) {
    logger.error("Session refresh failed", { error });
    return { response, user: null, configured: true };
  }
}
