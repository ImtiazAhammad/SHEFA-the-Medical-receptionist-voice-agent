"""Tool definitions for the LLM function-calling interface."""

from __future__ import annotations

from sefa.models.base import ToolDefinition


def get_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="verify_patient",
            description="Verify patient identity using name, date of birth, phone, or MRN.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Patient full name"},
                    "date_of_birth": {
                        "type": "string",
                        "description": "Date of birth (YYYY-MM-DD)",
                    },
                    "phone": {"type": "string", "description": "Phone number"},
                    "mrn": {"type": "string", "description": "Medical Record Number"},
                },
            },
        ),
        ToolDefinition(
            name="check_appointment_slots",
            description="Check available appointment slots for a given date and optional doctor.",
            parameters={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date to check (YYYY-MM-DD)"},
                    "doctor_name": {"type": "string", "description": "Doctor name (optional)"},
                    "specialty": {
                        "type": "string",
                        "description": "Specialty (e.g., cardiology)",
                    },
                },
                "required": ["date"],
            },
        ),
        ToolDefinition(
            name="book_appointment",
            description="Book an appointment for a verified patient.",
            parameters={
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string", "description": "Verified patient ID"},
                    "date": {"type": "string", "description": "Appointment date (YYYY-MM-DD)"},
                    "time": {"type": "string", "description": "Appointment time (HH:MM)"},
                    "doctor_name": {"type": "string", "description": "Doctor name"},
                    "reason": {"type": "string", "description": "Reason for visit"},
                },
                "required": ["patient_id", "date", "time"],
            },
        ),
        ToolDefinition(
            name="cancel_appointment",
            description="Cancel an existing appointment.",
            parameters={
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string", "description": "Appointment ID"},
                    "patient_id": {"type": "string", "description": "Patient ID"},
                    "reason": {"type": "string", "description": "Cancellation reason"},
                },
                "required": ["appointment_id", "patient_id"],
            },
        ),
        ToolDefinition(
            name="reschedule_appointment",
            description="Reschedule an existing appointment to a new date/time.",
            parameters={
                "type": "object",
                "properties": {
                    "appointment_id": {"type": "string", "description": "Current appointment ID"},
                    "new_date": {"type": "string", "description": "New date (YYYY-MM-DD)"},
                    "new_time": {"type": "string", "description": "New time (HH:MM)"},
                    "patient_id": {"type": "string", "description": "Patient ID"},
                },
                "required": ["appointment_id", "patient_id", "new_date", "new_time"],
            },
        ),
        ToolDefinition(
            name="get_doctor_info",
            description=(
                "Get information about a doctor "
                "(availability, specialty, languages spoken)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "doctor_name": {"type": "string", "description": "Doctor name to look up"},
                },
                "required": ["doctor_name"],
            },
        ),
        ToolDefinition(
            name="lookup_patient_history",
            description="Retrieve basic patient history (recent visits, medications).",
            parameters={
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string", "description": "Patient ID"},
                },
                "required": ["patient_id"],
            },
        ),
        ToolDefinition(
            name="send_confirmation",
            description="Send appointment confirmation via SMS or email.",
            parameters={
                "type": "object",
                "properties": {
                    "patient_id": {"type": "string", "description": "Patient ID"},
                    "appointment_id": {"type": "string", "description": "Appointment ID"},
                    "method": {
                        "type": "string",
                        "enum": ["sms", "email"],
                        "description": "Delivery method",
                    },
                },
                "required": ["patient_id", "appointment_id", "method"],
            },
        ),
        ToolDefinition(
            name="transfer_to_human",
            description="Transfer the call to a human receptionist.",
            parameters={
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Reason for transfer"},
                },
                "required": ["reason"],
            },
        ),
    ]
