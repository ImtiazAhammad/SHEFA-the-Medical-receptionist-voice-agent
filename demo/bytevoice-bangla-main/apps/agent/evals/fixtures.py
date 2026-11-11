from datetime import time
from uuid import UUID

from agent.schemas.catalog import Clinic, ClinicCatalog, Doctor, DoctorSchedule, Service

CLINIC_ID = UUID("a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01")
DOCTOR_IDS = {
    "ruhan": UUID("d0c70001-0000-4000-8000-000000000001"),
    "nusrat": UUID("d0c70001-0000-4000-8000-000000000002"),
    "rakib": UUID("d0c70001-0000-4000-8000-000000000003"),
}
_SERVICES = [
    ("checkup", "চেকআপ ও কনসালটেশন", "Check-up and consultation", 20, 800, False),
    ("scaling", "স্কেলিং ও পলিশ", "Scaling and polishing", 40, 2500, False),
    ("filling", "ফিলিং", "Filling", 40, 2000, True),
    ("root_canal", "রুট ক্যানেল", "Root canal treatment", 60, 8000, True),
    ("extraction", "দাঁত তোলা", "Tooth extraction", 30, 1500, True),
    ("braces_consult", "ব্রেসেস কনসালটেশন", "Braces consultation", 30, 1000, False),
    ("whitening", "দাঁত সাদা করা (whitening)", "Teeth whitening", 60, 6000, True),
]
_DOCTOR_SERVICES = {
    "ruhan": {"checkup", "root_canal", "filling", "whitening"},
    "nusrat": {"checkup", "braces_consult", "filling"},
    "rakib": {"checkup", "scaling", "filling", "extraction"},
}
_SCHEDULES = (
    [("ruhan", weekday, time(16), time(21)) for weekday in (6, 0, 2, 4)]
    + [("nusrat", weekday, time(10), time(16)) for weekday in (6, 1, 3)]
    + [
        ("rakib", 6, time(10), time(14)),
        *[("rakib", weekday, time(10), time(17)) for weekday in (0, 1, 2, 3, 4)],
    ]
)


def build_seed_catalog() -> ClinicCatalog:
    """The same clinic, doctors, services and schedules as supabase/seed.sql, for offline evals."""
    open_day = ["10:00", "21:00"]
    services = [
        Service(
            id=UUID(f"5e7f0001-0000-4000-8000-00000000000{index + 1}"),
            code=code,
            name_bn=name_bn,
            name_en=name_en,
            duration_min=duration,
            fee_bdt=fee,
            fee_is_starting_price=starting,
        )
        for index, (code, name_bn, name_en, duration, fee, starting) in enumerate(_SERVICES)
    ]
    service_ids = {service.code: service.id for service in services}
    return ClinicCatalog(
        clinic=Clinic(
            id=CLINIC_ID,
            name_bn="ওয়ান স্মাইল ডেন্টাল লাউঞ্জ",
            name_en="One Smile Dental Lounge",
            address_bn="বাড়ি ৩০, সেক্টর ১১, উত্তরা, ঢাকা (জমজম টাওয়ারের বিপরীতে)",
            phone="+8801700000000",
            opening_hours={day: open_day for day in ("sat", "sun", "mon", "tue", "wed", "thu")}
            | {"fri": None},
        ),
        doctors=[
            Doctor(
                id=DOCTOR_IDS["ruhan"],
                full_name_bn="ডা. মোঃ মুশফিকুর রুহান",
                full_name_en="Dr. Md. Musfiqur Ruhan",
                specialty_bn="মাইক্রো এন্ডোডন্টিস্ট ও এসথেটিক ডেন্টিস্ট",
            ),
            Doctor(
                id=DOCTOR_IDS["nusrat"],
                full_name_bn="ডা. নুসরাত জাহান",
                full_name_en="Dr. Nusrat Jahan",
                specialty_bn="শিশু দন্তরোগ ও অর্থোডন্টিক্স",
            ),
            Doctor(
                id=DOCTOR_IDS["rakib"],
                full_name_bn="ডা. রাকিব হাসান",
                full_name_en="Dr. Rakib Hasan",
                specialty_bn="জেনারেল ডেন্টিস্ট্রি",
            ),
        ],
        services=services,
        doctor_service_ids={
            DOCTOR_IDS[doctor]: {service_ids[code] for code in codes}
            for doctor, codes in _DOCTOR_SERVICES.items()
        },
        schedules=[
            DoctorSchedule(doctor_id=DOCTOR_IDS[doctor], weekday=weekday, start_time=start, end_time=end)
            for doctor, weekday, start, end in _SCHEDULES
        ],
    )
