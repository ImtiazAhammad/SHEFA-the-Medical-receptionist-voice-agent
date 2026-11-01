"""Importing a clinic's directory from YAML, and the `shefa clinic` commands."""

from __future__ import annotations

import pytest

from shefa.cli import main
from shefa.clinic import ClinicError, ClinicStore, default_clinic_store
from shefa.clinic.loader import import_directory, import_directory_file

DIRECTORY = {
    "departments": [
        {
            "name": "Cardiology",
            "name_bn": "হৃদরোগ",
            "doctors": [
                {
                    "name": "Rahman",
                    "name_bn": "রহমান",
                    "qualification": "MBBS",
                    "visit_fee": 800,
                    "schedule": [
                        {
                            "days": ["Mon", "Wednesday"],
                            "start": "09:00",
                            "end": "10:00",
                            "slot_minutes": 30,
                        }
                    ],
                    "leave": [{"from": "2026-11-09", "to": "2026-11-09", "reason": "conf"}],
                }
            ],
        }
    ]
}


@pytest.fixture
def store(tmp_path):
    with ClinicStore(tmp_path / "loader.db") as opened:
        yield opened


def test_import_builds_the_whole_directory(store):
    counts = import_directory(store, DIRECTORY)
    assert counts == {"departments": 1, "doctors": 1, "windows": 2, "leaves": 1}
    doctor = store.find_doctor("rahman")
    assert doctor["visit_fee"] == 800 and doctor["department_bn"] == "হৃদরোগ"
    assert [s["day"] for s in store.doctor_schedule(doctor["id"])] == ["Monday", "Wednesday"]
    assert store.doctor_on_leave(doctor["id"], "2026-11-09")


def test_reimport_restates_schedule_and_keeps_appointments(store):
    import_directory(store, DIRECTORY)
    doctor_id = store.find_doctor("rahman")["id"]
    patient = store.upsert_patient("+8801711000001", "Karim")
    booked = store.book(patient, doctor_id, "2026-11-30", "09:00")

    changed = {
        "departments": [
            {
                "name": "Cardiology",
                "doctors": [
                    {
                        "name": "RAHMAN",
                        "visit_fee": 900,
                        "schedule": [{"days": ["Mon"], "start": "09:00", "end": "11:00"}],
                    }
                ],
            }
        ]
    }
    import_directory(store, changed)
    assert len(store.doctors()) == 1
    assert store.find_doctor("rahman")["visit_fee"] == 900
    assert [s["day"] for s in store.doctor_schedule(doctor_id)] == ["Monday"]
    assert not store.doctor_on_leave(doctor_id, "2026-11-09")
    assert store.get_appointment(booked["appointment_id"])["status"] == "booked"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"departments": [{"name_bn": "x"}]}, "needs a 'name'"),
        ({"departments": [{"name": "A", "doctors": [{}]}]}, "needs a 'name'"),
        (
            {
                "departments": [
                    {"name": "A", "doctors": [{"name": "D", "schedule": [{"days": ["Mon"]}]}]}
                ]
            },
            "needs a 'start'",
        ),
        (
            {
                "departments": [
                    {
                        "name": "A",
                        "doctors": [
                            {
                                "name": "D",
                                "schedule": [
                                    {"days": ["Funday"], "start": "09:00", "end": "10:00"}
                                ],
                            }
                        ],
                    }
                ]
            },
            "Unknown weekday",
        ),
    ],
)
def test_bad_directories_are_named_errors(store, data, message):
    with pytest.raises(ClinicError, match=message):
        import_directory(store, data)


def test_empty_directory_imports_nothing(store):
    assert import_directory(store, {}) == {
        "departments": 0,
        "doctors": 0,
        "windows": 0,
        "leaves": 0,
    }


def test_file_import_requires_a_mapping(store, tmp_path):
    good = tmp_path / "clinic.yaml"
    good.write_text("departments:\n  - name: General\n", encoding="utf-8")
    assert import_directory_file(store, good)["departments"] == 1
    bad = tmp_path / "list.yaml"
    bad.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ClinicError, match="YAML mapping"):
        import_directory_file(store, bad)


def test_cli_import_and_show(tmp_path, capsys):
    path = tmp_path / "clinic.yaml"
    path.write_text(
        "departments:\n"
        "  - name: Medicine\n"
        "    doctors:\n"
        "      - name: Hossain\n"
        "        schedule:\n"
        "          - {days: [Sat], start: '09:00', end: '12:00'}\n"
        "      - name: Idle\n",
        encoding="utf-8",
    )
    assert main(["clinic", "import", str(path)]) == 0
    assert "imported 1 departments, 2 doctors, 1 schedule windows, 0 leave periods" in (
        capsys.readouterr().out
    )
    assert main(["clinic", "show"]) == 0
    shown = capsys.readouterr().out
    assert "Hossain" in shown and "Sat 09:00-12:00" in shown and "no schedule" in shown
    assert default_clinic_store().find_doctor("hossain")


def test_cli_import_failures_exit_nonzero(tmp_path, capsys):
    assert main(["clinic", "import", str(tmp_path / "missing.yaml")]) == 1
    assert "import failed" in capsys.readouterr().err
    broken = tmp_path / "broken.yaml"
    broken.write_text("departments: [unclosed", encoding="utf-8")
    assert main(["clinic", "import", str(broken)]) == 1
    assert main(["clinic"]) == 2
    assert "usage: shefa clinic" in capsys.readouterr().err
