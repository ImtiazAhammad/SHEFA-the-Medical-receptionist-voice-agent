"""Asterisk AudioSocket wire format.

One TCP connection per call. Each frame is a 1-byte kind, a 2-byte big-endian
payload length, then the payload. Audio is signed-linear 16-bit, 8 kHz, mono.
"""

from __future__ import annotations

import asyncio

KIND_HANGUP = 0x00
KIND_UUID = 0x01
KIND_DTMF = 0x03
KIND_AUDIO = 0x10
KIND_ERROR = 0xFF

MAX_PAYLOAD = 0xFFFF


def encode_frame(kind: int, payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError(f"AudioSocket payload too large: {len(payload)}")
    return bytes([kind]) + len(payload).to_bytes(2, "big") + payload


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
    """Next `(kind, payload)`, or None when the peer closed (also mid-frame)."""
    try:
        header = await reader.readexactly(3)
        payload = await reader.readexactly(int.from_bytes(header[1:], "big"))
    except asyncio.IncompleteReadError:
        return None
    return header[0], payload
