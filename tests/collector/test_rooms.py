"""Two-person calls follow the same branching script: the patient's choices move the call on, the
front desk is guided to answer professionally and never extends the call by itself."""

# ruff: noqa: E501
import uuid

from tests.collector.conftest import Person, make_wav


def room_pair(pub, config):
    caller, desk = Person(pub, config), Person(pub, config)
    for _ in range(20):  # a booking card with a doctor list, so there is a real fork
        room = pub.post("/api/c/room", json={}, headers=caller.h).json()
        if "list" in room["card"]["nodes"]:
            break
    pub.post("/api/c/room/join", json={"code": room["code"]}, headers=desk.h)
    return caller, desk, room["code"], room["card"]


def say(person, code, turn, step="", choice="", persona=""):
    headers = {"x-room": code, "x-turn": str(turn), "x-step": step}
    if choice:
        headers["x-choice"] = choice
    if persona:
        headers["x-persona"] = persona
    return person.client.put(
        f"/api/c/clip/{uuid.uuid4().hex}",
        content=make_wav(seed=turn * 7 + 3),
        headers={**person.h, **headers},
    )


def state(pub, person, code):
    return pub.get(f"/api/c/room/{code}", headers=person.h).json()


def test_the_call_moves_with_the_patients_choices(pub, config, ctx):
    caller, desk, code, card = room_pair(pub, config)
    assert state(pub, desk, code)["node"] == "open"
    assert say(desk, code, 1, "open").status_code == 200
    answer = card["nodes"]["open"]["choices"][0]
    assert say(caller, code, 2, "open", answer["id"], "a").status_code == 200
    now = state(pub, desk, code)["node"]
    assert now == answer["next"]
    if now == "who":  # a vague opener asks one more question first
        say(desk, code, 3, "who")
        say(caller, code, 4, "who", "x", "a")
        now = state(pub, desk, code)["node"]
    assert now == "list"
    # the patient asks for advice: the desk's next line is the recommendation, nothing else
    say(desk, code, 5, "list")
    say(caller, code, 6, "list", "advice", "a")
    assert state(pub, caller, code)["node"] == "rec"
    assert "সিনিয়র" in card["nodes"]["rec"]["line_bn"]


def test_front_desk_clips_are_stored_as_front_desk_speech(pub, config, ctx):
    caller, desk, code, card = room_pair(pub, config)
    reply = say(desk, code, 1, "open")
    clip = ctx.store.get_clip(reply.json()["clip_id"])
    assert clip["role"] == "desk" and clip["slot"] == "desk" and clip["expected_text"] is None
    assert clip["question_bn"] == card["nodes"]["open"]["line_bn"] and clip["step_id"] == "open"
    answer = say(caller, code, 2, "open", "x", "b")
    clip = ctx.store.get_clip(answer.json()["clip_id"])
    assert clip["role"] == "caller" and clip["slot"] == "open" and clip["step_id"] == "open#x"


def test_a_retried_answer_does_not_move_the_call_twice(pub, config, ctx):
    caller, desk, code, card = room_pair(pub, config)
    say(desk, code, 1, "open")
    say(caller, code, 2, "open", "x", "a")
    after_one = state(pub, desk, code)["node"]
    say(caller, code, 2, "open", "x", "a")  # the same answer sent again
    assert state(pub, desk, code)["node"] == after_one


def test_the_room_reaches_the_end_of_the_script(pub, config, ctx):
    from shefa.collector.api import _room_node

    card = {
        "v": 2,
        "start": "a",
        "nodes": {
            "a": {"id": "a", "choices": [{"id": "x", "next": "b"}]},
            "b": {"id": "b", "choices": [{"id": "x", "next": None}]},
        },
    }
    clips = [
        {"role": "caller", "turn": 2, "step_id": "a#x", "created_at": 1},
        {"role": "caller", "turn": 4, "step_id": "b#x", "created_at": 2},
    ]
    assert _room_node(card, clips[:1]) == "b" and _room_node(card, clips) == ""
