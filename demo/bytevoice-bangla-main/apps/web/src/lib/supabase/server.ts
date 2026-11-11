import { createServerClient } from "@supabase/ssr";
import type { SupabaseClient, User } from "@supabase/supabase-js";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { LOGIN_PATH } from "@/constants/app";
import { getSupabasePublicConfig } from "@/lib/env";
import { createLogger } from "@/lib/logger";

const logger = createLogger("supabase.server");

export async function createSupabaseServerClient(): Promise<SupabaseClient | null> {
  const config = getSupabasePublicConfig();
  if (!config) {
    return null;
  }
  const cookieStore = await cookies();
  return createServerClient(config.url, config.anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch (error) {
          logger.debug("Cookie write skipped outside a mutable context", { error });
        }
      },
    },
  });
}

export interface AuthenticatedContext {
  client: SupabaseClient;
  user: User;
}

export async function getAuthenticatedContext(): Promise<AuthenticatedContext | null> {
  try {
    const client = await createSupabaseServerClient();
    if (!client) {
      return null;
    }
    const { data, error } = await client.auth.getUser();
    if (error || !data.user) {
      return null;
    }
    return { client, user: data.user };
  } catch (error) {
    logger.error("Failed to resolve the signed-in user", { error });
    return null;
  }
}

export async function requirePortalContext(): Promise<AuthenticatedContext | "unconfigured"> {
  if (!getSupabasePublicConfig()) {
    return "unconfigured";
  }
  const authenticated = await getAuthenticatedContext();
  if (!authenticated) {
    redirect(LOGIN_PATH);
  }
  return authenticated;
}
