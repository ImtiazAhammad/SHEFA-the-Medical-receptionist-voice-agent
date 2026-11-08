export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
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
    try {
      const body = await response.json()
      message = body?.error?.message ?? body?.detail?.message ?? message
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, message)
  }
  return (await response.json()) as T
}

export interface Me {
  signed_in: boolean
  name?: string
  role?: string
  permissions?: string[]
}

export interface CallRow {
  call_sid: string
  direction: string | null
  status: string | null
  disposition: string | null
  duration_seconds: number | null
  started_at: number | null
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

export interface CallDetail extends CallRow {
  turns: Turn[]
}

export interface Appointment {
  appointment_id: string
  date: string
  start_time: string
  doctor: string
  patient_name: string | null
  phone: string
  status: string
}

export interface Doctor {
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
