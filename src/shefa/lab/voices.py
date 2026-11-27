"""Blind listening test: the same receptionist lines in every candidate voice.

    shefa lab voices --voice piper:models/piper/bn_BD-google-medium.onnx \\
                     --voice azure:bn-BD-NabanitaNeural --voice vits:models/vits/my_voice

writes voice-test/index.html: per line, one player per voice under a shuffled letter, a
1-5 score for each, and a "Reveal" button that names the voices and averages the scores.
Bangladeshi listeners scoring accent, numbers and loanwords is the measurement that
decides the voice; nobody had listened to the current one before this tool existed.
"""

from __future__ import annotations

import html
import json
import random
from pathlib import Path
from typing import Any

from shefa.lab.report import write_wav

# Lines a receptionist actually says, rendered by the same code as live replies.
PROMPTS: dict[str, list[str]] = {
    "bn": [
        "শেফা ক্লিনিকে আপনাকে স্বাগতম। আমি আপনাকে কিভাবে সাহায্য করতে পারি?",
        "আপনার অ্যাপয়েন্টমেন্ট রবিবার, আট নভেম্বর সকাল নয়টা বিশ মিনিটে ডাক্তার হোসেন-এর সাথে "
        "বুক হয়েছে। আপনার রেফারেন্স নম্বর বারো।",
        "ডাক্তার রহমান হৃদরোগ বিভাগে বসেন রবিবার, মঙ্গলবার ও বৃহস্পতিবার বিকেল চারটা থেকে রাত আটটা। "
        "ভিজিট ফি আটশো টাকা।",
        "দুঃখিত, ওই সময়টি খালি নেই। আমি কি খালি সময়গুলো বলব?",
        "আপনার নাম আর ফোন নম্বরটা বলবেন?",
        "আমি আপনাকে আমাদের রিসেপশনিস্টের কাছে স্থানান্তর করছি। অনুগ্রহ করে অপেক্ষা করুন।",
        "দুঃখিত, আমি স্পষ্টভাবে বুঝতে পারলাম না। আবার বলবেন?",
        "আমি ওষুধের পরামর্শ দিতে পারি না, তবে আপনাকে মেডিসিনের ডাক্তারের সিরিয়াল দিতে পারি।",
        "আপনার cardiology appointment টা কি এই সপ্তাহেই চান?",
        "আসসালামু আলাইকুম। কালকের অ্যাপয়েন্টমেন্টের কথা মনে করিয়ে দিতে ফোন করেছি।",
    ],
    "en": [
        "Thank you for calling SHEFA Clinic. How may I help you today?",
        "Your appointment with Dr. Hossain is booked for Sunday 8 November at 9:20 am. "
        "Your reference number is 12.",
        "Dr. Rahman sees Cardiology patients Sunday, Tuesday and Thursday, 4 to 8 pm.",
        "Sorry, that time is not available. Shall I read out the free times?",
        "I'm transferring you to our receptionist now. Please hold.",
        "I can't give medical advice, but I can book you with our medicine doctor.",
    ],
}


def parse_voice_spec(spec: str) -> dict[str, str]:
    """'piper:models/x.onnx' -> a VoiceConfig mapping (voice_path or voice_id)."""
    provider, _, target = spec.partition(":")
    if provider not in {"piper", "vits", "kokoro", "azure", "elevenlabs"} or not target:
        raise ValueError(
            f"voice {spec!r}: use piper:<file.onnx>, vits:<dir>, kokoro:<voice>, azure:<voice>"
        )
    field = "voice_path" if provider in {"piper", "vits"} else "voice_id"
    return {"provider": provider, field: target}


def label_for(spec: dict[str, str]) -> str:
    target = spec.get("voice_path") or spec.get("voice_id", "")
    return f"{spec['provider']} {Path(target).stem if '/' in target else target}"


async def render(voices: dict[str, Any], prompts: list[str], out: Path, language: str = "bn",
                 seed: int = 7) -> list[dict[str, Any]]:
    """Every prompt in every voice, as WAV files; returns the page's rows (shuffled)."""
    folder = out / "audio"
    folder.mkdir(parents=True, exist_ok=True)
    shuffle = random.Random(seed)
    rows = []
    for index, text in enumerate(prompts):
        clips = []
        for number, (name, voice) in enumerate(voices.items()):
            frames = [frame async for frame in voice.synthesize_stream(text, language)]
            pcm = b"".join(frame.to_s16le_16k_mono() for frame in frames)
            path = f"audio/{index:02d}-{number}.wav"
            write_wav(out / path, pcm)
            clips.append({"voice": name, "src": path})
        shuffle.shuffle(clips)
        rows.append({"text": text, "clips": clips})
    return rows


_PAGE = """<!doctype html><html lang="bn"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SHEFA voice test</title>
<style>
:root{--bg:oklch(0.963 0.006 165);--panel:oklch(0.993 0.003 165);--fg:oklch(0.23 0.012 165);
--mute:oklch(0.41 0.012 165);
--line:oklch(0.895 0.007 165);--accent:oklch(0.5 0.12 158);--on-accent:oklch(0.985 0.004 165);
--rail:oklch(0.5 0.17 265);
--shadow:0 1px 2px oklch(0.3 0.02 165 / .07),0 6px 16px -8px oklch(0.3 0.02 165 / .18)}
@media(prefers-color-scheme:dark){:root{--bg:oklch(0.2 0.008 165);--panel:oklch(0.25 0.009 165);
--fg:oklch(0.95 0.006 165);--mute:oklch(0.8 0.01 165);--line:oklch(0.33 0.01 165);
--accent:oklch(0.58 0.12 158);
--rail:oklch(0.42 0.13 265);--shadow:0 1px 2px oklch(0 0 0 / .35)}}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 "Baloo Da 2","Hind Siliguri","Noto Sans Bengali",system-ui,sans-serif}
main{max-width:820px;margin:0 auto;padding:0 16px 64px}
h1{margin:0 -16px;padding:22px 16px 18px;background:var(--rail);color:oklch(0.985 0.004 165);
font-size:28px;
line-height:1.15;
border-radius:0 0 12px 12px}
.card{background:var(--panel);border-radius:10px;box-shadow:var(--shadow);
padding:16px;margin:14px 0}
.clip{display:grid;grid-template-columns:2.2em 1fr auto;gap:10px;align-items:center;margin:8px 0}
.clip b{font-size:20px}.who{color:var(--accent);font-weight:700;display:none}
.revealed .who{display:inline}audio{width:100%}select{font:inherit;min-height:40px;
border-radius:6px}
button{font:inherit;font-weight:700;min-height:44px;padding:10px 18px;border-radius:6px;border:0;
background:var(--accent);color:var(--on-accent);cursor:pointer}.mute{color:var(--mute)}
table{width:100%;border-collapse:collapse}
td,th{text-align:left;padding:6px;border-bottom:1px solid var(--line)}
</style></head><body><main>
<h1>SHEFA voice test</h1>
<p class="mute">Listen to each line in every voice and give each a score from 1 (robotic,
wrong accent) to 5 (sounds like a Bangladeshi receptionist). The voices are hidden behind
letters, shuffled on every line. Press Reveal when done.</p>
__ROWS__
<div class="card"><button id="reveal">Reveal voices and averages</button>
<div id="result"></div></div>
</main><script>
const rows=__DATA__;
document.getElementById('reveal').onclick=()=>{
  document.body.classList.add('revealed');
  const sums={};document.querySelectorAll('select').forEach(s=>{if(!s.value)return;
    const v=s.dataset.voice;sums[v]=sums[v]||[0,0];sums[v][0]+=+s.value;sums[v][1]++});
  const voices=[...new Set(rows.flatMap(r=>r.clips.map(c=>c.voice)))];
  document.getElementById('result').innerHTML='<table><tr><th>Voice</th><th>Average</th>'+
    '<th>Scored</th></tr>'+voices.map(v=>{const s=sums[v]||[0,0];
    return '<tr><td>'+v+'</td><td>'+(s[1]?(s[0]/s[1]).toFixed(2):'-')+'</td><td>'+s[1]+
    '</td></tr>'}).join('')+'</table>'};
</script></body></html>"""


def write_page(rows: list[dict[str, Any]], out: Path) -> Path:
    cards = []
    for row in rows:
        clips = "".join(
            f'<div class="clip"><b>{chr(65 + i)}</b><audio controls preload="none" '
            f'src="{html.escape(clip["src"])}"></audio><span><select data-voice='
            f'"{html.escape(clip["voice"])}"><option value="">score</option>'
            + "".join(f"<option>{n}</option>" for n in range(1, 6))
            + f'</select> <span class="who">{html.escape(clip["voice"])}</span></span></div>'
            for i, clip in enumerate(row["clips"])
        )
        cards.append(f'<div class="card"><p>{html.escape(row["text"])}</p>{clips}</div>')
    page = out / "index.html"
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    page.write_text(_PAGE.replace("__ROWS__", "".join(cards)).replace("__DATA__", data),
                    encoding="utf-8")
    return page
