# How to run SHEFA: the simple note

**Nothing works until you start it.** SHEFA doesn't start when the PC turns on. You press
**Start SHEFA**, and it stays on until you press **Stop SHEFA** or shut the PC down.

Two addresses. Don't mix them up:

| Address | Who uses it | Where it opens |
|---|---|---|
| **https://shefa-voice.tail195ef8.ts.net** | Volunteers (anyone) | Any phone or computer, while SHEFA is started **and** the link is on |
| **http://127.0.0.1:8101** | You and the reviewers | **Only on this PC**, while SHEFA is started |

✅ Send people only the `shefa-voice` link. It never changes.
❌ Never send anyone the `127.0.0.1:8101` address. That's your private review room.

---

## 1. Start SHEFA

1. Turn on the PC and log in.
2. Double-click **Start SHEFA** on the desktop.
   (Or press the Windows key, type **SHEFA**, and click **Start SHEFA**.)
   - The first time, Ubuntu may ask about the icon: right-click it → **Allow Launching**.
3. A black window opens and shows dots `.....` while SHEFA wakes up. That takes **1 to 5 minutes**.
4. When it says **✅ SHEFA is running**, the admin page opens in your browser by itself.
5. Press Enter to close the black window. SHEFA keeps running.

## 2. Turn the public link on or off (on the admin page)

The admin page has a **পাবলিক লিংক (Public link)** box at the top of the
**সারসংক্ষেপ (Overview)** tab.

- It says **লিংক চালু (Link is LIVE)** → volunteers can open the link.
- It says **লিংক বন্ধ (Link is OFF)** → nobody can open the link.
- Press **লিংক বন্ধ করুন** to take the link off the internet, or **লিংক চালু করুন** to put it back.
  It asks "are you sure?" first.

The link is the same every time you turn it back on.
The switch remembers its setting: if you turn the link off today, it's still off tomorrow until you turn it on.
Review (127.0.0.1:8101) works whether the link is on or off.

## 3. Review recordings

1. Start SHEFA (step 1).
2. On this PC, open **http://127.0.0.1:8101** and log in with your staff account.

## 4. Stop SHEFA

Double-click **Stop SHEFA** on the desktop (or search **SHEFA** → **Stop SHEFA**).
It says **✅ SHEFA is off**. The link stops opening, and the graphics card is free for other work.

Shutting the PC down also stops SHEFA. Next time, start it again with step 1.

---

## 5. Which button for what?

| I want… | Do this |
|---|---|
| SHEFA working for everyone | **Start SHEFA**, then check the link says **লিংক চালু** |
| Only review, no volunteers coming in | **Start SHEFA**, then **লিংক বন্ধ করুন** |
| A short pause; volunteers' recordings wait on their phones | Admin → Overview → **আপলোড বন্ধ করুন (Pause uploads)**. The page still opens and says SHEFA is resting. Undo with **আপলোড চালু করুন**. |
| The PC for something else (games, other AI) | **Stop SHEFA** |
| Nothing at all | Do nothing. SHEFA doesn't start by itself. |

---

## 6. Something's wrong

**The black window says ❌ SHEFA did not start:**
1. Restart the PC, log in, and press **Start SHEFA** again.
2. Still ❌? Take a photo of the black window and send it to whoever looks after the code.
   Logs for them: `data/collector/logs/serve.log` and `data/vllm.log`.

**The admin page says the link is LIVE, but the link doesn't open:**
Wait a minute and try again. Then press **লিংক বন্ধ করুন** and **লিংক চালু করুন** once.

**The admin page says "এই কম্পিউটার থেকে লিংক বদলানো যাচ্ছে না":**
Tailscale isn't running or isn't logged in. Open the Tailscale app and log in with **regnum.com.bd**.

**Without icons, from a terminal (Ctrl+Alt+T):**
```
cd ~/"Projects/Shefa-Medical voice agent/SHEFA-the-Medical-receptionist-voice-agent"
bash deploy/shefa.sh start     # start
bash deploy/shefa.sh stop      # stop
bash deploy/shefa.sh status    # is it running?
```

**Icons missing (after a reinstall):** run `bash deploy/autostart/install.sh` in the project folder.
**Want it to start by itself at power-on again?** Run `bash deploy/autostart/install.sh --autostart`.

---

## 7. Keep your recordings safe

The recordings live on this PC's disk. Once a week, copy a backup to a **USB drive or another disk**:

1. Plug in the USB drive.
2. Open a terminal (Ctrl+Alt+T) and run (change the USB path to yours):
   ```
   cd ~/"Projects/Shefa-Medical voice agent/SHEFA-the-Medical-receptionist-voice-agent"
   uv run shefa collect backup /media/$USER/YOUR-USB/shefa-backup
   ```
3. Wait until it says `0 problems`.

---

## 8. Things never to do

- ❌ Don't share `127.0.0.1:8101` with anyone.
- ❌ Don't rename the PC in Tailscale. That changes the link and breaks it for everyone.
- ❌ Don't log Tailscale out of **regnum.com.bd**. The link belongs to that account.
