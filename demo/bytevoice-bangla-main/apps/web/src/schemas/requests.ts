import { z } from "zod";
import { VISITOR_KEY_PATTERN } from "@/constants/call";

const visitorKeySchema = z.string().trim().regex(VISITOR_KEY_PATTERN);

export const tokenRequestSchema = z
  .object({
    language: z.enum(["bn", "en"]).optional(),
    geminiApiKey: visitorKeySchema.optional(),
  })
  .strict();

export const visitorKeyTestSchema = z.object({ apiKey: visitorKeySchema }).strict();

export const callIdParamSchema = z.uuid();

export const leadRequestSchema = z.object({
  contactName: z.string().trim().min(1).max(120),
  organisation: z.string().trim().max(160).optional().default(""),
  phone: z
    .string()
    .trim()
    .max(32)
    .regex(/^[+0-9০-৯\s-]*$/u)
    .optional()
    .default(""),
  email: z.union([z.literal(""), z.email().max(254)]).optional().default(""),
  message: z.string().trim().max(2000).optional().default(""),
});

export const signInRequestSchema = z.object({
  email: z.email(),
  password: z.string().min(1).max(200),
  redirectTo: z.string().optional(),
});

export const resolveCallbackRequestSchema = z.object({
  callbackId: z.uuid(),
});

export const toolEventMessageSchema = z.object({
  tool: z.string(),
  phase: z.enum(["start", "success", "error"]),
  label_bn: z.string(),
  label_en: z.string(),
});

export const callIdMessageSchema = z.object({
  call_id: z.uuid(),
});

export const latencyPayloadSchema = z.object({
  metric: z.string(),
  value_ms: z.number(),
});

const dayKeySchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export const callListQuerySchema = z.object({
  q: z.string().max(80).optional().catch(undefined),
  status: z.enum(["in_progress", "completed", "failed"]).optional().catch(undefined),
  outcome: z
    .enum(["booked", "rescheduled", "cancelled", "enquiry", "follow_up_needed", "incomplete", "failed"])
    .optional()
    .catch(undefined),
  from: dayKeySchema.optional().catch(undefined),
  to: dayKeySchema.optional().catch(undefined),
  page: z.coerce.number().int().min(1).max(10_000).optional().catch(undefined),
});

export const apiErrorSchema = z.object({ error: z.object({ code: z.string(), message: z.string() }) });
