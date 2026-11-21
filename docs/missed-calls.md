# Missed-call call-back

A call nobody answers is usually a patient lost to the next clinic. SHEFA can call those people
back itself, a few minutes later, with the normal booking conversation. It opens with:
"আসসালামু আলাইকুম, <clinic> থেকে বলছি। আপনি একটু আগে ফোন করেছিলেন, তখন ধরতে পারিনি…"

**Status: built and tested with a fake phone line. It has never run on a real trunk.** Try it on
one number (your own) before switching it on for a clinic.

## How a number gets on the list

1. **SHEFA was busy on every line.** Those callers are queued automatically
   (`telephony/asterisk.py`).
2. **The desk did not pick up.** The phone system tells SHEFA. In the Asterisk dialplan, after
   ringing the desk:

   ```
   exten => s,n,Dial(PJSIP/desk,25)
   exten => s,n,GotoIf($["${DIALSTATUS}" = "ANSWER"]?done)
   exten => s,n,System(curl -s -m 5 -X POST http://127.0.0.1:8000/api/v1/missed-calls -H "Authorization: Bearer ${SHEFA_PBX_TOKEN}" -H "Content-Type: application/json" -d '{"phone":"${CALLERID(num)}","dialed":"${EXTEN}"}')
   exten => s,n(done),Hangup()
   ```

   The token is one you mint for the phone system (`shefa token --name pbx --role admin`), kept
   in Asterisk's environment, never in the dialplan file. It needs the `calls:place` permission.

`dialed` is the clinic number the patient called. On a machine serving several clinics
(docs/many-clinics.md) it decides whose missed call it is, and whose name SHEFA calls back with.

The same number again within two hours counts as one missed call: people redial.

## When SHEFA calls back

- It waits `delay_minutes` (3) first: the desk may ring back, or the caller may redial.
- Never in quiet hours (the reminders' window, 20:00 to 08:00 by default).
- If the number has booked in the meantime (phone, web or at the desk), SHEFA doesn't call.
- At most `max_attempts` (2) tries, `retry_minutes` (30) apart, then it gives up.
- An answered call becomes "reached", and "booked" once that number books. The owner's weekly
  report counts missed calls and how many became bookings.

## Switching it on

In `configs/local.yaml`:

```yaml
missed_calls:
  enabled: true
```

Then restart SHEFA. The list is at `GET /api/v1/missed-calls`, with phones masked.
