import type { Lang } from './i18n'

/** What the agent did, in words a front-desk person understands. Unknown tools show as-is. */
const ACTIONS: Record<string, [string, string]> = {
  book_appointment: ['Booked an appointment', 'অ্যাপয়েন্টমেন্ট বুক করেছে'],
  cancel_appointment: ['Cancelled an appointment', 'অ্যাপয়েন্টমেন্ট বাতিল করেছে'],
  reschedule_appointment: ['Moved an appointment', 'অ্যাপয়েন্টমেন্টের সময় বদলেছে'],
  check_appointment_slots: ['Looked up free times', 'খালি সময় দেখেছে'],
  list_my_appointments: ['Read out their appointments', 'তাঁর অ্যাপয়েন্টমেন্টগুলো পড়েছে'],
  get_doctor_info: ['Answered about a doctor', 'ডাক্তার সম্পর্কে জানিয়েছে'],
  list_doctors: ['Listed doctors', 'ডাক্তারদের তালিকা দিয়েছে'],
  list_departments: ['Listed departments', 'বিভাগের তালিকা দিয়েছে'],
  lookup_patient_history: ['Looked up patient history', 'রোগীর ইতিহাস দেখেছে'],
  send_confirmation: ['Sent a confirmation', 'নিশ্চিতকরণ পাঠিয়েছে'],
  transfer_to_human: ['Handed over to a person', 'একজন মানুষের কাছে দিয়েছে'],
  verify_patient: ['Checked who the patient is', 'রোগীকে শনাক্ত করেছে'],
}

export function actionLabel(name: string, lang: Lang): string {
  const pair = ACTIONS[name]
  return pair ? pair[lang === 'bn' ? 1 : 0] : name
}

const DISPOSITIONS: Record<string, [string, string]> = {
  completed: ['Finished', 'শেষ হয়েছে'],
  handed_over: ['Handed to a person', 'মানুষের কাছে দেওয়া হয়েছে'],
  escalated: ['Handed to a person', 'মানুষের কাছে দেওয়া হয়েছে'],
  caller_hung_up: ['Caller hung up', 'কলার ফোন রেখে দিয়েছেন'],
  unsupported_language: ['Language not supported', 'ভাষা সমর্থিত নয়'],
  turned_away: ['Lines busy, call-back queued', 'লাইন ব্যস্ত, কল-ব্যাক রাখা হয়েছে'],
  failed: ['Failed', 'ব্যর্থ'],
}

export function dispositionLabel(value: string | null, lang: Lang): string {
  if (!value) return '-'
  const pair = DISPOSITIONS[value]
  return pair ? pair[lang === 'bn' ? 1 : 0] : value
}

export function languageName(code: string): string {
  return code === 'bn' ? 'বাংলা' : code === 'en' ? 'English' : code
}
