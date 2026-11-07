"""Build a clinic directory file from Labaid's public doctor listing.

    python scripts/import_labaid_directory.py --limit 14 --out configs/clinic.labaid.local.yaml

What the site publishes (name, designation, qualification, hospital) is taken as is, with the
profile URL recorded next to each doctor. What it does NOT publish (visiting days and hours, fees,
rooms) is not invented: a placeholder weekly schedule is written so the booking engine has slots
to offer, and it is marked as a placeholder in the file. Replace it with the clinic's real one.

Courtesy: robots.txt is checked before every host is used, requests are one per second with a
plain client name, and the output file is gitignored so the scraped records are not republished
in this repository. Use only for a local demo.
"""

from __future__ import annotations

import argparse
import html
import re
import time
import urllib.request
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

import yaml

LISTING = "https://labaid.com.bd/en/doctors"
AGENT = "SHEFA-research/0.1 (polite; low volume; local demo)"
DELAY_S = 1.0

# (keyword in the designation, department English, department Bangla). First match wins.
DEPARTMENTS = [
    ("cardi", "Cardiology", "হৃদরোগ"),
    ("neuro", "Neurology", "স্নায়ুরোগ"),
    ("nephro", "Nephrology", "কিডনি রোগ"),
    ("urolog", "Urology", "ইউরোলজি"),
    ("gastro", "Gastroenterology", "গ্যাস্ট্রোএন্টারোলজি"),
    ("pediatric", "Pediatrics", "শিশু"),
    ("paediatric", "Pediatrics", "শিশু"),
    ("gynae", "Gynecology", "গাইনি"),
    ("gynec", "Gynecology", "গাইনি"),
    ("obstet", "Gynecology", "গাইনি"),
    ("orthop", "Orthopedics", "অর্থোপেডিক্স"),
    ("ent", "ENT", "নাক কান গলা"),
    ("dermat", "Dermatology", "চর্মরোগ"),
    ("oncolog", "Oncology", "ক্যান্সার"),
    ("endocrin", "Endocrinology", "ডায়াবেটিস ও হরমোন"),
    ("medicine", "Medicine", "মেডিসিন"),
    ("physician", "Medicine", "মেডিসিন"),
    ("surg", "Surgery", "সার্জারি"),
]
# What each department generally sees. It is about the department, not the individual doctor,
# and is the only text in the output that does not come from the site.
CONDITIONS = {
    "Cardiology": (
        ["high blood pressure", "palpitations", "heart check-up", "follow-up after a heart issue"],
        ["উচ্চ রক্তচাপ", "বুক ধড়ফড়", "হার্ট চেকআপ", "হৃদরোগের পর ফলো-আপ"],
    ),
    "Neurology": (
        ["headache", "dizziness", "numbness", "epilepsy follow-up"],
        ["মাথা ব্যথা", "মাথা ঘোরা", "অসাড়তা", "মৃগীরোগের ফলো-আপ"],
    ),
    "Pediatrics": (
        ["child fever", "cough and cold in children", "vaccination", "newborn care"],
        ["বাচ্চার জ্বর", "বাচ্চার সর্দি কাশি", "টিকা", "নবজাতকের যত্ন"],
    ),
    "Gynecology": (
        ["pregnancy care", "period problems", "women's health check-up"],
        ["গর্ভকালীন সেবা", "মাসিকের সমস্যা", "মহিলাদের স্বাস্থ্য পরীক্ষা"],
    ),
    "Orthopedics": (
        ["joint pain", "back pain", "fracture follow-up"],
        ["জয়েন্টে ব্যথা", "কোমর ব্যথা", "হাড় ভাঙার ফলো-আপ"],
    ),
    "Medicine": (
        ["fever", "diabetes", "thyroid", "stomach pain", "general check-up"],
        ["জ্বর", "ডায়াবেটিস", "থাইরয়েড", "পেট ব্যথা", "সাধারণ চেকআপ"],
    ),
    "Gastroenterology": (
        ["gastric problems", "liver problems", "stomach pain"],
        ["গ্যাস্ট্রিকের সমস্যা", "লিভারের সমস্যা", "পেট ব্যথা"],
    ),
    "Nephrology": (["kidney problems", "dialysis"], ["কিডনির সমস্যা", "ডায়ালাইসিস"]),
    "Urology": (["urinary problems", "kidney stones"], ["প্রস্রাবের সমস্যা", "কিডনিতে পাথর"]),
    "ENT": (["ear pain", "sore throat", "sinus"], ["কান ব্যথা", "গলা ব্যথা", "সাইনাস"]),
    "Dermatology": (["skin rash", "acne", "hair loss"], ["চর্মের র‍্যাশ", "ব্রণ", "চুল পড়া"]),
    "Endocrinology": (["diabetes", "thyroid"], ["ডায়াবেটিস", "থাইরয়েড"]),
}
# A surgeon in these departments still sees outpatients for the department's usual problems; a
# cardiac or neuro surgeon does not see "high blood pressure" or "headache", so gets no list.
SURGEONS_WHO_SEE_OUTPATIENTS = {"Orthopedics", "Urology", "Gynecology", "ENT"}
PLACEHOLDER_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu"]

_robots: dict[str, robotparser.RobotFileParser] = {}
_last = 0.0


def fetch(url: str) -> str:
    """GET ``url`` if robots.txt allows it, at most one request per second."""
    global _last
    host = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if host not in _robots:
        parser = robotparser.RobotFileParser(f"{host}/robots.txt")
        parser.read()
        _robots[host] = parser
    if not _robots[host].can_fetch(AGENT, url):
        raise SystemExit(f"robots.txt at {host} does not allow {url}; stopping")
    wait = DELAY_S - (time.monotonic() - _last)
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        _last = time.monotonic()
        return response.read().decode("utf-8", errors="ignore")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_listing(page: str) -> list[dict[str, str]]:
    doctors = []
    for card in re.split(r'<div class="featured-thumbnail">', page)[1:]:
        link = re.search(r'href="(https://labaid\.com\.bd/en/doctor/[^"]+)"', card)
        name = re.search(r'<h5 class="mb-0">(.*?)</h5>', card, re.S)
        role = re.search(r'<div class="ttm-team-position">\s*<span>(.*?)</span>', card, re.S)
        hospital = re.search(r"<p>\s*([^<]+?)\s*</p>", card.split("ttm-team-position")[-1])
        if link and name and role:
            doctors.append(
                {
                    "url": link.group(1),
                    "name": _text(name.group(1)),
                    "designation": _text(role.group(1)),
                    "hospital": _text(hospital.group(1)) if hospital else "",
                }
            )
    return doctors


def parse_qualification(page: str) -> str:
    match = re.search(r"Speciality\s*</[^>]+>\s*(?:<[^>]+>\s*)*([^<]+)", page, re.S)
    return _text(match.group(1)) if match else ""


def department_for(designation: str) -> tuple[str, str] | None:
    text = designation.lower()
    for keyword, english, bangla in DEPARTMENTS:
        # Whole-word start: "ent" must not match inside "Department".
        if re.search(rf"\b{re.escape(keyword)}" + (r"\b" if len(keyword) <= 3 else ""), text):
            return english, bangla
    return None


def short_designation(text: str, limit: int = 120) -> str:
    """The designation, cut at a word boundary: some run to several lines of titles."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",&- ") + " ..."


def bare_name(full: str) -> str:
    """'Prof. Dr. Baren Chakraborty' -> 'Baren Chakraborty'."""
    cleaned = re.sub(r"(?i)\b(prof(?:essor)?|dr|brig|gen|maj|col)\b\.?", " ", full)
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned.replace("-", " ")).strip(" .,")


def build(doctors: list[dict[str, str]], limit: int, per_department: int) -> dict:
    chosen: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for doctor in doctors:
        department = department_for(doctor["designation"])
        if not department or counts.get(department[0], 0) >= per_department:
            continue
        counts[department[0]] = counts.get(department[0], 0) + 1
        chosen.append({**doctor, "department": department})
        if len(chosen) >= limit:
            break
    departments: dict[str, dict] = {}
    for doctor in chosen:
        english, bangla = doctor["department"]
        group = departments.setdefault(english, {"name": english, "name_bn": bangla, "doctors": []})
        profile: dict = {"designation": short_designation(doctor["designation"])}
        surgeon = "surgeon" in doctor["designation"].lower()
        if english in CONDITIONS and (not surgeon or english in SURGEONS_WHO_SEE_OUTPATIENTS):
            profile["conditions"] = {"en": CONDITIONS[english][0], "bn": CONDITIONS[english][1]}
        group["doctors"].append(
            {
                "name": bare_name(doctor["name"]) or doctor["name"],
                "qualification": doctor.get("qualification", ""),
                "profile": profile,
                "schedule": [
                    {"days": PLACEHOLDER_DAYS, "start": "10:00", "end": "13:00", "slot_minutes": 15}
                ],
                "_source": doctor["url"],
            }
        )
    return {"departments": list(departments.values())}


def to_yaml(directory: dict) -> str:
    header = (
        "# Doctors listed on https://labaid.com.bd/en/doctors (name, designation, qualification).\n"
        "# LOCAL DEMO ONLY. Generated by scripts/import_labaid_directory.py; not committed.\n"
        "# SCHEDULES ARE PLACEHOLDERS and there are no fees or rooms: the site does not publish\n"
        "# them. Replace them with the clinic's real ones before anyone relies on this.\n"
        "# 'conditions' describe the department in general, not the individual doctor.\n"
    )

    class Plain(yaml.SafeDumper):
        def ignore_aliases(self, data):  # repeat lists instead of writing &id001 anchors
            return True

    body = yaml.dump(directory, Dumper=Plain, allow_unicode=True, sort_keys=False, width=100)
    return header + re.sub(r"(\n\s+)_source: (\S+)", r"\1# source: \2", body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=14)
    parser.add_argument("--per-department", type=int, default=2)
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--out", default="configs/clinic.labaid.local.yaml")
    args = parser.parse_args()

    listed: list[dict[str, str]] = []
    for number in range(1, args.pages + 1):
        listed += parse_listing(fetch(f"{LISTING}?page={number}"))
    print(f"{len(listed)} doctors listed")
    # Pick first, then fetch profiles for only the chosen ones.
    pick = build(listed, args.limit, args.per_department)
    chosen_urls = {d["_source"] for dep in pick["departments"] for d in dep["doctors"]}
    qualifications = {url: parse_qualification(fetch(url)) for url in sorted(chosen_urls)}
    for department in pick["departments"]:
        for doctor in department["doctors"]:
            doctor["qualification"] = qualifications.get(doctor["_source"], "")
    Path(args.out).write_text(to_yaml(pick), encoding="utf-8")
    total = sum(len(d["doctors"]) for d in pick["departments"])
    print(f"wrote {total} doctors in {len(pick['departments'])} departments to {args.out}")


if __name__ == "__main__":
    main()
