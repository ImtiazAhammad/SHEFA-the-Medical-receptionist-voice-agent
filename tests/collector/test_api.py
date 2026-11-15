# ruff: noqa: E501, N812, TC001, TC003

from tests.collector.conftest import Person, make_wav


def test_config_reports_consent_and_state(pub, config):
    reply = pub.get("/api/c/config").json()
    assert reply["consent_version"] == config.consent_version
    assert "SHEFA" in reply["consent_bn"] and reply["maintenance"] == ""


def test_start_needs_consent_of_the_current_version(pub, config):
    assert (
        pub.post(
            "/api/c/start", json={"consent": False, "consent_version": config.consent_version}
        ).status_code
        == 400
    )
    assert (
        pub.post("/api/c/start", json={"consent": True, "consent_version": "old"}).status_code
        == 400
    )


def test_upload_stores_a_clip_and_counts_toward_progress(person, pub, ctx):
    reply = person.clip(headers={"x-card": "b000", "x-step": "b000.who", "x-setting": "home"})
    assert reply.status_code == 200 and reply.json()["ok"]
    first_id = reply.json()["clip_id"]
    clip = ctx.store.get_clip(first_id)
    assert clip["slot"] == "who" and clip["kind"] == "booking" and clip["setting"] == "home"
    assert clip["question_bn"] and clip["split"] in {"train", "dev", "test"}
    progress = pub.get("/api/c/progress").json()
    assert progress["clips"] == 1 and progress["speakers"] == 1


def test_the_server_not_the_phone_decides_what_the_clip_answers(person, ctx):
    first_id = person.clip(
        headers={"x-card": "d000", "x-step": "d000.phone", "x-slot": "who", "x-kind": "info"}
    ).json()["clip_id"]
    clip = ctx.store.get_clip(first_id)
    assert clip["slot"] == "phone" and clip["kind"] == "digits"
    assert clip["expected_text"] and clip["expected_text"].startswith("01")


def test_a_retried_upload_is_safe(person, ctx):
    data = make_wav(seed=9)
    first = person.clip(data, clip_id="a" * 32)
    again = person.clip(data, clip_id="a" * 32)
    assert first.status_code == again.status_code == 200 and again.json()["duplicate"]
    assert ctx.store.progress()["clips"] == 1


def test_the_same_audio_under_a_new_id_is_refused(person):
    data = make_wav(seed=4)
    assert person.clip(data, clip_id="b" * 32).status_code == 200
    assert person.clip(data, clip_id="c" * 32).status_code == 409


def test_bad_recordings_are_refused_with_a_reason(person):
    assert person.clip(make_wav(seconds=0.2)).json()["error"]["reason"] == "too_short"
    assert person.clip(make_wav(seconds=25)).status_code in (413, 422)
    assert (
        person.clip(make_wav(amp=0.0004, noise=0.0004, seed=2)).json()["error"]["reason"]
        == "silent"
    )
    assert person.clip(make_wav(clip=True, seed=3)).json()["error"]["reason"] == "clipped"
    assert person.clip(b"this is not audio at all " * 20).json()["error"]["reason"] == "unreadable"


def test_oversized_upload_is_refused_before_decoding(person, config):
    assert person.clip(b"\0" * (config.max_clip_bytes + 10)).status_code == 413


def test_wrong_secret_cannot_upload(person, pub):
    reply = pub.put(
        f"/api/c/clip/{'d' * 32}", content=make_wav(), headers={**person.h, "x-secret": "nope"}
    )
    assert reply.status_code == 401


def test_one_contributor_cannot_use_anothers_speaker(person, pub, config):
    other = Person(pub, config)
    headers = {**other.h, "x-speaker": person.info["speaker_id"]}
    assert (
        pub.put(f"/api/c/clip/{'e' * 32}", content=make_wav(), headers=headers).status_code == 401
    )


def test_kill_switch_pauses_uploads_but_keeps_health(person, pub, ctx):
    ctx.store.set_setting("kill_switch", "1")
    assert person.clip().status_code == 503
    assert pub.get("/health").json()["maintenance"] == "paused"


def test_daily_cap(person, config):
    config.clips_per_contributor_per_day = 2
    assert person.clip().status_code == 200 and person.clip().status_code == 200
    assert person.clip().status_code == 429


def test_withdrawal_deletes_audio_and_blocks_a_restore(person, pub, ctx):
    data = make_wav(seed=11)
    person.clip(data, clip_id="f" * 32)
    path = ctx.store.get_clip("f" * 32)["path"]
    code = person.info["delete_code"]
    reply = pub.post("/api/c/delete", json={"delete_code": code}).json()
    assert reply["deleted"] == 1
    assert not __import__("pathlib").Path(path).exists()
    assert ctx.store.get_clip("f" * 32) is None
    assert ctx.store.tombstoned("f" * 32, "x")
    # the same audio can never be uploaded again by anyone
    other = Person(pub, ctx.config)
    assert other.clip(data, clip_id="9" * 32).status_code == 410


def test_wrong_delete_code(pub):
    assert pub.post("/api/c/delete", json={"delete_code": "0000-0000-0000"}).status_code == 404


def test_profile_only_accepts_known_values_and_names_are_opt_in(person, pub, ctx):
    pub.post(
        "/api/c/profile",
        json={
            "age_band": "25-34",
            "gender": "female",
            "division": "mars",
            "nickname": "<b>Rina</b>",
            "credit_ok": True,
        },
        headers=person.h,
    )
    row = ctx.store._one("SELECT * FROM speakers WHERE id=?", (person.info["speaker_id"],))
    assert row["age_band"] == "25-34" and row["division"] == "" and "<" not in row["nickname"]
    assert pub.get("/api/c/thanks").json()["names"] == ["bRinab"]


def test_pass_the_phone_gives_each_person_their_own_speaker(person, pub):
    made = pub.post("/api/c/speaker", headers=person.h).json()
    second = made["speaker_id"]
    assert second != person.info["speaker_id"] and made["delete_code"] != person.info["delete_code"]
    headers = {**person.h, "x-speaker": second}
    assert (
        pub.put(f"/api/c/clip/{'1' * 32}", content=make_wav(seed=21), headers=headers).status_code
        == 200
    )


def test_cards_are_served_and_avoid_repeats(person, pub):
    first = pub.get("/api/c/cards?n=4", headers=person.h).json()["cards"]
    assert len(first) == 4 and all(card["nodes"] and card["v"] == 2 for card in first)
    seen = ",".join(card["id"] for card in first)
    again = pub.get(f"/api/c/cards?n=4&seen={seen}", headers=person.h).json()["cards"]
    assert not {c["id"] for c in again} & {c["id"] for c in first}


def test_public_app_has_no_staff_routes(pub):
    assert pub.get("/api/admin/stats").status_code in (404, 405)
    assert pub.get("/api/review/next").status_code == 404


def test_security_headers(pub):
    reply = pub.get("/health")
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert "microphone=(self)" in reply.headers["permissions-policy"]


def test_two_phone_room(person, pub, config):
    other = Person(pub, config)
    room = pub.post("/api/c/room", json={}, headers=person.h).json()
    assert room["role"] == "caller"
    joined = pub.post("/api/c/room/join", json={"code": room["code"]}, headers=other.h).json()
    assert joined["role"] == "desk" and joined["sheet"]["doctors"]
    third = Person(pub, config)
    assert (
        pub.post("/api/c/room/join", json={"code": room["code"]}, headers=third.h).status_code
        == 409
    )
    person.clip(
        make_wav(seed=31),
        clip_id="2" * 32,
        headers={"x-room": room["code"], "x-role": "caller", "x-turn": "1"},
    )
    state = pub.get(f"/api/c/room/{room['code']}", headers=other.h).json()
    assert state["clips"][0]["role"] == "caller"
    assert (
        pub.get(f"/api/c/room/{room['code']}/clip/{'2' * 32}", headers=other.h).status_code == 200
    )
    assert pub.get(f"/api/c/room/{room['code']}", headers=third.h).status_code == 404


def test_each_person_on_a_shared_phone_has_their_own_delete_code_and_profile(person, pub, ctx):
    first_clip = person.clip().json()["clip_id"]
    made = pub.post("/api/c/speaker", headers=person.h).json()
    second_headers = {**person.h, "x-speaker": made["speaker_id"]}
    pub.put(f"/api/c/clip/{'3' * 32}", content=make_wav(seed=77), headers=second_headers)
    pub.post(
        "/api/c/profile",
        json={"gender": "female", "nickname": "Mina", "credit_ok": True},
        headers=second_headers,
    )
    pub.post("/api/c/profile", json={"gender": "male"}, headers=person.h)
    rows = {r["id"]: r for r in ctx.store._q("SELECT * FROM speakers")}
    assert (
        rows[made["speaker_id"]]["gender"] == "female"
        and rows[person.info["speaker_id"]]["gender"] == "male"
    )
    # the second person withdraws: the first person's clip is untouched
    assert (
        pub.post("/api/c/delete", json={"delete_code": made["delete_code"]}).json()["deleted"] == 1
    )
    assert ctx.store.get_clip(first_clip) is not None and ctx.store.get_clip("3" * 32) is None
    assert pub.get("/api/c/thanks").json()["names"] == []
    assert person.clip().status_code == 200  # the phone's first person can carry on
    # the withdrawn speaker can no longer upload
    assert (
        pub.put(
            f"/api/c/clip/{'4' * 32}", content=make_wav(seed=78), headers=second_headers
        ).status_code
        == 401
    )


def test_room_clips_are_only_accepted_from_members_and_the_server_sets_the_role(
    person, pub, config
):
    other, stranger = Person(pub, config), Person(pub, config)
    room = pub.post("/api/c/room", json={}, headers=person.h).json()["code"]
    pub.post("/api/c/room/join", json={"code": room}, headers=other.h)
    assert stranger.clip(headers={"x-room": room, "x-role": "caller"}).status_code == 403
    sent = other.clip(headers={"x-room": room, "x-role": "caller", "x-turn": "2"})
    assert sent.status_code == 200
    state = pub.get(f"/api/c/room/{room}", headers=person.h).json()
    assert state["clips"][-1]["role"] == "desk"  # the phone said "caller"; the server knows better


def test_a_voice_that_never_pauses_is_not_called_silent(person):
    import io
    import wave

    import numpy as np

    t = np.arange(int(2.0 * 16000)) / 16000
    x = 0.25 * np.sin(2 * np.pi * 200 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    assert person.clip(buf.getvalue()).status_code == 200
