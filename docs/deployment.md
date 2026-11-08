# Deploying SHEFA for a clinic

A runbook for one clinic on one server. It says what is verified and what is not (see the end).

## 1. What you need

| Item | Minimum | Notes |
|---|---|---|
| Server | Linux, 8 cores, 32 GB RAM, NVIDIA GPU with 16 GB (24 GB is comfortable) | Speech recognition, the language model and the voice share the GPU. |
| Disk | 100 GB SSD, **full-disk encryption (LUKS)** | The clinic directory (patient names and numbers) is not encrypted by SHEFA because it must be searched by number. LUKS protects it. |
| Phone line | A licensed Bangladeshi SIP trunk (BTRC) | See `docs/asterisk-setup.md` and `docs/carrier-inquiry.md`. |
| A human line | A staff phone SHEFA rings when it is down or hands over | Set `FALLBACK_DIAL` and `escalation.on_call_numbers`. |
| Power and network | UPS; a second internet path if the clinic can afford it | A call-taking box that loses power takes the phone line with it unless the fallback rings a person. |

## 2. Install

```bash
sudo useradd --system --create-home --home-dir /opt/shefa shefa
sudo -u shefa git clone <repo> /opt/shefa && cd /opt/shefa
sudo -u shefa uv sync
sudo -u shefa python scripts/fetch_stt_model.py          # Bangla speech model
sudo -u shefa uv run shefa doctor                          # fetches the voice, checks the rest
# language model server (recommended for more than one line):
sudo -u shefa uv venv .venv-vllm --python 3.12
sudo -u shefa env VIRTUAL_ENV=.venv-vllm UV_HTTP_TIMEOUT=900 uv pip install vllm
sudo -u shefa uv run shefa setup --profile vllm
sudo -u shefa uv run shefa clinic import <your-clinic-file>.yaml   # real doctors, schedules, fees
sudo -u shefa uv run shefa staff add <owner-name> --role owner
```

Edit `configs/local.yaml`:

- `escalation.on_call_numbers: ["+8801XXXXXXXXX"]`. **Without it the health check reports degraded
  and an emergency call cannot be handed to a person.**
- `telephony.provider: asterisk`, `telephony.max_concurrent_calls` (see the load test below).
- `storage.keep_transcripts`, `storage.transcript_retention_days` (30 is a sensible start), and
  keep `storage.encrypt_at_rest: true`.
- If you switch transcripts off, edit the greeting so it no longer says the call is written down.

## 3. Secrets

Copy `deploy/shefa.env.example` to `/etc/shefa/shefa.env`, mode 0600. Generate `SHEFA_DATA_KEY` once
and store a copy **somewhere other than the server's backups** (a sealed envelope in the clinic safe is
fine). Lose the key and the stored transcripts are unreadable. Never commit the file.

## 4. Run it as a service

```bash
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now shefa.service shefa-backup.timer
journalctl -u shefa -f
```

`Restart=always` brings the service back within seconds of a crash. `shefa serve` starts and waits
for the model server itself (about 75 s once the weights are cached).

## 5. Asterisk

Render the configuration from the templates (`docs/asterisk-setup.md`) with `FALLBACK_DIAL` set.
The dialplan then rings that line if SHEFA does not take the call within 5 seconds, so a restart or a
dead GPU box does not drop callers.

## 6. HTTPS and the staff app

Put a reverse proxy with a real certificate in front of port 8000 (Caddy example):

```
clinic.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

and set `booking.trust_forwarded_for: true` **only** behind a proxy you run, so the rate limits see
the patient's address and not the proxy's. The patient page is `/book`; the staff app is `/app`.

## 7. Backups and restore

`shefa-backup.timer` writes `/var/backups/shefa/shefa-*.db` nightly (online backup, safe while
running; keeps 30). One file holds calls, the directory, staff accounts and the audit trail.
**Test a restore** before go-live: stop the service, copy a backup over `data/shefa.db`, start it,
sign in, open yesterday's calls. A backup that has never been restored is a hope, not a backup.

## 8. Monitoring

`GET /health` (needs a token with `sessions:read`) returns `healthy` or `degraded` with `database`,
`asterisk` and `emergency_transfer`. Poll it every minute from a second machine and alert a person
on `degraded`. SHEFA logs an error at start-up if `on_call_numbers` is empty. Alert on the call-back
list growing: it means people are waiting for a human.

## 9. Capacity

`telephony.max_concurrent_calls` defaults to 3. A caller beyond it hears a busy message, a call-back
is queued with their number, and the line is released.

Measured on a 16 GB RTX 4060 Ti with the Bangla speech model and vLLM loaded together (12.4 GB of
the card in use; the voice runs on the CPU), callers pausing 6 s between turns
(`docs/research/2026-11-09-vllm-vs-ollama.md`):

| Callers | Speech recognition p95 | Language model p95 | Both, worst case |
|---|---|---|---|
| 3 | 1.9 s | 1.4 s | about 3.3 s |
| 5 | 4.9 s | 1.4 s | about 6.3 s |
| 8 | 8.1 s | 1.4 s | unusable |

Speech recognition is now the limit: about 0.3-0.5 s per utterance, one after another. Letting
two or three decode at once (`models.adapters.stt_whisper_local.concurrency`) helps only a little
(5 callers: 4.9 s, 4.2 s, 3.5 s). A larger GPU, or a smaller speech model, is the real fix. The
test is deliberately harsher than real callers, who listen as well as talk, so treat these as an
upper bound on latency. **A real-call load test over the trunk has not been done.**

## 10. Go-live checklist

- [ ] Real doctors, schedules and fees imported and checked by the clinic.
- [ ] `on_call_numbers` and `FALLBACK_DIAL` set; a test call hands over to a human phone.
- [ ] Emergency phrases reviewed and signed off by the clinic's doctor (`configs/default.yaml`,
      `escalation.emergency_keywords`; test with `tests/unit/test_emergency_recall.py`).
- [ ] Greeting wording approved by the clinic (it says the call is automated and written down).
- [ ] LUKS on the data disk; `SHEFA_DATA_KEY` backed up apart from the database.
- [ ] A backup restored once.
- [ ] 20 real test calls made by staff over the real trunk, including noisy ones.
- [ ] A named person at the clinic and a named person at the vendor who answer when it fails.

## What is NOT verified (be honest with the clinic)

- A real call over a real trunk through Asterisk (no live trunk was available in development).
- Bangla recognition accuracy on 8 kHz telephone audio (measured only on clean and simulated audio).
- The complete load test (speech + model + voice at once).
- Barge-in (a caller interrupting the agent).
- Whether the Bangla voice sounds natural to Bangladeshi listeners (nobody on the team has judged it).
