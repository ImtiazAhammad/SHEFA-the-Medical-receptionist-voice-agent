create extension if not exists btree_gist with schema extensions;

create type public.call_status as enum ('in_progress', 'completed', 'failed');
create type public.call_outcome as enum (
  'booked', 'rescheduled', 'cancelled', 'enquiry', 'follow_up_needed', 'incomplete', 'failed'
);
create type public.speaker_role as enum ('agent', 'caller');
create type public.appointment_status as enum ('booked', 'rescheduled', 'cancelled', 'completed', 'no_show');
create type public.callback_status as enum ('open', 'in_progress', 'done');

create table public.clinics (
  id uuid primary key default gen_random_uuid(),
  name_bn text not null,
  name_en text not null,
  address_bn text,
  address_en text,
  phone text,
  map_url text,
  timezone text not null default 'Asia/Dhaka',
  opening_hours jsonb not null,
  created_at timestamptz not null default now()
);

create table public.doctors (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id),
  full_name_bn text not null,
  full_name_en text not null,
  specialty_bn text,
  specialty_en text,
  is_active boolean not null default true
);

create table public.services (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id),
  code text not null,
  name_bn text not null,
  name_en text not null,
  duration_min int not null check (duration_min > 0),
  fee_bdt int not null check (fee_bdt >= 0),
  fee_is_starting_price boolean not null default false,
  prep_notes_bn text,
  prep_notes_en text,
  unique (clinic_id, code)
);

create table public.doctor_services (
  doctor_id uuid not null references public.doctors (id) on delete cascade,
  service_id uuid not null references public.services (id) on delete cascade,
  primary key (doctor_id, service_id)
);

create table public.doctor_schedules (
  id uuid primary key default gen_random_uuid(),
  doctor_id uuid not null references public.doctors (id) on delete cascade,
  weekday smallint not null check (weekday between 0 and 6),
  start_time time not null,
  end_time time not null,
  check (end_time > start_time)
);

create table public.patients (
  id uuid primary key default gen_random_uuid(),
  full_name_bn text,
  full_name_en text,
  phone_e164 text unique check (phone_e164 ~ '^\+8801[3-9][0-9]{8}$'),
  created_at timestamptz not null default now()
);

create table public.calls (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id),
  patient_id uuid references public.patients (id),
  room_name text not null unique,
  channel text not null default 'web',
  engine text not null,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  duration_s int generated always as (extract(epoch from (ended_at - started_at))::int) stored,
  status public.call_status not null default 'in_progress',
  outcome public.call_outcome,
  after_hours boolean not null default false,
  summary_bn text,
  summary_en text,
  recording_path text,
  check (ended_at is null or ended_at >= started_at)
);

create table public.transcript_turns (
  id bigint generated always as identity primary key,
  call_id uuid not null references public.calls (id) on delete cascade,
  seq int not null,
  speaker public.speaker_role not null,
  text_bn text not null,
  text_en text,
  offset_ms int not null check (offset_ms >= 0),
  interrupted boolean not null default false,
  created_at timestamptz not null default now(),
  unique (call_id, seq)
);

create table public.call_extractions (
  call_id uuid primary key references public.calls (id) on delete cascade,
  intent text check (intent in ('book', 'reschedule', 'cancel', 'enquiry', 'other')),
  patient_name_bn text,
  patient_name_en text,
  name_confirmed boolean,
  phone_spoken_raw text,
  phone_e164 text,
  phone_valid boolean,
  reason_for_visit text,
  service_code text,
  preferred_date date,
  preferred_time_window text,
  confidence jsonb not null default '{}'::jsonb,
  extractor_model text,
  extracted_at timestamptz not null default now()
);

create table public.appointments (
  id uuid primary key default gen_random_uuid(),
  clinic_id uuid not null references public.clinics (id),
  patient_id uuid not null references public.patients (id),
  doctor_id uuid not null references public.doctors (id),
  service_id uuid not null references public.services (id),
  call_id uuid references public.calls (id),
  slot tstzrange not null check (not isempty(slot)),
  status public.appointment_status not null default 'booked',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint appointments_no_double_booking
    exclude using gist (doctor_id with =, slot with &&) where (status in ('booked', 'rescheduled'))
);

create table public.callback_requests (
  id uuid primary key default gen_random_uuid(),
  call_id uuid not null references public.calls (id) on delete cascade,
  patient_id uuid references public.patients (id),
  reason text not null,
  priority smallint not null default 2 check (priority between 1 and 3),
  status public.callback_status not null default 'open',
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table public.call_events (
  id bigint generated always as identity primary key,
  call_id uuid not null references public.calls (id) on delete cascade,
  occurred_at timestamptz not null default now(),
  event_type text not null check (event_type in ('state', 'tool_call', 'tool_result', 'latency', 'error')),
  payload jsonb not null default '{}'::jsonb
);

create table public.leads (
  id uuid primary key default gen_random_uuid(),
  contact_name text not null check (char_length(contact_name) between 1 and 120),
  organisation text check (char_length(organisation) <= 160),
  phone text check (char_length(phone) <= 32),
  email text check (char_length(email) <= 254),
  message text check (char_length(message) <= 2000),
  created_at timestamptz not null default now()
);

create index doctors_clinic_id_idx on public.doctors (clinic_id);
create index doctor_services_service_id_idx on public.doctor_services (service_id);
create index doctor_schedules_doctor_id_idx on public.doctor_schedules (doctor_id);
create index calls_started_at_idx on public.calls (started_at desc);
create index calls_outcome_idx on public.calls (outcome);
create index calls_clinic_id_idx on public.calls (clinic_id);
create index calls_patient_id_idx on public.calls (patient_id);
create index appointments_patient_id_idx on public.appointments (patient_id);
create index appointments_clinic_id_idx on public.appointments (clinic_id);
create index appointments_service_id_idx on public.appointments (service_id);
create index appointments_call_id_idx on public.appointments (call_id);
create index callback_requests_call_id_idx on public.callback_requests (call_id);
create index callback_requests_patient_id_idx on public.callback_requests (patient_id);
create index callback_requests_open_idx on public.callback_requests (created_at) where status <> 'done';
create index call_events_call_id_idx on public.call_events (call_id, occurred_at);

create view public.call_overview
with (security_invoker = true) as
select
  calls.id,
  calls.clinic_id,
  calls.room_name,
  calls.engine,
  calls.started_at,
  calls.ended_at,
  calls.duration_s,
  calls.status,
  calls.outcome,
  calls.after_hours,
  calls.summary_bn,
  calls.summary_en,
  coalesce(patients.full_name_bn, call_extractions.patient_name_bn) as caller_name_bn,
  coalesce(patients.full_name_en, call_extractions.patient_name_en) as caller_name_en,
  coalesce(patients.phone_e164, call_extractions.phone_e164) as caller_phone,
  call_extractions.intent,
  call_extractions.reason_for_visit,
  (select count(*) from public.transcript_turns turns where turns.call_id = calls.id) as turn_count
from public.calls
left join public.patients on patients.id = calls.patient_id
left join public.call_extractions on call_extractions.call_id = calls.id;

alter table public.clinics enable row level security;
alter table public.doctors enable row level security;
alter table public.services enable row level security;
alter table public.doctor_services enable row level security;
alter table public.doctor_schedules enable row level security;
alter table public.patients enable row level security;
alter table public.calls enable row level security;
alter table public.transcript_turns enable row level security;
alter table public.call_extractions enable row level security;
alter table public.appointments enable row level security;
alter table public.callback_requests enable row level security;
alter table public.call_events enable row level security;
alter table public.leads enable row level security;

create policy "Staff can read clinics" on public.clinics for select to authenticated using (true);
create policy "Staff can read doctors" on public.doctors for select to authenticated using (true);
create policy "Staff can read services" on public.services for select to authenticated using (true);
create policy "Staff can read doctor services" on public.doctor_services for select to authenticated using (true);
create policy "Staff can read doctor schedules" on public.doctor_schedules for select to authenticated using (true);
create policy "Staff can read patients" on public.patients for select to authenticated using (true);
create policy "Staff can read calls" on public.calls for select to authenticated using (true);
create policy "Staff can read transcript turns" on public.transcript_turns for select to authenticated using (true);
create policy "Staff can read call extractions" on public.call_extractions for select to authenticated using (true);
create policy "Staff can read appointments" on public.appointments for select to authenticated using (true);
create policy "Staff can read callback requests" on public.callback_requests for select to authenticated using (true);
create policy "Staff can update callback status" on public.callback_requests for update to authenticated
  using (true) with check (true);
create policy "Staff can read call events" on public.call_events for select to authenticated using (true);
create policy "Staff can read leads" on public.leads for select to authenticated using (true);
create policy "Visitors can submit leads" on public.leads for insert to anon, authenticated with check (true);

revoke update on public.callback_requests from authenticated;
grant update (status, resolved_at) on public.callback_requests to authenticated;

alter publication supabase_realtime add table public.calls, public.transcript_turns, public.call_events;
