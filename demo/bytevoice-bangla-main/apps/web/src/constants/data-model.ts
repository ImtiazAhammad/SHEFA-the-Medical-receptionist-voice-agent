export const ENTITY_RELATIONSHIP_DIAGRAM = `erDiagram
  clinics ||--o{ doctors : employs
  clinics ||--o{ services : offers
  doctors ||--o{ doctor_services : performs
  services ||--o{ doctor_services : "performed by"
  doctors ||--o{ doctor_schedules : "works on"
  clinics ||--o{ calls : receives
  patients |o--o{ calls : makes
  calls ||--o{ transcript_turns : contains
  calls ||--o| call_extractions : "summarised as"
  calls ||--o{ call_events : logs
  calls |o--o{ appointments : creates
  calls ||--o{ callback_requests : raises
  patients ||--o{ appointments : holds
  doctors ||--o{ appointments : "assigned to"
  services ||--o{ appointments : "booked for"
  patients |o--o{ callback_requests : "asks for"

  calls {
    uuid id PK
    uuid patient_id FK
    text room_name UK
    text engine
    timestamptz started_at
    timestamptz ended_at
    int duration_s "generated"
    call_status status
    call_outcome outcome
    bool after_hours
    text summary_bn
    text summary_en
  }
  transcript_turns {
    bigint id PK
    uuid call_id FK
    int seq "unique per call"
    speaker_role speaker
    text text_bn
    text text_en
    int offset_ms
    bool interrupted
  }
  call_extractions {
    uuid call_id PK
    text intent
    text patient_name_bn
    text phone_e164
    bool phone_valid
    text reason_for_visit
    date preferred_date
    text preferred_time_window
    jsonb confidence
  }
  patients {
    uuid id PK
    text full_name_bn
    text full_name_en
    text phone_e164 UK
  }
  appointments {
    uuid id PK
    uuid patient_id FK
    uuid doctor_id FK
    uuid service_id FK
    uuid call_id FK
    tstzrange slot "no overlap per doctor"
    appointment_status status
  }
  callback_requests {
    uuid id PK
    uuid call_id FK
    text reason
    smallint priority
    callback_status status
  }
  call_events {
    bigint id PK
    uuid call_id FK
    text event_type
    jsonb payload
  }
  doctors {
    uuid id PK
    text full_name_bn
    text specialty_en
  }
  services {
    uuid id PK
    text code UK
    int duration_min
    int fee_bdt
  }
  doctor_schedules {
    uuid id PK
    smallint weekday
    time start_time
    time end_time
  }
`;

export const CALL_FLOW_DIAGRAM = `flowchart LR
  visitor([Browser caller]) -- "POST /api/livekit/token" --> web[Next.js on Vercel]
  web -- "10-min token + agent dispatch" --> visitor
  visitor <-- "WebRTC audio" --> livekit[(LiveKit Cloud room)]
  livekit <--> agent[Python agent: Gemini Live bn-BD]
  agent -- "calls row, live turns, events" --> db[(Supabase Postgres, Singapore)]
  agent -- "tools: patients, appointments, callbacks" --> db
  agent -- "on hang-up: finalize" --> api[Agent API: extraction + summary]
  api -- "call_extractions, summaries, text_en, outcome" --> db
  db -- "Realtime: calls, turns, events" --> portal[Staff portal]
`;

export interface TableExplanation {
  name: string;
  grain: string;
  writer: string;
  purpose: string;
}

export const TABLE_EXPLANATIONS: TableExplanation[] = [
  {
    name: "clinics, doctors, services, doctor_services, doctor_schedules",
    grain: "Reference data",
    writer: "Seed / admin",
    purpose: "The agent quotes fees, hours and doctors only from these tables, so it cannot invent facts.",
  },
  {
    name: "patients",
    grain: "One person, keyed by phone (E.164)",
    writer: "Agent tools",
    purpose: "Repeat callers link to one record; a CHECK constraint enforces +8801[3-9]XXXXXXXX.",
  },
  {
    name: "calls",
    grain: "One LiveKit room",
    writer: "Agent on connect and hang-up",
    purpose: "Status, outcome, after-hours flag and bilingual summary; duration_s is a generated column.",
  },
  {
    name: "transcript_turns",
    grain: "One utterance",
    writer: "Agent, live during the call",
    purpose: "Speaker-labelled Bangla text, English translation added after the call, offset from call start, interruption flag. Append-only.",
  },
  {
    name: "call_extractions",
    grain: "One call",
    writer: "Post-call extraction job",
    purpose: "Structured fields kept apart from the raw transcript so extraction can be re-run (Reprocess) without touching the source.",
  },
  {
    name: "appointments",
    grain: "One booking",
    writer: "book / reschedule / cancel tools",
    purpose: "slot is a tstzrange; a GiST exclusion constraint makes overlapping active bookings for the same doctor impossible.",
  },
  {
    name: "callback_requests",
    grain: "One hand-over to a human",
    writer: "request_human_callback tool",
    purpose: "Staff queue. Staff may update only status and resolved_at (column-level grant).",
  },
  {
    name: "call_events",
    grain: "One event",
    writer: "Agent",
    purpose: "Audit trail: tool calls and results, state changes, errors and per-turn latency.",
  },
  {
    name: "leads",
    grain: "One demo request",
    writer: "Landing-page form",
    purpose: "The only table anonymous visitors can insert into.",
  },
  {
    name: "call_overview (view)",
    grain: "One call",
    writer: "—",
    purpose: "Joins calls, patients and extractions for the portal list; security_invoker keeps RLS in force.",
  },
];

export const STORAGE_FACTS: { label: string; value: string }[] = [
  { label: "Database", value: "Supabase Postgres 17, project bytevoice-bangla" },
  { label: "Region", value: "ap-southeast-1 (Singapore), the nearest Supabase region to Dhaka" },
  { label: "Access control", value: "Row Level Security on every table; staff read, anonymous visitors may only insert leads" },
  { label: "Writes", value: "Only the Python agent writes call data, with a server-side service-role key that never reaches the browser" },
  { label: "Realtime", value: "calls, transcript_turns and call_events are published, so the portal updates during the call" },
  { label: "Recordings", value: "Not stored in this demo; the planned design is a private bucket served through short-lived signed URLs" },
  { label: "Patient data", value: "Fake demo data only; phone numbers stored in E.164" },
];

export const VALIDATION_RULES: { field: string; rule: string; enforcedIn: string }[] = [
  { field: "Phone", rule: "Bangla digits and spoken digit words (incl. ডাবল / double) normalised, then ^01[3-9]\\d{8}$, stored as +8801…", enforcedIn: "Agent normaliser and DB CHECK" },
  { field: "Appointment slot", rule: "Inside the doctor's schedule and clinic hours, not in the past, not Friday", enforcedIn: "check_availability tool and DB exclusion constraint" },
  { field: "Booking", rule: "Needs an explicit caller confirmation (confirmed = true) after the read-back", enforcedIn: "book_appointment tool" },
  { field: "Transcript order", rule: "(call_id, seq) is unique", enforcedIn: "DB unique constraint" },
  { field: "Extracted fields", rule: "LLM output re-checked by the same validators; disagreements are flagged in confidence", enforcedIn: "Agent API finalize step" },
];
