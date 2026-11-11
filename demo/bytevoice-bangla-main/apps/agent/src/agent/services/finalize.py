import logging
from datetime import date
from typing import Any

from google import genai
from google.genai import types

from agent.config import get_settings
from agent.constants import CLINIC_TIMEZONE, LOGGER_NAME
from agent.normalize.phone import validate_bangladesh_mobile
from agent.repositories.calls import (
    CallbackRepository,
    CallEventRecord,
    CallEventRepository,
    CallExtractionRepository,
    CallRecord,
    CallRepository,
    TranscriptRepository,
    TranscriptTurnRecord,
)
from agent.repositories.patients import PatientRecord, PatientRepository
from agent.schemas.extraction import CallExtractionResult
from agent.services.reception import names_match

logger = logging.getLogger(LOGGER_NAME)

KNOWN_SERVICE_CODES = {
    "checkup",
    "scaling",
    "filling",
    "root_canal",
    "extraction",
    "braces_consult",
    "whitening",
}
TOOL_OUTCOMES = {
    "book_appointment": "booked",
    "reschedule_appointment": "rescheduled",
    "cancel_appointment": "cancelled",
    "request_human_callback": "follow_up_needed",
}
OUTCOME_PRIORITY = ("rescheduled", "booked", "cancelled", "follow_up_needed")

EXTRACTION_INSTRUCTIONS = """You extract structured data from a phone call between "Nila", the AI receptionist of a
Bangladeshi dental clinic, and a caller. The transcript is mostly colloquial Bangla with some English words.

Rules:
- Use only what the caller actually said and confirmed. Never invent a name, number, date or reason.
- phone_spoken_raw: copy the caller's digits exactly (Bangla or English digits/words are fine).
- preferred_date: resolve relative days ("আগামী রবিবার") against the call date given below; ISO YYYY-MM-DD.
- service_code: one of checkup, scaling, filling, root_canal, extraction, braces_consult, whitening, or null.
- conversation_outcome: "enquiry" if the caller only asked questions and got answers; "follow_up_needed" if staff
  must call back or something was left unresolved; "incomplete" if the call ended before the caller's need was met.
- summaries: neutral, two sentences, no medical advice.
- translations: natural English for every turn, keyed by seq.
- confidence: 0..1 per field; use 0 when the field was never mentioned."""


def _format_transcript(turns: list[TranscriptTurnRecord]) -> str:
    return "\n".join(
        f"[{turn.seq}] {'Caller' if turn.speaker == 'caller' else 'Nila'}: {turn.text_bn}" for turn in turns
    )


async def _run_extraction(
    call: CallRecord, turns: list[TranscriptTurnRecord], api_key: str | None = None
) -> tuple[CallExtractionResult, str]:
    settings = get_settings()
    client = genai.Client(api_key=api_key or settings.google_api_key or None)
    call_date = call.started_at.astimezone(CLINIC_TIMEZONE)
    contents = (
        f"{EXTRACTION_INSTRUCTIONS}\n\nCall date and time (Asia/Dhaka): {call_date.strftime('%A %Y-%m-%d %H:%M')}\n\n"
        f"Transcript:\n{_format_transcript(turns)}"
    )
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=CallExtractionResult,
        temperature=0.1,
    )
    last_error: Exception | None = None
    for model in (settings.extraction_model, settings.extraction_fallback_model):
        try:
            response = await client.aio.models.generate_content(model=model, contents=contents, config=config)
            if isinstance(response.parsed, CallExtractionResult):
                return response.parsed, model
            return CallExtractionResult.model_validate_json(response.text or ""), model
        except Exception as error:
            logger.exception("extraction attempt failed", extra={"model": model})
            last_error = error
    raise RuntimeError("All extraction models failed") from last_error


def _outcome_from_events(events: list[CallEventRecord]) -> str | None:
    achieved = {
        TOOL_OUTCOMES[str(event.payload.get("tool"))]
        for event in events
        if event.event_type == "tool_result"
        and event.payload.get("ok")
        and event.payload.get("tool") in TOOL_OUTCOMES
    }
    return next((outcome for outcome in OUTCOME_PRIORITY if outcome in achieved), None)


def _valid_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def build_extraction_row(
    result: CallExtractionResult | None, patient: PatientRecord | None, model: str | None
) -> dict[str, Any]:
    """Validate model output and let data written by tools during the call take precedence."""
    confidence: dict[str, Any] = result.confidence.model_dump() if result else {}
    disagreements: list[str] = []

    phone_raw = result.phone_spoken_raw if result else None
    phone_validation = validate_bangladesh_mobile(phone_raw) if phone_raw else None
    phone_e164 = phone_validation.e164 if phone_validation and phone_validation.is_valid else None
    phone_valid = bool(phone_e164) if phone_raw else None

    name_bn = result.patient_name_bn if result else None
    name_en = result.patient_name_en if result else None
    name_confirmed = result.name_confirmed if result else None

    if patient is not None:
        if phone_e164 and patient.phone_e164 and phone_e164 != patient.phone_e164:
            disagreements.append("phone")
        if name_bn and patient.full_name_bn and name_bn.strip() != patient.full_name_bn.strip():
            disagreements.append("patient_name")
        phone_e164 = patient.phone_e164 or phone_e164
        phone_valid = True if patient.phone_e164 else phone_valid
        name_bn = patient.full_name_bn or name_bn
        name_en = patient.full_name_en or name_en
        name_confirmed = True
        confidence["source"] = "tool"
    else:
        confidence["source"] = "transcript"
    if disagreements:
        confidence["disagreements"] = disagreements

    service_code = result.service_code if result and result.service_code in KNOWN_SERVICE_CODES else None
    return {
        "intent": result.intent if result else None,
        "patient_name_bn": name_bn,
        "patient_name_en": name_en,
        "name_confirmed": name_confirmed,
        "phone_spoken_raw": phone_raw,
        "phone_e164": phone_e164,
        "phone_valid": phone_valid,
        "reason_for_visit": result.reason_for_visit if result else None,
        "service_code": service_code,
        "preferred_date": _valid_iso_date(result.preferred_date if result else None),
        "preferred_time_window": result.preferred_time_window if result else None,
        "confidence": confidence,
        "extractor_model": model,
    }


async def _link_caller_to_patient(
    call_id: str, extraction_row: dict[str, Any], calls: CallRepository
) -> None:
    """Attach a call with no tool-linked patient to the caller's record so a follow-up call can recall it."""
    phone_e164 = extraction_row.get("phone_e164")
    name_bn = extraction_row.get("patient_name_bn")
    if not phone_e164 or not name_bn or not extraction_row.get("phone_valid"):
        return
    patients = PatientRepository()
    existing = await patients.find_by_phone(phone_e164)
    if existing is not None and not names_match(name_bn, existing):
        return
    patient = existing or await patients.upsert(phone_e164, name_bn, extraction_row.get("patient_name_en"))
    await calls.update(call_id, {"patient_id": str(patient.id)})
    await CallbackRepository().link_patient(call_id, patient.id)


async def finalize_call(call_id: str, api_key: str | None = None) -> str | None:
    """Turn a finished call's raw transcript and tool events into validated, structured fields and an outcome."""
    calls, turns_repository, events_repository = (
        CallRepository(),
        TranscriptRepository(),
        CallEventRepository(),
    )
    try:
        call = await calls.get(call_id)
        if call is None:
            logger.debug("finalize skipped: call not found", extra={"call_id": call_id})
            return None
        turns = await turns_repository.list_for_call(call_id)
        events = await events_repository.list_for_call(call_id)
        patient = await PatientRepository().get(str(call.patient_id)) if call.patient_id else None
        tool_outcome = _outcome_from_events(events)

        caller_turns = [turn for turn in turns if turn.speaker == "caller"]
        if not caller_turns:
            outcome = tool_outcome or (
                "failed" if any(event.event_type == "error" for event in events) else "incomplete"
            )
            await calls.update(
                call_id,
                {
                    "outcome": outcome,
                    "summary_en": "The caller did not speak.",
                    "summary_bn": "কলার কোনো কথা বলেননি।",
                },
            )
            await events_repository.insert(call_id, "state", {"state": "finalized", "outcome": outcome})
            return outcome

        result: CallExtractionResult | None = None
        model: str | None = None
        try:
            result, model = await _run_extraction(call, turns, api_key)
        except RuntimeError:
            await events_repository.insert(call_id, "error", {"stage": "extraction"})

        extraction_row = build_extraction_row(result, patient, model)
        await CallExtractionRepository().upsert(call_id, extraction_row)
        if patient is None:
            await _link_caller_to_patient(call_id, extraction_row, calls)
        if result:
            known_sequences = {turn.seq for turn in turns}
            for translation in result.translations:
                if translation.seq in known_sequences and translation.text_en.strip():
                    await turns_repository.set_translation(
                        call_id, translation.seq, translation.text_en.strip()
                    )

        outcome = tool_outcome or (result.conversation_outcome if result else "incomplete")
        fields: dict[str, Any] = {"outcome": outcome}
        if call.ended_at is None:
            fields["status"] = "completed"
        if result:
            fields |= {"summary_bn": result.summary_bn, "summary_en": result.summary_en}
        await calls.update(call_id, fields)
        await events_repository.insert(
            call_id, "state", {"state": "finalized", "outcome": outcome, "model": model}
        )
        logger.debug("call finalized", extra={"call_id": call_id, "outcome": outcome})
        return outcome
    except Exception:
        logger.exception("finalize failed", extra={"call_id": call_id})
        try:
            await calls.update(call_id, {"outcome": "incomplete"})
            await events_repository.insert(call_id, "error", {"stage": "finalize"})
        except Exception:
            logger.exception("failed to record finalize failure", extra={"call_id": call_id})
        return None
