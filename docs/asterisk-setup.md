# Asterisk + Bangladeshi SIP trunk setup

SHEFA answers and places calls through your own Asterisk server connected to a BTRC-licensed
IPTSP trunk. No per-minute cloud telephony bill, and call audio never leaves your machines.

```
patient phone ── carrier ── SIP trunk ── Asterisk ──AudioSocket (TCP 4573)── SHEFA
                                            └──────ARI REST (127.0.0.1:8088)── SHEFA (hang up, transfer, dial)
```

## 1. Get a trunk
Send `docs/carrier-inquiry.md` to at least three providers and fill the comparison table.
You need: host/port, username + password (or your server's IP whitelisted), a DID, the
codecs they accept (G.711 a-law/µ-law), and written permission for automated reminder calls.

## 2. Render and start Asterisk
```bash
export SIP_TRUNK_HOST=sip.example.net SIP_TRUNK_USER=clinic01 \
       SIP_TRUNK_PASSWORD=... ARI_PASSWORD=... PUBLIC_IP=203.0.113.9   # PUBLIC_IP only behind NAT
shefa asterisk render --out deploy/asterisk/rendered      # directory is gitignored, mode 700
docker compose -f deploy/asterisk/docker-compose.yml up -d
docker compose -f deploy/asterisk/docker-compose.yml exec asterisk asterisk -rx "pjsip show registrations"
```
Open UDP 5060 and the RTP range (10000-20000) to the carrier's IPs only.

## 3. Point SHEFA at it
```yaml
telephony:
  provider: asterisk
  asterisk:
    ari_password: "${ARI_PASSWORD}"
    trunk_endpoint: "PJSIP/trunk"
    caller_id: "096XXXXXXXX"      # the number patients should see on reminder calls
```
Start the server; it listens for AudioSocket on `127.0.0.1:4573`. Call the DID and talk to it.

## 4. Check
- `pjsip show registrations` says `Registered`.
- A test call shows `AudioSocket call connected` in the SHEFA log.
- `GET /health` reports `asterisk: ok`.
- Ask the carrier for the real codec and caller-ID behaviour before going live; the template
  allows a-law and µ-law.
