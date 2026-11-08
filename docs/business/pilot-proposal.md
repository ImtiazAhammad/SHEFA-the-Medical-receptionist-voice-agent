# SHEFA pilot proposal (template)

Fill the `[brackets]`. Prices are **hypotheses to test in the first three conversations**, taken
from our own buyer and market reviews (BDT 10-25k a month for one line); no clinic has agreed to
them. Have a lawyer review this before it is signed.

## 1. What this pilot is

A supervised trial of SHEFA, an automated receptionist that answers your booking line in Bangla and
English, books and changes appointments in your own schedule, and passes anything it cannot do to
your staff. It runs on a server **in your clinic**; conversation text and audio do not leave it.

It is not a doctor. It never gives medical advice, doses or diagnoses, sends emergencies to a
person with a "call 999" message, and never replaces your staff.

## 2. Scope

- **One phone line**, in the hours you choose (we recommend after-hours and overflow when your
  receptionists are busy), for 2 weeks in **shadow mode** (it listens and logs what it would have
  done, your staff answer) then 30 days live.
- **Your doctors and schedules**, loaded and checked by you before the first live call.
- Staff app for your front desk and owner; a booking page at your clinic's own address.
- Not included: hospital-system integration beyond the appointment export (quoted separately),
  payment, SMS and WhatsApp (not built yet), other languages.

## 3. What we measure, and when it counts as a success

Agreed in writing before the pilot, measured from the call log and reported weekly:

| Measure | Success |
|---|---|
| Bookings made by the agent that your staff confirm are correct | at least [20] in the 30 days |
| Calls fully handled with no human | at least [70]% of calls it was given |
| Double bookings or wrong doctor/time | **zero** |
| Emergencies handed to a person | every one, within the same call |
| Calls that ended in silence or an unexplained hang-up | zero |
| Time from the end of the caller's sentence to the agent's reply (95th percentile) | under [2.5] seconds |

If these are not met you may stop, and the setup fee is refunded [in full / pro rata].

## 4. Responsibilities

- **Clinic:** the real schedule and fees; a named person who watches the call-back list daily; a
  doctor who reviews the emergency phrases; a staff phone that SHEFA hands calls to; caller notice
  (the greeting says the call is automated and written down).
- **Vendor:** install and tuning; a named person reachable at [hours/phone]; weekly report; fixes.
- **Both:** the first 20 live calls are listened to together.

## 5. Safety net (not optional)

- A staff line (`FALLBACK_DIAL`) rings if SHEFA is down. Callers are never dropped.
- Past [4] simultaneous calls the next caller is told the lines are busy and queued for a call-back.
- Web bookings are held but marked unconfirmed until your desk confirms them by phone.
- Daily review of call-backs and transcripts for the first weeks; transcripts kept [30] days.

## 6. Price (hypothesis)

| Item | Amount |
|---|---|
| Setup: install, load your directory, tune, train staff | BDT [30,000-60,000] one-off |
| Monthly, one line, pilot period | BDT [15,000-25,000] |
| Hardware | yours, or rented through us at cost + [x]% |
| Carrier / SIP trunk | yours, at carrier rates |
| After the pilot, with an uptime commitment | BDT [40,000-80,000] a month, quoted separately |

No payment is taken for a year in advance. Fees are fixed amounts for defined work and service; there
is no charge that depends on an undefined outcome. [A per-booking fee, if you want one, is capped
at BDT [x] a month and defined in writing; check with your religious adviser if that matters to you.]

## 7. Ending

Either side may end the pilot with [7] days' notice. On ending we delete your data from our
systems on written request and give you a copy of the appointment export. Your data is yours.

## 8. What we have not yet proven (told to you plainly)

SHEFA has been tested with recorded and simulated speech and in a lab. A live call over a real
Bangladeshi trunk, recognition accuracy on real phone audio, and the full multi-call load test are
done together with you in the shadow period. If they do not meet the measures above, the pilot
tells us so before it costs you a single missed patient.
