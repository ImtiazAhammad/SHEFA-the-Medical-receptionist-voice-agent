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
        "আপনার অ্যাপয়েন্টমেন্ট রবিবার, ৮ নভেম্বর সকাল ৯টা ২০ মিনিটে ডাক্তার হোসেন-এর সাথে "
        "বুক হয়েছে। আপনার রেফারেন্স নম্বর ১২।",
        "ডাক্তার রহমান হৃদরোগ বিভাগে বসেন রবিবার, মঙ্গলবার ও বৃহস্পতিবার বিকেল ৪টা থেকে রাত ৮টা। "
        "ভিজিট ফি ৮০০ টাকা।",
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
:root{--bg:#f4f6f4;--panel:#fff;--fg:#14211d;--mute:#5f6f69;--line:#dde3df;--accent:#0b7a63}
@media(prefers-color-scheme:dark){:root{--bg:#0e1513;--panel:#16201d;--fg:#e7eeeb;
--mute:#91a39b;--line:#26332e;--accent:#38b89c}}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.5 system-ui,"Noto Sans Bengali",sans-serif}
main{max-width:820px;margin:0 auto;padding:24px 16px 64px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;
margin:14px 0}
.clip{display:grid;grid-template-columns:2.2em 1fr auto;gap:10px;align-items:center;
margin:8px 0}
.clip b{font-size:20px}.who{color:var(--accent);font-weight:600;display:none}
.revealed .who{display:inline}audio{width:100%}select{font:inherit}
button{font:inherit;padding:10px 16px;border-radius:10px;border:0;background:var(--accent);
color:#fff;cursor:pointer}.mute{color:var(--mute)}table{width:100%;border-collapse:collapse}
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
    return '<tr><td>'+v+'</td><td>'+(s[1]?(s[0]/s[1]).toFixed(2):'—')+'</td><td>'+s[1]+
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
