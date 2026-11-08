# Support and availability terms (template)

Honest terms for a one-person vendor. Promise only what you can staff; raise it later with a team.

| | Pilot | Standard (after the pilot) |
|---|---|---|
| Support hours | [09:00-20:00, Sat-Thu] | [same, plus on-call for outages] |
| First response to "calls are failing" | within [30] minutes in hours | within [30] minutes, any time |
| First response to anything else | next working day | within [4] working hours |
| Uptime target of the AI service | best effort | [99%] measured monthly, excluding clinic power and internet |
| If the AI is down | the dialplan rings the clinic's fallback line; no caller is dropped | same |
| Reports | weekly summary | weekly summary plus monthly review |
| Updates | applied in agreed windows, with a rollback | same |

**What counts as an outage:** the health check reports `degraded` for more than [5] minutes, or
calls reach the fallback line.

**What is not covered:** the clinic's own power, internet or phone trunk; hardware the clinic owns
(unless a hardware plan is bought); misuse; requests outside the agreed scope.

**Named contacts:** vendor [name, phone]; clinic [name, phone].

**Credit:** for each full day of outage beyond the target, [x]% of that month's fee is credited.
