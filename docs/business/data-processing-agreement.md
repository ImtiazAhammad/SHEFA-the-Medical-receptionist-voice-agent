# Data processing terms (template, NOT legal advice)

Have a Bangladeshi lawyer adapt and approve this before use. It reflects how SHEFA actually works
(see `docs/security.md`); do not promise more than the software does.

**Parties.** The clinic ([name]) decides why and how patient data is used (the controller). The
vendor ([name]) installs and supports SHEFA on the clinic's server (the processor).

1. **Purpose.** Answering calls, booking and changing appointments, handing calls to staff,
   reminders. Nothing else. The vendor does not use patient data to train models, for advertising,
   or for any purpose of its own, and does not sell or share it.
2. **Where data lives.** On the clinic's own server in Bangladesh. The vendor does not copy patient
   data off that server. If remote support needs access, the clinic opens it, the vendor's access is
   logged, and it ends when the work ends.
3. **What is held.** Patient name, phone number, appointments and reasons for visit; call
   transcripts and call-back details (encrypted at rest); staff accounts; an audit trail. Call audio
   is not stored.
4. **Security.** As described in `docs/security.md`: encrypted transcripts, full-disk encryption on
   the server, role-based access, audit trail, rate-limited public page. The clinic keeps the
   transcript key; the vendor holds no copy.
5. **Retention and deletion.** Transcripts are kept [30] days (configurable) and can be deleted by
   the clinic's owner at any time. On ending the agreement the vendor deletes any data it holds on
   written request and confirms in writing within [14] days.
6. **Staff of the vendor.** Only named people, bound by confidentiality, may access the system.
7. **Notification of a breach.** The vendor tells the clinic within [24] hours of learning of a
   breach affecting its data and helps the clinic respond.
8. **Caller notice and consent.** The greeting tells callers the assistant is automated and that
   the call is written down, and how to reach a person. The clinic is responsible for any further
   notice its own policy or the law requires and approves the greeting wording.
9. **Audit.** The clinic may review the audit trail and the vendor's access log at any time.
10. **Liability.** [To be set by the parties' lawyers.] SHEFA gives no medical advice and does not
    replace clinical judgement or staff; emergency handling is a safety net, not a guarantee.
11. **Law.** [Governing law and the data-protection rules that apply to the clinic.]
