from typing import Literal

from pydantic import BaseModel, Field

CallIntent = Literal["book", "reschedule", "cancel", "enquiry", "other"]
ConversationOutcome = Literal["enquiry", "follow_up_needed", "incomplete"]


class TurnTranslation(BaseModel):
    seq: int
    text_en: str


class FieldConfidence(BaseModel):
    patient_name: float = Field(ge=0, le=1)
    phone: float = Field(ge=0, le=1)
    reason_for_visit: float = Field(ge=0, le=1)
    preferred_date: float = Field(ge=0, le=1)
    preferred_time: float = Field(ge=0, le=1)


class CallExtractionResult(BaseModel):
    intent: CallIntent
    patient_name_bn: str | None = Field(
        default=None, description="Patient name in Bangla script as confirmed"
    )
    patient_name_en: str | None = Field(
        default=None, description="Patient name transliterated to English letters"
    )
    name_confirmed: bool | None = Field(
        default=None, description="True if the agent read the name back and the caller agreed"
    )
    phone_spoken_raw: str | None = Field(
        default=None, description="Phone number exactly as the caller said it"
    )
    reason_for_visit: str | None = Field(
        default=None, description="Short English description of the dental problem or request"
    )
    service_code: str | None = None
    preferred_date: str | None = Field(default=None, description="ISO date YYYY-MM-DD the caller preferred")
    preferred_time_window: str | None = Field(default=None, description="e.g. 'evening', '17:30', 'morning'")
    conversation_outcome: ConversationOutcome
    summary_bn: str = Field(description="Two-sentence summary in Bangla for clinic staff")
    summary_en: str = Field(description="Two-sentence summary in English for clinic staff")
    translations: list[TurnTranslation] = Field(
        description="English translation for every transcript turn by seq"
    )
    confidence: FieldConfidence
