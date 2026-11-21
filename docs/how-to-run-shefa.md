# How to run SHEFA: the simple note

Two addresses. Don't mix them up:

| Address | Who uses it | Where it opens |
|---|---|---|
| **https://shefa-voice.tail195ef8.ts.net** | Volunteers (anyone) | Any phone or computer |
| **http://127.0.0.1:8101** | You and the reviewers | **Only on this PC** |

✅ Send people only the `shefa-voice` link. It never changes.
❌ Never send anyone the `127.0.0.1:8101` address. That's your private review room.

---

## 1. Start SHEFA

1. **Turn on the PC.** You don't have to log in; SHEFA starts by itself.
2. **Wait about 5 minutes.** SHEFA's brain (the language model) takes a few minutes to wake up.
3. **Check it:** open https://shefa-voice.tail195ef8.ts.net on your phone.
   - The page opens → ✅ done.
   - It doesn't open → wait 5 more minutes, then try again.

## 2. Review recordings

1. On this PC, open the browser.
2. Go to **http://127.0.0.1:8101**
3. Log in with your staff account.

## 3. Turn the PC off

Shut down normally. Nothing else to do.
While it's off, volunteers can't open the link. When you turn it on again, everything comes back by itself (step 1).

---

## 4. PC stays on, SHEFA takes a break

Pick the one you need.

### A. Short break: "Pause uploads" (easiest, no terminal)

Use this when you need a short pause, for example while you change something or take a backup.

1. Open **http://127.0.0.1:8101** and log in.
2. On the **সারসংক্ষেপ (Overview)** tab, press **আপলোড বন্ধ করুন (Pause uploads)**, then confirm.
3. The page now says **আপলোড বন্ধ আছে (Uploads are PAUSED)**.

What volunteers see: the page still opens, but it says SHEFA is resting today. Anything they record waits on their phone and uploads later by itself. SHEFA live calls stop.

**To start again:** press **আপলোড চালু করুন (Resume uploads)** on the same tab.

### B. Full stop until you start it again (frees the graphics card)

Use this when you want the PC's power for something else, like gaming or other AI work.

1. Open a terminal (**Ctrl+Alt+T**).
2. Copy, paste, and press Enter:
   ```
   systemctl --user stop shefa-collector shefa-vllm
   ```
3. Done. The link stops opening, and the graphics card is free.

**To start again:**
```
systemctl --user start shefa-vllm shefa-collector
```
Then wait about 5 minutes (like step 1).

Note: with B, SHEFA still starts by itself the next time the PC is turned on.

### C. Long holiday: don't start by itself any more

Use this when you don't want SHEFA running at all, even after restarting the PC.

1. Open a terminal (**Ctrl+Alt+T**).
2. Copy, paste, and press Enter:
   ```
   systemctl --user disable --now shefa-collector shefa-vllm
   ```

**To bring it back (and start by itself again):**
```
systemctl --user enable --now shefa-vllm shefa-collector
```
Then wait about 5 minutes.

---

## 5. Is it running? (a quick check)

Open a terminal (**Ctrl+Alt+T**) and type:
```
systemctl --user is-active shefa-vllm shefa-collector
```
- Two lines saying `active` → ✅ running.
- `inactive` → it's stopped (see 4B to start it).
- `failed` → see section 6.

---

## 6. Something's wrong

**The link doesn't open after 10 minutes:**
1. Restart the PC.
2. Wait 5 minutes.
3. Try the link again.

**Still broken?** In a terminal, run:
```
systemctl --user status shefa-collector
```
Send what it shows to whoever looks after the code.

**Where the logs are (for whoever fixes it):**
- Site: `data/collector/logs/serve.log`
- Language model: `data/vllm.log`

---

## 7. Keep your recordings safe

The recordings live on this PC's disk. Once a week, copy a backup to a **USB drive or another disk**:

1. Plug in the USB drive.
2. Open a terminal, go to the project folder, and run (change the USB path to yours):
   ```
   cd ~/"Projects/Shefa-Medical voice agent/SHEFA-the-Medical-receptionist-voice-agent"
   uv run shefa collect backup /media/$USER/YOUR-USB/shefa-backup
   ```
3. Wait until it says `0 problems`.

---

## 8. Things never to do

- ❌ Don't share `127.0.0.1:8101` with anyone.
- ❌ Don't rename the PC in Tailscale. That changes the link and breaks it for everyone.
- ❌ Don't run `tailscale funnel reset` or `tailscale funnel off`. That turns the link off.
