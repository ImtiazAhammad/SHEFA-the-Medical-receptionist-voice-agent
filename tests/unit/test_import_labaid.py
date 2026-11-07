"""Parsing of the public doctor listing; no network."""

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

SPEC = importlib.util.spec_from_file_location(
    "import_labaid", Path(__file__).parents[2] / "scripts" / "import_labaid_directory.py"
)
labaid = importlib.util.module_from_spec(SPEC)
sys.modules["import_labaid"] = labaid
SPEC.loader.exec_module(labaid)

CARD = """
<div class="featured-thumbnail"><img src="x.jpg"></div>
<div class="featured-iconbox"><a href="https://labaid.com.bd/en/doctor/dr.-a-b"><i></i></a></div>
<div class="featured-title"><h5 class="mb-0"><a href="https://labaid.com.bd/en/doctor/dr.-a-b">
 Prof. Dr. A B Chowdhury </a></h5></div>
<div class="ttm-team-position"><span>Senior Consultant Cardiologist</span>
<p>LABAID Cardiac Hospital </p></div>
"""
PROFILE = "<div>Speciality</div><div><span>MBBS, FCPS (Medicine)</span></div>"


def test_listing_card_is_parsed():
    [doctor] = labaid.parse_listing(CARD)
    assert doctor == {
        "url": "https://labaid.com.bd/en/doctor/dr.-a-b",
        "name": "Prof. Dr. A B Chowdhury",
        "designation": "Senior Consultant Cardiologist",
        "hospital": "LABAID Cardiac Hospital",
    }


def test_qualification_comes_from_the_profile_page():
    assert labaid.parse_qualification(PROFILE) == "MBBS, FCPS (Medicine)"
    assert labaid.parse_qualification("<p>nothing</p>") == ""


@pytest.mark.parametrize(
    ("full", "bare"),
    [
        ("Prof. Dr. Baren Chakraborty", "Baren Chakraborty"),
        ("Professor. (Dr.) F. M. Siddiqui", "F. M. Siddiqui"),
        ("Dr. Md. Asifudduza (Asif)", "Md. Asifudduza"),
        ("Brig. Gen. Professor Nurunnahar Fatema", "Nurunnahar Fatema"),
    ],
)
def test_titles_are_dropped_from_names(full, bare):
    assert labaid.bare_name(full) == bare


@pytest.mark.parametrize(
    ("designation", "department"),
    [
        ("Senior Consultant Cardiologist", "Cardiology"),
        ("Specialist in Neurology & Internal Medicine", "Neurology"),
        ("Ear, Nose & Throat Specialist (ENT)", "ENT"),
        ("General Surgeon, Head, Department of Surgery", "Surgery"),  # "ent" inside "Department"
        ("Gynecologist, Obstetrician", "Gynecology"),
    ],
)
def test_department_from_designation(designation, department):
    assert labaid.department_for(designation)[0] == department


def test_unknown_designation_has_no_department():
    assert labaid.department_for("Hospital Administrator") is None


def test_long_designations_are_cut_on_a_word():
    long = "Senior Consultant " * 20
    short = labaid.short_designation(long)
    assert len(short) <= 125 and short.endswith("...") and "Consu ..." not in short


def test_output_is_loadable_marked_placeholder_and_conditions_skip_surgeons(tmp_path):
    doctors = [
        {
            "url": "u1",
            "name": "Dr. X Rahman",
            "designation": "Consultant Cardiologist",
            "hospital": "H",
            "qualification": "MBBS",
        },
        {
            "url": "u2",
            "name": "Dr. Y Khan",
            "designation": "Cardiac Surgeon",
            "hospital": "H",
            "qualification": "MS",
        },
        {
            "url": "u3",
            "name": "Dr. Z Ali",
            "designation": "Orthopedic Surgeon",
            "hospital": "H",
            "qualification": "MS",
        },
    ]
    directory = labaid.build(doctors, limit=10, per_department=2)
    text = labaid.to_yaml(directory)
    assert "PLACEHOLDERS" in text and "# source: u1" in text and "&id" not in text
    loaded = yaml.safe_load(text)
    by_name = {d["name"]: d for dep in loaded["departments"] for d in dep["doctors"]}
    assert "conditions" in by_name["X Rahman"]["profile"]
    assert "conditions" not in by_name["Y Khan"]["profile"]  # a cardiac surgeon, not a clinic GP
    assert "conditions" in by_name["Z Ali"]["profile"]  # orthopaedic surgeons see outpatients


def test_per_department_and_total_limits():
    doctors = [
        {"url": f"u{i}", "name": f"Dr. N{i}", "designation": "Cardiologist", "hospital": ""}
        for i in range(5)
    ]
    built = labaid.build(doctors, limit=10, per_department=2)
    assert sum(len(d["doctors"]) for d in built["departments"]) == 2


def test_bangla_names_are_added_where_known_and_a_clinic_file_overrides_them():
    doctors = [
        {"url": "u1", "name": "Dr. Lutfor Rahman", "designation": "Cardiologist", "hospital": ""},
        {"url": "u2", "name": "Dr. Nobody Known", "designation": "Cardiologist", "hospital": ""},
    ]
    built = labaid.build(doctors, limit=10, per_department=5)
    by_name = {d["name"]: d for dep in built["departments"] for d in dep["doctors"]}
    assert by_name["Lutfor Rahman"]["name_bn"] == "লুৎফর রহমান"
    assert "name_bn" not in by_name["Nobody Known"]  # never guessed for an unknown name
    own = labaid.build(doctors, 10, 5, {"Nobody Known": "কেউ না"})
    names = {d["name"]: d.get("name_bn") for dep in own["departments"] for d in dep["doctors"]}
    assert names == {"Lutfor Rahman": None, "Nobody Known": "কেউ না"}
    assert "UNVERIFIED" in labaid.to_yaml(built)
