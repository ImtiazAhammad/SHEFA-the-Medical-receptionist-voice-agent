# Voice Commons: is the collection worth it, and what can sink it (2026-11-20)

Measured on the live database: 850 clips, 72.7 minutes, 38 speakers, 790 reviewed.

## Is the data narrowing the conversation? Yes, in five measured ways
| What real callers do | What we collect |
|---|---|
| Long, messy turns, restarts, "hello, শুনতে পাচ্ছেন?" | One short answer per question: median 4.3 s, 90% under 9.3 s |
| Their own words | Paraphrases of a hint: 1,017 distinct words, the top 30 words are 40% of everything; only 5 free-talk clips so far |
| Phone network audio (8 kHz codec, loss), speakerphone, crowds | Phone mic at 16 kHz, 90% home/office, median SNR 28 dB, 3 street clips |
| Older relatives, rural, stressed, regional speech | One social circle: 16 of 17 known ages are under 35, 11 men / 6 women, 21 of 38 gave no profile, 1 dialect known |
| Real doctor and hospital names, symptoms | One made-up clinic and roster |
One person is 25% of all clips.

## Will a model trained on it work?
It will help where it is strong: domain words (সিরিয়াল, doctor titles, days, times, digits,
names) in real Bangla voices on real phones. On its own it will be brittle on real callers. Used
as a small fine-tune ON TOP of a broad Bangla model (not instead of one), mixed with general Bangla
speech, it should add value. Nobody knows yet: no real-caller error rate has ever been measured.

## Single points of failure and catastrophes
1. **No real-call test set (the biggest one).** Our test set is the same style as training, so a
   model can score well and still fail on real callers. We would find out only after launch.
2. **Test set integrity.** All 846 reviews are by the `admin` account (the reviewer account has 0).
   The 50 test clips were reviewed once, with the machine draft visible. Test labels should be two
   blind reviews; otherwise the test measures agreement with the drafting model.
3. **Drafts feed back into training.** 63% of drafts are accepted unchanged; model mistakes a tired
   reviewer misses become training targets, and the model learns its own errors.
4. **One disk.** Audio, database and every backup sit on one laptop disk (89% full). Theft, a
   dead SSD or a bad `rm` loses everything.
5. **One laptop and a quick tunnel.** Sleep, a reboot or a cloudflared restart takes the site down
   or changes the address. Collection has also stalled: about 10 clips since 2026-11-19.
6. **One dominant voice** (25%); the export caps it, but the model still hears mostly one circle.
7. **Legal.** Consent is now one short sentence including sharing/licensing; a per-person record
   is kept. Before selling or licensing, a lawyer should check it against Bangladesh's current
   data-protection rules (not checked here).

## Mitigation plan, in order
1. **This week, no code:** copy `data/collector` to an external drive (and a second place) weekly;
   the reviewer signs in with their own account, never `admin`.
2. **Build a real-world test set (~1 hour, never trained on):** recorded real calls from the design
   partner clinic with permission, or real receptionists role-playing over an actual phone call.
   Measure today's model on it now, so we know the starting point.
3. **Widen the data:** free talk to 50%; a "whole call" mode that records the caller side
   continuously; a speakerphone/outside goal; an older-voices goal (parents of contributors, 50+,
   target 25%); people outside Dhaka; keep capping the top speaker.
4. **Clean labels:** test clips get two blind reviews with no draft; spot-check 5% of
   "accepted unchanged" train drafts blind to measure how much anchoring costs.
5. **Train carefully:** small learning rate, mix with general Bangla speech, judge only on the
   real-world set; stop when that stops improving.
6. **Decision gate at ~5 reviewed hours:** fine-tune and compare to the baseline on the real-world
   set. If it is not clearly better, change the approach before collecting more of the same.
