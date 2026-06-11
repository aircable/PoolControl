"""PoolControl custom component core - TCP client and frame parser.

RS485 over TCP from ESP32 bridge:
  Frame format: DLE(0x10) STX(0x02) type_hi type_lo payload_len payload checksum trailing_DLE(0x10)
  No EOF delimiter - frames are back-to-back with trailing DLE
  DLE stuffing: 0x10 0x00 = literal 0x10 in data
  Checksum: sum(frame[:-2]) & 0xFF == frame[-2] (second-to-last byte)
  Types 0x0103, 0x0102, 0x0002, 0x0201 have "inconsistent checksum" - parse regardless

Frame types:
  0x0101 - Status text (strict checksum) - "Pool Temp XX_C Air Temp YY_C" + time
  0x0102 - LED state (inconsistent checksum) - payload[0]=mask1, [1]=mask2, [2:6]=temps
  0x0103 - Display text (inconsistent checksum) - 24 bytes LCD text
  0x0201 - LED alternate (inconsistent checksum)
  0x0002 - Pump data (inconsistent checksum) - RPM, GPM, watts
  0x0407 - Pump status (inconsistent checksum) - speed, power, relay state
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from datetime import date
from dataclasses import dataclass, field
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

DLE = 0x10
STX = 0x02

TYPE_DISPLAY = 0x0103
TYPE_LED = 0x0102
TYPE_STATUS = 0x0101
TYPE_LED_ALT = 0x0002
TYPE_CHEM = 0x0201
TYPE_PUMP_STATUS = 0x0407

INCONSISTENT_CHECKSUM_TYPES = {TYPE_DISPLAY, TYPE_LED, TYPE_LED_ALT, TYPE_CHEM, TYPE_PUMP_STATUS}

# Key codes for sending commands to the panel
KEY_CODES = {
    "RIGHT": 0x0001,
    "MENU": 0x0002,
    "LEFT": 0x0004,
    "SERVICE_KEY": 0x0008,
    "MINUS": 0x0010,
    "PLUS": 0x0020,
    "POOL_SPA": 0x0040,
    "FILTER": 0x0080,
    "LIGHTS": 0x0100,
    "AUX_1": 0x0200,
    "AUX_2": 0x0400,
    "AUX_3": 0x0800,
    "AUX_4": 0x1000,
    "AUX_5": 0x2000,
    "AUX_6": 0x4000,
    "AUX_7": 0x8000,
}

# LED bit positions in the bitfield
LED_MAP = {
    "HEATER_1": 0, "VALVE_3": 1, "CHECK_SYSTEM": 2, "POOL": 3, "SPA": 4,
    "FILTER": 5, "LIGHTS": 6, "AUX_1": 7, "AUX_2": 8, "SERVICE": 9,
    "AUX_3": 10, "AUX_4": 11, "AUX_5": 12, "AUX_6": 13, "VALVE_4": 14,
    "SPILLOVER": 15, "SUPER_CHLORINATE": 25, "HEATER_AUTO_MODE": 30,
    "FILTER_LOW_SPEED": 31,
}


@dataclass
class PoolControlData:
    display_raw: bytes | None = None
    display_text: str | None = None
    display_line1: str | None = None
    display_line2: str | None = None
    panel_hour: int | None = None
    panel_minute: int | None = None
    panel_day: str | None = None
    filter_running: bool = False
    heater_on: bool = False
    heater_state: int = 0
    spa_on: bool = False
    pool_on: bool = False
    solar_on: bool = False
    solar_state: int = 0
    aux1: bool = False
    aux2: bool = False
    aux3: bool = False
    filter_blinking: bool = False
    pump_rpm: int | None = None
    pump_gpm: int | None = None
    pump_watts: int | None = None
    air_temp: int | None = None
    pool_temp: int | None = None
    spa_temp: int | None = None
    solar_temp: int | None = None
    ph: float | None = None
    orp: int | None = None
    online: bool = False
    leds: dict[str, bool] = field(default_factory=dict)
    leds_steady: dict[str, bool] = field(default_factory=dict)
    leds_flashing: dict[str, bool] = field(default_factory=dict)


def _validate_checksum(frame: bytes, frame_type: int) -> bool:
    if len(frame) < 6:
        return False
    if frame_type in INCONSISTENT_CHECKSUM_TYPES:
        return True
    expected = frame[-2]
    calculated = sum(frame[:-2]) & 0xFF
    if calculated != expected:
        _LOGGER.debug("Checksum fail type=0x%04x: sum=0x%02x expected=0x%02x",
                       frame_type, calculated, expected)
    return calculated == expected


def _scan_frames(buf: bytes):
    frames = []
    i = 0
    while i < len(buf) - 1:
        if buf[i] != DLE or buf[i + 1] != STX:
            i += 1
            continue
        j = i + 2
        while j < len(buf):
            if buf[j] == DLE:
                if j + 1 < len(buf) and buf[j + 1] == 0x00:
                    j += 2
                    continue
                frame = bytes(buf[i:j + 1])
                if len(frame) >= 6:
                    frames.append(frame)
                i = j + 1
                break
            j += 1
        else:
            break
    return frames, buf[i:]


def _unstuff(payload: bytes) -> bytes:
    result = bytearray()
    i = 0
    while i < len(payload):
        if payload[i] == DLE and i + 1 < len(payload) and payload[i + 1] == 0x00:
            result.append(DLE)
            i += 2
        else:
            result.append(payload[i])
            i += 1
    return bytes(result)


def _parse_display(payload: bytes) -> dict[str, Any]:
    result = {}
    if not payload:
        return result
    raw = _unstuff(bytes(payload))

    # Mirror bridge-side sanitization: keep printable ASCII only.
    clean = bytearray()
    for b in raw:
        if 0x20 <= b <= 0x7E:
            clean.append(b)
        else:
            clean.append(0x20)

    text_full = bytes(clean).decode("ascii", errors="replace")
    text = text_full.strip()
    result["display_raw"] = bytes(raw)
    result["display_text"] = text

    # Mirror panel formatting: two fixed lines, usually up to 21 chars each.
    line_len = min(21, max(1, len(text_full) // 2))
    line1 = text_full[:line_len].strip()
    line2 = text_full[line_len : line_len * 2].strip()
    combined = f"{line1} {line2}".strip()
    if line1:
        result["display_line1"] = line1
    if line2:
        result["display_line2"] = line2

    # Display frames often carry day/time and sometimes temperatures.
    # Extract what we can so key sensors keep updating even when 0x0101 is absent.
    import re

    day_match = re.search(
        r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b",
        combined or text,
        re.IGNORECASE,
    )
    if day_match:
        day_raw = day_match.group(1).strip()
        result["panel_day"] = day_raw[:3].title()

    # Panels sometimes use non-standard separators (e.g. degree-like glyph) between HH and MM.
    time_match = re.search(r"\b([01]?\d|2[0-3])\D([0-5]\d)\b", combined or text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            result["panel_hour"] = hour
            result["panel_minute"] = minute

    # Some panels show either "Pool Temp" or "Spa Temp". We only keep one water temp.
    pool_match = re.search(r"(?:Pool|Spa)\s*Temp\s*(-?\d{1,3})", combined or text, re.IGNORECASE)
    if not pool_match:
        pool_match = re.search(r"\b(?:Pool|Spa)\s*(-?\d{1,3})\b", combined or text, re.IGNORECASE)
    if pool_match:
        temp = int(pool_match.group(1))
        if -20 < temp < 80:
            result["pool_temp"] = temp

    air_match = re.search(r"Air\s*Temp\s*(-?\d{1,3})", combined or text, re.IGNORECASE)
    if not air_match:
        air_match = re.search(r"\bAir\s*(-?\d{1,3})\b", combined or text, re.IGNORECASE)
    if air_match:
        temp = int(air_match.group(1))
        if -20 < temp < 80:
            result["air_temp"] = temp

    return result


def _parse_led(payload: bytes) -> dict[str, Any]:
    """Parse LED bitfield payload (0x0102 / 0x0002).

    WishMesh bridge forwards the panel format:
    - payload[0..3]  : steady LED bitfield (little-endian)
    - payload[4..7]  : flashing LED bitfield (little-endian)
    Effective LED state is steady OR flashing.
    """
    result: dict[str, Any] = {}
    if len(payload) < 8:
        return result

    # Some bridges prepend a payload length byte. Strip it if it matches.
    if len(payload) >= 9 and payload[0] == (len(payload) - 1):
        payload = payload[1:]
        if len(payload) < 8:
            return result

    steady = (
        payload[0]
        | (payload[1] << 8)
        | (payload[2] << 16)
        | (payload[3] << 24)
    )
    flashing = (
        payload[4]
        | (payload[5] << 8)
        | (payload[6] << 16)
        | (payload[7] << 24)
    )
    def _bit(bits: int, mask: int) -> bool:
        return bool(bits & mask)

    masks = {
        "HEATER_1": 1 << 0,
        "VALVE_3": 1 << 1,
        "CHECK_SYSTEM": 1 << 2,
        "POOL": 1 << 3,
        "SPA": 1 << 4,
        "FILTER": 1 << 5,
        "LIGHTS": 1 << 6,
        "AUX_1": 1 << 7,
        "AUX_2": 1 << 8,
        "SERVICE": 1 << 9,
        "AUX_3": 1 << 10,
        "AUX_4": 1 << 11,
        "AUX_5": 1 << 12,
        "AUX_6": 1 << 13,
        "VALVE_4": 1 << 14,
        "SPILLOVER": 1 << 15,
        "SUPER_CHLORINATE": 1 << 25,
        "HEATER_AUTO_MODE": 1 << 30,
        "FILTER_LOW_SPEED": 1 << 31,
    }

    leds_steady = {name: _bit(steady, mask) for name, mask in masks.items()}
    leds_flashing = {name: _bit(flashing, mask) for name, mask in masks.items()}
    leds = {name: (leds_steady[name] or leds_flashing[name]) for name in masks}

    result["leds"] = leds
    result["leds_steady"] = leds_steady
    result["leds_flashing"] = leds_flashing
    result["filter_blinking"] = leds_flashing["FILTER"]
    result["filter_running"] = leds["FILTER"]
    result["pool_on"] = leds["POOL"]
    result["spa_on"] = leds["SPA"]
    result["aux1"] = leds["AUX_1"]
    result["aux2"] = leds["AUX_2"]
    result["aux3"] = leds["AUX_3"]
    return result


def _parse_pump_status(payload: bytes, raw_frame: bytes) -> dict[str, Any]:
    """Parse pump status frame (type 0x0407).
    
    This frame type is not fully documented. Log raw data for analysis
    and attempt to extract pump speed/power information.
    """
    result = {}
    _LOGGER.info("Pump status 0x0407: raw=%s (len=%d)", raw_frame.hex(), len(raw_frame))
    _LOGGER.info("Pump status payload (%d bytes): hex=%s", len(payload), payload.hex())
    
    # Try ASCII decode first
    try:
        ascii_text = payload.decode("ascii", errors="replace").strip()
        if ascii_text and any(c.isprintable() for c in ascii_text):
            _LOGGER.info("Pump status ASCII: %s", ascii_text)
    except Exception:
        pass
    
    # Try binary extraction based on common Aqualogic pump status format
    # Hypothesis: byte[0]=pump_speed_pct, byte[1]=power_hi, byte[2]=power_lo
    if len(payload) >= 3:
        speed_pct = payload[0]
        power = (payload[1] << 8) | payload[2]
        _LOGGER.info("Pump status decoded: speed_pct=%d power=%d", speed_pct, power)
        # Don't set these yet - just log for analysis
    
    return result


def _parse_chem(payload: bytes) -> dict[str, Any]:
    result = {}
    if len(payload) >= 4:
        result["ph"] = payload[0] / 10.0
        result["orp"] = (payload[1] << 8) | payload[2]
    return result


def _parse_status(payload: bytes) -> dict[str, Any]:
    """Parse binary status frame (0x0101) as produced by WishMesh bridge.

    Layout used by bridge parser:
    - payload[4]  air_temp
    - payload[5]  pool_temp
    - payload[6]  relay bitfield
    - payload[7]  relay bitfield 2
    - payload[8]  month
    - payload[9]  day
    - payload[10] year (2-digit, +2000)
    - payload[11] hour
    - payload[12] minute
    """
    result = {}
    if len(payload) < 13:
        return result
    # Some bridges prepend a payload length byte. Strip it if it matches.
    if len(payload) >= 14 and payload[0] == (len(payload) - 1):
        payload = payload[1:]
        if len(payload) < 13:
            return result

    # Primary layout (WishMesh):
    # [4]=air [5]=pool [6]=relays [7]=relays2 [8]=month [9]=day [10]=yy [11]=hour [12]=minute
    # Fallback layout (shifted by +1) handled if primary date/time is invalid.
    idx = 0
    month = payload[8]
    day = payload[9]
    hour = payload[11]
    minute = payload[12]
    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
        if len(payload) >= 14:
            idx = 1
            month = payload[8 + idx]
            day = payload[9 + idx]
            hour = payload[11 + idx]
            minute = payload[12 + idx]
        if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
            return result

    air = payload[4 + idx]
    pool = payload[5 + idx]
    relays = payload[6 + idx]
    relays2 = payload[7 + idx]

    if 0 < air < 130:
        result["air_temp"] = int(air)
    if 0 < pool < 130:
        result["pool_temp"] = int(pool)

    result["filter_running"] = bool(relays & 0x01)
    result["aux1"] = bool(relays & 0x08)
    result["aux2"] = bool(relays & 0x10)
    result["aux3"] = bool(relays2 & 0x01)
    result["panel_hour"] = hour
    result["panel_minute"] = minute
    try:
        year = 2000 + payload[10 + idx]
        dt = date(year, month, day)
        result["panel_day"] = dt.strftime("%a")
    except ValueError:
        pass

    return result


def _parse_frame(frame: bytes) -> dict[str, Any] | None:
    if len(frame) < 6:
        return None
    if frame[0] != DLE or frame[1] != STX:
        return None
    frame_type = (frame[2] << 8) | frame[3]
    if frame[-1] != DLE:
        return None

    # WishMesh forwards bridge-native format:
    # DLE STX type_hi type_lo payload checksum trailing_DLE
    payload = _unstuff(frame[4:-2])

    if not _validate_checksum(frame, frame_type):
        _LOGGER.debug("Checksum fail for type 0x%04x, parsing anyway", frame_type)
        if frame_type not in INCONSISTENT_CHECKSUM_TYPES:
            return None

    if frame_type == TYPE_DISPLAY:
        return _parse_display(payload)
    elif frame_type == TYPE_LED:
        return _parse_led(payload)
    elif frame_type == TYPE_STATUS:
        return _parse_status(payload)
    elif frame_type == TYPE_LED_ALT:
        return _parse_led(payload)
    elif frame_type == TYPE_CHEM:
        return _parse_chem(payload)
    elif frame_type == TYPE_PUMP_STATUS:
        return _parse_pump_status(payload, frame)
    else:
        _LOGGER.debug("Unknown frame type: 0x%04x (len=%d)", frame_type, len(frame))
        return None


def build_command(key_code: int) -> bytes:
    """Build remote-wired key event command to match WishMesh Aqualogic bridge.

    Frame format:
    DLE STX 00 03 [key LE 4 bytes][key LE 4 bytes] checksum16(hi,lo) DLE ETX
    with DLE stuffing applied to data/checksum bytes.
    """
    frame = bytearray([DLE, STX])

    def _append_stuffed(val: int) -> None:
        frame.append(val & 0xFF)
        if (val & 0xFF) == DLE:
            frame.append(0x00)

    _append_stuffed(0x00)
    _append_stuffed(0x03)

    key_lo = key_code & 0xFF
    key_hi = (key_code >> 8) & 0xFF
    for _ in range(2):
        _append_stuffed(key_lo)
        _append_stuffed(key_hi)
        _append_stuffed(0x00)
        _append_stuffed(0x00)

    checksum = sum(frame) & 0xFFFF
    _append_stuffed((checksum >> 8) & 0xFF)
    _append_stuffed(checksum & 0xFF)

    frame.append(DLE)
    frame.append(0x03)
    return bytes(frame)


class PoolControlTCPClient:
    def __init__(self, host: str, port: int, data_callback: Callable):
        self._host = host
        self._port = port
        self._data_callback = data_callback
        self._socket = None
        self._thread = None
        self._running = False
        self._online = False
        self._recv_buf = bytearray()
        self.data = PoolControlData()

    @property
    def online(self):
        return self._online

    def start(self):
        if self._thread and self._thread.is_alive():
            _LOGGER.debug("PoolControl TCP client already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._main, name="PoolControlTCP", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._socket:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._socket.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def restart(self):
        """Force a clean TCP reconnect."""
        self.stop()
        # Small gap to let the bridge release the previous connection cleanly.
        time.sleep(0.2)
        self.start()

    def send_command(self, key_code: int) -> bool:
        """Send a key command to the panel via TCP."""
        if not self._socket or not self._running or not self._online:
            _LOGGER.warning("Cannot send command: not connected (socket=%s, running=%s, online=%s)",
                           self._socket is not None, self._running, self._online)
            return False
        frame = build_command(key_code)
        try:
            self._socket.sendall(frame)
            _LOGGER.info("Sent command key=0x%04x frame=%s", key_code, frame.hex())
            return True
        except OSError as e:
            _LOGGER.error("Error sending command: %s", e)
            return False

    def _main(self):
        while self._running:
            try:
                self._connect_and_recv()
            except Exception as exc:
                _LOGGER.error("PoolControl TCP error: %s", exc)
                self._online = False
            if self._running:
                _LOGGER.info("Reconnecting in 5 seconds...")
                time.sleep(5)

    def _connect_and_recv(self):
        _LOGGER.info("Connecting to PoolControl bridge at %s:%d", self._host, self._port)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(10)
        self._socket.connect((self._host, self._port))
        self._socket.settimeout(1.0)
        _LOGGER.info("Connected to PoolControl bridge at %s:%d", self._host, self._port)
        self._online = True
        self.data.online = True
        self._recv_buf = bytearray()
        while self._running:
            try:
                data = self._socket.recv(256)
                if not data:
                    _LOGGER.warning("Connection closed by remote host")
                    break
                self._recv_buf.extend(data)
                self._process_buffer()
            except socket.timeout:
                continue
            except OSError as exc:
                if self._running:
                    _LOGGER.warning("Socket error: %s", exc)
                else:
                    _LOGGER.debug("Socket closed during stop/reload")
                break
        self._online = False
        self.data.online = False
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _process_buffer(self):
        frames, remaining = _scan_frames(bytes(self._recv_buf))
        self._recv_buf = bytearray(remaining)
        if not frames:
            return
        merged = {}
        for frame in frames:
            parsed = _parse_frame(frame)
            if parsed is not None:
                merged.update(parsed)
                if "air_temp" in parsed or "pool_temp" in parsed:
                    _LOGGER.info(
                        "Status decoded: air=%s pool=%s time=%s:%s day=%s",
                        parsed.get("air_temp"),
                        parsed.get("pool_temp"),
                        parsed.get("panel_hour"),
                        parsed.get("panel_minute"),
                        parsed.get("panel_day"),
                    )
            elif len(frame) >= 4:
                ft = (frame[2] << 8) | frame[3]
                _LOGGER.debug("Failed to parse frame type=0x%04x len=%d", ft, len(frame))
            if len(frame) >= 4:
                ft = (frame[2] << 8) | frame[3]
                if ft in (TYPE_STATUS, TYPE_LED, TYPE_LED_ALT, TYPE_DISPLAY):
                    _LOGGER.debug("RX frame type=0x%04x len=%d raw=%s", ft, len(frame), frame.hex())
        if merged:
            for k, v in merged.items():
                setattr(self.data, k, v)
            try:
                self._data_callback(merged)
            except Exception:
                _LOGGER.exception("Error in data callback")
