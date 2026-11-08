import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type Lang = 'bn' | 'en'

const en = {
  appName: 'SHEFA',
  signIn: 'Sign in',
  signInIntro: 'Sign in with your clinic access token.',
  token: 'Access token',
  tokenHelp: 'Your clinic administrator gave you this. It is not your phone number.',
  signingIn: 'Signing in…',
  wrongToken: 'That token did not work. Check it and try again.',
  signOut: 'Sign out',
  language: 'Language',
  navLive: 'Live',
  navCalls: 'Calls',
  navAppointments: 'Appointments',
  navDoctors: 'Doctors',
  navMain: 'Main',
  skip: 'Skip to content',
  liveTitle: 'Calls right now',
  ringingTitle: 'Ringing',
  recentTitle: 'Recent calls',
  noCallsNow: 'No calls right now',
  lastCall: 'Last call {when}',
  noCallsYet: 'No calls yet. They will appear here as they happen.',
  callsTitle: 'Call history',
  open: 'Open',
  direction: 'Direction',
  inbound: 'Incoming',
  outbound: 'Outgoing',
  status: 'Status',
  inProgress: 'In progress',
  completed: 'Finished',
  disposition: 'Outcome',
  duration: 'Length',
  started: 'Started',
  back: 'Back',
  transcript: 'What was said',
  noTurns: 'Nothing was recorded for this call.',
  caller: 'Caller',
  agent: 'SHEFA',
  heardAt: 'heard with {pct} confidence',
  lowConfidence: 'Low confidence: check this line',
  typed: 'typed',
  appointmentsTitle: 'Appointments',
  day: 'Day',
  today: 'Today',
  noAppointments: 'No appointments on this day.',
  reference: 'Ref',
  patient: 'Patient',
  doctor: 'Doctor',
  time: 'Time',
  markDone: 'Seen',
  markNoShow: 'No-show',
  markCancel: 'Cancel',
  markBooked: 'Reopen',
  statusBooked: 'Booked',
  statusCompleted: 'Seen',
  statusNoShow: 'No-show',
  statusCancelled: 'Cancelled',
  couldNotSave: 'Could not save that change. Nothing was changed.',
  doctorsTitle: 'Doctors',
  searchDoctors: 'Search by name, department or problem',
  noDoctors: 'No doctor matches that.',
  noDirectory: 'No doctors are loaded yet. Import a clinic file: shefa clinic import <file>.',
  nextFree: 'Next free',
  noFreeTime: 'No free time found',
  room: 'Room',
  fee: 'Fee',
  experienceLabel: 'Experience',
  experience: '{n} years',
  speaks: 'Speaks',
  seesFor: 'Sees patients with',
  hours: 'Hours (as entered by the clinic)',
  noHours: 'No hours entered',
  loading: 'Loading…',
  retry: 'Try again',
  offline: 'Cannot reach the SHEFA server. This page may be out of date.',
  failed: 'Could not load this.',
  denied: 'Your sign-in does not allow this page.',
  updated: 'Updated {when}',
  min: 'min',
  sec: 'sec',
  male: 'Male',
  female: 'Female',
  consoleLink: 'Voice console (talk to the agent)',
  username: 'Username',
  password: 'Password',
  wrongLogin: 'The username or password is wrong, or the account is locked for a few minutes.',
  useToken: 'Use an access token instead',
  usePassword: 'Use a username and password',
  navMyDay: 'My day',
  myDayTitle: 'My patients',
  noPatients: 'No patients booked on this day.',
  reasonLabel: 'Reason',
  navOverview: 'Overview',
  overviewTitle: 'How it is going',
  lastDays: 'Last {n} days',
  today1: 'Today',
  statCalls: 'Calls answered',
  statBooked: 'Appointments booked by the agent',
  statHandedOver: 'Handed to a person',
  statFailed: 'Calls that failed',
  statCallbacks: 'People waiting for a call-back',
  statReminders: 'Reminder calls completed',
  ofAttempted: 'of {n} tried',
  avgLength: 'Average call length',
  noCallsPeriod: 'No calls in this period yet.',
  callbacksTitle: 'Call these people back',
  noCallbacks: 'Nobody is waiting for a call-back.',
  callBack: 'Call',
  waiting: 'waiting since {when}',
  resolve: 'Done: I called them',
  resolving: 'Saving…',
  deleteCall: 'Delete what was said',
  deleteConfirm: 'Delete the words of this call? This cannot be undone. The call itself stays in the list.',
  deleted: 'The words of this call were deleted.',
}

export type Key = keyof typeof en

const bn: Record<Key, string> = {
  appName: 'শেফা',
  signIn: 'সাইন ইন',
  signInIntro: 'ক্লিনিকের অ্যাক্সেস টোকেন দিয়ে সাইন ইন করুন।',
  token: 'অ্যাক্সেস টোকেন',
  tokenHelp: 'এটি আপনার ক্লিনিকের অ্যাডমিন দিয়েছেন। এটি আপনার ফোন নম্বর নয়।',
  signingIn: 'সাইন ইন হচ্ছে…',
  wrongToken: 'টোকেনটি কাজ করেনি। আবার দেখে চেষ্টা করুন।',
  signOut: 'সাইন আউট',
  language: 'ভাষা',
  navLive: 'এখন',
  navCalls: 'কল',
  navAppointments: 'অ্যাপয়েন্টমেন্ট',
  navDoctors: 'ডাক্তার',
  navMain: 'প্রধান মেনু',
  skip: 'মূল অংশে যান',
  liveTitle: 'এই মুহূর্তের কল',
  ringingTitle: 'বাজছে',
  recentTitle: 'সাম্প্রতিক কল',
  noCallsNow: 'এখন কোনো কল নেই',
  lastCall: 'শেষ কল {when}',
  noCallsYet: 'এখনো কোনো কল আসেনি। কল এলে এখানে দেখা যাবে।',
  callsTitle: 'কলের ইতিহাস',
  open: 'খুলুন',
  direction: 'ধরন',
  inbound: 'আসা কল',
  outbound: 'করা কল',
  status: 'অবস্থা',
  inProgress: 'চলছে',
  completed: 'শেষ',
  disposition: 'ফলাফল',
  duration: 'সময়',
  started: 'শুরু',
  back: 'পেছনে',
  transcript: 'কী কথা হয়েছে',
  noTurns: 'এই কলের কোনো কথা রেকর্ড হয়নি।',
  caller: 'কলকারী',
  agent: 'শেফা',
  heardAt: '{pct} নিশ্চিততায় শোনা',
  lowConfidence: 'নিশ্চিততা কম: লাইনটি দেখে নিন',
  typed: 'লেখা',
  appointmentsTitle: 'অ্যাপয়েন্টমেন্ট',
  day: 'দিন',
  today: 'আজ',
  noAppointments: 'এই দিনে কোনো অ্যাপয়েন্টমেন্ট নেই।',
  reference: 'রেফারেন্স',
  patient: 'রোগী',
  doctor: 'ডাক্তার',
  time: 'সময়',
  markDone: 'দেখা হয়েছে',
  markNoShow: 'আসেননি',
  markCancel: 'বাতিল',
  markBooked: 'আবার চালু',
  statusBooked: 'বুক করা',
  statusCompleted: 'দেখা হয়েছে',
  statusNoShow: 'আসেননি',
  statusCancelled: 'বাতিল',
  couldNotSave: 'পরিবর্তনটি সংরক্ষণ করা যায়নি। কিছুই বদলায়নি।',
  doctorsTitle: 'ডাক্তার',
  searchDoctors: 'নাম, বিভাগ বা সমস্যা দিয়ে খুঁজুন',
  noDoctors: 'এই নামে কোনো ডাক্তার পাওয়া যায়নি।',
  noDirectory: 'এখনো কোনো ডাক্তার যোগ করা হয়নি। ক্লিনিকের ফাইল ইমপোর্ট করুন: shefa clinic import <file>।',
  nextFree: 'পরবর্তী খালি সময়',
  noFreeTime: 'খালি সময় পাওয়া যায়নি',
  room: 'রুম',
  fee: 'ফি',
  experienceLabel: 'অভিজ্ঞতা',
  experience: '{n} বছর',
  speaks: 'ভাষা',
  seesFor: 'যে সমস্যায় দেখেন',
  hours: 'বসার সময় (ক্লিনিকের দেওয়া)',
  noHours: 'বসার সময় দেওয়া নেই',
  loading: 'লোড হচ্ছে…',
  retry: 'আবার চেষ্টা করুন',
  offline: 'শেফা সার্ভারের সাথে যোগাযোগ হচ্ছে না। এই পাতার তথ্য পুরোনো হতে পারে।',
  failed: 'এটি লোড করা যায়নি।',
  denied: 'আপনার সাইন-ইনে এই পাতা দেখার অনুমতি নেই।',
  updated: 'হালনাগাদ {when}',
  min: 'মিনিট',
  sec: 'সেকেন্ড',
  male: 'পুরুষ',
  female: 'নারী',
  consoleLink: 'ভয়েস কনসোল (এজেন্টের সাথে কথা বলুন)',
  username: 'ইউজারনেম',
  password: 'পাসওয়ার্ড',
  wrongLogin: 'ইউজারনেম বা পাসওয়ার্ড ভুল, অথবা অ্যাকাউন্টটি কিছুক্ষণের জন্য বন্ধ।',
  useToken: 'এর বদলে অ্যাক্সেস টোকেন ব্যবহার করুন',
  usePassword: 'ইউজারনেম ও পাসওয়ার্ড ব্যবহার করুন',
  navMyDay: 'আমার দিন',
  myDayTitle: 'আমার রোগী',
  noPatients: 'এই দিনে কোনো রোগী বুক করা নেই।',
  reasonLabel: 'কারণ',
  navOverview: 'সারসংক্ষেপ',
  overviewTitle: 'কেমন চলছে',
  lastDays: 'গত {n} দিন',
  today1: 'আজ',
  statCalls: 'ধরা কল',
  statBooked: 'এজেন্টের বুক করা অ্যাপয়েন্টমেন্ট',
  statHandedOver: 'মানুষের কাছে দেওয়া',
  statFailed: 'ব্যর্থ কল',
  statCallbacks: 'কল-ব্যাকের অপেক্ষায় থাকা মানুষ',
  statReminders: 'সম্পন্ন রিমাইন্ডার কল',
  ofAttempted: '{n}টির মধ্যে',
  avgLength: 'গড় কলের সময়',
  noCallsPeriod: 'এই সময়ে এখনো কোনো কল নেই।',
  callbacksTitle: 'এঁদের ফিরতি কল করুন',
  noCallbacks: 'কেউ ফিরতি কলের অপেক্ষায় নেই।',
  callBack: 'কল করুন',
  waiting: '{when} থেকে অপেক্ষায়',
  resolve: 'হয়েছে: কল করেছি',
  resolving: 'সংরক্ষণ হচ্ছে…',
  deleteCall: 'কথাবার্তা মুছুন',
  deleteConfirm: 'এই কলের কথাবার্তা মুছবেন? এটি ফেরানো যাবে না। কলটি তালিকায় থাকবে।',
  deleted: 'এই কলের কথাবার্তা মুছে ফেলা হয়েছে।',
}

const dictionaries: Record<Lang, Record<Key, string>> = { en, bn }

interface I18n {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: Key, vars?: Record<string, string | number>) => string
  /** Digits, dates and times in the reader's language, in clinic time (Asia/Dhaka). */
  num: (n: number, digits?: number) => string
  date: (iso: string | number, opts?: Intl.DateTimeFormatOptions) => string
  clock: (hhmm: string) => string
  /** Bangla or English text for a bilingual record. */
  pick: (en?: string | null, bn?: string | null) => string
}

const Ctx = createContext<I18n | null>(null)

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem('shefa.lang')
    if (saved === 'bn' || saved === 'en') return saved
  } catch {
    /* storage blocked */
  }
  return 'bn'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try {
      localStorage.setItem('shefa.lang', next)
    } catch {
      /* storage blocked */
    }
  }, [])

  const value = useMemo<I18n>(() => {
    const locale = lang === 'bn' ? 'bn-BD' : 'en-GB'
    const tz = 'Asia/Dhaka'
    return {
      lang,
      setLang,
      t: (key, vars) =>
        Object.entries(vars ?? {}).reduce(
          (text, [name, v]) => text.replace(`{${name}}`, String(v)),
          dictionaries[lang][key],
        ),
      num: (n, digits = 0) =>
        new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(n),
      date: (value, opts) => {
        const d = typeof value === 'number' ? new Date(value * 1000) : new Date(`${value}T12:00:00+06:00`)
        return new Intl.DateTimeFormat(
          locale,
          opts ?? { weekday: 'short', day: 'numeric', month: 'short', timeZone: tz },
        ).format(d)
      },
      clock: (hhmm) => {
        const [h, m] = hhmm.split(':').map(Number)
        const d = new Date(Date.UTC(2000, 0, 1, h, m))
        return new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }).format(d)
      },
      pick: (e, b) => (lang === 'bn' ? b || e || '' : e || b || ''),
    }
  }, [lang, setLang])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useI18n(): I18n {
  const value = useContext(Ctx)
  if (!value) throw new Error('useI18n outside I18nProvider')
  return value
}
