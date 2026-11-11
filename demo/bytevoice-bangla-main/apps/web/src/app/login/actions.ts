"use server";

import { redirect } from "next/navigation";
import { PORTAL_PATH } from "@/constants/app";
import { createLogger } from "@/lib/logger";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { signInRequestSchema } from "@/schemas/requests";
import type { ActionState } from "@/types/portal";

const logger = createLogger("auth.sign-in");

function safeRedirectPath(candidate: string | undefined): string {
  if (candidate && candidate.startsWith(PORTAL_PATH) && !candidate.startsWith("//")) {
    return candidate;
  }
  return PORTAL_PATH;
}

export async function signIn(_previous: ActionState, formData: FormData): Promise<ActionState> {
  const parsed = signInRequestSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
    redirectTo: formData.get("redirectTo") ?? undefined,
  });
  if (!parsed.success) {
    return { status: "error", message: "Enter a valid email and password." };
  }

  try {
    const client = await createSupabaseServerClient();
    if (!client) {
      return { status: "error", message: "The portal is not connected to Supabase yet." };
    }
    const { error } = await client.auth.signInWithPassword({
      email: parsed.data.email,
      password: parsed.data.password,
    });
    if (error) {
      logger.info("Sign-in rejected", { reason: error.message });
      return { status: "error", message: "Email or password is incorrect." };
    }
  } catch (error) {
    logger.error("Sign-in failed", { error });
    return { status: "error", message: "Could not reach the sign-in service. Try again." };
  }

  redirect(safeRedirectPath(parsed.data.redirectTo));
}
