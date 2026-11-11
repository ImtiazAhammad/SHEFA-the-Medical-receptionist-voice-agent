"use client";

import { useState, type FormEvent } from "react";
import { useLanguage } from "@/i18n/language-provider";
import { createLogger } from "@/lib/logger";
import type { ApiErrorResponse, FormStatus } from "@/types/api";

const logger = createLogger("landing.contact");

const inputClass =
  "mt-1.5 block w-full rounded-xl border border-line bg-paper px-4 py-3 text-ink placeholder:text-slate/60 transition focus:border-teal focus:outline-none focus:ring-2 focus:ring-teal/25";

export function ContactSection() {
  const { dictionary } = useLanguage();
  const text = dictionary.contact;
  const [status, setStatus] = useState<FormStatus>("idle");
  const [message, setMessage] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const payload = {
      contactName: String(formData.get("contactName") ?? "").trim(),
      organisation: String(formData.get("organisation") ?? "").trim(),
      phone: String(formData.get("phone") ?? "").trim(),
      email: String(formData.get("email") ?? "").trim(),
      message: String(formData.get("message") ?? "").trim(),
    };
    if (!payload.contactName) {
      setStatus("error");
      setMessage(text.errorName);
      return;
    }
    if (!payload.phone && !payload.email) {
      setStatus("error");
      setMessage(text.errorContact);
      return;
    }

    setStatus("submitting");
    setMessage("");
    try {
      const response = await fetch("/api/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as ApiErrorResponse | null;
        logger.warn("Lead submission rejected", { status: response.status, code: body?.error.code });
        setStatus("error");
        setMessage(text.errorGeneric);
        return;
      }
      form.reset();
      setStatus("success");
      setMessage(text.success);
    } catch (error) {
      logger.error("Lead submission failed", { error });
      setStatus("error");
      setMessage(text.errorGeneric);
    }
  }

  return (
    <section id="contact" aria-labelledby="contact-title" className="bg-paper">
      <div className="mx-auto grid w-full max-w-7xl gap-12 px-4 py-20 sm:px-6 lg:grid-cols-[0.8fr_1.2fr] lg:px-8 lg:py-24">
        <div>
          <h2 id="contact-title" className="text-[clamp(1.9rem,3.6vw,2.9rem)] font-bold leading-tight text-ink">
            {text.title}
          </h2>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-ink-soft">{text.body}</p>
        </div>
        <form onSubmit={handleSubmit} noValidate className="grid gap-5 sm:grid-cols-2">
          <label className="text-sm font-medium text-ink">
            {text.fields.contactName}
            <input name="contactName" required maxLength={120} autoComplete="name" className={inputClass} />
          </label>
          <label className="text-sm font-medium text-ink">
            {text.fields.organisation}
            <input name="organisation" maxLength={160} autoComplete="organization" className={inputClass} />
          </label>
          <label className="text-sm font-medium text-ink">
            {text.fields.phone}
            <input name="phone" type="tel" maxLength={32} autoComplete="tel" inputMode="tel" className={inputClass} />
          </label>
          <label className="text-sm font-medium text-ink">
            {text.fields.email}
            <input name="email" type="email" maxLength={254} autoComplete="email" className={inputClass} />
          </label>
          <label className="text-sm font-medium text-ink sm:col-span-2">
            {text.fields.message}
            <textarea name="message" rows={4} maxLength={2000} className={inputClass} />
          </label>
          <div className="flex flex-wrap items-center gap-4 sm:col-span-2">
            <button
              type="submit"
              disabled={status === "submitting"}
              className="inline-flex h-12 items-center rounded-full bg-teal-deep px-6 font-semibold text-white transition hover:bg-ink disabled:cursor-wait disabled:opacity-70"
            >
              {status === "submitting" ? text.submitting : text.submit}
            </button>
            {message ? (
              <p role={status === "error" ? "alert" : "status"} className={status === "error" ? "text-rose" : "text-teal-deep"}>
                {message}
              </p>
            ) : null}
          </div>
        </form>
      </div>
    </section>
  );
}
