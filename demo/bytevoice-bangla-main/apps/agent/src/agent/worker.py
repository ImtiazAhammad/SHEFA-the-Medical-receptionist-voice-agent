import asyncio
import logging

from dotenv import load_dotenv
from livekit.agents import AgentServer, AgentSession, JobContext, cli
from livekit.agents.voice.events import CloseEvent, ConversationItemAddedEvent, UserStateChangedEvent

from agent.config import get_settings
from agent.constants import (
    CALL_DATA_TOPIC,
    CALL_LIMIT_INSTRUCTION,
    LOGGER_NAME,
    SILENCE_GOODBYE_INSTRUCTION,
    SILENCE_REPROMPT_INSTRUCTION,
)
from agent.engines import build_session
from agent.prompts.persona import GREETING_INSTRUCTION, build_instructions
from agent.receptionist import Receptionist
from agent.repositories.appointments import AppointmentRepository
from agent.repositories.calls import CallbackRepository, CallRepository
from agent.repositories.catalog import CatalogRepository
from agent.repositories.patients import PatientRepository
from agent.schemas.catalog import ClinicCatalog
from agent.security.visitor_key import visitor_key_from_metadata
from agent.services.call_recorder import CallRecorder
from agent.services.finalize import finalize_call
from agent.services.reception import ReceptionService, ReceptionStores

load_dotenv(".env.local")
load_dotenv(".env")

logger = logging.getLogger(LOGGER_NAME)
SHUTDOWN_TIMEOUT_SECONDS = 90.0
WORKER_LOAD_THRESHOLD = 0.95
server = AgentServer(
    shutdown_process_timeout=SHUTDOWN_TIMEOUT_SECONDS, num_idle_processes=1, load_threshold=WORKER_LOAD_THRESHOLD
)


async def _load_catalog(clinic_id: str) -> ClinicCatalog | None:
    try:
        return await CatalogRepository().load(clinic_id)
    except Exception:
        logger.exception("clinic catalog unavailable; tools will offer a callback instead")
        return None


async def _say_and_close(session: AgentSession, instructions: str) -> None:
    try:
        await session.generate_reply(instructions=instructions, allow_interruptions=False)
    except Exception:
        logger.exception("failed to speak closing line")
    finally:
        session.shutdown()


def _attach_conversation_handlers(session: AgentSession, recorder: CallRecorder) -> None:
    silence_count = 0
    background: set[asyncio.Task[None]] = set()

    def _spawn(coroutine) -> None:
        task = asyncio.create_task(coroutine)
        background.add(task)
        task.add_done_callback(background.discard)

    @session.on("conversation_item_added")
    def _on_item(event: ConversationItemAddedEvent) -> None:
        item = event.item
        role = getattr(item, "role", None)
        if role not in ("user", "assistant"):
            return
        metrics = dict(getattr(item, "metrics", {}) or {})
        recorder.record_turn(
            speaker="caller" if role == "user" else "agent",
            text=getattr(item, "text_content", None) or "",
            interrupted=bool(getattr(item, "interrupted", False)),
            spoken_at=metrics.get("started_speaking_at") or getattr(item, "created_at", None),
            metrics=metrics,
        )

    @session.on("user_state_changed")
    def _on_user_state(event: UserStateChangedEvent) -> None:
        nonlocal silence_count
        if event.new_state != "away":
            return
        silence_count += 1
        recorder.record_event("state", {"state": "caller_silent", "count": silence_count})
        if silence_count == 1:
            session.generate_reply(instructions=SILENCE_REPROMPT_INSTRUCTION)
        elif silence_count == 2:
            _spawn(_say_and_close(session, SILENCE_GOODBYE_INSTRUCTION))


async def _enforce_call_limit(session: AgentSession, recorder: CallRecorder, max_call_seconds: int) -> None:
    await asyncio.sleep(max_call_seconds)
    logger.debug("call limit reached", extra={"max_call_seconds": max_call_seconds})
    recorder.record_event("state", {"state": "call_limit_reached", "seconds": max_call_seconds})
    await _say_and_close(session, CALL_LIMIT_INSTRUCTION)


@server.rtc_session(agent_name=get_settings().agent_name)
async def receptionist_session(context: JobContext) -> None:
    settings = get_settings()
    context.log_context_fields = {"room": context.room.name, "voice_engine": settings.voice_engine.value}
    recorder = CallRecorder(
        room=context.room, clinic_id=settings.clinic_id, engine=settings.voice_engine.value
    )
    visitor_api_key = visitor_key_from_metadata(context.job.metadata, settings.internal_api_token)
    try:
        catalog = await _load_catalog(settings.clinic_id)
        call_id: str | None = None
        reception: ReceptionService | None = None
        if catalog is not None:
            recorder.allowed_phone_numbers.add(catalog.clinic.phone or "")
            call_id = await recorder.start(
                room_name=context.room.name, opening_hours=catalog.clinic.opening_hours
            )
            reception = ReceptionService(
                catalog=catalog,
                stores=ReceptionStores(
                    appointments=AppointmentRepository(),
                    patients=PatientRepository(),
                    callbacks=CallbackRepository(),
                    calls=CallRepository(),
                ),
                call_id=call_id,
            )

        async def _on_shutdown(reason: str) -> None:
            await recorder.finish(reason)
            if call_id:
                await finalize_call(call_id, api_key=visitor_api_key)

        context.add_shutdown_callback(_on_shutdown)

        if visitor_api_key:
            recorder.record_event(
                "state", {"state": "visitor_api_key", "detail": "Caller supplied their own Gemini key"}
            )
        session = build_session(settings, api_key=visitor_api_key)
        _attach_conversation_handlers(session, recorder)

        @session.on("close")
        def _on_close(event: CloseEvent) -> None:
            logger.debug("session closed", extra={"reason": str(event.reason)})
            context.shutdown(reason=str(event.reason))

        await session.start(
            room=context.room,
            agent=Receptionist(
                instructions=build_instructions(catalog=catalog), reception=reception, recorder=recorder
            ),
        )
        if call_id:
            await recorder.publish(CALL_DATA_TOPIC, {"call_id": call_id})
        call_limit_task = asyncio.create_task(
            _enforce_call_limit(session, recorder, settings.max_call_seconds)
        )

        async def _cancel_call_limit() -> None:
            call_limit_task.cancel()

        context.add_shutdown_callback(_cancel_call_limit)
        await session.generate_reply(instructions=GREETING_INSTRUCTION)
    except Exception:
        logger.exception("receptionist session failed")
        recorder.record_event("error", {"stage": "session_start"})
        raise


if __name__ == "__main__":
    cli.run_app(server)
