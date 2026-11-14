# SHEFA Voice Commons: how to run it

A small, separate web app that lets friends, family and the community record made-up hospital
phone calls so SHEFA's speech recogniser can learn Bangla hospital talk. Design and reasons:
[`designs/shefa-voice-commons.md`](designs/shefa-voice-commons.md). Web API contract:
[`designs/collector-api.md`](designs/collector-api.md).

Everything runs on your own computer. Recordings are saved to `data/collector/` on your disk (never
in a cloud store), so there is no download-and-clear step, no storage cap and no foreign cloud
holding personal voice data. Contributors reach it through a free tunnel.

## One-time setup

```bash
uv run shefa collect init            # makes data/collector/, the database, the cards, and your admin token
uv run shefa collect build-prompts   # speaks the agent's questions with the local Bangla voice (about 2 minutes)
uv run shefa collect staff Rina reviewer        # one token per reviewer; "adjudicator" settles disagreements
```

`init` prints your admin token once. Keep it in a password manager. Optional settings go in
`configs/collector.yaml` (ignored by git); every key is in `src/shefa/collector/config.py`.

Add a short welcome voice note from yourself (about 20 seconds, Ogg/Opus) as
`data/collector/voice_note.ogg`; the page plays it on the first screen. People answer a person.

## Running a collection day

```bash
uv run shefa collect serve
```

* Contributor page: `http://127.0.0.1:8100/` (put the tunnel on this port only).
* Staff page: `http://127.0.0.1:8101/` (your computer only: admin and review).

### Give it a public address for free

A Cloudflare quick tunnel needs no account (download the `cloudflared` binary from Cloudflare's
site, no installer or sudo needed):

```bash
./cloudflared tunnel --url http://127.0.0.1:8100
```

It prints an `https://<random>.trycloudflare.com` address. Quick tunnels have no uptime promise and
the address changes every time you restart it. If the address changing is a problem, use the static
page below. Never point a tunnel at port 8101.

### Make the link survive a power cut (recommended before a WhatsApp campaign)

```bash
uv run shefa collect shell ./shell --api https://<your-tunnel-address>
```

Upload the `shell/` folder to any free static host (GitHub Pages or Cloudflare Pages) and add that
page's address to `allowed_origins` in `configs/collector.yaml`. The page then always loads, keeps
recordings on each phone and uploads them when your computer and tunnel are back. Share the static
page's link, not the tunnel's. When the tunnel address changes, re-run the command and republish.

### Review sessions

Reviewers normally cannot reach your computer. For a review session:

```bash
uv run shefa collect serve --with-review
```

Reviewer and adjudicator tokens then work on the public address at `/review/`. Admin tokens do
not, and the admin routes are never on the public port. Stop the session when you are done.

## Making campaign links

Open the staff page, Campaigns, "New". A link like `https://.../?c=ab12cd` shows each person the
sender's name ("রাহুল পাঠিয়েছে") and tells you which group brought which recordings.

## Reviewing

Reviewers sign in with their token at the staff page. The page shows one clip at a time.
Convention (also shown on the page): write exactly what is said, numbers/dates/times as Bangla
words (typed digits are converted for you), phone numbers as digits, English words in Bangla
script, no punctuation, and flag anything unusable instead of guessing. Test-set clips are
transcribed blind by two people and settled by an adjudicator; a small share of the queue is
known-answer clips that measure each reviewer's accuracy.

## Machine drafts, backups, measuring, exporting

```bash
uv run shefa collect draft                # draft transcripts for training-pool clips (uses the speech model)
uv run shefa collect backup /media/usb/collector   # verified copy to another disk; withdrawn clips never survive in it
uv run shefa collect score --hints        # baseline of the CURRENT model; --hints also tries booking-word hints (they hurt on synthetic audio, see docs/research/2026-11-15-*)
uv run shefa collect export ./trainset --phone-copies   # speaker-disjoint train/dev/test + 8 kHz phone-line copies
```

`score` and `export` print the go/no-go gate: about 100 speakers and 8 hours of reviewed audio
before a fine-tune is worth trying; below that, use the data as a test set. A fine-tuned model
ships only if slot-critical words (name, phone digits, day, time, yes/no) reach 90% on phone-line
audio and general Bangla does not get worse (`docs/fine-tuning-plan.md`).

## What to tell contributors (copy and send)

Bangla:

> আসসালামু আলাইকুম। আমি SHEFA নামে একটা প্রযুক্তি বানাচ্ছি, যেটা হাসপাতালে ফোনে সিরিয়াল নিতে
> সাহায্য করবে, যাতে কাউকে অপেক্ষা করতে না হয়। বাংলা কথা ঠিকমতো বোঝানোর জন্য ১০ মিনিট সময় দিয়ে
> কয়েকটা কাল্পনিক ফোনকলের কথা রেকর্ড করে দিতে পারবেন? আসল নাম বা নম্বর বলতে হবে না। রেকর্ডিং
> শুধু এই কাজেই ব্যবহার হবে, প্রকাশ হবে না, আর চাইলে যেকোনো সময় মুছে ফেলতে পারবেন। এটা একটা
> বাণিজ্যিক পণ্যের অংশ, তাই জানিয়ে রাখলাম। লিংক: <link>

English:

> Hi! I'm building SHEFA, a voice assistant that helps patients book hospital appointments by phone
> so nobody has to wait. To teach it Bangla, could you spend 10 minutes recording a few made-up
> phone calls? You never say your real name or number. The recordings are used only for this, are
> not published, and you can delete them any time. It is part of a commercial product, so I want
> you to know. Link: <link>

(The Bangla is a draft; have a native speaker read it before you send it widely.)

## Privacy and safety checklist

* Contributors speak made-up details from the card; reviewers are told clips may still contain real
  ones and must not share them. Flag them and the clip is excluded.
* The audio never leaves your computer except through the tunnel's encrypted connection (Cloudflare
  passes the traffic). Reviewers hear audio only through short-lived signed links.
* A contributor's delete code removes their recordings and leaves a tombstone so they cannot
  return from a backup. The consent text says a model that has already been trained cannot un-learn.
* Uploads pause by themselves when disk space is low or when you press Pause on the staff page.
* **Have a lawyer read Bangladesh's current personal-data rules** before a wide campaign (voice may
  count as sensitive data; sending data abroad has rules). This has not been verified here.
* Never publish the audio or a model trained on it without fresh consent (decision D6).

## Troubleshooting

* **Microphone blocked inside Facebook/Messenger:** the page detects it and shows "Chrome-এ খুলুন".
* **iPhone records nothing or in a strange format:** the page uses a WAV recorder with a
  MediaRecorder fallback; if a model of phone fails, ask the person to open it in Safari or Chrome.
  Test every phone type you can before a campaign.
* **Uploads say "paused":** disk free is below `min_free_disk_mb`, or you pressed Pause.
* **The link stopped working:** the tunnel restarted. Use the static page so only one place changes.

## Not built (on purpose)

A live in-browser two-person call (needs a relay server for mobile networks; the voice-message style
"call a friend" covers it), a public reviewer sign-up, a contributors wall with personal details,
automatic personal-detail detection, and any cloud storage adapter. The audio store has a small
interface (`LocalAudioStore`) so a cloud one can be added later.
