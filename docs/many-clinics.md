# Many clinics on one SHEFA machine

A chamber can't buy a GPU, but one SHEFA machine can answer for many of them. Each clinic lives in
**its own database file**: its doctors, patients, bookings, SMS log, missed calls and call log.
Two clinics' patients can't mix through a forgotten filter, because the separation is physical.

With no `clinics:` list in the config, SHEFA is one clinic exactly as before.

## Set up

`configs/local.yaml`:

```yaml
clinics:
  - id: alo                      # lower-case letters, digits, dashes
    name_bn: আলো ক্লিনিক
    name_en: Alo Clinic
    db_path: data/clinics/alo.db # default data/clinics/<id>.db
    numbers: ["09612000001"]     # the numbers patients dial for this clinic
  - id: nur
    name_bn: নূর চেম্বার
    numbers: ["01811000002"]
```

Restart SHEFA. Each clinic's file is created on first use.

## Who sees what

| Way in | Which clinic |
|---|---|
| A phone call | The number dialled. The dialplan sets `SHEFA_DIALED` (like `SHEFA_CALLER`). An unknown number goes to the default clinic and is logged. |
| A staff account made with `--clinic` | Always its own clinic. A header can't change it. |
| An owner account with no clinic (you) | The default clinic, or the one picked with `?clinic=<id>` in the address (kept for that browser tab) |
| The patient booking page | `/book?clinic=<id>`. An unknown id is refused, never swapped for the default clinic. |
| Reminders, missed-call call-backs | One loop per clinic |

Accounts:

```
shefa staff add alo-owner --role owner --name "Alo owner" --clinic alo
```

An owner can only see, create, reset or switch off accounts of their own clinic. New accounts made in
the app belong to the creator's clinic. Each clinic sets up its own doctors and chamber days in
the app (Setup), and its weekly report counts only its own calls and bookings.

## Dialplan

Pass the dialled number alongside the caller's, before handing the call to SHEFA:

```
same => n,Set(SHEFA_DIALED=${EXTEN})
same => n,Set(SHEFA_CALLER=${CALLERID(num)})
```

## Not yet

- Calls from the browser (demo console) always use the default clinic.
- There's no screen for adding a clinic. Clinics are added in the config.
- Backups: `shefa collect backup` covers the voice collection only. Copy `data/clinics/` too.
