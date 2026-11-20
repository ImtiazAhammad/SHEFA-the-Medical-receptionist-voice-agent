"""Version 2 scripts: branching calls to one fictional clinic, and the desk's recorded voices."""

# ruff: noqa: E501, N812
import random

import pytest

from shefa.collector import scripts as S
from tests.collector.conftest import make_wav
from tests.collector.test_review import bearer

CARDS = S.generate()
BOOKINGS = [c for c in CARDS if c["kind"] == "booking"]


def walk(card):
    """Every node reachable from the start."""
    seen, stack = set(), [card["start"]]
    while stack:
        nid = stack.pop()
        if nid in seen:
            continue
        seen.add(nid)
        stack += [c["next"] for c in card["nodes"][nid]["choices"] if c["next"]]
    return seen


def test_every_script_is_a_closed_graph_with_one_question_per_node():
    for card in CARDS:
        assert walk(card) == set(card["nodes"]), card["id"]
        for node in card["nodes"].values():
            assert node["line_bn"] and node["slot"] and len(node["audio_name"]) == 16
            for choice in node["choices"]:
                assert choice["hint_bn"] and (
                    choice["next"] is None or choice["next"] in card["nodes"]
                )
            if len(node["choices"]) > 1:  # a fork must say what each tap means
                assert all(c["label_bn"] for c in node["choices"])


def test_generation_is_deterministic():
    assert S.generate() == CARDS


def test_the_desk_opens_with_salam_and_the_clinic_name():
    for card in BOOKINGS:
        opening = card["nodes"]["open"]["line_bn"]
        assert "আসসালামু আলাইকুম" in opening and S.CLINIC in opening


def test_every_department_has_a_professor_an_associate_and_an_assistant():
    for dept in S.ROSTER.values():
        assert [d["rank_bn"] for d in dept["doctors"]] == ["অধ্যাপক", "সহযোগী অধ্যাপক", "সহকারী অধ্যাপক"]
        assert len({d["surname"] for d in dept["doctors"]}) == 3
    assert len({d["surname"] for dept in S.ROSTER.values() for d in dept["doctors"]}) == 69
    assert len(S.clinic_sheet()["doctors"]) == 69


def test_the_desk_lists_the_three_doctors_and_recommends_the_most_senior_when_asked():
    listed = [c for c in BOOKINGS if "list" in c["nodes"]]
    assert len(listed) > 80
    for card in listed:
        dept = next(d for d in S.ROSTER.values() if d["name"] == card["department"])
        line = card["nodes"]["list"]["line_bn"]
        assert all(d["title"] in line for d in dept["doctors"])
        ids = [c["id"] for c in card["nodes"]["list"]["choices"]]
        assert ids == ["p0", "p1", "p2", "advice", "sched", "fee"]
        rec = card["nodes"]["rec"]
        assert dept["doctors"][0]["title"] in rec["line_bn"] and "সিনিয়র" in rec["line_bn"]
        assert rec["choices"][0]["next"] == "d0.day"


def test_the_patient_is_a_pair_and_names_match_gender_and_age():
    male = set(S.NAMES["child_m"] + S.NAMES["adult_m"] + S.NAMES["elder_m"])
    female = set(S.NAMES["child_f"] + S.NAMES["adult_f"] + S.NAMES["elder_f"])
    assert not male & female
    for card in BOOKINGS:
        people = card["personas"]
        assert len(people) == 2 and people[0]["name"] != people[1]["name"]
        for p in people:
            assert p["name"] in (male if p["gender"] == "m" else female), (card["id"], p)
            if p["label_bn"] in ("বাবা", "মা", "শ্বশুর", "শাশুড়ি"):
                assert p["age"] >= 50
        if card["department"] == "শিশুরোগ":
            assert {p["label_bn"] for p in people} == {"ছেলে", "মেয়ে"} and all(
                p["age"] <= 12 for p in people
            )
        if card["department"] == "গাইনি":
            assert all(p["gender"] == "f" for p in people)
        if card["department"] != "গাইনি":
            assert {p["gender"] for p in people} == {"m", "f"}


def test_the_time_offered_is_for_a_day_that_doctor_sits_and_a_wrong_read_back_is_really_wrong():
    wrong = 0
    for card in BOOKINGS:
        for nid, node in card["nodes"].items():
            if nid.endswith(".confirm") and node["choices"][0]["facts"].get("agree") is False:
                facts = node["choices"][0]["facts"]
                assert facts["said"] != facts["right"]
                wrong += 1
            if nid.endswith(".daybad"):
                assert "বসেন না" in node["line_bn"]
    assert wrong > 20


def test_a_call_can_be_short_or_long():
    def turns(card, nid, pick):
        count = 0
        while nid:
            choices = card["nodes"][nid]["choices"]
            if not choices:
                break
            count += 1
            nid = pick(choices)["next"]
        return count

    rng = random.Random(1)
    lengths = [turns(c, c["start"], rng.choice) for c in BOOKINGS for _ in range(4)]
    assert min(lengths) >= 5 and max(lengths) >= 12


def test_hints_never_show_a_24_hour_clock():
    for card in BOOKINGS:
        for node in card["nodes"].values():
            for choice in node["choices"]:
                assert not any(
                    f"{h}:" in choice["hint_bn"]
                    for h in ("১৩", "১৪", "১৫", "১৬", "১৭", "১৮", "১৯", "২০")
                )


# ---------------------------------------------------------------------------------- through the API
def card_with(pub, person, kind="booking"):
    for _ in range(30):
        for card in pub.get(f"/api/c/cards?n=6&kinds={kind}", headers=person.h).json()["cards"]:
            if any(k.endswith(".name") for k in card["nodes"]):
                return card
    raise AssertionError("no card with a name step")


def test_the_server_resolves_what_a_clip_answers_from_node_choice_and_patient(person, pub, ctx):
    card = card_with(pub, person)
    name_node = next(k for k in card["nodes"] if k.endswith(".name"))
    woman = next(p for p in card["personas"] if p["gender"] == "f")
    reply = person.clip(
        headers={
            "x-card": card["id"],
            "x-step": name_node,
            "x-choice": "x",
            "x-persona": woman["id"],
            "x-autostop": "1",
            "x-slot": "who",
        }
    )
    clip = ctx.store.get_clip(reply.json()["clip_id"])
    assert (
        clip["slot"] == "name"
        and clip["expected_text"] == woman["name"]
        and clip["kind"] == "booking"
    )
    assert (
        clip["step_id"] == f"{name_node}#x"
        and clip["question_bn"] == card["nodes"][name_node]["line_bn"]
    )
    import json

    facts = json.loads(clip["facts"])
    assert (
        facts["persona"] == woman["id"] and facts["gender"] == "f" and facts["auto_stopped"] is True
    )


def test_a_fork_records_which_intent_was_spoken(person, pub, ctx):
    card = next(
        c
        for c in pub.get("/api/c/cards?n=8&kinds=booking", headers=person.h).json()["cards"]
        if "list" in c["nodes"]
    )
    reply = person.clip(headers={"x-card": card["id"], "x-step": "list", "x-choice": "advice"})
    import json

    clip = ctx.store.get_clip(reply.json()["clip_id"])
    assert clip["slot"] == "pick_doctor" and json.loads(clip["facts"])["asks"] == "advice"


def test_first_version_cards_still_resolve_for_clips_that_waited_on_a_phone(person, ctx):
    clip = ctx.store.get_clip(
        person.clip(headers={"x-card": "b000", "x-step": "b000.who"}).json()["clip_id"]
    )
    assert clip["slot"] == "who" and clip["question_bn"]


def test_open_turns_may_run_to_twenty_seconds(person):
    assert person.clip(make_wav(seconds=19.5)).status_code == 200


def test_rooms_use_the_same_clinic_as_the_scripts(person, pub, config):
    from tests.collector.conftest import Person

    other = Person(pub, config)
    room = pub.post("/api/c/room", json={}, headers=person.h).json()
    assert (
        room["card"]["v"] == 2 and room["card"]["goals_bn"] and len(room["card"]["personas"]) == 2
    )
    joined = pub.post("/api/c/room/join", json={"code": room["code"]}, headers=other.h).json()
    assert (
        len(joined["sheet"]["doctors"]) == 69
        and "অধ্যাপক" in joined["sheet"]["doctors"][0]["name_bn"]
    )


# ---------------------------------------------------------------------------------- voice packs
@pytest.fixture
def voices(ctx, priv):
    admin = ctx.store.open_session(
        ctx.store.create_staff("Boss", "admin", "boss", "correct horse 9")["id"]
    )
    made = ctx.store.create_staff("Rina", "reviewer", "rina", "correct horse 9")
    return {"admin": admin, "rina": ctx.store.open_session(made["id"]), "rina_id": made["id"]}


def test_a_staff_voice_is_played_only_after_consent_recording_and_admin_approval(
    priv, pub, person, ctx, voices
):
    h = bearer(voices["rina"])
    listing = priv.get("/api/voice/lines", headers=h).json()
    assert listing["consented"] is False and len(listing["lines"]) >= 20
    openings = [line for line in listing["lines"] if line["group"] == "opening"]
    assert len(openings) == len(S.OPENINGS)
    first = openings[0]["name"]
    assert (
        priv.put(f"/api/voice/line/{first}", content=make_wav(seconds=3), headers=h).status_code
        == 403
    )
    priv.post("/api/voice/consent", headers=h)
    assert (
        priv.put(f"/api/voice/line/{'0' * 16}", content=make_wav(seconds=3), headers=h).status_code
        == 404
    )
    assert (
        priv.put(f"/api/voice/line/{first}", content=make_wav(seconds=0.4), headers=h).status_code
        == 422
    )
    for line in openings:
        assert (
            priv.put(
                f"/api/voice/line/{line['name']}", content=make_wav(seconds=3, seed=3), headers=h
            ).status_code
            == 200
        )
    assert priv.get(f"/api/voice/line/{first}", headers=h).headers["content-type"] == "audio/mp4"
    ctx.store.set_setting("human_voice_share", "1")

    def served():
        cards = pub.get("/api/c/cards?n=6&kinds=booking", headers=person.h).json()["cards"]
        return [c["voice"] for c in cards if "voice" in c]

    assert served() == []  # recorded, but the admin has not switched it on
    assert (
        priv.post(
            f"/api/admin/voices/{voices['rina_id']}", headers=h, json={"enabled": True}
        ).status_code
        == 403
    )
    assert (
        priv.post(
            f"/api/admin/voices/{voices['rina_id']}",
            headers=bearer(voices["admin"]),
            json={"enabled": True},
        ).status_code
        == 200
    )
    packs = served()
    assert len(packs) == 6 and all(v["names"] for v in packs)
    url = f"/hv/{packs[0]['pack']}/{packs[0]['names'][0]}.m4a"
    assert pub.get(url).status_code == 200 and pub.get(url).headers["cache-control"] == "no-store"
    assert "rina" not in url and len(packs[0]["pack"]) == 32  # a random id, never who the person is
    # the person removes their voice: it stops at once
    assert priv.delete("/api/voice", headers=h).json()["deleted"] == len(openings)
    assert served() == [] and pub.get(url).status_code == 404


def test_share_zero_means_the_synthetic_voice_only(priv, pub, person, ctx, voices):
    h = bearer(voices["rina"])
    priv.post("/api/voice/consent", headers=h)
    for line in S.common_lines():
        priv.put(f"/api/voice/line/{line['name']}", content=make_wav(seconds=3, seed=5), headers=h)
    priv.post(
        f"/api/admin/voices/{voices['rina_id']}",
        headers=bearer(voices["admin"]),
        json={"enabled": True},
    )
    priv.post("/api/admin/settings", headers=bearer(voices["admin"]), json={"human_voice_share": 0})
    cards = pub.get("/api/c/cards?n=6", headers=person.h).json()["cards"]
    assert not any("voice" in c for c in cards)
    listing = priv.get("/api/admin/voices", headers=bearer(voices["admin"])).json()
    assert listing["share"] == 0 and listing["packs"][0]["lines"] == len(S.common_lines())


def test_a_deactivated_person_is_no_longer_heard(priv, pub, ctx, voices):
    h = bearer(voices["rina"])
    priv.post("/api/voice/consent", headers=h)
    name = S.common_lines()[0]["name"]
    priv.put(f"/api/voice/line/{name}", content=make_wav(seconds=3, seed=6), headers=h)
    priv.post(
        f"/api/admin/voices/{voices['rina_id']}",
        headers=bearer(voices["admin"]),
        json={"enabled": True},
    )
    pack = ctx.store.voice_pack(voices["rina_id"])["public_id"]
    assert pub.get(f"/hv/{pack}/{name}.m4a").status_code == 200
    priv.delete(f"/api/admin/staff/{voices['rina_id']}", headers=bearer(voices["admin"]))
    assert pub.get(f"/hv/{pack}/{name}.m4a").status_code == 404


def test_cards_json_is_compressed_but_audio_never_is(pub, person, ctx):
    cards = pub.get("/api/c/cards?n=3", headers={**person.h, "accept-encoding": "gzip"})
    assert cards.headers.get("content-encoding") == "gzip"
    folder = ctx.config.prompts_dir / "q2"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("a" * 16 + ".m4a")).write_bytes(b"\0" * 9000)
    audio = pub.get(
        "/q2/" + "a" * 16 + ".m4a", headers={"accept-encoding": "gzip", "range": "bytes=0-1"}
    )
    assert audio.status_code == 206 and "content-encoding" not in audio.headers
