# Submission email (draft — the owner reviews and sends it)

**To:** hr@strategybyte.com.au
**Subject:** AI Engineer Task Submission: Rifat Bin Siraj

Hi StrategyByte team,

Please find my submission for the AI Engineer task below.

1. Landing page: https://bytevoice-bangla.vercel.app
2. Back-end portal: https://bytevoice-bangla.vercel.app/portal  Reviewer login: reviewer@bytevoice-bangla.demo / <password from .env.reviewer>
3. GitHub repository: https://github.com/Rifat024/bytevoice-bangla (access granted to <REVIEWER_GITHUB_OR_EMAILS>, or public)
4. Video overview (≤ 3 min): <VIDEO_URL>

Stack in one line: Next.js on Vercel + LiveKit WebRTC + a Python LiveKit Agents worker running Gemini Live (`bn-BD`) for Bangla speech, with Supabase Postgres (Singapore) for storage and Realtime for the live portal.

A few things worth a look: phone numbers spoken in mixed Bangla/English are validated and read back digit by digit; double booking is blocked by a Postgres exclusion constraint; the receptionist refuses medical advice, staff personal details and other patients' information (with an audit trail in the portal); and returning callers are recognised after a name + number check. Known limitations are listed honestly in the README.

Thank you,
Rifat Bin Siraj
