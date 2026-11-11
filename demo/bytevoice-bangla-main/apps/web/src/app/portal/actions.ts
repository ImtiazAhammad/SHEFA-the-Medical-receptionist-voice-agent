"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { LOGIN_PATH } from "@/constants/app";
import { createLogger } from "@/lib/logger";
import { markCallbackRequestDone } from "@/lib/repositories/callbacks-repository";
import { createSupabaseServerClient, getAuthenticatedContext } from "@/lib/supabase/server";
import { resolveCallbackRequestSchema } from "@/schemas/requests";
import type { ActionState } from "@/types/portal";

const logger = createLogger("portal.actions");

export async function signOut(): Promise<void> {
  try {
    const client = await createSupabaseServerClient();
    await client?.auth.signOut();
  } catch (error) {
    logger.error("Sign-out failed", { error });
  }
  redirect(LOGIN_PATH);
}

export async function resolveCallback(_previous: ActionState, formData: FormData): Promise<ActionState> {
  try {
    const parsed = resolveCallbackRequestSchema.safeParse({ callbackId: formData.get("callbackId") });
    if (!parsed.success) {
      return { status: "error", message: "Invalid callback id." };
    }
    const authenticated = await getAuthenticatedContext();
    if (!authenticated) {
      return { status: "error", message: "Your session has expired. Sign in again." };
    }
    await markCallbackRequestDone(authenticated.client, parsed.data.callbackId, new Date());
    revalidatePath("/portal/callbacks");
    revalidatePath("/portal/calls/[id]", "page");
    revalidatePath("/portal");
    return { status: "success", message: "Marked as done." };
  } catch (error) {
    logger.error("Resolving callback failed", { error });
    return { status: "error", message: "Could not update the callback. Try again." };
  }
}
