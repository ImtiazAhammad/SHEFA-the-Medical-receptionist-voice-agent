insert into public.clinics (id, name_bn, name_en, address_bn, address_en, phone, map_url, opening_hours)
values (
  'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01',
  'ওয়ান স্মাইল ডেন্টাল লাউঞ্জ',
  'One Smile Dental Lounge',
  'বাড়ি ৩০, সেক্টর ১১, উত্তরা, ঢাকা (জমজম টাওয়ারের বিপরীতে)',
  'House 30, Sector 11, Uttara, Dhaka (opposite Zamzam Tower)',
  '+8801700000000',
  'https://maps.google.com/?q=Sector+11+Uttara+Dhaka',
  '{"sat": ["10:00", "21:00"], "sun": ["10:00", "21:00"], "mon": ["10:00", "21:00"], "tue": ["10:00", "21:00"], "wed": ["10:00", "21:00"], "thu": ["10:00", "21:00"], "fri": null}'::jsonb
)
on conflict (id) do nothing;

insert into public.doctors (id, clinic_id, full_name_bn, full_name_en, specialty_bn, specialty_en)
values
  ('d0c70001-0000-4000-8000-000000000001', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01',
   'ডা. মোঃ মুশফিকুর রুহান', 'Dr. Md. Musfiqur Ruhan',
   'মাইক্রো এন্ডোডন্টিস্ট ও এসথেটিক ডেন্টিস্ট', 'Micro-endodontist and aesthetic dentist'),
  ('d0c70001-0000-4000-8000-000000000002', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01',
   'ডা. নুসরাত জাহান', 'Dr. Nusrat Jahan',
   'শিশু দন্তরোগ ও অর্থোডন্টিক্স', 'Paediatric dentistry and orthodontics'),
  ('d0c70001-0000-4000-8000-000000000003', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01',
   'ডা. রাকিব হাসান', 'Dr. Rakib Hasan',
   'জেনারেল ডেন্টিস্ট্রি', 'General dentistry')
on conflict (id) do nothing;

insert into public.services (id, clinic_id, code, name_bn, name_en, duration_min, fee_bdt, fee_is_starting_price, prep_notes_bn, prep_notes_en)
values
  ('5e7f0001-0000-4000-8000-000000000001', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01', 'checkup',
   'চেকআপ ও কনসালটেশন', 'Check-up and consultation', 20, 800, false,
   'আগের ডেন্টাল এক্স-রে বা প্রেসক্রিপশন থাকলে সাথে আনবেন।', 'Bring any previous dental X-rays or prescriptions.'),
  ('5e7f0001-0000-4000-8000-000000000002', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01', 'scaling',
   'স্কেলিং ও পলিশ', 'Scaling and polishing', 40, 2500, false,
   'আসার আগে স্বাভাবিকভাবে খাওয়া-দাওয়া করতে পারেন।', 'You can eat normally before the visit.'),
  ('5e7f0001-0000-4000-8000-000000000003', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01', 'filling',
   'ফিলিং', 'Filling', 40, 2000, true, null, null),
  ('5e7f0001-0000-4000-8000-000000000004', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01', 'root_canal',
   'রুট ক্যানেল', 'Root canal treatment', 60, 8000, true,
   'আগের এক্স-রে থাকলে সাথে আনবেন; প্রথম সেশনে প্রায় এক ঘণ্টা লাগতে পারে।', 'Bring previous X-rays; the first session can take about an hour.'),
  ('5e7f0001-0000-4000-8000-000000000005', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01', 'extraction',
   'দাঁত তোলা', 'Tooth extraction', 30, 1500, true,
   'আসার আগে হালকা কিছু খেয়ে আসবেন।', 'Have a light meal before the visit.'),
  ('5e7f0001-0000-4000-8000-000000000006', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01', 'braces_consult',
   'ব্রেসেস কনসালটেশন', 'Braces consultation', 30, 1000, false, null, null),
  ('5e7f0001-0000-4000-8000-000000000007', 'a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01', 'whitening',
   'দাঁত সাদা করা (whitening)', 'Teeth whitening', 60, 6000, true, null, null)
on conflict (id) do nothing;

insert into public.doctor_services (doctor_id, service_id)
select doctor.id, service.id
from (values
  ('d0c70001-0000-4000-8000-000000000001'::uuid, 'checkup'),
  ('d0c70001-0000-4000-8000-000000000001'::uuid, 'root_canal'),
  ('d0c70001-0000-4000-8000-000000000001'::uuid, 'filling'),
  ('d0c70001-0000-4000-8000-000000000001'::uuid, 'whitening'),
  ('d0c70001-0000-4000-8000-000000000002'::uuid, 'checkup'),
  ('d0c70001-0000-4000-8000-000000000002'::uuid, 'braces_consult'),
  ('d0c70001-0000-4000-8000-000000000002'::uuid, 'filling'),
  ('d0c70001-0000-4000-8000-000000000003'::uuid, 'checkup'),
  ('d0c70001-0000-4000-8000-000000000003'::uuid, 'scaling'),
  ('d0c70001-0000-4000-8000-000000000003'::uuid, 'filling'),
  ('d0c70001-0000-4000-8000-000000000003'::uuid, 'extraction')
) as pairing (doctor_id, service_code)
join public.doctors doctor on doctor.id = pairing.doctor_id
join public.services service on service.code = pairing.service_code and service.clinic_id = doctor.clinic_id
on conflict do nothing;

insert into public.doctor_schedules (doctor_id, weekday, start_time, end_time)
select doctor_id::uuid, weekday, start_time::time, end_time::time
from (values
  ('d0c70001-0000-4000-8000-000000000001', 6, '16:00', '21:00'),
  ('d0c70001-0000-4000-8000-000000000001', 0, '16:00', '21:00'),
  ('d0c70001-0000-4000-8000-000000000001', 2, '16:00', '21:00'),
  ('d0c70001-0000-4000-8000-000000000001', 4, '16:00', '21:00'),
  ('d0c70001-0000-4000-8000-000000000002', 6, '10:00', '16:00'),
  ('d0c70001-0000-4000-8000-000000000002', 1, '10:00', '16:00'),
  ('d0c70001-0000-4000-8000-000000000002', 3, '10:00', '16:00'),
  ('d0c70001-0000-4000-8000-000000000003', 6, '10:00', '14:00'),
  ('d0c70001-0000-4000-8000-000000000003', 0, '10:00', '17:00'),
  ('d0c70001-0000-4000-8000-000000000003', 1, '10:00', '17:00'),
  ('d0c70001-0000-4000-8000-000000000003', 2, '10:00', '17:00'),
  ('d0c70001-0000-4000-8000-000000000003', 3, '10:00', '17:00'),
  ('d0c70001-0000-4000-8000-000000000003', 4, '10:00', '17:00')
) as schedule (doctor_id, weekday, start_time, end_time)
where not exists (select 1 from public.doctor_schedules existing where existing.doctor_id = schedule.doctor_id::uuid);
