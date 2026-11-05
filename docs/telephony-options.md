# Reaching the phone network: why SIP, and the options

Written 2026-11-04 after Amber IT declined to provide a SIP trunk (they had stopped selling to
clients after misuse by earlier customers). The software side is ready: `docs/asterisk-setup.md`.

## Why a SIP trunk is needed

A phone number belongs to a licensed operator, and only licensed operators may put calls into the
phone network. A server on the internet cannot "dial 01711..." by itself. A SIP trunk is the
hand-off: SIP carries call set-up (ring, answer, hang up), RTP carries the audio in 20 ms packets.

```
Patient's phone -- mobile/landline network -- Operator -- SIP trunk -- Asterisk -- SHEFA (AudioSocket)
```

In Bangladesh carrying calls into the network needs a BTRC licence (IPTSP etc.). Routing calls any
other way is the illegal VoIP termination BTRC prosecutes, which is why providers vet buyers.

## Options

| Option | What it is | Notes |
|---|---|---|
| SIP trunk from an IPTSP | A number (usually 09xx) plus SIP credentials | What the code targets |
| IP-phone line / SIP account from an IPTSP | The product sold for IP desk phones and softphones | Often easier to get; Asterisk registers as that phone; fine for 1-2 channels |
| Clinic's existing landline + FXO gateway | A box (e.g. Grandstream HT813) that turns a normal line into SIP | Clinic's own number; one call per line; good for a pilot. Outbound through it needs a small code addition |
| Mobile operators' enterprise products | GP / Robi / Banglalink business IP telephony or hosted PBX | Formal KYC instead of a blanket no |
| GSM gateway / SIM box | SIMs in a box | Do not use: blocked by operators, and the offence BTRC prosecutes |

Apply in the **clinic's name** (trade licence), ask small (1 number, 2 channels, mostly inbound,
reminders to own patients only). Inquiry text in Bangla and English: `docs/carrier-inquiry.md`.

## Telecom details to get right

- Audio is narrowband (8 kHz, 300-3400 Hz); use G.711 A-law (`alaw`), refuse G.729. Measure
  speech recognition on the phone path, not the browser.
- NAT is the usual cause of one-way audio: set `PUBLIC_IP`, forward the RTP range (10000-20000),
  allow 5060 and RTP only from the provider's IPs.
- DTMF RFC 2833/4733; caller ID must be the clinic's authorised number; ask the provider's number
  format for outbound (`+880...`, `880...` or `01...`).
- 2 channels means 2 simultaneous calls; a transfer bridged through the trunk uses two.
- Say it is an automated assistant; outbound only to the clinic's own patients about their own
  appointments; quiet hours are enforced; recording only with consent; tell emergency callers to
  dial **999** (not yet in the emergency prompt).

## Testing without a trunk

1. Browser console (`shefa serve`, typed chat or microphone).
2. Asterisk + a softphone (Linphone/Zoiper, extension 1001 dials 1000): the exact production path
   minus the carrier; `docs/asterisk-setup.md`.
3. `scripts/simulate_call.py` (plays Asterisk over AudioSocket) and `shefa lab run --speech`.
4. FXO gateway on any landline for real calls.

When a trunk arrives: set `SIP_TRUNK_HOST`, `SIP_TRUNK_USER`, `SIP_TRUNK_PASSWORD`, `PUBLIC_IP`,
`shefa asterisk render`, restart Asterisk, then test inbound from mobile and landline, a reminder
out (check caller ID), DTMF, a transfer, hang-up mid-sentence, two calls at once, and a one-hour
idle soak.
