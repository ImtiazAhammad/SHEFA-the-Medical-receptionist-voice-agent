# Asterisk + Bangladeshi SIP trunk setup

SHEFA answers and places calls through your own Asterisk server connected to a BTRC-licensed
IPTSP trunk. No per-minute cloud telephony bill, and call audio never leaves your machines.

```
patient phone ── carrier ── SIP trunk ── Asterisk ──AudioSocket (TCP 4573)── SHEFA
                                            └──────ARI REST (127.0.0.1:8088)── SHEFA (hang up, transfer, dial)
```

## 0. Use your own phone today (no carrier needed)

Install a free softphone app on your phone (Linphone or Zoiper) and let it join your Asterisk over
Wi-Fi. Then you can call the agent, and the agent can call you.

```bash
sudo apt install asterisk                       # Asterisk 20+ (needs res_audiosocket and ARI)
export ARI_PASSWORD=$(openssl rand -hex 12) SOFTPHONE_PASSWORD=$(openssl rand -hex 6)
echo "ARI_PASSWORD=$ARI_PASSWORD  SOFTPHONE_PASSWORD=$SOFTPHONE_PASSWORD"     # keep these
shefa asterisk render --out deploy/asterisk/rendered
sudo cp deploy/asterisk/rendered/* /etc/asterisk/ && sudo systemctl restart asterisk
```
Put `telephony.provider: asterisk` and `telephony.asterisk.ari_password: <ARI_PASSWORD>` in
`configs/local.yaml`, then `shefa serve`.

In the phone app add a SIP account: **username `1001`**, **password = SOFTPHONE_PASSWORD**,
**domain = this computer's Wi-Fi IP**, transport UDP.

- **Phone calls the agent:** dial `1000`.
- **Agent calls the phone:** console, Talk tab, "Have the agent call me" (or reminders; use number `1001`).

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
