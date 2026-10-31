"""AudioSocket framing: 1-byte kind, 2-byte big-endian length, payload."""

from __future__ import annotations

import asyncio

from shefa.audio import s16le_16k_mono_to_slin8k
from shefa.telephony.audiosocket import (
    KIND_AUDIO,
    KIND_HANGUP,
    KIND_UUID,
    encode_frame,
    read_frame,
)


def test_encode_frame_layout():
    assert encode_frame(KIND_AUDIO, b"ab") == b"\x10\x00\x02ab"
    assert encode_frame(KIND_HANGUP, b"") == b"\x00\x00\x00"


async def test_read_frame_handles_coalesced_and_split_input():
    reader = asyncio.StreamReader()
    first = encode_frame(KIND_UUID, bytes(range(16)))
    second = encode_frame(KIND_AUDIO, b"\x01\x02" * 160)
    third = encode_frame(KIND_HANGUP, b"")
    reader.feed_data(first + second)
    for byte in third:  # split byte by byte
        reader.feed_data(bytes([byte]))
    reader.feed_eof()

    assert await read_frame(reader) == (KIND_UUID, bytes(range(16)))
    assert await read_frame(reader) == (KIND_AUDIO, b"\x01\x02" * 160)
    assert await read_frame(reader) == (KIND_HANGUP, b"")
    assert await read_frame(reader) is None


async def test_truncated_frame_is_treated_as_eof():
    reader = asyncio.StreamReader()
    reader.feed_data(b"\x10\x00\x05ab")
    reader.feed_eof()
    assert await read_frame(reader) is None


def test_downsample_halves_the_byte_count():
    assert len(s16le_16k_mono_to_slin8k(b"\x00\x01" * 160)) == 160
    assert s16le_16k_mono_to_slin8k(b"") == b""
