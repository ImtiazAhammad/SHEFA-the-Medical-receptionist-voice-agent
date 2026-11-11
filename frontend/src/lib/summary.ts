import type { CallSummary } from './api'
import type { Lang } from './i18n'

export interface Formatters {
  /** An ISO day ("2026-11-10") in the staff member's language. */
  day: (iso: string) => string
  /** "09:30" as digits in the staff member's language. */
  clock: (hhmm: string) => string
}

type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'quiet'

const HANDOVER: Record<string, [string, string]> = {
  emergency: ['the caller described an emergency', 'কলার জরুরি অবস্থার কথা বলেছেন'],
  asked_for_person: ['the caller asked for a person', 'কলার একজন মানুষের সাথে কথা বলতে চেয়েছেন'],
  not_understood: ['the agent could not understand the caller', 'এজেন্ট কলারের কথা বুঝতে পারেনি'],
}
const STOPPED: Record<string, [string, string]> = {
  doctor: ['choosing a doctor', 'ডাক্তার বাছাইয়ে'],
  day: ['choosing a day', 'দিন বাছাইয়ে'],
  time: ['choosing a time', 'সময় বাছাইয়ে'],
  name: ['giving the patient name', 'রোগীর নাম বলায়'],
  phone: ['giving a phone number', 'ফোন নম্বর বলায়'],
  confirmation: ['the final yes', 'শেষ নিশ্চিতকরণে'],
}
const ASKED: Record<string, [string, string]> = {
  doctor_info: ['about a doctor', 'ডাক্তার সম্পর্কে'],
  doctors: ['the doctors', 'ডাক্তারদের তালিকা'],
  departments: ['the departments', 'বিভাগগুলো'],
  availability: ['free times', 'খালি সময়'],
  my_appointments: ['their appointments', 'নিজের অ্যাপয়েন্টমেন্ট'],
}

const pick = (pair: [string, string] | undefined, lang: Lang, fallback = '') =>
  pair ? pair[lang === 'bn' ? 1 : 0] : fallback

/** One plain sentence for the desk, built from the facts the server recorded. */
export function summaryText(
  s: CallSummary | null | undefined,
  lang: Lang,
  f: Formatters,
): { text: string; tone: Tone } | null {
  if (!s || !s.outcome) return null
  const bn = lang === 'bn'
  const doctor = String((bn ? s.doctor_bn || s.doctor : s.doctor) ?? '')
  const wanted = (s.wanted_doctor as string | undefined) ?? (s.wanted_department as string | undefined) ?? ''
  switch (s.outcome) {
    case 'booked': {
      const when = s.date && s.time ? `${f.day(String(s.date))} ${f.clock(String(s.time))}` : ''
      const who = s.patient ? `${s.patient}: ` : ''
      const check = s.confirmed === false ? (bn ? ' — ডেস্কের নিশ্চিত করা বাকি।' : ' — the desk still needs to confirm.') : '.'
      return {
        tone: s.confirmed === false ? 'warn' : 'ok',
        text: bn
          ? `${who}ডাক্তার ${doctor}-এর সাথে ${when} বুক হয়েছে (রেফারেন্স ${s.ref ?? ''})${check}`
          : `${who}booked with Dr. ${doctor} on ${when} (reference ${s.ref ?? ''})${check}`,
      }
    }
    case 'cancelled':
      return { tone: 'info', text: bn ? 'একটি অ্যাপয়েন্টমেন্ট বাতিল হয়েছে।' : 'An appointment was cancelled.' }
    case 'rescheduled':
      return { tone: 'info', text: bn ? 'একটি অ্যাপয়েন্টমেন্টের সময় বদলানো হয়েছে।' : 'An appointment was moved.' }
    case 'handed_over': {
      const why = pick(HANDOVER[String(s.reason)], lang, '')
      return {
        tone: s.reason === 'emergency' ? 'bad' : 'warn',
        text: bn ? `মানুষের কাছে দেওয়া হয়েছে: ${why}। ফোন করে ধরতে হবে।` : `Handed to a person: ${why}. Needs a call-back.`,
      }
    }
    case 'booking_not_finished': {
      const where = pick(STOPPED[String(s.stopped_at)], lang, '')
      const who = wanted ? (bn ? ` ডাক্তার/বিভাগ: ${wanted}।` : ` Wanted: ${wanted}.`) : ''
      return {
        tone: 'warn',
        text: bn ? `বুকিং শেষ হয়নি, ${where} থেমে গেছে।${who}` : `Booking not finished: stopped at ${where}.${who}`,
      }
    }
    case 'information': {
      const topics = ((s.asked as string[] | undefined) ?? []).map((a) => pick(ASKED[a], lang, a)).join(bn ? ', ' : ', ')
      return { tone: 'info', text: bn ? `তথ্য জানতে চেয়েছেন: ${topics}।` : `Asked for information: ${topics}.` }
    }
    case 'other_language':
      return { tone: 'warn', text: bn ? 'অন্য ভাষায় কথা বলেছেন; সাহায্য করা যায়নি।' : 'Spoke another language; could not help.' }
    case 'turned_away':
      return { tone: 'warn', text: bn ? 'লাইন ব্যস্ত ছিল; কল-ব্যাক রাখা হয়েছে।' : 'Lines were busy; a call-back was queued.' }
    case 'failed':
      return { tone: 'bad', text: bn ? 'কলটি কারিগরি সমস্যায় ব্যর্থ হয়েছে।' : 'The call failed on a technical fault.' }
    default:
      return { tone: 'quiet', text: bn ? 'কোনো অনুরোধ ছিল না।' : 'The caller made no request.' }
  }
}
