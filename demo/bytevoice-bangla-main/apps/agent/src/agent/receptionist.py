import logging
from collections.abc import AsyncIterable, Awaitable, Callable

from livekit import rtc
from livekit.agents import Agent, ModelSettings, RunContext, function_tool, llm
from livekit.agents.beta.tools import EndCallTool
from pydantic import BaseModel, ValidationError

from agent.audio.smoothing import fade_out_tail
from agent.constants import (
    ENGLISH_REPLY_HINT,
    LOGGER_NAME,
    SYSTEM_UNAVAILABLE_MESSAGE,
    TOOL_CHIP_ERROR_LABELS,
    TOOL_CHIP_LABELS,
)
from agent.normalize.language import is_mostly_english
from agent.schemas.tools import (
    AvailabilityArguments,
    BookingArguments,
    CallbackArguments,
    CallerHistoryArguments,
    CancelArguments,
    ClinicInfoArguments,
    ClinicInfoTopic,
    FindAppointmentsArguments,
    PhoneCheckArguments,
    RescheduleArguments,
    ToolOutcome,
)
from agent.services.call_recorder import CallRecorder
from agent.services.reception import ReceptionService

logger = logging.getLogger(LOGGER_NAME)

END_CALL_EXTRA_DESCRIPTION = (
    "Call this after summarising what was arranged and saying goodbye in Bangla, "
    "or after a polite goodbye when the caller stays silent or keeps abusing."
)


class Receptionist(Agent):
    def __init__(
        self, *, instructions: str, reception: ReceptionService | None, recorder: CallRecorder | None
    ) -> None:
        super().__init__(
            instructions=instructions, tools=[EndCallTool(extra_description=END_CALL_EXTRA_DESCRIPTION)]
        )
        self._reception = reception
        self._recorder = recorder

    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        if is_mostly_english(new_message.text_content or ""):
            turn_ctx.add_message(role="system", content=ENGLISH_REPLY_HINT)

    async def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings):
        return fade_out_tail(Agent.default.tts_node(self, text, model_settings))

    async def realtime_audio_output_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        return fade_out_tail(Agent.default.realtime_audio_output_node(self, audio, model_settings))

    async def _run_tool[ArgumentsT: BaseModel](
        self,
        tool_name: str,
        arguments_type: type[ArgumentsT],
        raw_arguments: dict[str, object],
        operation: Callable[[ReceptionService, ArgumentsT], Awaitable[ToolOutcome] | ToolOutcome],
    ) -> str:
        start_bn, start_en, success_bn, success_en = TOOL_CHIP_LABELS[tool_name]
        recorder = self._recorder
        if recorder:
            recorder.record_event("tool_call", {"tool": tool_name, "arguments": raw_arguments})
            await recorder.publish_tool_chip(tool_name, "start", start_bn, start_en)
        try:
            if self._reception is None:
                outcome = ToolOutcome(ok=False, message_for_agent=SYSTEM_UNAVAILABLE_MESSAGE)
            else:
                arguments = arguments_type.model_validate(raw_arguments)
                result = operation(self._reception, arguments)
                outcome = await result if isinstance(result, Awaitable) else result
        except ValidationError as error:
            logger.debug("tool arguments rejected", extra={"tool": tool_name, "errors": error.errors()})
            outcome = ToolOutcome(
                ok=False, message_for_agent="তথ্য অসম্পূর্ণ। রোগীর কাছ থেকে প্রয়োজনীয় তথ্য নিয়ে আবার চেষ্টা করো।"
            )
        except Exception as error:
            logger.exception("tool failed", extra={"tool": tool_name})
            if recorder:
                recorder.record_event("error", {"tool": tool_name, "error": type(error).__name__})
            outcome = ToolOutcome(ok=False, message_for_agent=SYSTEM_UNAVAILABLE_MESSAGE)
        if recorder:
            if outcome.ok and self._reception and self._reception.state.known_phone_e164:
                recorder.allowed_phone_numbers.add(self._reception.state.known_phone_e164)
            recorder.record_event(
                "tool_result",
                {
                    "tool": tool_name,
                    "ok": outcome.ok,
                    "data": outcome.data,
                    "message": outcome.message_for_agent,
                },
            )
            if outcome.ok:
                await recorder.publish_tool_chip(tool_name, "success", success_bn, success_en)
            else:
                await recorder.publish_tool_chip(tool_name, "error", *TOOL_CHIP_ERROR_LABELS)
        return outcome.model_dump_json(exclude_none=True)

    @function_tool
    async def get_clinic_info(self, context: RunContext, topic: ClinicInfoTopic) -> str:
        """Look up verified clinic facts. Never answer clinic facts from memory.

        Args:
            topic: One of hours, location, services, fees, preparation, doctors, contact.
        """
        return await self._run_tool(
            "get_clinic_info",
            ClinicInfoArguments,
            {"topic": topic},
            lambda service, arguments: service.clinic_info(arguments),
        )

    @function_tool
    async def check_phone_number(self, context: RunContext, phone_spoken: str) -> str:
        """Validate the caller's Bangladeshi mobile number and get the digit-by-digit Bangla read-back.

        Args:
            phone_spoken: The number exactly as the caller said it, in digits or words (Bangla or English).
        """
        return await self._run_tool(
            "check_phone_number",
            PhoneCheckArguments,
            {"phone_spoken": phone_spoken},
            lambda service, arguments: service.check_phone(arguments),
        )

    @function_tool
    async def check_availability(
        self,
        context: RunContext,
        date_text: str,
        time_hint: str | None = None,
        service_code: str | None = None,
        doctor_name: str | None = None,
    ) -> str:
        """Find up to three free appointment slots. Returns slot codes to use with book_appointment.

        Args:
            date_text: The day as the caller said it, e.g. "আগামী রবিবার", "কাল", "১০ তারিখ", or an ISO date.
            time_hint: Preferred time as said, e.g. "সন্ধ্যা", "সকাল", "সাড়ে ৫টা". Omit if no preference.
            service_code: One of the clinic's service codes (checkup, scaling, filling, root_canal, extraction, braces_consult, whitening). Use checkup when unsure.
            doctor_name: Only if the caller asked for a specific doctor.
        """
        return await self._run_tool(
            "check_availability",
            AvailabilityArguments,
            {
                "date_text": date_text,
                "time_hint": time_hint,
                "service_code": service_code,
                "doctor_name": doctor_name,
            },
            lambda service, arguments: service.check_availability(arguments),
        )

    @function_tool
    async def book_appointment(
        self,
        context: RunContext,
        patient_name: str,
        phone_spoken: str,
        slot_code: str,
        confirmed: bool,
        patient_name_en: str | None = None,
        reason: str | None = None,
    ) -> str:
        """Book the slot after reading back all details and hearing an explicit yes from the caller.

        Args:
            patient_name: Patient's name as confirmed by the caller, in Bangla script if spoken in Bangla.
            phone_spoken: The confirmed mobile number.
            slot_code: A slot_code returned by check_availability in this call.
            confirmed: True only if the caller explicitly said yes to the full read-back.
            patient_name_en: The same name in English letters, if you can transliterate it.
            reason: Short reason for the visit in the caller's words.
        """
        return await self._run_tool(
            "book_appointment",
            BookingArguments,
            {
                "patient_name": patient_name,
                "phone_spoken": phone_spoken,
                "slot_code": slot_code,
                "confirmed": confirmed,
                "patient_name_en": patient_name_en,
                "reason": reason,
            },
            lambda service, arguments: service.book(arguments),
        )

    @function_tool
    async def recall_caller_history(self, context: RunContext, phone_spoken: str, patient_name: str) -> str:
        """Check whether this caller has called before and load their previous call summaries, open callback
        requests and upcoming appointments. Call once, right after the caller confirms their name and number.

        Args:
            phone_spoken: The caller's confirmed mobile number.
            patient_name: The caller's confirmed name.
        """
        return await self._run_tool(
            "recall_caller_history",
            CallerHistoryArguments,
            {"phone_spoken": phone_spoken, "patient_name": patient_name},
            lambda service, arguments: service.recall_caller_history(arguments),
        )

    @function_tool
    async def find_appointments(self, context: RunContext, phone_spoken: str, patient_name: str) -> str:
        """Find the caller's own upcoming appointments. Both the name and the number must match.

        Args:
            phone_spoken: The caller's mobile number.
            patient_name: The patient's name the appointment was booked under.
        """
        return await self._run_tool(
            "find_appointments",
            FindAppointmentsArguments,
            {"phone_spoken": phone_spoken, "patient_name": patient_name},
            lambda service, arguments: service.find_appointments(arguments),
        )

    @function_tool
    async def reschedule_appointment(
        self, context: RunContext, appointment_code: str, new_slot_code: str, confirmed: bool
    ) -> str:
        """Move a verified appointment to a new slot after the caller confirms.

        Args:
            appointment_code: An appointment_code returned by find_appointments in this call.
            new_slot_code: A slot_code returned by check_availability in this call.
            confirmed: True only if the caller explicitly agreed to the change.
        """
        return await self._run_tool(
            "reschedule_appointment",
            RescheduleArguments,
            {"appointment_code": appointment_code, "new_slot_code": new_slot_code, "confirmed": confirmed},
            lambda service, arguments: service.reschedule(arguments),
        )

    @function_tool
    async def cancel_appointment(self, context: RunContext, appointment_code: str, confirmed: bool) -> str:
        """Cancel a verified appointment after the caller confirms.

        Args:
            appointment_code: An appointment_code returned by find_appointments in this call.
            confirmed: True only if the caller explicitly agreed to cancel.
        """
        return await self._run_tool(
            "cancel_appointment",
            CancelArguments,
            {"appointment_code": appointment_code, "confirmed": confirmed},
            lambda service, arguments: service.cancel(arguments),
        )

    @function_tool
    async def request_human_callback(
        self,
        context: RunContext,
        reason: str,
        priority: int = 2,
        phone_spoken: str | None = None,
        patient_name: str | None = None,
    ) -> str:
        """Ask clinic staff or a doctor to call the caller back (medical questions, unknown info, complaints).

        Args:
            reason: Short summary of what the caller needs.
            priority: 1 = urgent, 2 = normal, 3 = low.
            phone_spoken: The caller's mobile number, if not already confirmed in this call.
            patient_name: The caller's name, if known.
        """
        return await self._run_tool(
            "request_human_callback",
            CallbackArguments,
            {
                "reason": reason,
                "priority": priority,
                "phone_spoken": phone_spoken,
                "patient_name": patient_name,
            },
            lambda service, arguments: service.request_callback(arguments),
        )
