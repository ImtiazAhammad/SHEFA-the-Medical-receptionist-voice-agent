# SHEFA Voice Commons: version 2 changes to the web API (read with `collector-api.md`)

Why: after about 30 people used version 1 the founder reported that every round felt the same, the
synthetic voice left people unsure what to do, the desk never greeted, and staff wanted a username
and password. Two reviews added: the desk's words were hidden behind a link, auto-stopped clips
were kept silently, and the admin must never be able to sign in through the tunnel.

## 1. Scripts replace cards (`GET /api/c/cards`)

Each card now has `"v": 2` and is a GRAPH:

```json
{ "id": "v2-b017", "v": 2, "kind": "booking|info|digits", "situation_bn": "…", "department": "শিশু",
  "personas": [ {"id":"a","label_bn":"ছেলে","relation_bn":"আপনার ছেলে","gender":"m","name":"রাফি আহমেদ","age":7,"age_bn":"৭","age_words":"সাত"},
                {"id":"b","label_bn":"মেয়ে", …} ],        // [] when the call has no patient
  "start": "open",
  "nodes": { "open": { "id":"open", "slot":"open", "line_bn":"আসসালামু আলাইকুম, শেফা ক্লিনিক থেকে বলছি…",
                       "audio":"q2/<name>.m4a" | "", "audio_name":"<16 hex>", "cap_s": 20,
                       "choices":[ {"id":"x","label_bn":"","hint_bn":"…","expected":null,"next":"list","facts":{}} ] },
             "list": { … "choices":[ {"id":"p0","label_bn":"ডাক্তার সুলতানা (অধ্যাপক)", "hint_bn":"ডাক্তার সুলতানা-কে বেছে নিন।","next":"d0.day"},
                                      {"id":"advice","label_bn":"কে ভালো হবে?", …,"next":"rec"}, … ] },
             "d0.bye": { "line_bn":"ধন্যবাদ, ভালো থাকবেন। আল্লাহ হাফেজ।", "choices": [] } },
  "goals_bn": ["…"],                       // the caller's intents along one path (for two-person calls)
  "voice": {"pack":"<32 hex>","names":["<audio_name>", …]}   // optional, see section 3
}
```

How the page walks it:
1. If `personas` has two entries, the contributor FIRST taps who the patient is (two big chips using
   `label_bn`; show the name and age of each). Remember the choice for the whole call. Hints contain
   the placeholders `{name}`, `{age}`, `{relation_bn}`: replace them from the chosen persona
   (`{age}` -> `age_bn`). Show the chosen patient on a small persistent line ("রোগী: আপনার ছেলে রাফি আহমেদ, ৭ বছর").
2. At a node: show the desk's line as an ALWAYS-VISIBLE speech bubble labelled "ফ্রন্ট ডেস্ক" (never
   behind a link) and play its audio (section 3). The record button is usable as soon as the audio
   ends, OR immediately with a "play" button if autoplay is blocked or audio fails: never leave the
   button disabled with no way forward.
3. One choice: show its `hint_bn` under "আপনি যা বলবেন" with the "নিজের মতো করে বলুন" nudge.
   Several choices (a fork): show "কী বলতে চান? একটা বেছে নিন" and the `label_bn` chips; after a tap
   show that choice's `hint_bn`; the person may change the tap before recording.
4. Record with a cap of `node.cap_s` seconds (14 or 20). Show a countdown for the last 5 s. If the
   recording was cut by the cap, tell the person it was cut and ask them to redo it shorter; if they
   keep it anyway send `X-Autostop: 1`.
5. Upload `PUT /api/c/clip/{id}` with `X-Card`, `X-Step` = node id, `X-Choice` = choice id,
   `X-Persona` = persona id (when chosen), plus the existing headers. Then go to `choice.next`.
6. A node with `choices: []` is the desk's last line: play/show it, then the call is over. `next: null`
   also ends the call. Show "কল শেষ" with "আরেকটা কল করি" / "শেষ করি".
7. Show the call so far as a short chat history (desk line, then "আপনি: ✓ রেকর্ড হয়েছে"), newest at the
   bottom, so people see the conversation grow. Show a turn counter ("কথা ৩").
8. Cards with `v` missing are first-version cards (`steps` list); the page no longer needs to render
   them (the server still accepts their uploads from old queues).

`GET /api/c/config` adds `clinic_bn`. `max_clip_s` is now the overall ceiling (21); use `cap_s`.

## 2. Two-person calls
`POST /api/c/room` returns a v2 card. The CALLER sees the situation, picks the patient from
`personas`, and sees `goals_bn` as a checklist of what to get done (not a script). The DESK sees
`sheet` (now `{title_bn, address_bn, doctors:[{name_bn, dept_bn, days_bn, hours_bn, fee, room}] (24), tips_bn}`):
group the doctors by `dept_bn`, make it searchable or collapsible, it is long. Room clips: send
`X-Room`, `X-Turn`; `X-Step`/`X-Choice` are optional there.

## 3. The desk's voice
* Synthetic: `GET {API}/{node.audio}` (m4a). If `audio` is empty fall back to showing the text only
  (and `speechSynthesis` bn-BD when available).
* Human: when the card has `voice` and `node.audio_name` is in `voice.names`, play
  `GET {API}/hv/{voice.pack}/{audio_name}.m4a` instead (on any error fall back to the synthetic one).
  One call uses one pack, so the desk does not change voice mid-call more than necessary.
* First-version audio stays at `/q/{name}.wav`.

## 4. Staff accounts (private app; also on `/review/` during a review session)

| Method and path | Body | Reply |
|---|---|---|
| `POST /api/staff/login` | `{username, password}` | `{token, name, role, must_change}`; `401 bad_login` (one generic message for wrong name or wrong password), `429 locked` / `slow_down` |
| `POST /api/staff/logout` | Bearer | `{ok}` |
| `POST /api/staff/password` | Bearer, `{old, new}` | `{ok, token}` (use the NEW token; old sessions end); `401 bad_login`, `400 weak_password` (message says why) |
| `GET /api/review/me` | Bearer | `{name, username, role, reviewed, must_change}` |

Rules: the session token is kept exactly as the old token was (sessionStorage, `Authorization:
Bearer`). While `must_change` is true every other call answers `403 {code:"must_change"}`: send the
person to a "choose your own password" screen (old = the one-time password; new twice; 10+
characters, not only digits, not the username). On the public address an admin account is answered
exactly like an unknown one (`401 bad_login`): do not show any special message for it.
There is no token sign-in any more: the sign-in form is username + password (with show/hide).

Admin: `POST /api/admin/staff {name, role, username}` -> `{username, password}` (a one-time
password, shown once, expires in 72 h); `POST /api/admin/staff/{id}/reset` -> `{username, password}`;
`GET /api/admin/staff` rows are `{id, name, role, active, created_at, username, must_change, has_password}`;
`POST /api/admin/clips/{id}/restore` undoes a rejection; settings accept `human_voice_share` (0..1);
stats return `human_voice_share`.

## 5. Voice packs (a staff member records the desk's lines; played to contributors)

Any signed-in staff member (also through `/review/`):

| Method and path | Reply |
|---|---|
| `GET /api/voice/lines` | `{consented, enabled, lines:[{name, text, group:"opening"\|"question"\|"closing"\|"doctors", recorded}]}` (about 34 lines; openings first) |
| `POST /api/voice/consent` | `{ok}` (required before any upload: `403 consent`) |
| `PUT /api/voice/line/{name}` | raw audio body (16 kHz WAV preferred; same recorder as the contributor page), `{ok, duration_s}` or `422 rejected` with `reason` |
| `GET /api/voice/line/{name}` | the person's own recording (m4a; fetch with the Bearer header, play from a blob URL) |
| `DELETE /api/voice/line/{name}`, `DELETE /api/voice` | `{ok, deleted}` (deleting everything also switches the pack off) |

Admin: `GET /api/admin/voices` -> `{packs:[{staff_id, name, lines, active, enabled, consented}], share, total_lines, lines:[…]}`;
`POST /api/admin/voices/{staff_id} {enabled}`; `GET /api/admin/voices/{staff_id}/{name}` (audio, Bearer).

The consent text the UI must show before the first recording (Bangla + English):
"এই রেকর্ডিংগুলো অংশগ্রহণকারীদের শোনানো হবে। লিংক যার কাছে আছে সে শুনতে ও কপি করতে পারবে, তাই কণ্ঠ
চেনা বা নকল হওয়ার ঝুঁকি আছে। যেকোনো সময় মুছে দিলে আর শোনানো হবে না, তবে আগে যা শোনা হয়ে গেছে তা
ফেরানো যায় না। এটা সম্পূর্ণ ঐচ্ছিক, শুধু প্রাপ্তবয়স্কদের জন্য।"
Only staff record packs. Contributors' recordings are never played to other contributors.
