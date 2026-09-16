"""ThinkGear/TGAM binary stream parsing and presentation-friendly state."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import struct
import time
from typing import Deque, Iterable


SYNC = 0xAA
MAX_PAYLOAD_LENGTH = 169

EEG_BANDS = (
    "delta",
    "theta",
    "low_alpha",
    "high_alpha",
    "low_beta",
    "high_beta",
    "low_gamma",
    "mid_gamma",
)

BAND_LABELS = {
    "delta": "Delta",
    "theta": "Theta",
    "low_alpha": "Low Alpha",
    "high_alpha": "High Alpha",
    "low_beta": "Low Beta",
    "high_beta": "High Beta",
    "low_gamma": "Low Gamma",
    "mid_gamma": "Mid Gamma",
}


@dataclass
class ParserStats:
    bytes_received: int = 0
    packets_ok: int = 0
    checksum_errors: int = 0
    invalid_lengths: int = 0


class ThinkGearParser:
    """Incremental parser for the NeuroSky ThinkGear serial protocol.

    The parser accepts arbitrarily fragmented byte chunks, resynchronizes after
    bad frames, validates the payload checksum, and decodes DataRows by code
    rather than relying on a fixed packet layout.
    """

    SEEK_SYNC = 0
    READ_LENGTH = 1
    READ_PAYLOAD = 2
    READ_CHECKSUM = 3

    def __init__(self) -> None:
        self.stats = ParserStats()
        self._state = self.SEEK_SYNC
        self._sync_count = 0
        self._payload_length = 0
        self._payload = bytearray()

    def reset(self) -> None:
        self.stats = ParserStats()
        self._state = self.SEEK_SYNC
        self._sync_count = 0
        self._payload_length = 0
        self._payload.clear()

    def feed(self, data: bytes | bytearray | Iterable[int]) -> list[dict]:
        decoded_packets: list[dict] = []

        for value in data:
            byte = int(value) & 0xFF
            self.stats.bytes_received += 1

            if self._state == self.SEEK_SYNC:
                if byte == SYNC:
                    self._sync_count += 1
                    if self._sync_count >= 2:
                        self._state = self.READ_LENGTH
                else:
                    self._sync_count = 0
                continue

            if self._state == self.READ_LENGTH:
                # Extra sync bytes are legal and can be ignored here.
                if byte == SYNC:
                    continue
                if byte > MAX_PAYLOAD_LENGTH:
                    self.stats.invalid_lengths += 1
                    self._return_to_sync(byte)
                    continue
                self._payload_length = byte
                self._payload.clear()
                self._state = (
                    self.READ_CHECKSUM
                    if self._payload_length == 0
                    else self.READ_PAYLOAD
                )
                continue

            if self._state == self.READ_PAYLOAD:
                self._payload.append(byte)
                if len(self._payload) >= self._payload_length:
                    self._state = self.READ_CHECKSUM
                continue

            expected = checksum(self._payload)
            if byte == expected:
                self.stats.packets_ok += 1
                packet = decode_payload(bytes(self._payload))
                if packet:
                    decoded_packets.append(packet)
            else:
                self.stats.checksum_errors += 1
            self._return_to_sync(byte)

        return decoded_packets

    def _return_to_sync(self, last_byte: int) -> None:
        self._state = self.SEEK_SYNC
        self._sync_count = 1 if last_byte == SYNC else 0
        self._payload_length = 0
        self._payload.clear()


def checksum(payload: bytes | bytearray) -> int:
    """Return the ThinkGear one's-complement payload checksum."""

    return (~sum(payload)) & 0xFF


def build_packet(payload: bytes | bytearray) -> bytes:
    """Build a valid ThinkGear frame, used by tests and Demo Mode."""

    payload_bytes = bytes(payload)
    if len(payload_bytes) > MAX_PAYLOAD_LENGTH:
        raise ValueError("ThinkGear payload is too long")
    return bytes((SYNC, SYNC, len(payload_bytes))) + payload_bytes + bytes(
        (checksum(payload_bytes),)
    )


def decode_payload(payload: bytes) -> dict:
    """Decode all recognized DataRows from one ThinkGear payload."""

    result: dict = {}
    index = 0

    while index < len(payload):
        extended_level = 0
        while index < len(payload) and payload[index] == 0x55:
            extended_level += 1
            index += 1

        if index >= len(payload):
            break

        code = payload[index]
        index += 1

        if code < 0x80:
            if index >= len(payload):
                break
            value = payload[index : index + 1]
            index += 1
        else:
            if index >= len(payload):
                break
            value_length = payload[index]
            index += 1
            if index + value_length > len(payload):
                break
            value = payload[index : index + value_length]
            index += value_length

        # Unknown extended codes are deliberately ignored for forward
        # compatibility, as required by the ThinkGear DataRow format.
        if extended_level:
            continue

        if code == 0x01 and value:
            result["battery"] = value[0]
        elif code == 0x02 and value:
            result["poor_signal"] = value[0]
        elif code == 0x03 and value:
            result["heart_rate"] = value[0]
        elif code == 0x04 and value:
            result["attention"] = value[0]
        elif code == 0x05 and value:
            result["meditation"] = value[0]
        elif code == 0x16 and value:
            # Some ThinkGear products expose blink strength with this code.
            result["blink_strength"] = value[0]
        elif code == 0x80 and len(value) == 2:
            result["raw_eeg"] = int.from_bytes(value, "big", signed=True)
        elif code == 0x83 and len(value) >= 24:
            result["eeg_power"] = {
                band: int.from_bytes(value[offset : offset + 3], "big")
                for band, offset in zip(EEG_BANDS, range(0, 24, 3))
            }
        elif code == 0x81 and len(value) >= 32:
            float_values = struct.unpack(">8f", value[:32])
            result["eeg_power"] = {
                band: max(0.0, float(number))
                for band, number in zip(EEG_BANDS, float_values)
                if math.isfinite(number)
            }

    return result


class EEGModel:
    """Rolling state used by the desktop dashboard."""

    def __init__(self, raw_capacity: int = 1536) -> None:
        self.raw_samples: Deque[int] = deque(maxlen=raw_capacity)
        self.attention_history: Deque[int] = deque(maxlen=300)
        self.meditation_history: Deque[int] = deque(maxlen=300)
        self.signal_history: Deque[int] = deque(maxlen=300)
        self.bands: dict[str, float] = {band: 0.0 for band in EEG_BANDS}
        self.poor_signal: int | None = None
        self.attention: int | None = None
        self.meditation: int | None = None
        self.blink_strength: int | None = None
        self.last_data_time: float | None = None
        self.started_at = time.monotonic()

    def reset(self) -> None:
        self.raw_samples.clear()
        self.attention_history.clear()
        self.meditation_history.clear()
        self.signal_history.clear()
        self.bands = {band: 0.0 for band in EEG_BANDS}
        self.poor_signal = None
        self.attention = None
        self.meditation = None
        self.blink_strength = None
        self.last_data_time = None
        self.started_at = time.monotonic()

    def update(self, packet: dict, now: float | None = None) -> None:
        if not packet:
            return

        now = time.monotonic() if now is None else now
        self.last_data_time = now

        if "raw_eeg" in packet:
            self.raw_samples.append(int(packet["raw_eeg"]))
        if "poor_signal" in packet:
            self.poor_signal = int(packet["poor_signal"])
            self.signal_history.append(self.poor_signal)
        if "attention" in packet and 0 <= int(packet["attention"]) <= 100:
            self.attention = int(packet["attention"])
            self.attention_history.append(self.attention)
        if "meditation" in packet and 0 <= int(packet["meditation"]) <= 100:
            self.meditation = int(packet["meditation"])
            self.meditation_history.append(self.meditation)
        if "blink_strength" in packet:
            self.blink_strength = int(packet["blink_strength"])
        if "eeg_power" in packet:
            for band in EEG_BANDS:
                if band in packet["eeg_power"]:
                    self.bands[band] = float(packet["eeg_power"][band])

    @property
    def has_data(self) -> bool:
        return self.last_data_time is not None

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    @property
    def signal_label(self) -> str:
        if self.poor_signal is None:
            return "Waiting"
        if self.poor_signal >= 200:
            return "Off head"
        if self.poor_signal == 0:
            return "Excellent"
        if self.poor_signal <= 25:
            return "Good"
        if self.poor_signal <= 50:
            return "Fair"
        if self.poor_signal <= 100:
            return "Poor"
        return "Very poor"

    @property
    def dominant_band(self) -> str:
        if not any(value > 0 for value in self.bands.values()):
            return "Waiting"
        key = max(self.bands, key=self.bands.get)
        return BAND_LABELS[key]

    @property
    def state_summary(self) -> str:
        if not self.has_data:
            return "Waiting for TGAM data"
        if self.poor_signal is not None and self.poor_signal >= 200:
            return "Sensor not detected"
        if self.poor_signal is not None and self.poor_signal > 50:
            return "Improve electrode contact"
        if self.attention is None or self.meditation is None:
            return "Collecting signal"
        if self.attention >= 70 and self.meditation >= 60:
            return "Focused and calm"
        if self.attention >= 70:
            return "High focus"
        if self.meditation >= 70:
            return "Relaxed state"
        if self.attention < 35 and self.meditation < 35:
            return "Low engagement"
        return "Balanced state"

    @staticmethod
    def average(values: Deque[int]) -> float | None:
        return sum(values) / len(values) if values else None

    def snapshot(self) -> dict:
        return {
            "elapsed_seconds": self.elapsed_seconds,
            "poor_signal": self.poor_signal,
            "signal_label": self.signal_label,
            "attention": self.attention,
            "meditation": self.meditation,
            "average_attention": self.average(self.attention_history),
            "average_meditation": self.average(self.meditation_history),
            "dominant_band": self.dominant_band,
            "state": self.state_summary,
            **{band: self.bands[band] for band in EEG_BANDS},
        }
