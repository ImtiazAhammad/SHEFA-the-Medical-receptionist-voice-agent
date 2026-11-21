export class ApiError extends Error {
  status: number
  /** The server's stable error code (for example "slot_taken"), when it sent one. */
  code: string
  constructor(status: number, message: string, code = '') {
    super(message)
    this.status = status
    this.code = code
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      credentials: 'same-origin',
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
      ...init,
    })
  } catch {
    throw new ApiError(0, 'network')
  }
  if (!response.ok) {
    let message = response.statusText
    let code = ''
    try {
      const body = await response.json()
      message = body?.error?.message ?? body?.detail?.message ?? message
      code = body?.error?.code ?? body?.detail?.code ?? ''
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, message, code)
  }
  return (await response.json()) as T
}

export interface Me {
  signed_in: boolean
  name?: string
  role?: string
  permissions?: string[]
  doctor_id?: number | null
}

/** Facts recorded about a call's outcome (see src/shefa/summary.py); worded in summary.ts. */
export interface CallSummary {
  outcome: string
  [fact: string]: unknown
}

export interface CallRow {
  call_sid: string
  direction: string | null
  status: string | null
  disposition: string | null
  duration_seconds: number | null
  started_at: number | null
  summary?: CallSummary | null
}

export interface Turn {
  idx: number
  at: number
  role: 'user' | 'assistant'
  language: string | null
  text: string
  confidence: number | null
  actions: string[]
  note: string | null
}

export interface EarlierCall {
  call_sid: string
  started_at: number | null
  disposition: string | null
  summary: CallSummary | null
}

export interface CallDetail extends CallRow {
  turns: Turn[]
  earlier_calls?: EarlierCall[]
}

export interface Appointment {
  appointment_id: string
  date: string
  start_time: string
  doctor: string
  doctor_bn?: string
  doctor_id?: number
  /** The chamber serial for a serial-mode doctor; null for a clock-time booking. */
  serial_no?: number | null
  patient_name: string | null
  phone: string
  status: string
  source?: string
  /** False for a web booking the desk has not yet checked with the patient. */
  confirmed?: boolean
}

export interface Doctor {
  id?: number
  name: string
  name_bn: string
  department: string
  department_bn: string
  qualification: string | null
  visit_fee: number | null
  schedule: string[]
  next_available: { date: string; time: string } | null
  designation?: string
  experience_years?: number
  gender?: string
  languages?: string[]
  room?: string
  fees?: Record<string, number>
  blurb?: { en?: string; bn?: string }
  booking_notes?: { en?: string; bn?: string }
  conditions?: { en?: string[]; bn?: string[] }
}

export interface Department {
  name: string
  name_bn: string
  doctors: Doctor[]
}

export interface Callback {
  id: number
  created_at: number
  call_sid: string | null
  phone: string | null
  language: string | null
  reason: string
}

export interface Overview {
  days: number
  calls: {
    calls: number
    inbound: number
    outbound: number
    dispositions: Record<string, number>
    average_seconds: number | null
  }
  booked_by_agent: number
  open_callbacks: number
  reminders: { attempted: number; completed: number }
}

export interface MyAppointment {
  appointment_id: string
  date: string
  start_time: string
  patient_name: string | null
  reason: string
  status: string
}

export interface StaffUser {
  username: string
  display_name: string
  role: 'desk' | 'owner' | 'doctor'
  doctor_id: number | null
  active: number | boolean
}

export interface DoctorChoice {
  id: number
  name: string
  name_bn: string
}
