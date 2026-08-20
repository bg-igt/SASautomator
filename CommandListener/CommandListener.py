from __future__ import annotations

import argparse
import glob
import http.client
import os
import re
import socket
import sys
import threading
import time
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlsplit
from xml.sax.saxutils import escape as xml_escape

try:
    import serial  # type: ignore[import-not-found]
    try:
        from serial.tools import list_ports as serial_list_ports  # type: ignore[import-not-found]
    except Exception:
        serial_list_ports = None
    SERIAL_IMPORT_ERROR: Optional[ModuleNotFoundError] = None
except ModuleNotFoundError as exc:
    serial = None
    serial_list_ports = None
    SERIAL_IMPORT_ERROR = exc


CRC_POLY = 0x8408
SUPPORTED_PYTHON_EXE = (
    r"C:\Users\zhv85164\AppData\Local\Programs\Python\Python311\python.exe"
)
SUPPORTED_RUN_HELPER = "run_CommandListener.cmd"
SUPPORTED_INSTALL_HELPER = "install_pyserial_python311.cmd"
DEFAULT_PORT = "COM1"
DEFAULT_ADDRESS = 1
SAFE_POLL_MS = 200
FAST_POLL_MS = 40
DEFAULT_POLL_MS = SAFE_POLL_MS
DEFAULT_BAUDRATE = 19200
DEFAULT_WAKEUP_DELAY_MS = 1.0
DEFAULT_READ_TIMEOUT_MS = 20
DEFAULT_INTER_BYTE_TIMEOUT_MS = 5
DEFAULT_MAX_FRAME_SIZE = 500
DEFAULT_STOPBITS = 2
DEFAULT_CONTROL_LINE_ENABLED = True
DEFAULT_STARTUP_SYNC = True
ECHO_MODE_AUTO = "auto"
ECHO_MODE_ON = "on"
ECHO_MODE_OFF = "off"
PROTOCOL_MODE_AUTO = "auto"
PROTOCOL_MODE_LEGACY = "legacy"
PROTOCOL_MODE_RTE = "rte"
POLL_PROFILE_AUTO = "auto"
POLL_PROFILE_SAFE = "safe"
POLL_PROFILE_FAST = "fast"
MODE_TCE = "tce"
MODE_SAS = "sas"

SERIAL_BYTESIZE = 8
SERIAL_PARITY_MARK = "M"
SERIAL_PARITY_SPACE = "S"
SERIAL_STOPBITS_TWO = 2

STARTUP_SYNC_BYTE = 0x80
RTE_TOGGLE_COMMAND = 0x0E
RTE_EVENT_IDENTIFIER = 0xFF
GENERIC_RTE_EVENT_FRAME_LENGTH = 5
MIN_GENERIC_RTE_FRAME_LENGTH = GENERIC_RTE_EVENT_FRAME_LENGTH
QATESTING_NAMESPACE = "http://tempspielo.com"
TECHNOLOGY_NAMESPACE = "http://tempspielo.com"
SOAP_ENVELOPE_NAMESPACE = "http://schemas.xmlsoap.org/soap/envelope/"
DEFAULT_TCE_CONFIG_GLOB = os.path.join("TCE", "bin", "Debug", "XML", "TCE-Checkwin_*.xml")
DEFAULT_TCE_PRIMARY_CONFIG_PATH = os.path.join(
    "TCE", "bin", "Debug", "XML", "TCE-Checkwin_1.xml"
)
DEFAULT_TCE_CFG_PATH = os.path.join("TCE", "bin", "Debug", "TCE-Checkwin.cfg")
DEFAULT_TCE_LABEL = "TCE1"
DEFAULT_TCE_TCE_NUMBER = 1
DEFAULT_TCE_MESSAGE_LEVEL_INFO = 0
DEFAULT_TCE_MESSAGE_LEVEL_VAR = 3
DEFAULT_TCE_NO_CALLBACK_WARNING_SECONDS = 30.0
DEFAULT_TCE_SERVICE_PREFLIGHT_TIMEOUT_SECONDS = 2.0
DEFAULT_TCE_STATE_POLL_INTERVAL_MS = 100
DEFAULT_TCE_STATE_POLL_INTERVAL_SECONDS = (
    DEFAULT_TCE_STATE_POLL_INTERVAL_MS / 1000.0
)
TCE_SELF_PROBE_PATH = "/__self_probe__"
IDLE_STATE_VALUE = "MarketWrapperReelStateMachine::Idle"
IDLE_TERMINAL_PAYLOAD = f"1|3||STATE|{IDLE_STATE_VALUE}"
TCE_XML_FILENAME_PATTERN = re.compile(r"^TCE-Checkwin_(\d+)\.xml$", re.IGNORECASE)
TCE_STATE_UPDATEVAR_ALIASES = frozenset({"STATE", "MSTATE", "GAMESTATE"})
MAX_TCE_DIAGNOSTIC_PREVIEW_LENGTH = 80
MAX_TCE_DIAGNOSTIC_CALLBACK_VARIABLES = 4
MAX_TCE_DIAGNOSTIC_FIELDS = 4

RTE_EVENT_FRAME_LENGTH_BY_CODE: dict[int, int] = {
    0x4F: 11,
    0x7C: 15,
    0x7E: 13,
    0x7F: 9,
    0x88: 7,
    0x8A: 9,
    0x8B: 6,
    0x8C: 7,
}
LEGACY_EVENT_CODE_RANGES: tuple[tuple[int, int], ...] = (
    (0x11, 0x57),
    (0x60, 0x7B),
    (0x80, 0x9B),
)


@dataclass(frozen=True)
class ListenerConfig:
    port: str
    address: int
    poll_ms: int
    poll_profile: str
    protocol_mode: str
    enable_rte: bool
    startup_sync: bool
    echo_mode: str
    verbose: bool
    debug: bool = False
    heartbeat_seconds: int = 5
    no_response_warning_seconds: int = 10
    wakeup_delay_ms: float = DEFAULT_WAKEUP_DELAY_MS
    read_timeout_ms: int = DEFAULT_READ_TIMEOUT_MS
    inter_byte_timeout_ms: int = DEFAULT_INTER_BYTE_TIMEOUT_MS
    max_frame_size: int = DEFAULT_MAX_FRAME_SIZE
    accept_legacy_single_byte_events: bool = False
    poll_ms_overridden: bool = False


@dataclass
class ParsedEvent:
    name: str
    event_code: int
    raw: bytes
    address: Optional[int] = None
    legacy: bool = False
    valid_crc: Optional[bool] = None
    transport_kind: str = "unknown"
    repeat_count: int = 1
    error: Optional[str] = None


@dataclass(frozen=True)
class ProtocolUnit:
    status: str
    frame: bytes


@dataclass(frozen=True)
class SerialPortInfo:
    device: str
    description: str
    hwid: str = ""


@dataclass(frozen=True)
class BufferExtraction:
    units: tuple[ProtocolUnit, ...]
    remaining: bytes
    dropped_echo_bytes: bytes = b""


@dataclass(frozen=True)
class DrainResult:
    raw: bytes
    units: tuple[ProtocolUnit, ...]
    dropped_echo_bytes: bytes
    buffered_bytes: bytes
    last_rx_type: str


def is_supported_runtime() -> bool:
    return os.path.normcase(os.path.normpath(sys.executable)) == os.path.normcase(
        os.path.normpath(SUPPORTED_PYTHON_EXE)
    )


def format_runtime_info() -> str:
    parts = [
        f"python={sys.executable}",
        f"runtime_supported={int(is_supported_runtime())}",
        f"supported_python={SUPPORTED_PYTHON_EXE}",
        f"serial_import={'ok' if serial is not None else 'missing'}",
    ]

    if serial is not None:
        serial_path = getattr(serial, "__file__", None)
        if serial_path:
            parts.append(f"serial_module={serial_path}")

        serial_version = getattr(serial, "__version__", None) or getattr(
            serial, "VERSION", None
        )
        if serial_version:
            parts.append(f"serial_version={serial_version}")
    elif SERIAL_IMPORT_ERROR is not None:
        parts.append(f"serial_error={SERIAL_IMPORT_ERROR}")

    return " | ".join(parts)


def build_pyserial_error_message() -> str:
    lines = [
        "pyserial is required to talk to the COM port.",
        f"python={sys.executable}",
        f"runtime_supported={int(is_supported_runtime())}",
        f"supported_python={SUPPORTED_PYTHON_EXE}",
        f"serial_import={'ok' if serial is not None else 'missing'}",
    ]

    if SERIAL_IMPORT_ERROR is not None:
        lines.append(f"serial_error={SERIAL_IMPORT_ERROR}")

    lines.append(f'install_command="{sys.executable}" -m pip install pyserial')
    lines.append(
        f'run_command="{sys.executable}" CommandListener.py --self-test'
    )
    lines.append(
        f'supported_install_command="{SUPPORTED_PYTHON_EXE}" -m pip install pyserial'
    )
    lines.append(
        f'supported_run_command="{SUPPORTED_PYTHON_EXE}" CommandListener.py --self-test'
    )
    lines.append(f"supported_install_helper={SUPPORTED_INSTALL_HELPER}")
    lines.append(f"supported_run_helper={SUPPORTED_RUN_HELPER}")
    return "\n".join(lines)


def list_serial_ports() -> tuple[SerialPortInfo, ...]:
    if serial_list_ports is None:
        return ()

    ports: list[SerialPortInfo] = []
    for port_info in serial_list_ports.comports():
        ports.append(
            SerialPortInfo(
                device=str(getattr(port_info, "device", "") or ""),
                description=str(
                    getattr(port_info, "description", "") or "Unknown serial device"
                ),
                hwid=str(getattr(port_info, "hwid", "") or ""),
            )
        )
    return tuple(sorted(ports, key=lambda item: item.device.upper()))


def format_serial_port_listing(
    ports: Optional[tuple[SerialPortInfo, ...]] = None,
) -> str:
    serial_ports = list_serial_ports() if ports is None else ports
    if not serial_ports:
        return "No serial ports detected."

    lines = ["Detected serial ports:"]
    for port_info in serial_ports:
        line = f"  {port_info.device}: {port_info.description}"
        if port_info.hwid:
            line += f" | {port_info.hwid}"
        lines.append(line)
    return "\n".join(lines)


def build_serial_open_error_message(
    port: str,
    exc: BaseException,
    ports: Optional[tuple[SerialPortInfo, ...]] = None,
) -> str:
    serial_ports = list_serial_ports() if ports is None else ports
    normalized_port = port.upper()
    selected_port = next(
        (item for item in serial_ports if item.device.upper() == normalized_port),
        None,
    )
    other_ports = [
        item.device for item in serial_ports if item.device.upper() != normalized_port
    ]
    error_text = str(exc)
    error_text_lower = error_text.lower()
    is_access_denied = (
        "access is denied" in error_text_lower or "permission denied" in error_text_lower
    )

    lines = [
        f"Could not open serial port {port}.",
        f"pyserial_error={error_text}",
    ]

    if is_access_denied:
        lines.append(
            "Windows reported access denied. Another app or driver usually already owns that port."
        )
        lines.append("Close any other serial tools using it, then try again.")
    elif "file not found" in error_text_lower or "cannot find the file" in error_text_lower:
        lines.append("Windows could not find that port name.")
    else:
        lines.append("Confirm the selected port name and cable are correct.")

    if selected_port is not None:
        lines.append(
            f"Selected port details: {selected_port.device} - {selected_port.description}"
        )
    elif serial_ports:
        lines.append(f"{port} is not currently in the detected serial-port list.")

    if serial_ports:
        lines.append(format_serial_port_listing(serial_ports))
    else:
        lines.append("Serial-port discovery is unavailable or no ports are currently visible.")

    if other_ports and (selected_port is None or not is_access_denied):
        lines.append(
            f'Try one of the detected alternatives, for example: {SUPPORTED_RUN_HELPER} --port {other_ports[0]}'
        )
    lines.append(f"List ports: {SUPPORTED_RUN_HELPER} --list-ports")
    return "\n".join(lines)


def compute_crc_ccitt(data: bytes) -> int:
    """Compute the reflected CCITT CRC used by SAS."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ CRC_POLY
            else:
                crc >>= 1
        crc &= 0xFFFF
    return crc


def append_crc(data: bytes) -> bytes:
    crc = compute_crc_ccitt(data)
    return data + bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def has_valid_crc(frame: bytes) -> bool:
    if len(frame) < 3:
        return False
    return append_crc(frame[:-2])[-2:] == frame[-2:]


def format_hex(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


def format_serial_parity(parity: object) -> str:
    names = {
        "N": "NONE",
        "E": "EVEN",
        "O": "ODD",
        "M": "MARK",
        "S": "SPACE",
    }
    if isinstance(parity, str):
        return names.get(parity, parity)
    return str(parity)


def format_serial_stopbits(stopbits: object) -> str:
    if stopbits in (1, 1.0):
        return "1"
    if stopbits == 1.5:
        return "1.5"
    if stopbits in (2, 2.0):
        return "2"
    return str(stopbits)


def format_enabled_flag(value: object) -> str:
    return "1" if bool(value) else "0"


def format_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def format_log_line(level: str, message: str) -> str:
    return f"{format_timestamp()} | {level} | {message}"


def format_sas_event_name(event_code: int, *, legacy: bool) -> str:
    prefix = "SAS legacy event" if legacy else "SAS event"
    return f"{prefix} 0x{event_code:02X}"


def is_known_legacy_event_code(event_code: int) -> bool:
    return any(start <= event_code <= end for start, end in LEGACY_EVENT_CODE_RANGES)


def parse_event(
    frame: bytes,
    *,
    accept_legacy_single_byte_events: bool = False,
    legacy_event_error: Optional[str] = None,
    transport_kind: Optional[str] = None,
) -> Optional[ParsedEvent]:
    if not frame:
        return None

    if len(frame) == 1:
        if not accept_legacy_single_byte_events:
            return None
        if not is_known_legacy_event_code(frame[0]):
            return None
        return ParsedEvent(
            name=format_sas_event_name(frame[0], legacy=True),
            event_code=frame[0],
            raw=frame,
            legacy=True,
            transport_kind=transport_kind or "legacy_exception",
            error=legacy_event_error,
        )

    if len(frame) < 3 or frame[1] != RTE_EVENT_IDENTIFIER:
        return None

    address = frame[0]
    event_code = frame[2]
    expected_length = RTE_EVENT_FRAME_LENGTH_BY_CODE.get(
        event_code,
        GENERIC_RTE_EVENT_FRAME_LENGTH,
    )
    event = ParsedEvent(
        name=format_sas_event_name(event_code, legacy=False),
        event_code=event_code,
        raw=frame,
        address=address,
        transport_kind=transport_kind or "rte_event",
    )

    if len(frame) != expected_length:
        event.valid_crc = False
        event.error = f"expected {expected_length} bytes, got {len(frame)}"
        return event

    event.valid_crc = has_valid_crc(frame)
    if not event.valid_crc:
        event.error = "invalid CRC"
    return event


def get_event_frame_length(frame: bytes) -> Optional[int]:
    if len(frame) < 3 or frame[1] != RTE_EVENT_IDENTIFIER:
        return None
    return RTE_EVENT_FRAME_LENGTH_BY_CODE.get(
        frame[2],
        GENERIC_RTE_EVENT_FRAME_LENGTH,
    )


def starts_known_unit(
    frame: bytes,
    *,
    address: int,
    expected_echoes: tuple[bytes, ...] = (),
    accept_legacy_single_byte_events: bool = False,
) -> bool:
    if not frame:
        return False

    for candidate in expected_echoes:
        if candidate and frame.startswith(candidate):
            return True

    if len(frame) >= 2 and frame[0] in {address, address | 0x80} and frame[1] == 0xFF:
        return True

    if frame[0] in {address, address | 0x80}:
        return True

    return is_known_legacy_event_code(frame[0]) or (
        accept_legacy_single_byte_events and is_known_legacy_event_code(frame[0])
    )


def starts_definite_unit(
    frame: bytes,
    *,
    address: int,
    expected_echoes: tuple[bytes, ...] = (),
) -> bool:
    if not frame:
        return False

    for candidate in expected_echoes:
        if candidate and frame.startswith(candidate):
            return True

    if len(frame) >= 2 and frame[0] in {address, address | 0x80} and frame[1] == 0xFF:
        return True

    return frame[0] == (address | 0x80)


def split_unknown_rte_frame(
    frame: bytes,
    *,
    address: int,
    expected_echoes: tuple[bytes, ...] = (),
    accept_legacy_single_byte_events: bool = False,
) -> tuple[bytes, bytes]:
    for index in range(1, len(frame)):
        if starts_known_unit(
            frame[index:],
            address=address,
            expected_echoes=expected_echoes,
            accept_legacy_single_byte_events=accept_legacy_single_byte_events,
        ):
            return frame[:index], frame[index:]
    return frame, b""


def extract_protocol_units(
    raw: bytes,
    *,
    address: int,
    echo_mode: str,
    expected_echoes: Optional[list[bytes]] = None,
    accept_legacy_single_byte_events: bool = False,
) -> BufferExtraction:
    expected = tuple(expected_echoes or [])
    remaining = raw
    dropped_echoes = bytearray()
    units: list[ProtocolUnit] = []

    if echo_mode != ECHO_MODE_OFF:
        while remaining:
            matched = False
            for candidate in expected:
                if candidate and remaining.startswith(candidate):
                    dropped_echoes.extend(candidate)
                    remaining = remaining[len(candidate) :]
                    matched = True
                    break
            if not matched:
                break

    while remaining:
        if len(remaining) >= 2 and remaining[0] in {address, address | 0x80} and remaining[1] == 0xFF:
            if len(remaining) < 3:
                break

            event_length = get_event_frame_length(remaining)
            if event_length is not None:
                if len(remaining) < event_length:
                    break
                units.append(ProtocolUnit(status="frame", frame=remaining[:event_length]))
                remaining = remaining[event_length:]
                continue

            if len(remaining) < MIN_GENERIC_RTE_FRAME_LENGTH:
                break

            unknown_rte, remaining = split_unknown_rte_frame(
                remaining,
                address=address,
                expected_echoes=expected,
                accept_legacy_single_byte_events=accept_legacy_single_byte_events,
            )
            units.append(ProtocolUnit(status="unknown_rte", frame=unknown_rte))
            continue

        first_byte = remaining[0]
        if first_byte == address:
            if len(remaining) == 1:
                break

            next_unit = remaining[1:]
            if starts_definite_unit(
                next_unit,
                address=address,
                expected_echoes=expected,
            ) or (
                len(remaining) == 2 and is_known_legacy_event_code(remaining[1])
            ):
                units.append(ProtocolUnit(status="ack", frame=remaining[:1]))
                remaining = remaining[1:]
                continue

            unknown = bytearray([first_byte])
            remaining = remaining[1:]
            while remaining and not starts_definite_unit(
                remaining,
                address=address,
                expected_echoes=expected,
            ):
                unknown.append(remaining[0])
                remaining = remaining[1:]
            units.append(ProtocolUnit(status="unknown", frame=bytes(unknown)))
            continue

        if first_byte == (address | 0x80):
            units.append(ProtocolUnit(status="nack", frame=remaining[:1]))
            remaining = remaining[1:]
            continue

        if is_known_legacy_event_code(first_byte):
            units.append(ProtocolUnit(status="frame", frame=remaining[:1]))
            remaining = remaining[1:]
            continue

        unknown = bytearray([first_byte])
        remaining = remaining[1:]
        while remaining and not starts_known_unit(
            remaining,
            address=address,
            expected_echoes=expected,
            accept_legacy_single_byte_events=accept_legacy_single_byte_events,
        ):
            unknown.append(remaining[0])
            remaining = remaining[1:]
        units.append(ProtocolUnit(status="unknown", frame=bytes(unknown)))

    return BufferExtraction(
        units=tuple(units),
        remaining=remaining,
        dropped_echo_bytes=bytes(dropped_echoes),
    )


class SASEventPrinter:
    @staticmethod
    def _extend_event_parts(
        parts: list[str],
        event: ParsedEvent,
        *,
        include_repeat_count: bool = True,
    ) -> None:
        if include_repeat_count and event.repeat_count > 1:
            parts.append(f"repeat_count={event.repeat_count}")

        if event.valid_crc is False:
            parts.append("crc=INVALID")

        if event.error:
            parts.append(f"error={event.error}")

    def format_compact_event(self, event: ParsedEvent) -> str:
        parts = [format_timestamp(), f"${event.event_code:02X} = {event.name}"]
        self._extend_event_parts(parts, event, include_repeat_count=False)
        return " | ".join(parts)

    def format_compact_event_with_raw(self, event: ParsedEvent) -> str:
        return f"{self.format_compact_event(event)} | RX<= {format_hex(event.raw)}"

    def format_event(self, event: ParsedEvent) -> str:
        parts = [format_timestamp(), "EVENT"]

        if event.address is not None:
            parts.append(f"addr=0x{event.address:02X}")

        parts.append(f"code=0x{event.event_code:02X}")
        parts.append(f"${event.event_code:02X} = {event.name}")
        parts.append(f"transport={event.transport_kind}")

        if event.legacy:
            parts.append("legacy=1")

        if event.valid_crc is not None:
            parts.append(f"crc={'OK' if event.valid_crc else 'INVALID'}")

        self._extend_event_parts(parts, event)

        parts.append(f"raw={format_hex(event.raw)}")
        return " | ".join(parts)

    def format_transport(self, label: str, frame: bytes) -> str:
        return f"{label} {format_hex(frame)}"


class SASDecodedMessagePrinter:
    @staticmethod
    def format_ack(address: int) -> str:
        return f"${address:02X} = ACK"

    @staticmethod
    def format_ack_with_raw(address: int, frame: bytes) -> str:
        return (
            f"{format_timestamp()} | ${address:02X} = ACK | "
            f"RX<= {format_hex(frame)}"
        )

    @staticmethod
    def format_nack(address: int) -> str:
        return f"${address | 0x80:02X} = NACK"

    @staticmethod
    def format_nack_with_raw(address: int, frame: bytes) -> str:
        return (
            f"{format_timestamp()} | ${address | 0x80:02X} = NACK | "
            f"RX<= {format_hex(frame)}"
        )


class SASSerialHost:
    def __init__(
        self,
        config: ListenerConfig,
        debug_log: Optional[Callable[[str], None]] = None,
    ) -> None:
        if serial is None:
            raise RuntimeError(build_pyserial_error_message())

        self.config = config
        self.debug_log = debug_log
        self.read_timeout_seconds = config.read_timeout_ms / 1000.0
        self.inter_byte_timeout_seconds = config.inter_byte_timeout_ms / 1000.0
        self.wakeup_delay_seconds = config.wakeup_delay_ms / 1000.0
        self._monotonic = time.monotonic
        self._sleep = time.sleep
        try:
            self.connection = serial.Serial(
                **self.build_transport_kwargs(
                    port=config.port,
                    read_timeout_seconds=self.read_timeout_seconds,
                )
            )
        except Exception as exc:
            raise RuntimeError(
                build_serial_open_error_message(config.port, exc)
            ) from exc
        self._enable_control_lines()
        self._reset_buffers()
        self._debug(f"Opened serial port {self.describe_connection()}")

    @staticmethod
    def build_transport_kwargs(
        port: str,
        read_timeout_seconds: float,
    ) -> dict[str, object]:
        return {
            "port": port,
            "baudrate": DEFAULT_BAUDRATE,
            "bytesize": SERIAL_BYTESIZE,
            "parity": SERIAL_PARITY_SPACE,
            "stopbits": SERIAL_STOPBITS_TWO,
            "timeout": read_timeout_seconds,
            "write_timeout": read_timeout_seconds,
            "xonxoff": False,
            "rtscts": False,
            "dsrdtr": False,
        }

    def _debug(self, message: str) -> None:
        if self.debug_log is not None:
            self.debug_log(message)

    def _enable_control_lines(self) -> None:
        self.connection.dtr = DEFAULT_CONTROL_LINE_ENABLED
        self.connection.rts = DEFAULT_CONTROL_LINE_ENABLED

    def _reset_buffers(self) -> None:
        reset_input_buffer = getattr(self.connection, "reset_input_buffer", None)
        if callable(reset_input_buffer):
            reset_input_buffer()
            self._debug("Reset input buffer after open")

        reset_output_buffer = getattr(self.connection, "reset_output_buffer", None)
        if callable(reset_output_buffer):
            reset_output_buffer()
            self._debug("Reset output buffer after open")

    def describe_connection(self) -> str:
        port = getattr(self.connection, "port", self.config.port)
        baudrate = getattr(self.connection, "baudrate", DEFAULT_BAUDRATE)
        bytesize = getattr(self.connection, "bytesize", SERIAL_BYTESIZE)
        parity = getattr(self.connection, "parity", SERIAL_PARITY_SPACE)
        stopbits = getattr(self.connection, "stopbits", DEFAULT_STOPBITS)
        dtr = getattr(self.connection, "dtr", False)
        rts = getattr(self.connection, "rts", False)
        return (
            f"port={port} baudrate={baudrate} bytesize={bytesize} "
            f"parity={format_serial_parity(parity)} "
            f"stopbits={format_serial_stopbits(stopbits)} "
            f"dtr={format_enabled_flag(dtr)} "
            f"rts={format_enabled_flag(rts)} "
            f"wakeup_delay_ms={self.config.wakeup_delay_ms:g} "
            f"read_timeout_ms={self.config.read_timeout_ms} "
            f"inter_byte_timeout_ms={self.config.inter_byte_timeout_ms}"
        )

    def close(self) -> None:
        if self.connection.is_open:
            self._debug(f"Closing serial port {self.config.port}")
            self.connection.close()

    def __enter__(self) -> "SASSerialHost":
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        self.close()

    def _set_parity(self, parity: str) -> None:
        if self.connection.parity != parity:
            self.connection.parity = parity

    def write_frame(self, payload: bytes, context: str = "TX") -> int:
        if not payload:
            return 0

        bytes_written = 0
        self._set_parity(SERIAL_PARITY_MARK)
        bytes_written += self.connection.write(payload[:1])
        self.connection.flush()

        if len(payload) == 1:
            self._set_parity(SERIAL_PARITY_SPACE)
            self._debug(
                f"{context} bytes_written={bytes_written} raw={format_hex(payload)}"
            )
            return bytes_written

        if self.wakeup_delay_seconds > 0:
            time.sleep(self.wakeup_delay_seconds)

        self._set_parity(SERIAL_PARITY_SPACE)
        bytes_written += self.connection.write(payload[1:])
        self.connection.flush()
        self._debug(
            f"{context} bytes_written={bytes_written} raw={format_hex(payload)}"
        )
        return bytes_written

    def send_startup_sync(self) -> bytes:
        frame = bytes([STARTUP_SYNC_BYTE])
        self.write_frame(frame, context="TX STARTUP_SYNC")
        return frame

    def send_general_poll(self) -> bytes:
        frame = bytes([self.config.address | 0x80])
        self.write_frame(frame, context="TX GENERAL_POLL")
        return frame

    def send_enable_rte(self) -> bytes:
        frame = append_crc(
            bytes([self.config.address, RTE_TOGGLE_COMMAND, 0x01])
        )
        self.write_frame(frame, context="TX ENABLE_RTE")
        return frame

    def send_disable_rte(self) -> bytes:
        frame = append_crc(
            bytes([self.config.address, RTE_TOGGLE_COMMAND, 0x00])
        )
        self.write_frame(frame, context="TX DISABLE_RTE")
        return frame

    def read_available(self, context: str) -> bytes:
        started_at = self._monotonic()
        first_byte_deadline = started_at + self.read_timeout_seconds
        window_deadline = first_byte_deadline
        frame = bytearray()

        while len(frame) < self.config.max_frame_size:
            waiting = int(getattr(self.connection, "in_waiting", 0) or 0)
            if waiting > 0:
                chunk = self.connection.read(
                    min(waiting, self.config.max_frame_size - len(frame))
                )
                if chunk:
                    frame.extend(chunk)
                    window_deadline = self._monotonic() + self.inter_byte_timeout_seconds
                    continue

            now = self._monotonic()
            if frame:
                if now >= window_deadline:
                    break
            elif now >= first_byte_deadline:
                break

            self._sleep(0.001)

        raw = bytes(frame)
        elapsed_ms = int((self._monotonic() - started_at) * 1000)
        self._debug(
            f"{context} receive_window_ms={elapsed_ms} raw_bytes={len(raw)} "
            f"raw={format_hex(raw)}"
        )
        return raw

class SASListener:
    def __init__(self, config: ListenerConfig) -> None:
        self.config = config
        self.printer = SASEventPrinter()
        self.decoded_printer = SASDecodedMessagePrinter()
        self.compact_output = not config.verbose and not config.debug
        self.poll_count = 0
        self.empty_poll_count = 0
        self.started_at = 0.0
        self.next_heartbeat_at = 0.0
        self.next_no_response_warning_at = 0.0
        self.current_poll_ms = config.poll_ms
        self.rx_buffer = bytearray()
        self.startup_raw_bytes = 0
        self.startup_unit_count = 0
        self.startup_last_rx_type = "none"
        self.runtime_started_at = 0.0
        self.runtime_raw_bytes = 0
        self.runtime_unit_count = 0
        self.runtime_event_count = 0
        self.repeated_event_count = 0
        self.runtime_last_rx_type = "none"
        self.last_runtime_raw_at = 0.0
        self.last_runtime_unit_at = 0.0
        self.last_runtime_event_at = 0.0
        self.last_event_key: Optional[tuple[str, bytes]] = None
        self.last_event_repeat_count = 0
        self.debug_reminder_printed = False
        self.rte_handshake_succeeded = config.protocol_mode == PROTOCOL_MODE_RTE
        self.rte_mode_active = config.protocol_mode == PROTOCOL_MODE_RTE

    def _log(self, level: str, message: str) -> None:
        print(format_log_line(level, message))

    def _log_debug(self, message: str) -> None:
        if self.config.debug:
            self._log("DEBUG", message)

    def _log_info(self, message: str) -> None:
        self._log("INFO", message)

    def _log_warn(self, message: str) -> None:
        self._log("WARN", message)

    def _print_launch_hint(self) -> None:
        self._log_info(
            f"Recommended wrapper: {SUPPORTED_RUN_HELPER} --port {self.config.port}"
        )

    def _print_startup_banner(self) -> None:
        self._log_info("Listener started.")
        self._log_info(
            f"python={sys.executable} | port={self.config.port} | "
            f"address={self.config.address} | poll_ms={self.current_poll_ms} | "
            f"poll_profile={self.config.poll_profile} | "
            f"protocol_mode={self.config.protocol_mode} | "
            f"enable_rte={int(self.config.enable_rte)} | "
            f"startup_sync={int(self.config.startup_sync)} | "
            f"legacy_byte_events={int(self.config.accept_legacy_single_byte_events)} | "
            f"poll_ms_overridden={int(self.config.poll_ms_overridden)} | "
            f"echo_mode={self.config.echo_mode} | "
            f"verbose={int(self.config.verbose)} | debug={int(self.config.debug)} | "
            f"heartbeat_seconds={self.config.heartbeat_seconds} | "
            f"no_response_warning_seconds={self.config.no_response_warning_seconds} | "
            f"wakeup_delay_ms={self.config.wakeup_delay_ms:g} | "
            f"read_timeout_ms={self.config.read_timeout_ms} | "
            f"inter_byte_timeout_ms={self.config.inter_byte_timeout_ms}"
        )
        self._print_launch_hint()
        self._log_info(f"Waiting for SAS traffic on {self.config.port}...")
        if not self.config.debug:
            self._log_info("Use --debug for detailed TX/RX diagnostics.")

    def _runtime_status_summary(self) -> str:
        return (
            f"polls={self.poll_count} | empty_polls={self.empty_poll_count} | "
            f"poll_ms={self.current_poll_ms} | "
            f"raw_bytes={self.runtime_raw_bytes} | decoded_units={self.runtime_unit_count} | "
            f"events={self.runtime_event_count} | repeated_events={self.repeated_event_count} | "
            f"protocol={'rte' if self.rte_mode_active else self.config.protocol_mode} | "
            f"last_rx={self.runtime_last_rx_type}"
        )

    def _print_heartbeat(self) -> None:
        self._log_info(
            f"Status | Waiting for SAS traffic on {self.config.port} | "
            f"{self._runtime_status_summary()}"
        )

    def _print_no_response_warning(self, elapsed_seconds: float) -> None:
        self._log_warn(
            f"No SAS protocol activity received on {self.config.port} after "
            f"{elapsed_seconds:.1f}s | address={self.config.address} | "
            f"poll_ms={self.current_poll_ms} | {self._runtime_status_summary()}"
        )
        self._log_warn(
            f"Troubleshooting: confirm Windows port name is {self.config.port}, "
            "confirm the cable/device is connected and powered, "
            f"confirm SAS address {self.config.address} is correct, "
            "and confirm the machine responds to general polls / RTE enable with full event frames. "
            "The default listener profile starts at a spec-safe polling interval; override --poll-ms, "
            "--read-timeout-ms, or --inter-byte-timeout-ms only if your device needs different values."
        )
        if not self.config.debug and not self.debug_reminder_printed:
            self._log_warn(
                f"For TX/RX transport detail, rerun exactly: "
                f"{SUPPORTED_RUN_HELPER} --port {self.config.port}"
            )
            self.debug_reminder_printed = True

    def _infer_last_rx_type(
        self,
        *,
        units: tuple[ProtocolUnit, ...],
        dropped_echo_bytes: bytes,
        buffered_bytes: bytes,
    ) -> str:
        for unit in units:
            if unit.status in {"frame", "unknown_rte"}:
                event = parse_event(
                    unit.frame,
                    accept_legacy_single_byte_events=(
                        self._allow_legacy_byte_events() or len(unit.frame) == 1
                    ),
                )
                if event is not None:
                    return "event"
        for unit in units:
            if unit.status == "unknown_rte":
                return "unknown_rte"
            if unit.status == "unknown":
                return "unknown"
            if unit.status == "ack":
                return "ack"
            if unit.status == "nack":
                return "nack"
        if dropped_echo_bytes:
            return "echo"
        if buffered_bytes:
            return "buffered"
        return "none"

    def _reset_runtime_observability(
        self,
        *,
        started_at: float,
        heartbeat_seconds: float,
        warning_seconds: float,
    ) -> None:
        self.runtime_started_at = started_at
        self.runtime_raw_bytes = 0
        self.runtime_unit_count = 0
        self.runtime_event_count = 0
        self.repeated_event_count = 0
        self.runtime_last_rx_type = "none"
        self.last_runtime_raw_at = 0.0
        self.last_runtime_unit_at = 0.0
        self.last_runtime_event_at = 0.0
        self.last_event_key = None
        self.last_event_repeat_count = 0
        self.debug_reminder_printed = False
        self.next_heartbeat_at = started_at + heartbeat_seconds
        self.next_no_response_warning_at = started_at + warning_seconds

    def _allow_legacy_byte_events(self) -> bool:
        if self.config.protocol_mode == PROTOCOL_MODE_LEGACY:
            return True
        if self.config.protocol_mode == PROTOCOL_MODE_AUTO and not self.rte_mode_active:
            return True
        return False

    def _legacy_event_error(self) -> Optional[str]:
        if self._allow_legacy_byte_events():
            return None
        return "legacy exception received while RTE mode is active"

    def _mark_rte_mode_active(self, *, reason: str) -> None:
        if not self.rte_handshake_succeeded:
            self.rte_handshake_succeeded = True
        if self.rte_mode_active:
            return
        self.rte_mode_active = True
        self._log_info(f"RTE mode is active | reason={reason}")
        if (
            self.config.poll_profile == POLL_PROFILE_AUTO
            and not self.config.poll_ms_overridden
            and self.current_poll_ms != FAST_POLL_MS
        ):
            self.current_poll_ms = FAST_POLL_MS
            self._log_info(
                f"Poll profile auto promoted to {FAST_POLL_MS} ms after RTE activation."
            )

    def _event_repeat_key(self, event: ParsedEvent) -> tuple[str, bytes]:
        return (event.transport_kind, event.raw)

    def _apply_event_repeat_count(self, event: ParsedEvent) -> bool:
        key = self._event_repeat_key(event)
        if key == self.last_event_key:
            self.last_event_repeat_count += 1
            self.repeated_event_count += 1
        else:
            self.last_event_key = key
            self.last_event_repeat_count = 1
        event.repeat_count = self.last_event_repeat_count
        return event.repeat_count > 1

    def _emit_transport_line(
        self,
        label: str,
        frame: bytes,
        *,
        force_in_compact: bool = False,
    ) -> None:
        line = self.printer.format_transport(label, frame)
        if self.compact_output:
            if force_in_compact:
                print(line)
            return
        print(f"TRANSPORT | {line}")

    def _emit_received_unit_transport(self, frame: bytes) -> None:
        if self.compact_output:
            return
        self._emit_transport_line("RX<=", frame)

    def _emit_decoded_line(self, line: str) -> None:
        if self.compact_output:
            print(line)
            return
        print(f"DECODED | {line}")

    def _emit_or_refresh_event(self, event: ParsedEvent, *, repeated: bool) -> None:
        if repeated and not self.config.verbose:
            return
        if self.compact_output:
            print(self.printer.format_compact_event_with_raw(event))
            return
        print(f"DECODED | {self.printer.format_event(event)}")

    def _note_startup_activity(self, drain_result: DrainResult) -> None:
        self.startup_raw_bytes += len(drain_result.raw)
        self.startup_unit_count += len(drain_result.units)
        if (
            drain_result.last_rx_type != "none"
            or drain_result.dropped_echo_bytes
            or drain_result.buffered_bytes
        ):
            self.startup_last_rx_type = drain_result.last_rx_type

    def _note_runtime_activity(self, drain_result: DrainResult, *, now: float) -> None:
        if drain_result.raw:
            self.runtime_raw_bytes += len(drain_result.raw)
            self.last_runtime_raw_at = now
        if drain_result.units:
            self.runtime_unit_count += len(drain_result.units)
            self.last_runtime_unit_at = now
        if (
            drain_result.last_rx_type != "none"
            or drain_result.dropped_echo_bytes
            or drain_result.buffered_bytes
        ):
            self.runtime_last_rx_type = drain_result.last_rx_type

    def _seconds_since_last_activity(self, now: float) -> float:
        last_activity_at = max(
            self.last_runtime_event_at,
            self.last_runtime_unit_at,
            self.last_runtime_raw_at,
        )
        if last_activity_at > 0:
            return now - last_activity_at
        return now - self.runtime_started_at

    def _should_print_heartbeat(
        self,
        *,
        now: float,
        heartbeat_seconds: float,
    ) -> bool:
        return (
            heartbeat_seconds > 0
            and now >= self.next_heartbeat_at
            and self._seconds_since_last_activity(now) >= heartbeat_seconds
        )

    def _should_print_no_response_warning(
        self,
        *,
        now: float,
        warning_seconds: float,
    ) -> bool:
        return (
            warning_seconds > 0
            and now >= self.next_no_response_warning_at
            and self._seconds_since_last_activity(now) >= warning_seconds
        )

    def _drain_receive_units(
        self,
        host: SASSerialHost,
        *,
        context: str,
        expected_echoes: Optional[list[bytes]] = None,
    ) -> DrainResult:
        raw = host.read_available(context)
        if raw:
            self.rx_buffer.extend(raw)

        extraction = extract_protocol_units(
            bytes(self.rx_buffer),
            address=self.config.address,
            echo_mode=self.config.echo_mode,
            expected_echoes=expected_echoes,
            accept_legacy_single_byte_events=self.config.accept_legacy_single_byte_events,
        )
        self.rx_buffer = bytearray(extraction.remaining)

        if raw and not self.compact_output and not extraction.units:
            self._emit_transport_line("RX<=", raw)

        if extraction.dropped_echo_bytes:
            self._log_debug(
                f"{context} dropped_echo_bytes={len(extraction.dropped_echo_bytes)} "
                f"raw={format_hex(extraction.dropped_echo_bytes)}"
            )

        if extraction.remaining:
            self._log_debug(
                f"{context} buffered_bytes={len(extraction.remaining)} "
                f"raw={format_hex(extraction.remaining)}"
            )
            if self.compact_output and not extraction.units:
                self._emit_transport_line(
                    "RX<=",
                    extraction.remaining,
                    force_in_compact=True,
                )

        return DrainResult(
            raw=raw,
            units=extraction.units,
            dropped_echo_bytes=extraction.dropped_echo_bytes,
            buffered_bytes=extraction.remaining,
            last_rx_type=self._infer_last_rx_type(
                units=extraction.units,
                dropped_echo_bytes=extraction.dropped_echo_bytes,
                buffered_bytes=extraction.remaining,
            ),
        )

    def _handle_protocol_unit(
        self,
        unit: ProtocolUnit,
        *,
        now: Optional[float] = None,
        host: Optional[SASSerialHost] = None,
    ) -> str:
        del host
        event_now = now if now is not None else time.monotonic()

        if unit.status == "ack":
            self._log_debug(f"RX ACK frame={format_hex(unit.frame)}")
            self._emit_received_unit_transport(unit.frame)
            self._emit_decoded_line(
                self.decoded_printer.format_ack_with_raw(
                    self.config.address,
                    unit.frame,
                )
                if self.compact_output
                else self.decoded_printer.format_ack(self.config.address)
            )
            return "ack"

        if unit.status == "nack":
            self._log_debug(f"RX NACK frame={format_hex(unit.frame)}")
            self._emit_received_unit_transport(unit.frame)
            self._emit_decoded_line(
                self.decoded_printer.format_nack_with_raw(
                    self.config.address,
                    unit.frame,
                )
                if self.compact_output
                else self.decoded_printer.format_nack(self.config.address)
            )
            return "nack"

        if unit.status == "unknown":
            self._log_debug("Received non-event traffic")
            if self.compact_output:
                self._emit_transport_line("RX<=", unit.frame, force_in_compact=True)
            else:
                self._emit_received_unit_transport(unit.frame)
            return "unknown"

        event = parse_event(
            unit.frame,
            accept_legacy_single_byte_events=(
                self._allow_legacy_byte_events() or len(unit.frame) == 1
            ),
            legacy_event_error=self._legacy_event_error(),
            transport_kind=(
                "legacy_exception" if len(unit.frame) == 1 else "rte_event"
            ),
        )
        if event is None:
            self._log_debug("Frame did not match a known event format")
            if self.compact_output:
                self._emit_transport_line("RX<=", unit.frame, force_in_compact=True)
            else:
                self._emit_received_unit_transport(unit.frame)
            return "unknown"

        self._log_debug(
            f"Classified frame as event code=0x{event.event_code:02X} "
            f"legacy={int(event.legacy)} crc="
            f"{'n/a' if event.valid_crc is None else ('ok' if event.valid_crc else 'invalid')}"
        )
        repeated = self._apply_event_repeat_count(event)

        if not event.legacy and event.valid_crc is True:
            self._mark_rte_mode_active(
                reason=f"received event 0x{event.event_code:02X}"
            )

        self.runtime_event_count += 1
        self.last_runtime_event_at = event_now
        self.runtime_last_rx_type = "repeated_event" if repeated else "event"
        if not (repeated and not self.config.verbose):
            self._emit_received_unit_transport(unit.frame)
        self._emit_or_refresh_event(event, repeated=repeated)
        return "event"

    def run(self) -> int:
        self.started_at = time.monotonic()
        next_poll_at = self.started_at
        heartbeat_seconds = float(self.config.heartbeat_seconds)
        warning_seconds = float(self.config.no_response_warning_seconds)

        with SASSerialHost(self.config, debug_log=self._log_debug) as host:
            self._print_startup_banner()
            self._log_debug(f"Effective serial settings: {host.describe_connection()}")

            if self.config.startup_sync:
                startup_sync_frame = host.send_startup_sync()
                self._emit_transport_line(
                    "TX>=",
                    startup_sync_frame,
                )
                startup_sync_result = self._drain_receive_units(
                    host,
                    context="RX STARTUP_SYNC",
                    expected_echoes=[startup_sync_frame],
                )
                self._note_startup_activity(startup_sync_result)
                for unit in startup_sync_result.units:
                    self._handle_protocol_unit(unit, host=host)

            if self.config.enable_rte:
                enable_frame = host.send_enable_rte()
                self._emit_transport_line(
                    "TX>=",
                    enable_frame,
                )
                setup_result = self._drain_receive_units(
                    host,
                    context="RX ENABLE_RTE",
                    expected_echoes=[enable_frame],
                )
                self._note_startup_activity(setup_result)
                for unit in setup_result.units:
                    self._handle_protocol_unit(unit, host=host)
                if any(unit.status == "ack" for unit in setup_result.units):
                    self._mark_rte_mode_active(reason="enable-rte acknowledged with ACK")
                else:
                    for unit in setup_result.units:
                        event = parse_event(
                            unit.frame,
                            accept_legacy_single_byte_events=True,
                        )
                        if event is not None and not event.legacy and event.valid_crc is True:
                            self._mark_rte_mode_active(
                                reason="enable-rte produced valid RTE traffic"
                            )
                            break

            runtime_start = time.monotonic()
            if self.rx_buffer:
                self._log_info(
                    f"Setup left {len(self.rx_buffer)} buffered RX byte(s); "
                    "carrying them into the first live poll."
                )
            self._reset_runtime_observability(
                started_at=runtime_start,
                heartbeat_seconds=heartbeat_seconds,
                warning_seconds=warning_seconds,
            )

            try:
                while True:
                    now = time.monotonic()
                    if now < next_poll_at:
                        time.sleep(next_poll_at - now)
                    next_poll_at = (
                        time.monotonic() + (self.current_poll_ms / 1000.0)
                    )

                    self.poll_count += 1
                    self._log_debug(
                        f"Poll cycle start poll={self.poll_count} port={self.config.port}"
                    )
                    poll_frame = host.send_general_poll()
                    self._emit_transport_line(
                        "TX>=",
                        poll_frame,
                    )
                    drain_result = self._drain_receive_units(
                        host,
                        context=f"RX POLL_OR_COMMAND poll={self.poll_count}",
                        expected_echoes=[poll_frame],
                    )
                    poll_now = time.monotonic()
                    self._note_runtime_activity(drain_result, now=poll_now)

                    if not drain_result.raw and not drain_result.units:
                        self.empty_poll_count += 1
                        self._log_debug(
                            f"Poll ended status=empty "
                            f"poll={self.poll_count} empty_polls={self.empty_poll_count}"
                        )
                        if self._should_print_heartbeat(
                            now=poll_now,
                            heartbeat_seconds=heartbeat_seconds,
                        ):
                            self._print_heartbeat()
                            self.next_heartbeat_at = poll_now + heartbeat_seconds
                        if self._should_print_no_response_warning(
                            now=poll_now,
                            warning_seconds=warning_seconds,
                        ):
                            elapsed_seconds = self._seconds_since_last_activity(poll_now)
                            self._print_no_response_warning(elapsed_seconds)
                            self.next_no_response_warning_at = poll_now + warning_seconds
                        continue

                    if not drain_result.units:
                        self._log_debug(
                            f"Poll ended with buffered partial data poll={self.poll_count}"
                        )
                        if self._should_print_heartbeat(
                            now=poll_now,
                            heartbeat_seconds=heartbeat_seconds,
                        ):
                            self._print_heartbeat()
                            self.next_heartbeat_at = poll_now + heartbeat_seconds
                        if self._should_print_no_response_warning(
                            now=poll_now,
                            warning_seconds=warning_seconds,
                        ):
                            elapsed_seconds = self._seconds_since_last_activity(poll_now)
                            self._print_no_response_warning(elapsed_seconds)
                            self.next_no_response_warning_at = poll_now + warning_seconds
                        continue

                    for unit in drain_result.units:
                        self._handle_protocol_unit(unit, now=poll_now, host=host)

                    if self._should_print_heartbeat(
                        now=poll_now,
                        heartbeat_seconds=heartbeat_seconds,
                    ):
                        self._print_heartbeat()
                        self.next_heartbeat_at = poll_now + heartbeat_seconds
                    if self._should_print_no_response_warning(
                        now=poll_now,
                        warning_seconds=warning_seconds,
                    ):
                        elapsed_seconds = self._seconds_since_last_activity(poll_now)
                        self._print_no_response_warning(elapsed_seconds)
                        self.next_no_response_warning_at = poll_now + warning_seconds
            finally:
                if self.config.enable_rte:
                    try:
                        disable_frame = host.send_disable_rte()
                        self._emit_transport_line(
                            "TX>=",
                            disable_frame,
                        )
                    except Exception:
                        self._log_debug("Failed to send disable RTE during shutdown")
                        pass


def parse_address(value: str) -> int:
    parsed = int(value, 0)
    if parsed < 1 or parsed > 0x7F:
        raise argparse.ArgumentTypeError("address must be in the range 1-127")
    return parsed


def parse_positive_int(value: str) -> int:
    parsed = int(value, 10)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def parse_non_negative_int(value: str) -> int:
    parsed = int(value, 10)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return parsed


def parse_non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return parsed


def parse_tcp_port(value: str) -> int:
    parsed = int(value, 10)
    if parsed < 1 or parsed > 65535:
        raise argparse.ArgumentTypeError("port must be in the range 1-65535")
    return parsed


def normalize_xml_element_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def get_xml_child_text(element: ET.Element, child_name: str) -> Optional[str]:
    target = child_name.upper()
    for child in element:
        if normalize_xml_element_name(child.tag).upper() == target:
            if child.text is None:
                return ""
            return child.text.strip()
    return None


def format_tce_timestamp() -> str:
    return datetime.now().strftime("%Y %m %d %H:%M:%S")


def format_tce_terminal_line(payload: str) -> str:
    return f"{format_tce_timestamp()} ---> {payload}"


def emit_tce_terminal_line(payload: str) -> str:
    line = format_tce_terminal_line(payload)
    print(line, flush=True)
    return line


@dataclass(frozen=True)
class TCEEndpointConfig:
    vlt_ip: str
    vlt_port: int
    tce_port: int
    state_poll_interval_ms: int = DEFAULT_TCE_STATE_POLL_INTERVAL_MS
    tce_number: int = DEFAULT_TCE_TCE_NUMBER
    tce_label: str = DEFAULT_TCE_LABEL
    config_path: Optional[str] = None
    tce_ip_override: Optional[str] = None
    configured_callback_ip: Optional[str] = None
    debug: bool = False

    @property
    def vlt_service_url(self) -> str:
        return f"http://{self.vlt_ip}:{self.vlt_port}"


@dataclass(frozen=True)
class TCERegistrationResult:
    requested_endpoint: str
    confirmed_endpoint: str


@dataclass(frozen=True)
class TCECallbackResolution:
    callback_ip: str
    source: str
    configured_callback_ip: Optional[str] = None


@dataclass
class TCECallbackDiagnostics:
    listener_bind_succeeded: bool = False
    tcp_connection_count: int = 0
    callback_delivery_count: int = 0
    http_request_count: int = 0
    parsed_callback_count: int = 0
    parse_error_count: int = 0
    unhandled_callback_count: int = 0
    last_client_address: Optional[str] = None
    last_operation_name: Optional[str] = None
    last_parse_error: Optional[str] = None
    last_request_line: Optional[str] = None
    self_probe_passed: bool = False
    last_request_size: Optional[int] = None
    state_pull_attempt_count: int = 0
    state_pull_success_count: int = 0
    state_pull_live_state_count: int = 0
    state_pull_error_count: int = 0
    last_state_pull_error: Optional[str] = None
    last_pulled_state: Optional[str] = None
    state_payload_seen: bool = False
    last_callback_updatevar_name: Optional[str] = None
    last_callback_updatevar_value_preview: Optional[str] = None
    callback_variable_counts: dict[str, int] = field(default_factory=dict)
    last_state_pull_operation_name: Optional[str] = None
    last_state_pull_fields_preview: Optional[str] = None
    last_state_pull_context: Optional[str] = None
    blank_state_seen_from_callback: bool = False
    blank_state_seen_from_qa: bool = False
    non_state_callback_seen: bool = False
    state_poller_started: bool = False
    state_poller_running: bool = False
    state_poller_failure_count: int = 0
    last_state_poller_error: Optional[str] = None


@dataclass(frozen=True)
class TCECallbackEmission:
    payload: Optional[str]
    counts_as_live_activity: bool
    is_supported: bool


@dataclass(frozen=True)
class SOAPBodyOperation:
    name: str
    values: dict[str, str]
    wrapper_name: Optional[str] = None
    wrapped_values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class QATestingStateResult:
    state: str
    status: int
    operation_name: str
    fields_preview: str


def parse_tce_xml_config(path: str) -> dict[str, str]:
    tree = ET.parse(path)
    root = tree.getroot()
    values: dict[str, str] = {}

    vlt_node = root.find("./VLT")
    if vlt_node is not None:
        vlt_ip = get_xml_child_text(vlt_node, "SOAP_LISTEN_IP")
        vlt_port = get_xml_child_text(vlt_node, "SOAP_LISTEN_PORT")
        if vlt_ip:
            values["vlt_ip"] = vlt_ip
        if vlt_port:
            values["vlt_port"] = vlt_port

    tce_node = root.find("./TCE")
    if tce_node is not None:
        tce_ip = get_xml_child_text(tce_node, "SOAP_LISTEN_IP")
        tce_port = get_xml_child_text(tce_node, "SOAP_LISTEN_PORT")
        if tce_ip:
            values["tce_ip"] = tce_ip
        if tce_port:
            values["tce_port"] = tce_port

    return values


def parse_tce_cfg_config(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("[") or "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip().upper()
            value = raw_value.strip()
            if not value:
                continue
            if key == "IP ADDRESS":
                values["vlt_ip"] = value
            elif key == "IP PORT":
                values["vlt_port"] = value
            elif key == "SOAP LISTEN IP":
                values["tce_ip"] = value
            elif key == "SOAP LISTEN PORT":
                values["tce_port"] = value
    return values


def normalize_soap_field_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", name).upper()


def get_soap_field_value(
    values: dict[str, str],
    *candidate_names: str,
) -> Optional[str]:
    normalized_values = {
        normalize_soap_field_name(key): value for key, value in values.items()
    }
    for candidate_name in candidate_names:
        value = normalized_values.get(normalize_soap_field_name(candidate_name))
        if value is not None:
            return value
    return None


def format_diagnostic_preview(
    value: Optional[str],
    *,
    limit: int = MAX_TCE_DIAGNOSTIC_PREVIEW_LENGTH,
) -> str:
    if value is None:
        return "<none>"
    text = format_single_line_text(value)
    if not text:
        return "<blank>"
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def format_diagnostic_fields_preview(
    values: dict[str, str],
    *,
    limit: int = MAX_TCE_DIAGNOSTIC_FIELDS,
) -> str:
    if not values:
        return "<none>"
    items = list(values.items())
    preview = ", ".join(
        f"{key}={format_diagnostic_preview(value)}"
        for key, value in items[:limit]
    )
    if len(items) > limit:
        preview += ", ..."
    return preview


def format_callback_variable_counts_preview(
    counts: dict[str, int],
    *,
    limit: int = MAX_TCE_DIAGNOSTIC_CALLBACK_VARIABLES,
) -> str:
    if not counts:
        return "<none>"
    items = list(counts.items())
    preview = ", ".join(f"{key}:{value}" for key, value in items[:limit])
    if len(items) > limit:
        preview += ", ..."
    return preview


def parse_qatesting_status(
    values: dict[str, str],
    *candidate_names: str,
) -> int:
    raw_status = get_soap_field_value(values, *candidate_names)
    if raw_status is None or raw_status == "":
        return -1
    return int(raw_status)


def parse_qatesting_state_values(values: dict[str, str]) -> tuple[str, int]:
    return (
        (get_soap_field_value(values, "state", "m-State", "mState") or "").strip(),
        parse_qatesting_status(values, "status", "m-Status", "mStatus"),
    )


def parse_qatesting_state_payload(
    operation: SOAPBodyOperation,
    *,
    expected_operation_name: str,
) -> QATestingStateResult:
    if operation.name not in (expected_operation_name, "QAGameInfo"):
        raise RuntimeError(f"Unexpected SOAP response operation: {operation.name}")
    active_values = operation.values
    active_wrapper_name: Optional[str] = None
    state_value, status = parse_qatesting_state_values(active_values)
    if not state_value and operation.wrapper_name and operation.wrapped_values:
        nested_state_value, nested_status = parse_qatesting_state_values(
            operation.wrapped_values
        )
        if nested_state_value or nested_status >= 0:
            active_values = operation.wrapped_values
            active_wrapper_name = operation.wrapper_name
            state_value = nested_state_value
            status = nested_status
    fields_preview = format_diagnostic_fields_preview(active_values)
    if active_wrapper_name:
        fields_preview = f"wrapper={active_wrapper_name} {fields_preview}"
    return QATestingStateResult(
        state=state_value,
        status=status,
        operation_name=operation.name,
        fields_preview=fields_preview,
    )


def derive_tce_label_from_path(path: Optional[str]) -> str:
    if path:
        match = TCE_XML_FILENAME_PATTERN.fullmatch(os.path.basename(path))
        if match:
            return f"TCE{match.group(1)}"
    return DEFAULT_TCE_LABEL


def derive_tce_number_from_path(path: Optional[str]) -> int:
    if path:
        match = TCE_XML_FILENAME_PATTERN.fullmatch(os.path.basename(path))
        if match:
            return int(match.group(1))
    return DEFAULT_TCE_TCE_NUMBER


def is_valid_tce_config_xml_path(path: str) -> bool:
    return bool(TCE_XML_FILENAME_PATTERN.fullmatch(os.path.basename(path)))


def list_valid_tce_config_xml_paths(glob_pattern: str) -> list[str]:
    return sorted(
        os.path.normpath(path)
        for path in glob.glob(glob_pattern)
        if is_valid_tce_config_xml_path(path)
    )


def parse_optional_tcp_port(value: Optional[str], *, field_name: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return parse_tcp_port(value)
    except argparse.ArgumentTypeError as exc:
        raise RuntimeError(f"Invalid {field_name}: {exc}") from exc


def pick_tce_config_paths(explicit_path: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if explicit_path:
        normalized = os.path.normpath(explicit_path)
        if not os.path.exists(normalized):
            raise RuntimeError(f"TCE config file was not found: {normalized}")
        if normalized.lower().endswith(".xml"):
            return normalized, DEFAULT_TCE_CFG_PATH if os.path.exists(DEFAULT_TCE_CFG_PATH) else None
        return None, normalized

    selected_xml_path: Optional[str] = None
    if os.path.exists(DEFAULT_TCE_PRIMARY_CONFIG_PATH):
        selected_xml_path = DEFAULT_TCE_PRIMARY_CONFIG_PATH
    else:
        matching_paths = list_valid_tce_config_xml_paths(DEFAULT_TCE_CONFIG_GLOB)
        if matching_paths:
            selected_xml_path = matching_paths[0]

    selected_cfg_path = DEFAULT_TCE_CFG_PATH if os.path.exists(DEFAULT_TCE_CFG_PATH) else None
    return selected_xml_path, selected_cfg_path


def build_tce_config(args: argparse.Namespace) -> TCEEndpointConfig:
    selected_xml_path, selected_cfg_path = pick_tce_config_paths(args.config_file)
    xml_values = parse_tce_xml_config(selected_xml_path) if selected_xml_path else {}
    cfg_values = parse_tce_cfg_config(selected_cfg_path) if selected_cfg_path else {}

    vlt_ip = args.vlt_ip or xml_values.get("vlt_ip") or cfg_values.get("vlt_ip")
    if not vlt_ip:
        raise RuntimeError("Missing VLT IP. Use --vlt-ip or provide it in the TCE config.")

    vlt_port = (
        args.vlt_port
        if args.vlt_port is not None
        else parse_optional_tcp_port(xml_values.get("vlt_port"), field_name="VLT port")
        or parse_optional_tcp_port(cfg_values.get("vlt_port"), field_name="VLT port")
    )
    if vlt_port is None:
        raise RuntimeError("Missing VLT port. Use --vlt-port or provide it in the TCE config.")

    tce_port = (
        args.tce_port
        if args.tce_port is not None
        else parse_optional_tcp_port(xml_values.get("tce_port"), field_name="TCE port")
        or parse_optional_tcp_port(cfg_values.get("tce_port"), field_name="TCE port")
    )
    if tce_port is None:
        raise RuntimeError("Missing TCE port. Use --tce-port or provide it in the TCE config.")

    configured_callback_ip = xml_values.get("tce_ip") or cfg_values.get("tce_ip")
    config_path = selected_xml_path or selected_cfg_path
    return TCEEndpointConfig(
        vlt_ip=vlt_ip,
        vlt_port=vlt_port,
        tce_port=tce_port,
        state_poll_interval_ms=args.state_poll_ms,
        tce_number=derive_tce_number_from_path(selected_xml_path),
        tce_label=derive_tce_label_from_path(selected_xml_path),
        config_path=config_path,
        tce_ip_override=args.tce_ip,
        configured_callback_ip=configured_callback_ip,
        debug=args.debug,
    )


def validate_ipv4_address(value: str, *, field_name: str) -> str:
    try:
        socket.inet_aton(value)
    except OSError as exc:
        raise RuntimeError(f"Invalid {field_name}: {value}") from exc
    return value


def detect_local_ipv4(
    vlt_ip: str,
    vlt_port: int,
    *,
    override: Optional[str] = None,
    socket_factory: Callable[..., socket.socket] = socket.socket,
    hostname_lookup: Callable[[str, object, int], list[tuple[object, ...]]] = socket.getaddrinfo,
) -> str:
    if override:
        return validate_ipv4_address(override, field_name="TCE IP override")

    try:
        probe = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect((vlt_ip, vlt_port))
            detected_ip = probe.getsockname()[0]
            if detected_ip and not detected_ip.startswith("127.") and detected_ip != "0.0.0.0":
                return detected_ip
        finally:
            probe.close()
    except OSError:
        pass

    try:
        for family, _, _, _, sockaddr in hostname_lookup(socket.gethostname(), None, socket.AF_INET):
            if family != socket.AF_INET:
                continue
            candidate_ip = sockaddr[0]
            if candidate_ip and not candidate_ip.startswith("127.") and candidate_ip != "0.0.0.0":
                return candidate_ip
    except OSError:
        pass

    raise RuntimeError(
        "Could not auto-detect a local IPv4 address for the TCE endpoint. "
        "Use --tce-ip to provide it explicitly."
    )


def resolve_tce_callback_ip(
    config: TCEEndpointConfig,
    *,
    local_ip_detector: Optional[Callable[[str, int], str]] = None,
) -> str:
    return resolve_tce_callback_resolution(
        config,
        local_ip_detector=local_ip_detector,
    ).callback_ip


def resolve_tce_callback_resolution(
    config: TCEEndpointConfig,
    *,
    local_ip_detector: Optional[Callable[[str, int], str]] = None,
) -> TCECallbackResolution:
    if local_ip_detector is None:
        local_ip_detector = detect_local_ipv4

    if config.tce_ip_override:
        return TCECallbackResolution(
            callback_ip=validate_ipv4_address(
                config.tce_ip_override,
                field_name="TCE IP override",
            ),
            source="override",
            configured_callback_ip=config.configured_callback_ip,
        )

    if config.configured_callback_ip:
        return TCECallbackResolution(
            callback_ip=validate_ipv4_address(
                config.configured_callback_ip,
                field_name="configured TCE callback IP",
            ),
            source="configured",
            configured_callback_ip=config.configured_callback_ip,
        )

    return TCECallbackResolution(
        callback_ip=local_ip_detector(config.vlt_ip, config.vlt_port),
        source="auto-detected",
        configured_callback_ip=config.configured_callback_ip,
    )


def parse_http_service_url(service_url: str) -> tuple[str, int, str]:
    parsed_url = urlsplit(service_url)
    if parsed_url.scheme not in {"", "http"}:
        raise RuntimeError(f"Unsupported SOAP scheme in endpoint: {service_url}")
    if not parsed_url.hostname:
        raise RuntimeError(f"Invalid SOAP endpoint: {service_url}")

    path = parsed_url.path or "/"
    if parsed_url.query:
        path = f"{path}?{parsed_url.query}"
    return parsed_url.hostname, parsed_url.port or 80, path


def build_soap_envelope(namespace_prefix: str, namespace_uri: str, operation_name: str, inner_xml: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<SOAP-ENV:Envelope xmlns:SOAP-ENV="{SOAP_ENVELOPE_NAMESPACE}" '
        f'xmlns:{namespace_prefix}="{namespace_uri}">'
        "<SOAP-ENV:Body>"
        f"<{namespace_prefix}:{operation_name}>{inner_xml}</{namespace_prefix}:{operation_name}>"
        "</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    ).encode("utf-8")


def format_tce_registration_context(service_url: str, endpoint_value: str) -> str:
    return f"service={service_url} callback={endpoint_value}"


def format_exception_detail(exc: BaseException) -> str:
    if exc.__cause__ is not None:
        return str(exc.__cause__)
    return str(exc)


def format_single_line_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def format_client_address(client_address: object) -> str:
    if (
        isinstance(client_address, tuple)
        and len(client_address) >= 2
        and isinstance(client_address[0], str)
    ):
        return f"{client_address[0]}:{client_address[1]}"
    return str(client_address)


def extract_client_ip(client_address: object) -> Optional[str]:
    if (
        isinstance(client_address, tuple)
        and len(client_address) >= 1
        and isinstance(client_address[0], str)
    ):
        return client_address[0]
    return None


def is_tce_self_probe_path(request_path: str) -> bool:
    return urlsplit(request_path).path == TCE_SELF_PROBE_PATH


def probe_vlt_soap_service(
    service_url: str,
    callback_endpoint: str,
    *,
    timeout_seconds: float = DEFAULT_TCE_SERVICE_PREFLIGHT_TIMEOUT_SECONDS,
    connection_factory: Callable[..., socket.socket] = socket.create_connection,
) -> None:
    context = format_tce_registration_context(service_url, callback_endpoint)
    try:
        host, port, _ = parse_http_service_url(service_url)
    except RuntimeError as exc:
        raise RuntimeError(
            f"VLT SOAP preflight failed: {context} error={format_exception_detail(exc)}"
        ) from exc

    connection: Optional[socket.socket] = None
    try:
        connection = connection_factory((host, port), timeout_seconds)
    except OSError as exc:
        raise RuntimeError(
            f"VLT SOAP preflight failed: {context} error={format_exception_detail(exc)}"
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def collect_soap_child_values(parent: ET.Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in parent:
        if not isinstance(child.tag, str):
            continue
        values[normalize_xml_element_name(child.tag)] = (child.text or "").strip()
    return values


def parse_soap_body_operation_details(payload: bytes) -> SOAPBodyOperation:
    root = ET.fromstring(payload)
    body_element: Optional[ET.Element] = None
    for element in root.iter():
        if normalize_xml_element_name(element.tag).upper() == "BODY":
            body_element = element
            break
    if body_element is None:
        raise RuntimeError("SOAP message did not contain a Body element")

    operation_element: Optional[ET.Element] = None
    for child in body_element:
        if isinstance(child.tag, str):
            operation_element = child
            break
    if operation_element is None:
        raise RuntimeError("SOAP message body did not contain an operation element")

    values = collect_soap_child_values(operation_element)
    wrapper_name: Optional[str] = None
    wrapped_values: dict[str, str] = {}
    operation_children = [
        child for child in operation_element if isinstance(child.tag, str)
    ]
    if len(operation_children) == 1:
        wrapper_element = operation_children[0]
        wrapped_values = collect_soap_child_values(wrapper_element)
        if wrapped_values:
            wrapper_name = normalize_xml_element_name(wrapper_element.tag)

    return SOAPBodyOperation(
        name=normalize_xml_element_name(operation_element.tag),
        values=values,
        wrapper_name=wrapper_name,
        wrapped_values=wrapped_values,
    )


def parse_soap_body_operation(payload: bytes) -> tuple[str, dict[str, str]]:
    operation = parse_soap_body_operation_details(payload)
    return operation.name, operation.values


def format_request_line_preview(raw_request_line: bytes, *, limit: int = 160) -> str:
    preview = raw_request_line[:limit]
    decoded = preview.decode("utf-8", errors="replace")
    collapsed = format_single_line_text(
        "".join(character if character.isprintable() else " " for character in decoded)
    )
    if collapsed:
        return collapsed + (" ..." if len(raw_request_line) > len(preview) else "")
    return format_hex(preview) + (" ..." if len(raw_request_line) > len(preview) else "")


def send_soap_request(
    service_url: str,
    envelope: bytes,
    *,
    debug: bool = False,
    operation_name: Optional[str] = None,
) -> bytes:
    host, port, path = parse_http_service_url(service_url)
    connection = http.client.HTTPConnection(
        host,
        port,
        timeout=5,
    )
    try:
        try:
            connection.request(
                "POST",
                path,
                body=envelope,
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": '""',
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            response_body = response.read()
        except TimeoutError as exc:
            raise RuntimeError(
                f"SOAP {operation_name or 'request'} to {service_url} timed out"
            ) from exc
        except (OSError, http.client.HTTPException) as exc:
            raise RuntimeError(
                f"SOAP {operation_name or 'request'} to {service_url} failed: {exc}"
            ) from exc
        if debug:
            print(
                format_log_line(
                    "DEBUG",
                    f"SOAP {operation_name or 'request'} -> {service_url} "
                    f"status={response.status} bytes={len(response_body)}",
                )
            )
        if response.status != 200:
            raise RuntimeError(
                f"SOAP {operation_name or 'request'} failed with HTTP status {response.status}"
            )
        return response_body
    finally:
        connection.close()


def call_qatesting_set_tce_endpoint(service_url: str, endpoint_value: str, *, debug: bool = False) -> int:
    context = format_tce_registration_context(service_url, endpoint_value)
    envelope = build_soap_envelope(
        "QATesting",
        QATESTING_NAMESPACE,
        "SetTCEEndPoint",
        f"<tceEndPoint>{xml_escape(endpoint_value)}</tceEndPoint>",
    )
    if debug:
        print(format_log_line("DEBUG", f"SetTCEEndPoint request {context}"))
    try:
        operation_name, values = parse_soap_body_operation(
            send_soap_request(
                service_url,
                envelope,
                debug=debug,
                operation_name="SetTCEEndPoint",
            )
        )
    except RuntimeError as exc:
        raise RuntimeError(
            f"SOAP SetTCEEndPoint failed: {context} error={format_exception_detail(exc)}"
        ) from exc
    if operation_name != "SetTCEEndPointResponse":
        raise RuntimeError(f"Unexpected SOAP response operation: {operation_name}")
    return int(values.get("status", "-1"))


def call_qatesting_get_tce_endpoint(service_url: str, *, debug: bool = False) -> tuple[str, int]:
    envelope = build_soap_envelope(
        "QATesting",
        QATESTING_NAMESPACE,
        "GetTCEEndPoint",
        "",
    )
    operation_name, values = parse_soap_body_operation(
        send_soap_request(
            service_url,
            envelope,
            debug=debug,
            operation_name="GetTCEEndPoint",
        )
    )
    if operation_name != "GetTCEEndPointResponse":
        raise RuntimeError(f"Unexpected SOAP response operation: {operation_name}")
    return values.get("value", ""), int(values.get("status", "-1"))


def call_qatesting_get_game_state(service_url: str) -> tuple[str, int]:
    result = call_qatesting_get_game_state_result(service_url)
    return result.state, result.status


def call_qatesting_get_game_state_result(service_url: str) -> QATestingStateResult:
    envelope = build_soap_envelope(
        "QATesting",
        QATESTING_NAMESPACE,
        "GetGameState",
        "",
    )
    operation = parse_soap_body_operation_details(
        send_soap_request(
            service_url,
            envelope,
            operation_name="GetGameState",
        )
    )
    return parse_qatesting_state_payload(
        operation,
        expected_operation_name="GetGameStateResponse",
    )


def call_qatesting_init_test_client_state(service_url: str) -> tuple[str, int]:
    result = call_qatesting_init_test_client_state_result(service_url)
    return result.state, result.status


def call_qatesting_init_test_client_state_result(
    service_url: str,
) -> QATestingStateResult:
    envelope = build_soap_envelope(
        "QATesting",
        QATESTING_NAMESPACE,
        "InitTestClient",
        "",
    )
    operation = parse_soap_body_operation_details(
        send_soap_request(
            service_url,
            envelope,
            operation_name="InitTestClient",
        )
    )
    return parse_qatesting_state_payload(
        operation,
        expected_operation_name="InitTestClientResponse",
    )


def register_tce_endpoint(service_url: str, endpoint_value: str, *, debug: bool = False) -> TCERegistrationResult:
    candidate_values = [endpoint_value]
    if not endpoint_value.lower().startswith("http://"):
        candidate_values.append(f"http://{endpoint_value}")

    last_error: Optional[str] = None
    for candidate_value in candidate_values:
        if debug:
            print(
                format_log_line(
                    "DEBUG",
                    f"Registering TCE endpoint {format_tce_registration_context(service_url, candidate_value)}",
                )
            )
        set_status = call_qatesting_set_tce_endpoint(service_url, candidate_value, debug=debug)
        confirmed_value, get_status = call_qatesting_get_tce_endpoint(service_url, debug=debug)
        if debug:
            print(
                format_log_line(
                    "DEBUG",
                    f"Endpoint registration {format_tce_registration_context(service_url, candidate_value)} "
                    f"set_status={set_status} get_status={get_status} confirmed={confirmed_value}",
                )
            )
        if set_status >= 0 and get_status >= 0 and confirmed_value.strip() == candidate_value:
            return TCERegistrationResult(
                requested_endpoint=candidate_value,
                confirmed_endpoint=confirmed_value.strip(),
            )
        last_error = (
            f"candidate={candidate_value} set_status={set_status} "
            f"get_status={get_status} confirmed={confirmed_value!r}"
        )

    raise RuntimeError(
        "Could not verify TCE endpoint registration through GetTCEEndPoint "
        f"for {format_tce_registration_context(service_url, endpoint_value)}"
        + (f" ({last_error})" if last_error else "")
    )


def build_tce_terminal_payload(
    tce_number: int,
    raw_message: str,
    *,
    message_level: int = DEFAULT_TCE_MESSAGE_LEVEL_VAR,
) -> str:
    return f"{tce_number}|{message_level}|{raw_message}"


def build_tce_variable_payload(tce_number: int, *parts: str) -> str:
    if len(parts) % 2 != 0:
        raise ValueError("TCE variable payload parts must be key/value pairs")
    raw_message = "".join(
        f"|{parts[index]}|{parts[index + 1]}"
        for index in range(0, len(parts), 2)
    )
    return build_tce_terminal_payload(tce_number, raw_message)


def build_tce_state_payload(
    tce_number: int,
    state_value: str,
) -> str:
    return build_tce_variable_payload(tce_number, "STATE", state_value)


def build_idle_terminal_payload(tce_number: int = DEFAULT_TCE_TCE_NUMBER) -> str:
    return build_tce_state_payload(tce_number, IDLE_STATE_VALUE)


def is_idle_tce_terminal_payload(payload: str) -> bool:
    return bool(
        re.fullmatch(
            rf"\d+\|{DEFAULT_TCE_MESSAGE_LEVEL_VAR}\|\|STATE\|{re.escape(IDLE_STATE_VALUE)}",
            payload,
        )
    )


def extract_tce_state_from_payload(payload: str) -> Optional[str]:
    match = re.fullmatch(r"\d+\|\d+\|\|STATE\|(.+)", payload)
    if not match:
        return None
    return match.group(1).strip()


def pack_client_ip_as_unsigned_int(client_ip: str) -> Optional[int]:
    try:
        return int.from_bytes(socket.inet_aton(client_ip), byteorder="big", signed=False)
    except OSError:
        return None


def format_tce_callback_emission(
    operation_name: str,
    values: dict[str, str],
    *,
    client_ip: Optional[str],
    expected_vlt_ip: Optional[str],
    tce_number: int,
) -> TCECallbackEmission:
    normalized_operation = operation_name.upper()

    def suppress_for_unexpected_source() -> Optional[TCECallbackEmission]:
        if expected_vlt_ip and client_ip and client_ip != expected_vlt_ip:
            return TCECallbackEmission(
                payload=None,
                counts_as_live_activity=False,
                is_supported=True,
            )
        return None

    if normalized_operation == "UPDATEVAR":
        name = values.get("name", "").strip()
        if not name:
            return TCECallbackEmission(None, False, False)
        state_value = values.get("valstr", "").strip()
        normalized_name = normalize_soap_field_name(name)
        suppressed = suppress_for_unexpected_source()
        if suppressed is not None:
            return suppressed
        if normalized_name in TCE_STATE_UPDATEVAR_ALIASES:
            if not state_value:
                return TCECallbackEmission(None, False, True)
            return TCECallbackEmission(
                payload=build_tce_state_payload(
                    tce_number,
                    state_value,
                ),
                counts_as_live_activity=True,
                is_supported=True,
            )
        return TCECallbackEmission(
            payload=build_tce_variable_payload(
                tce_number,
                name.upper(),
                state_value,
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )

    if normalized_operation == "STATETRANSITION":
        state_name = values.get("name", "").strip()
        if not state_name:
            return TCECallbackEmission(None, False, False)
        suppressed = suppress_for_unexpected_source()
        if suppressed is not None:
            return suppressed
        return TCECallbackEmission(
            payload=build_tce_state_payload(tce_number, state_name),
            counts_as_live_activity=True,
            is_supported=True,
        )

    if normalized_operation == "BANKTRANSITION":
        suppressed = suppress_for_unexpected_source()
        if suppressed is not None:
            return suppressed
        return TCECallbackEmission(
            payload=build_tce_variable_payload(
                tce_number,
                "BANK",
                values.get("amount", "").strip(),
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )

    if normalized_operation == "BETTRANSITION":
        suppressed = suppress_for_unexpected_source()
        if suppressed is not None:
            return suppressed
        return TCECallbackEmission(
            payload=build_tce_variable_payload(
                tce_number,
                "BET",
                values.get("amount", "").strip(),
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )

    if normalized_operation == "PAYLINETRANSITION":
        suppressed = suppress_for_unexpected_source()
        if suppressed is not None:
            return suppressed
        return TCECallbackEmission(
            payload=build_tce_terminal_payload(
                tce_number,
                f"Number Of Lines: {values.get('paylines', '').strip()}",
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )

    if normalized_operation == "UPDATEWINAMOUNT":
        suppressed = suppress_for_unexpected_source()
        if suppressed is not None:
            return suppressed
        return TCECallbackEmission(
            payload=build_tce_variable_payload(
                tce_number,
                "WIN",
                values.get("amount", "").strip(),
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )

    if normalized_operation == "UPDATEGAMEINFO":
        suppressed = suppress_for_unexpected_source()
        if suppressed is not None:
            return suppressed
        return TCECallbackEmission(
            payload=build_tce_variable_payload(
                tce_number,
                "ID",
                values.get("gameid", "").strip(),
                "GameName",
                values.get("gamename", "").strip(),
                "CreditSz",
                values.get("creditsize", "").strip(),
                "Percent",
                values.get("percentage", "").strip(),
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )

    if normalized_operation == "MESSAGEQUEUECOUNT":
        suppressed = suppress_for_unexpected_source()
        if suppressed is not None:
            return suppressed
        return TCECallbackEmission(
            payload=build_tce_terminal_payload(
                0,
                "SOAP PUSH Event - Update Message Queue (Count) "
                f"({values.get('queuecount', '').strip()})",
            ),
            counts_as_live_activity=False,
            is_supported=True,
        )

    return TCECallbackEmission(None, False, False)


def build_technology_soap_response(operation_name: str, *, status: int = 0) -> bytes:
    return build_soap_envelope(
        "Technology",
        TECHNOLOGY_NAMESPACE,
        f"{operation_name}Response",
        f"<status>{status}</status>",
    )


def build_soap_fault(message: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<SOAP-ENV:Envelope xmlns:SOAP-ENV="{SOAP_ENVELOPE_NAMESPACE}">'
        "<SOAP-ENV:Body>"
        "<SOAP-ENV:Fault>"
        "<faultcode>SOAP-ENV:Client</faultcode>"
        f"<faultstring>{xml_escape(message)}</faultstring>"
        "</SOAP-ENV:Fault>"
        "</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    ).encode("utf-8")


def run_tce_callback_self_probe(
    callback_ip: str,
    callback_port: int,
    *,
    timeout_seconds: float = 5.0,
    debug: bool = False,
) -> None:
    if debug:
        print(
            format_log_line(
                "DEBUG",
                f"Self-probing TCE callback listener http://{callback_ip}:{callback_port}{TCE_SELF_PROBE_PATH}",
            )
        )
    connection = http.client.HTTPConnection(
        callback_ip,
        callback_port,
        timeout=timeout_seconds,
    )
    try:
        try:
            connection.request(
                "POST",
                TCE_SELF_PROBE_PATH,
                body=build_soap_envelope(
                    "Technology",
                    TECHNOLOGY_NAMESPACE,
                    "UpdateVar",
                    "<name>STATE</name><valstr>SelfProbe</valstr>",
                ),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": '""',
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            response_body = response.read()
        except TimeoutError as exc:
            raise RuntimeError("TCE callback self-probe timed out") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise RuntimeError(f"TCE callback self-probe failed: {exc}") from exc

        if response.status != 200:
            raise RuntimeError(
                f"TCE callback self-probe failed with HTTP status {response.status}"
            )
        operation_name, values = parse_soap_body_operation(response_body)
        if operation_name != "UpdateVarResponse":
            raise RuntimeError(
                f"Unexpected TCE callback self-probe response operation: {operation_name}"
            )
        if int(values.get("status", "-1")) < 0:
            raise RuntimeError(
                f"TCE callback self-probe failed with status {values.get('status', '-1')}"
            )
        if debug:
            print(
                format_log_line(
                    "DEBUG",
                    f"TCE callback self-probe succeeded http://{callback_ip}:{callback_port}{TCE_SELF_PROBE_PATH}",
                )
            )
    finally:
        connection.close()


class TCEOutputSession:
    def __init__(self, *, emit_diagnostic_payloads: bool = False) -> None:
        self._lock = threading.Lock()
        self._emit_diagnostic_payloads = emit_diagnostic_payloads
        self._live_payload_seen = False
        self._state_payload_seen = False
        self._callback_seen = False
        self._non_idle_state_seen = False
        self._last_emitted_payload: Optional[str] = None
        self._last_emitted_state: Optional[str] = None
        self._stop_event = threading.Event()
        self._diagnostics = TCECallbackDiagnostics()

    @property
    def stop_event(self) -> threading.Event:
        return self._stop_event

    @property
    def callback_seen(self) -> bool:
        with self._lock:
            return self._callback_seen

    @property
    def live_payload_seen(self) -> bool:
        with self._lock:
            return self._live_payload_seen

    @property
    def state_payload_seen(self) -> bool:
        with self._lock:
            return self._state_payload_seen

    def diagnostics_snapshot(self) -> TCECallbackDiagnostics:
        with self._lock:
            return deepcopy(self._diagnostics)

    def note_listener_bound(self) -> None:
        with self._lock:
            self._diagnostics.listener_bind_succeeded = True

    def note_tcp_connection(self, *, client_address: str) -> None:
        with self._lock:
            self._diagnostics.tcp_connection_count += 1
            self._diagnostics.last_client_address = client_address

    def note_callback_delivery(self, *, request_size: int, client_address: str) -> None:
        with self._lock:
            self._diagnostics.callback_delivery_count += 1
            self._diagnostics.last_client_address = client_address
            self._diagnostics.last_request_size = request_size

    def note_http_request(self, *, request_size: int, client_address: str) -> None:
        with self._lock:
            self._diagnostics.callback_delivery_count += 1
            self._diagnostics.http_request_count += 1
            self._diagnostics.last_client_address = client_address
            self._diagnostics.last_request_size = request_size

    def note_request_line(self, request_line: str) -> None:
        with self._lock:
            self._diagnostics.last_request_line = request_line

    def note_parsed_callback(
        self,
        operation_name: str,
        values: Optional[dict[str, str]] = None,
    ) -> None:
        with self._lock:
            self._diagnostics.parsed_callback_count += 1
            self._diagnostics.last_operation_name = operation_name
            if operation_name.upper() != "UPDATEVAR" or not values:
                return
            raw_name = values.get("name", "").strip()
            if not raw_name:
                return
            normalized_name = normalize_soap_field_name(raw_name)
            self._diagnostics.last_callback_updatevar_name = normalized_name
            self._diagnostics.last_callback_updatevar_value_preview = (
                format_diagnostic_preview(values.get("valstr"))
            )
            self._diagnostics.callback_variable_counts[normalized_name] = (
                self._diagnostics.callback_variable_counts.get(normalized_name, 0) + 1
            )
            if normalized_name in TCE_STATE_UPDATEVAR_ALIASES:
                if not values.get("valstr", "").strip():
                    self._diagnostics.blank_state_seen_from_callback = True
            else:
                self._diagnostics.non_state_callback_seen = True

    def note_unhandled_callback(self, operation_name: str) -> None:
        with self._lock:
            self._diagnostics.unhandled_callback_count += 1
            self._diagnostics.last_operation_name = operation_name

    def note_parse_error(
        self,
        *,
        request_size: int,
        client_address: str,
        error_text: str,
    ) -> None:
        with self._lock:
            self._diagnostics.parse_error_count += 1
            self._diagnostics.last_client_address = client_address
            self._diagnostics.last_request_size = request_size
            self._diagnostics.last_parse_error = format_single_line_text(error_text)

    def note_self_probe_passed(self) -> None:
        with self._lock:
            self._diagnostics.self_probe_passed = True

    def note_state_poller_started(self) -> None:
        with self._lock:
            self._diagnostics.state_poller_started = True
            self._diagnostics.state_poller_running = True

    def note_state_poller_stopped(self) -> None:
        with self._lock:
            if self._diagnostics.state_poller_started:
                self._diagnostics.state_poller_running = False

    def note_state_poller_failure(self, *, error_text: str) -> None:
        with self._lock:
            self._diagnostics.state_poller_failure_count += 1
            self._diagnostics.state_poller_running = False
            self._diagnostics.last_state_poller_error = format_single_line_text(
                error_text
            )

    def note_state_pull_attempt(self) -> None:
        with self._lock:
            self._diagnostics.state_pull_attempt_count += 1

    def note_state_pull_success(
        self,
        *,
        state: str,
        operation_name: Optional[str] = None,
        fields_preview: Optional[str] = None,
        context_label: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._diagnostics.state_pull_success_count += 1
            self._diagnostics.last_pulled_state = state
            if operation_name is not None:
                self._diagnostics.last_state_pull_operation_name = operation_name
            if fields_preview is not None:
                self._diagnostics.last_state_pull_fields_preview = format_single_line_text(
                    fields_preview
                )
            if context_label is not None:
                self._diagnostics.last_state_pull_context = format_single_line_text(
                    context_label
                )
            if state:
                self._diagnostics.state_pull_live_state_count += 1
            else:
                self._diagnostics.blank_state_seen_from_qa = True

    def note_state_pull_error(
        self,
        *,
        error_text: str,
        operation_name: Optional[str] = None,
        fields_preview: Optional[str] = None,
        context_label: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._diagnostics.state_pull_error_count += 1
            self._diagnostics.last_state_pull_error = format_single_line_text(error_text)
            if operation_name is not None:
                self._diagnostics.last_state_pull_operation_name = operation_name
            if fields_preview is not None:
                self._diagnostics.last_state_pull_fields_preview = format_single_line_text(
                    fields_preview
                )
            if context_label is not None:
                self._diagnostics.last_state_pull_context = format_single_line_text(
                    context_label
                )

    def _emit_payload_locked(
        self,
        payload: str,
        *,
        counts_as_live_activity: bool,
        from_callback: bool,
    ) -> None:
        if payload == self._last_emitted_payload:
            if counts_as_live_activity and from_callback:
                self._callback_seen = True
            return
        state_value = extract_tce_state_from_payload(payload)
        emit_tce_terminal_line(payload)
        self._last_emitted_payload = payload
        if not counts_as_live_activity:
            return

        self._live_payload_seen = True
        if from_callback:
            self._callback_seen = True
        if state_value is None:
            return

        self._state_payload_seen = True
        self._diagnostics.state_payload_seen = True
        self._last_emitted_state = state_value
        if state_value == IDLE_STATE_VALUE:
            if self._non_idle_state_seen:
                self._stop_event.set()
        else:
            self._non_idle_state_seen = True

    def emit_callback_emission(self, emission: TCECallbackEmission) -> None:
        if not emission.payload:
            return
        if (
            not emission.counts_as_live_activity
            and not self._emit_diagnostic_payloads
        ):
            return
        with self._lock:
            self._emit_payload_locked(
                emission.payload,
                counts_as_live_activity=emission.counts_as_live_activity,
                from_callback=True,
            )

    def emit_live_payload(self, payload: Optional[str]) -> None:
        if not payload:
            return
        with self._lock:
            self._emit_payload_locked(
                payload,
                counts_as_live_activity=True,
                from_callback=False,
            )


class TCEStatePoller:
    def __init__(
        self,
        config: TCEEndpointConfig,
        output_session: TCEOutputSession,
        *,
        poll_interval_seconds: float = DEFAULT_TCE_STATE_POLL_INTERVAL_SECONDS,
        debug_log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.config = config
        self.output_session = output_session
        self.poll_interval_seconds = poll_interval_seconds
        self.debug_log = debug_log
        self._stop_requested = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _log_debug(self, message: str) -> None:
        if self.debug_log is not None:
            self.debug_log(message)

    def _should_stop(self) -> bool:
        return self._stop_requested.is_set() or self.output_session.stop_event.is_set()

    def _handle_state_response(
        self,
        *,
        result: QATestingStateResult,
        context_label: str,
    ) -> None:
        self._log_debug(
            f"{context_label} returned operation={result.operation_name} "
            f"status={result.status} state={result.state!r} "
            f"fields={result.fields_preview}"
        )
        if result.status < 0:
            self._log_debug(
                f"Ignoring {context_label} response because status={result.status}"
            )
            self.output_session.note_state_pull_error(
                error_text=f"{context_label} returned status {result.status}",
                operation_name=result.operation_name,
                fields_preview=result.fields_preview,
            )
            return

        self.output_session.note_state_pull_success(
            state=result.state,
            operation_name=result.operation_name,
            fields_preview=result.fields_preview,
            context_label=context_label,
        )
        if not result.state:
            self._log_debug(f"Ignoring blank state from {context_label}")
            return

        self._log_debug(f"Emitting state from {context_label}: {result.state}")
        self.output_session.emit_live_payload(
            build_tce_state_payload(self.config.tce_number, result.state)
        )

    def _recover_state_via_init_test_client(
        self,
        *,
        reason: str,
    ) -> Optional[tuple[QATestingStateResult, str]]:
        context_label = f"InitTestClient fallback after {reason}"
        try:
            result = call_qatesting_init_test_client_state_result(
                self.config.vlt_service_url
            )
        except RuntimeError as exc:
            self._log_debug(f"{context_label} failed: {exc}")
            self.output_session.note_state_pull_error(
                error_text=f"{context_label} failed: {exc}",
                operation_name="InitTestClient",
                context_label=context_label,
            )
            return None
        self._log_debug(
            f"{context_label} returned operation={result.operation_name} "
            f"status={result.status} state={result.state!r} fields={result.fields_preview}"
        )
        if result.status < 0:
            self.output_session.note_state_pull_error(
                error_text=f"{context_label} returned status {result.status}",
                operation_name=result.operation_name,
                fields_preview=result.fields_preview,
                context_label=context_label,
            )
            return None
        if not result.state:
            return None
        return (
            result,
            context_label,
        )

    def bootstrap_state(self) -> None:
        self.output_session.note_state_pull_attempt()
        try:
            result = call_qatesting_init_test_client_state_result(
                self.config.vlt_service_url
            )
        except RuntimeError as exc:
            self._log_debug(f"InitTestClient failed: {exc}")
            self.output_session.note_state_pull_error(
                error_text=str(exc),
                operation_name="InitTestClient",
                context_label="InitTestClient",
            )
            return
        self._handle_state_response(
            result=result,
            context_label="InitTestClient",
        )

    def poll_current_state(self) -> None:
        self.output_session.note_state_pull_attempt()
        try:
            result = call_qatesting_get_game_state_result(
                self.config.vlt_service_url
            )
        except RuntimeError as exc:
            self._log_debug(f"GetGameState failed: {exc}")
            fallback_result = self._recover_state_via_init_test_client(
                reason="GetGameState failure",
            )
            if fallback_result is None:
                self.output_session.note_state_pull_error(
                    error_text=str(exc),
                    operation_name="GetGameState",
                    context_label="GetGameState",
                )
                return
            result, context_label = fallback_result
        else:
            if result.state and result.status >= 0:
                context_label = "GetGameState"
            else:
                if result.status < 0:
                    fallback_reason = f"GetGameState returned status {result.status}"
                else:
                    fallback_reason = "blank GetGameState"
                fallback_result = self._recover_state_via_init_test_client(
                    reason=fallback_reason,
                )
                if fallback_result is not None:
                    result, context_label = fallback_result
                else:
                    context_label = "GetGameState"
        self._handle_state_response(
            result=result,
            context_label=context_label,
        )

    def _run(self) -> None:
        self.output_session.note_state_poller_started()
        self._log_debug(
            "Standalone STATE poller started "
            f"service={self.config.vlt_service_url} "
            f"interval_ms={self.config.state_poll_interval_ms} "
            "bootstrap=InitTestClient live=GetGameState fallback=InitTestClient"
        )
        try:
            self.bootstrap_state()
            next_poll_deadline = time.monotonic()
            while not self._should_stop():
                self.poll_current_state()
                if self._should_stop():
                    break
                next_poll_deadline += self.poll_interval_seconds
                remaining_delay = next_poll_deadline - time.monotonic()
                if remaining_delay <= 0:
                    next_poll_deadline = time.monotonic()
                    continue
                self._stop_requested.wait(remaining_delay)
        except Exception as exc:
            error_text = (
                "Standalone STATE poller crashed: "
                f"{type(exc).__name__}: {format_exception_detail(exc)}"
            )
            self.output_session.note_state_poller_failure(error_text=error_text)
            self._log_debug(error_text)
        finally:
            self.output_session.note_state_poller_stopped()
            self._log_debug("Standalone STATE poller stopped")

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="TCEStatePoller",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)


class TCECallbackRequestHandler(BaseHTTPRequestHandler):
    server_version = "TCEEndpointListener/1.0"

    def setup(self) -> None:
        super().setup()
        try:
            self.connection.settimeout(1.0)
        except OSError:
            pass

        client_address = format_client_address(self.client_address)
        client_ip = extract_client_ip(self.client_address)
        expected_vlt_ip = getattr(self.server, "expected_vlt_ip", None)
        if client_ip and expected_vlt_ip and client_ip == expected_vlt_ip:
            self.server.output_session.note_tcp_connection(client_address=client_address)
        if getattr(self.server, "debug_enabled", False):
            print(
                format_log_line(
                    "DEBUG",
                    f"TCE callback TCP accept from={client_address}",
                )
            )

    def log_message(self, format_text: str, *args: object) -> None:
        if getattr(self.server, "debug_enabled", False):
            print(format_log_line("DEBUG", format_text % args))

    def _is_expected_vlt_client(self) -> bool:
        client_ip = extract_client_ip(self.client_address)
        expected_vlt_ip = getattr(self.server, "expected_vlt_ip", None)
        return bool(client_ip and expected_vlt_ip and client_ip == expected_vlt_ip)

    def _warn_if_unexpected_vlt_client(
        self,
        *,
        client_ip: Optional[str],
        operation_name: str,
    ) -> None:
        expected_vlt_ip = getattr(self.server, "expected_vlt_ip", None)
        if client_ip and expected_vlt_ip and client_ip != expected_vlt_ip:
            print(
                format_log_line(
                    "WARNING",
                    f"TCE callback source mismatch expected_vlt_ip={expected_vlt_ip} "
                    f"actual_client_ip={client_ip} operation={operation_name}",
                )
            )

    def _read_remaining_non_http_payload(self, *, max_total: int = 262144) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while total < max_total:
            try:
                chunk = self.rfile.read1(min(65536, max_total - total))
            except (OSError, TimeoutError, socket.timeout):
                break
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)

    def _handle_raw_xml_payload(self, initial_bytes: bytes) -> bool:
        stripped = initial_bytes.lstrip()
        if not stripped.startswith((b"<", b"\xef\xbb\xbf<")):
            return False

        client_address = format_client_address(self.client_address)
        payload = initial_bytes + self._read_remaining_non_http_payload()
        request_size = len(payload)
        preview = format_request_line_preview(initial_bytes)
        if self._is_expected_vlt_client():
            self.server.output_session.note_request_line(preview)
        self.server.output_session.note_callback_delivery(
            request_size=request_size,
            client_address=client_address,
        )

        try:
            operation_name, values = parse_soap_body_operation(payload)
            self.server.output_session.note_parsed_callback(operation_name, values)
            if getattr(self.server, "debug_enabled", False):
                print(
                    format_log_line(
                        "DEBUG",
                        f"TCE callback raw XML from={client_address} operation={operation_name} "
                        f"size={request_size} values={values}",
                    )
                )
            client_ip = extract_client_ip(self.client_address)
            self._warn_if_unexpected_vlt_client(
                client_ip=client_ip,
                operation_name=operation_name,
            )
            emission = format_tce_callback_emission(
                operation_name,
                values,
                client_ip=client_ip,
                expected_vlt_ip=getattr(self.server, "expected_vlt_ip", None),
                tce_number=getattr(
                    self.server,
                    "tce_number",
                    DEFAULT_TCE_TCE_NUMBER,
                ),
            )
            if not emission.is_supported:
                self.server.output_session.note_unhandled_callback(operation_name)
                if getattr(self.server, "debug_enabled", False):
                    print(
                        format_log_line(
                            "DEBUG",
                            f"Unhandled raw-XML TCE callback operation={operation_name} values={values}",
                        )
                    )
            else:
                self.server.output_session.emit_callback_emission(emission)
            response_body = build_technology_soap_response(operation_name)
        except Exception as exc:
            self.server.output_session.note_parse_error(
                request_size=request_size,
                client_address=client_address,
                error_text=f"raw XML callback parse failed: {exc}",
            )
            if getattr(self.server, "debug_enabled", False):
                print(
                    format_log_line(
                        "DEBUG",
                        f"TCE raw-XML callback error from={client_address} size={request_size}: {exc}",
                    )
                )
            response_body = build_soap_fault(str(exc))

        self.close_connection = True
        try:
            self.wfile.write(response_body)
            self.wfile.flush()
        except OSError:
            pass
        return True

    def handle_one_request(self) -> None:
        try:
            self.raw_requestline = self.rfile.readline(65537)
        except (OSError, TimeoutError, socket.timeout):
            self.close_connection = True
            return

        if len(self.raw_requestline) > 65536:
            self.requestline = ""
            self.request_version = ""
            self.command = ""
            self.send_error(414)
            return

        if not self.raw_requestline:
            self.close_connection = True
            return

        client_address = format_client_address(self.client_address)
        request_line_preview = format_request_line_preview(self.raw_requestline)
        if self._is_expected_vlt_client():
            self.server.output_session.note_request_line(request_line_preview)
        if getattr(self.server, "debug_enabled", False):
            print(
                format_log_line(
                    "DEBUG",
                    f"TCE callback request line from={client_address} raw={request_line_preview}",
                )
            )

        if self._handle_raw_xml_payload(self.raw_requestline):
            return

        if not self.parse_request():
            if self._is_expected_vlt_client():
                self.server.output_session.note_parse_error(
                    request_size=0,
                    client_address=client_address,
                    error_text=f"HTTP request parse failed: {request_line_preview}",
                )
            return

        method_name = "do_" + self.command
        if not hasattr(self, method_name):
            self.send_error(501, f"Unsupported method ({self.command!r})")
            return

        getattr(self, method_name)()
        try:
            self.wfile.flush()
        except OSError:
            pass

    def do_POST(self) -> None:
        request_size = int(self.headers.get("Content-Length", "0"))
        request_body = self.rfile.read(request_size)
        client_address = format_client_address(self.client_address)
        client_ip = extract_client_ip(self.client_address)
        is_self_probe = is_tce_self_probe_path(self.path)
        request_recorded = False
        try:
            operation_name, values = parse_soap_body_operation(request_body)
            if is_self_probe:
                self.server.output_session.note_self_probe_passed()
                if getattr(self.server, "debug_enabled", False):
                    print(
                        format_log_line(
                            "DEBUG",
                            f"TCE callback self-probe from={client_address} operation={operation_name}",
                        )
                    )
            else:
                self.server.output_session.note_http_request(
                    request_size=request_size,
                    client_address=client_address,
                )
                request_recorded = True
                self.server.output_session.note_parsed_callback(operation_name, values)
                if getattr(self.server, "debug_enabled", False):
                    print(
                        format_log_line(
                            "DEBUG",
                            f"TCE callback from={client_address} operation={operation_name} "
                            f"size={request_size} values={values}",
                        )
                    )
                self._warn_if_unexpected_vlt_client(
                    client_ip=client_ip,
                    operation_name=operation_name,
                )
            emission = format_tce_callback_emission(
                operation_name,
                values,
                client_ip=client_ip,
                expected_vlt_ip=getattr(self.server, "expected_vlt_ip", None),
                tce_number=getattr(
                    self.server,
                    "tce_number",
                    DEFAULT_TCE_TCE_NUMBER,
                ),
            )
            if not emission.is_supported:
                if not is_self_probe:
                    self.server.output_session.note_unhandled_callback(operation_name)
                if getattr(self.server, "debug_enabled", False):
                    print(
                        format_log_line(
                            "DEBUG",
                            f"Unhandled TCE callback operation={operation_name} values={values}",
                        )
                    )
            elif not is_self_probe:
                self.server.output_session.emit_callback_emission(emission)
            response_body = build_technology_soap_response(operation_name)
            self.send_response(200)
        except Exception as exc:
            if not is_self_probe and not request_recorded:
                self.server.output_session.note_http_request(
                    request_size=request_size,
                    client_address=client_address,
                )
                request_recorded = True
            if not is_self_probe:
                self.server.output_session.note_parse_error(
                    request_size=request_size,
                    client_address=client_address,
                    error_text=str(exc),
                )
            if getattr(self.server, "debug_enabled", False):
                print(
                    format_log_line(
                        "DEBUG",
                        f"TCE callback error from={client_address} size={request_size}: {exc}",
                    )
                )
            response_body = build_soap_fault(str(exc))
            self.send_response(500)

        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)


class TCECallbackServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        output_session: TCEOutputSession,
        expected_vlt_ip: Optional[str] = None,
        tce_number: int = DEFAULT_TCE_TCE_NUMBER,
        debug: bool = False,
    ) -> None:
        try:
            self.httpd = ThreadingHTTPServer((host, port), TCECallbackRequestHandler)
        except OSError as exc:
            raise RuntimeError(
                f"TCE callback listener failed to bind to {host}:{port}: {exc}"
            ) from exc
        self.httpd.daemon_threads = True
        self.httpd.output_session = output_session
        self.httpd.debug_enabled = debug
        self.httpd.expected_vlt_ip = expected_vlt_ip
        self.httpd.tce_number = tce_number
        self.httpd.bound_host = host
        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            name="TCECallbackServer",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self._thread.join(timeout=2.0)

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def host(self) -> str:
        return str(self.httpd.server_address[0])


class TCEListener:
    def __init__(self, config: TCEEndpointConfig) -> None:
        self.config = config
        self.output_session = TCEOutputSession(
            emit_diagnostic_payloads=config.debug
        )

    def _log_debug(self, message: str) -> None:
        if self.config.debug:
            print(format_log_line("DEBUG", message))

    def _emit_startup_terminal_line(self, payload: str) -> None:
        if self.config.debug:
            emit_tce_terminal_line(payload)

    def _emit_registration_attempt_line(self, requested_endpoint: str) -> None:
        self._emit_startup_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            f"{self.config.tce_label}:1 runCheckwinFunction: "
            f"settceendpoint({requested_endpoint})"
        )

    def _emit_startup_context_line(self, callback_endpoint: str) -> None:
        self._emit_startup_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            f"TCE startup config={self.config.config_path or '<none>'} "
            f"vlt_service={self.config.vlt_service_url} "
            f"callback={callback_endpoint} "
            f"state_poll_ms={self.config.state_poll_interval_ms} "
            f"python={sys.executable} "
            f"python_version={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )

    def _emit_configured_callback_ip_warning(
        self,
        resolution: TCECallbackResolution,
        callback_endpoint: str,
    ) -> None:
        configured_callback_ip = resolution.configured_callback_ip
        if resolution.source != "override" or not configured_callback_ip:
            return
        if configured_callback_ip == resolution.callback_ip:
            return
        print(
            format_log_line(
                "WARNING",
                "Using TCE IP override instead of configured callback IP "
                f"config={self.config.config_path or '<none>'} "
                f"configured_callback_ip={configured_callback_ip} "
                f"override_callback_ip={resolution.callback_ip} "
                f"callback={callback_endpoint} "
                f"vlt_service={self.config.vlt_service_url}",
            )
        )

    def _emit_listener_bound_line(self, bound_host: str, bound_port: int) -> None:
        self._emit_startup_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            f"TCE callback listener bound to: {bound_host}:{bound_port}"
        )

    def _emit_self_probe_success_line(self, callback_endpoint: str) -> None:
        self._emit_startup_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            f"TCE callback self-probe succeeded: {callback_endpoint}{TCE_SELF_PROBE_PATH}"
        )

    def _emit_startup_lines(
        self,
        registration: TCERegistrationResult,
        *,
        emit_attempt_line: bool = True,
    ) -> None:
        if emit_attempt_line:
            self._emit_registration_attempt_line(registration.requested_endpoint)
        self._emit_startup_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            f"VLT's TCE Endpoint updated to: {registration.confirmed_endpoint}"
        )
        self._emit_startup_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            "settceendpoint success, status: 1"
        )

    def _emit_no_callback_warning(self, registration: TCERegistrationResult) -> None:
        diagnostics = self.output_session.diagnostics_snapshot()
        if diagnostics.last_pulled_state is None:
            last_pulled_state_text = "<none>"
        elif diagnostics.last_pulled_state == "":
            last_pulled_state_text = "<blank>"
        else:
            last_pulled_state_text = diagnostics.last_pulled_state
        callback_variables_text = format_callback_variable_counts_preview(
            diagnostics.callback_variable_counts
        )
        blank_state_sources: list[str] = []
        if diagnostics.blank_state_seen_from_callback:
            blank_state_sources.append("callback_blank_state")
        elif (
            diagnostics.callback_delivery_count > 0
            and diagnostics.non_state_callback_seen
            and not diagnostics.state_payload_seen
        ):
            blank_state_sources.append("callback_non_state")
        if diagnostics.blank_state_seen_from_qa:
            blank_state_sources.append("qa_blank")
        blank_state_sources_text = ",".join(blank_state_sources) or "<none>"
        if diagnostics.callback_delivery_count == 0:
            warning_summary = (
                f"No TCE callbacks received after {DEFAULT_TCE_NO_CALLBACK_WARNING_SECONDS:g} seconds. "
            )
        else:
            warning_summary = (
                f"No usable STATE payload emitted after {DEFAULT_TCE_NO_CALLBACK_WARNING_SECONDS:g} seconds. "
            )
        emit_tce_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            f"{warning_summary}"
            f"config={self.config.config_path or '<none>'} "
            f"vlt_service={self.config.vlt_service_url} "
            f"callback={registration.confirmed_endpoint}"
        )
        emit_tce_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            "TCE callback diagnostics: "
            f"listener_bound={int(diagnostics.listener_bind_succeeded)} "
            f"self_probe_passed={int(diagnostics.self_probe_passed)} "
            f"tcp_connections={diagnostics.tcp_connection_count} "
            f"callback_deliveries={diagnostics.callback_delivery_count} "
            f"http_requests={diagnostics.http_request_count} "
            f"parsed_callbacks={diagnostics.parsed_callback_count} "
            f"parse_errors={diagnostics.parse_error_count} "
            f"unhandled_callbacks={diagnostics.unhandled_callback_count} "
            f"state_pull_attempts={diagnostics.state_pull_attempt_count} "
            f"state_pull_successes={diagnostics.state_pull_success_count} "
            f"state_pull_live_states={diagnostics.state_pull_live_state_count} "
            f"state_pull_errors={diagnostics.state_pull_error_count} "
            f"state_poller_started={int(diagnostics.state_poller_started)} "
            f"state_poller_running={int(diagnostics.state_poller_running)} "
            f"state_poller_failures={diagnostics.state_poller_failure_count} "
            f"state_payload_seen={int(diagnostics.state_payload_seen)} "
            f"last_client={diagnostics.last_client_address or '<none>'} "
            f"last_operation={diagnostics.last_operation_name or '<none>'} "
            f"last_callback_var={diagnostics.last_callback_updatevar_name or '<none>'} "
            f"last_callback_val={diagnostics.last_callback_updatevar_value_preview or '<none>'} "
            f"callback_variables={callback_variables_text} "
            f"last_request_line={diagnostics.last_request_line or '<none>'} "
            f"last_state_pull_context={diagnostics.last_state_pull_context or '<none>'} "
            f"last_state_pull_op={diagnostics.last_state_pull_operation_name or '<none>'} "
            f"last_state_pull_fields={diagnostics.last_state_pull_fields_preview or '<none>'} "
            f"last_pulled_state={last_pulled_state_text} "
            f"last_state_pull_error={diagnostics.last_state_pull_error or '<none>'} "
            f"last_state_poller_error={diagnostics.last_state_poller_error or '<none>'} "
            f"blank_state_sources={blank_state_sources_text}"
        )
        if diagnostics.state_payload_seen:
            return
        if (
            diagnostics.state_poller_failure_count > 0
            and diagnostics.state_pull_live_state_count == 0
        ):
            if diagnostics.callback_delivery_count > 0 and diagnostics.non_state_callback_seen:
                prefix = (
                    "TCE callback traffic is active, but only non-state callback variables were seen "
                    f"({callback_variables_text}); "
                )
            elif diagnostics.callback_delivery_count > 0:
                prefix = "TCE callback traffic is active; "
            else:
                prefix = "No inbound HTTP callback attempts reached the listener, and "
            emit_tce_terminal_line(
                f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                f"{prefix}"
                "standalone QA SOAP STATE poller stopped unexpectedly before any usable STATE was emitted. "
                f"state_poller_failures={diagnostics.state_poller_failure_count} "
                f"last_state_pull_context={diagnostics.last_state_pull_context or '<none>'} "
                f"last_error={diagnostics.last_state_poller_error or '<none>'}"
            )
            return
        if diagnostics.parse_error_count > 0 and diagnostics.parsed_callback_count == 0:
            emit_tce_terminal_line(
                f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                "Inbound callback traffic reached the listener, but SOAP parsing failed. "
                f"parse_errors={diagnostics.parse_error_count} "
                f"last_error={diagnostics.last_parse_error or '<none>'}"
            )
            return
        if diagnostics.unhandled_callback_count > 0 and not self.output_session.callback_seen:
            emit_tce_terminal_line(
                f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                "Inbound callbacks were received, but no supported gameplay events were emitted. "
                f"parsed_callbacks={diagnostics.parsed_callback_count} "
                f"unhandled_callbacks={diagnostics.unhandled_callback_count} "
                f"last_operation={diagnostics.last_operation_name or '<none>'}"
            )
            return
        if diagnostics.callback_delivery_count > 0:
            if (
                diagnostics.state_pull_success_count > 0
                and diagnostics.state_pull_live_state_count == 0
            ):
                if diagnostics.blank_state_seen_from_callback:
                    callback_context = (
                        "TCE callback traffic is active, but state-like callback variables were blank"
                    )
                elif diagnostics.non_state_callback_seen:
                    callback_context = (
                        "TCE callback traffic is active, but only non-state callback variables were seen "
                        f"({callback_variables_text})"
                    )
                else:
                    callback_context = "TCE callback traffic is active"
                emit_tce_terminal_line(
                    f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                    f"{callback_context}; QA SOAP state pull remained blank. "
                    f"state_pull_successes={diagnostics.state_pull_success_count} "
                    f"last_state_pull_op={diagnostics.last_state_pull_operation_name or '<none>'} "
                    f"last_state_pull_fields={diagnostics.last_state_pull_fields_preview or '<none>'} "
                    f"last_pulled_state={last_pulled_state_text}"
                )
                return
            if (
                diagnostics.state_pull_error_count > 0
                and diagnostics.state_pull_live_state_count == 0
            ):
                if diagnostics.non_state_callback_seen:
                    callback_context = (
                        "TCE callback traffic is active, but only non-state callback variables were seen "
                        f"({callback_variables_text})"
                    )
                else:
                    callback_context = "TCE callback traffic is active"
                emit_tce_terminal_line(
                    f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                    f"{callback_context}; QA SOAP state pull failed before any usable STATE was emitted. "
                    f"state_pull_errors={diagnostics.state_pull_error_count} "
                    f"last_state_pull_op={diagnostics.last_state_pull_operation_name or '<none>'} "
                    f"last_error={diagnostics.last_state_pull_error or '<none>'}"
                )
                return
            if diagnostics.blank_state_seen_from_callback:
                emit_tce_terminal_line(
                    f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                    "TCE callback traffic included state-like variables, but their state value was blank. "
                    f"last_callback_var={diagnostics.last_callback_updatevar_name or '<none>'} "
                    f"last_callback_val={diagnostics.last_callback_updatevar_value_preview or '<none>'}"
                )
                return
            if diagnostics.non_state_callback_seen:
                emit_tce_terminal_line(
                    f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                    "TCE callback traffic is active, but only non-state callback variables were seen. "
                    f"callback_variables={callback_variables_text} "
                    f"last_operation={diagnostics.last_operation_name or '<none>'}"
                )
                return
            emit_tce_terminal_line(
                f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                "TCE callback traffic is active, but no usable STATE payload has been emitted yet. "
                f"parsed_callbacks={diagnostics.parsed_callback_count} "
                f"last_operation={diagnostics.last_operation_name or '<none>'}"
            )
            return
        if (
            diagnostics.tcp_connection_count > 0
            and diagnostics.http_request_count == 0
            and diagnostics.callback_delivery_count == 0
        ):
            emit_tce_terminal_line(
                f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                "TCP callback connections reached the listener, but no HTTP POST was parsed. "
                f"tcp_connections={diagnostics.tcp_connection_count} "
                f"last_request_line={diagnostics.last_request_line or '<none>'}"
            )
            return
        if diagnostics.callback_delivery_count == 0:
            if (
                diagnostics.state_pull_success_count > 0
                and diagnostics.state_pull_live_state_count == 0
            ):
                emit_tce_terminal_line(
                    f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                    "QA SOAP state pull reached the VLT, but no non-empty game state was returned. "
                    f"state_pull_successes={diagnostics.state_pull_success_count} "
                    f"last_pulled_state={last_pulled_state_text}"
                )
                return
            if (
                diagnostics.state_pull_error_count > 0
                and diagnostics.state_pull_success_count == 0
            ):
                emit_tce_terminal_line(
                    f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                    "No inbound HTTP callback attempts reached the listener, and QA SOAP state pull failed. "
                    f"state_pull_errors={diagnostics.state_pull_error_count} "
                    f"last_error={diagnostics.last_state_pull_error or '<none>'}"
                )
                return
            emit_tce_terminal_line(
                f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
                "No inbound HTTP callback attempts reached the listener. "
                f"Verify VLT reachability to {registration.confirmed_endpoint}, local firewall rules, "
                "and that the callback IP is bound on this machine."
            )
            return
        emit_tce_terminal_line(
            f"{self.config.tce_number}|{DEFAULT_TCE_MESSAGE_LEVEL_INFO}|"
            "Callback traffic reached the listener, but no usable STATE payload was emitted. "
            f"parsed_callbacks={diagnostics.parsed_callback_count} "
            f"last_operation={diagnostics.last_operation_name or '<none>'}"
        )

    def _maybe_emit_no_callback_warning(
        self,
        registration: TCERegistrationResult,
        registration_time: float,
        warning_emitted: bool,
        *,
        now_monotonic: Optional[float] = None,
    ) -> bool:
        if warning_emitted or self.output_session.state_payload_seen:
            return warning_emitted
        now_value = time.monotonic() if now_monotonic is None else now_monotonic
        if now_value - registration_time < DEFAULT_TCE_NO_CALLBACK_WARNING_SECONDS:
            return warning_emitted
        self._emit_no_callback_warning(registration)
        return True

    def run(self) -> int:
        callback_resolution = resolve_tce_callback_resolution(self.config)
        callback_ip = callback_resolution.callback_ip
        requested_endpoint = f"{callback_ip}:{self.config.tce_port}"
        self._log_debug(
            f"TCE config path={self.config.config_path or '<none>'} "
            f"vlt_service={self.config.vlt_service_url} "
            f"callback_source={callback_resolution.source} "
            f"tce_ip={callback_ip} "
            f"tce_port={self.config.tce_port} configured_callback_ip="
            f"{self.config.configured_callback_ip or '<none>'}"
        )
        self._emit_startup_context_line(requested_endpoint)
        self._emit_configured_callback_ip_warning(callback_resolution, requested_endpoint)
        callback_server: Optional[TCECallbackServer] = None
        state_poller: Optional[TCEStatePoller] = None
        try:
            callback_server = TCECallbackServer(
                host=callback_ip,
                port=self.config.tce_port,
                output_session=self.output_session,
                expected_vlt_ip=self.config.vlt_ip,
                tce_number=self.config.tce_number,
                debug=self.config.debug,
            )
            callback_server.start()
            self.output_session.note_listener_bound()
            self._emit_listener_bound_line(callback_server.host, callback_server.port)
            run_tce_callback_self_probe(
                callback_ip,
                callback_server.port,
                debug=self.config.debug,
            )
            self._emit_self_probe_success_line(
                f"{callback_ip}:{callback_server.port}"
            )
            self._log_debug(
                f"Preflight VLT SOAP service "
                f"{format_tce_registration_context(self.config.vlt_service_url, requested_endpoint)} "
                f"timeout={DEFAULT_TCE_SERVICE_PREFLIGHT_TIMEOUT_SECONDS:.1f}s"
            )
            probe_vlt_soap_service(self.config.vlt_service_url, requested_endpoint)
            self._emit_registration_attempt_line(requested_endpoint)
            registration = register_tce_endpoint(
                self.config.vlt_service_url,
                requested_endpoint,
                debug=self.config.debug,
            )
            self._emit_startup_lines(registration, emit_attempt_line=False)
            state_poller = TCEStatePoller(
                self.config,
                self.output_session,
                poll_interval_seconds=self.config.state_poll_interval_ms / 1000.0,
                debug_log=self._log_debug,
            )
            state_poller.start()
            registration_time = time.monotonic()
            warning_emitted = False
            while not self.output_session.stop_event.wait(0.1):
                warning_emitted = self._maybe_emit_no_callback_warning(
                    registration,
                    registration_time,
                    warning_emitted,
                )
                pass
            return 0
        finally:
            if state_poller is not None:
                state_poller.stop()
            if callback_server is not None:
                callback_server.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Listen for TCE endpoint callbacks or live SAS protocol traffic."
        )
    )
    parser.add_argument(
        "--mode",
        choices=[MODE_TCE, MODE_SAS],
        default=MODE_TCE,
        help="listener mode: tce starts the SOAP callback listener, sas uses the serial SAS listener",
    )
    parser.add_argument(
        "--config-file",
        help=(
            "TCE mode config source: XML or CFG file. If omitted, the listener looks for "
            "TCE/bin/Debug/XML/TCE-Checkwin_*.xml and TCE/bin/Debug/TCE-Checkwin.cfg"
        ),
    )
    parser.add_argument(
        "--vlt-ip",
        help="TCE mode override for the VLT SOAP host IP",
    )
    parser.add_argument(
        "--vlt-port",
        type=parse_tcp_port,
        default=None,
        help="TCE mode override for the VLT SOAP port",
    )
    parser.add_argument(
        "--tce-ip",
        help="TCE mode override for the local callback IP; otherwise auto-detected at startup",
    )
    parser.add_argument(
        "--tce-port",
        type=parse_tcp_port,
        default=None,
        help="TCE mode override for the local callback port",
    )
    parser.add_argument(
        "--state-poll-ms",
        type=parse_positive_int,
        default=DEFAULT_TCE_STATE_POLL_INTERVAL_MS,
        help=(
            "TCE mode game-state poll interval in milliseconds "
            f"(default: {DEFAULT_TCE_STATE_POLL_INTERVAL_MS})"
        ),
    )
    parser.add_argument(
        "--port",
        default=DEFAULT_PORT,
        help=f"serial port name for --mode sas (default: {DEFAULT_PORT}), for example COM3",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="list the serial ports Windows currently detects and exit (SAS mode helper)",
    )
    parser.add_argument(
        "--address",
        type=parse_address,
        default=DEFAULT_ADDRESS,
        help="SAS address to poll (default: 1)",
    )
    parser.add_argument(
        "--poll-ms",
        type=parse_positive_int,
        default=None,
        help=(
            "override the poll interval in milliseconds; otherwise the listener uses "
            "the selected poll profile"
        ),
    )
    parser.add_argument(
        "--poll-profile",
        choices=[POLL_PROFILE_AUTO, POLL_PROFILE_SAFE, POLL_PROFILE_FAST],
        default=POLL_PROFILE_AUTO,
        help=(
            "polling profile: auto starts at 200 ms and promotes to 40 ms after valid "
            "RTE activation, safe stays at 200 ms, fast forces 40 ms"
        ),
    )
    parser.add_argument(
        "--protocol-mode",
        choices=[PROTOCOL_MODE_AUTO, PROTOCOL_MODE_LEGACY, PROTOCOL_MODE_RTE],
        default=PROTOCOL_MODE_AUTO,
        help=(
            "protocol handling mode: auto tolerates legacy startup then promotes to RTE, "
            "legacy stays on one-byte exceptions, rte expects full event frames"
        ),
    )
    parser.add_argument(
        "--enable-rte",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="enable or skip real-time event mode setup (default: enabled)",
    )
    parser.add_argument(
        "--startup-sync",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_STARTUP_SYNC,
        help="send an initial legacy startup sync byte 0x80 (default: enabled)",
    )
    parser.add_argument(
        "--echo-mode",
        choices=[ECHO_MODE_AUTO, ECHO_MODE_ON, ECHO_MODE_OFF],
        default=ECHO_MODE_AUTO,
        help="echo filtering mode for leading self-echo bytes (default: auto)",
    )
    parser.add_argument(
        "--legacy-byte-events",
        action="store_true",
        help=(
            "treat lone one-byte legacy exception codes as events "
            "(default: off; require full RTE event frames)"
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print setup frames and raw non-event traffic, including ignored lone legacy bytes",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print detailed diagnostic logs for port open, polls, TX, RX, and frame classification",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=parse_non_negative_int,
        default=5,
        help="print a waiting message every N seconds until traffic arrives (default: 5, 0 disables)",
    )
    parser.add_argument(
        "--no-response-warning-seconds",
        type=parse_non_negative_int,
        default=10,
        help="print escalated warning diagnostics every N seconds until traffic arrives (default: 10, 0 disables)",
    )
    parser.add_argument(
        "--wakeup-delay-ms",
        type=parse_non_negative_float,
        default=DEFAULT_WAKEUP_DELAY_MS,
        help="delay between wakeup/address byte and payload bytes in milliseconds (default: 1)",
    )
    parser.add_argument(
        "--read-timeout-ms",
        type=parse_non_negative_int,
        default=DEFAULT_READ_TIMEOUT_MS,
        help="poll receive window before the first byte arrives in milliseconds (default: 20)",
    )
    parser.add_argument(
        "--inter-byte-timeout-ms",
        type=parse_non_negative_int,
        default=DEFAULT_INTER_BYTE_TIMEOUT_MS,
        help="additional receive window after each byte in milliseconds (default: 5)",
    )
    parser.add_argument(
        "--runtime-info",
        action="store_true",
        help="print interpreter and pyserial import details before running",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run parser and CRC self-tests without serial hardware",
    )
    return parser


def build_config(args: argparse.Namespace) -> ListenerConfig:
    poll_ms_overridden = args.poll_ms is not None
    if poll_ms_overridden:
        poll_ms = args.poll_ms
    elif args.poll_profile == POLL_PROFILE_FAST:
        poll_ms = FAST_POLL_MS
    else:
        poll_ms = SAFE_POLL_MS

    enable_rte = args.enable_rte
    if args.protocol_mode == PROTOCOL_MODE_LEGACY:
        enable_rte = False
    elif args.protocol_mode == PROTOCOL_MODE_RTE:
        enable_rte = True

    return ListenerConfig(
        port=args.port,
        address=args.address,
        poll_ms=poll_ms,
        poll_profile=args.poll_profile,
        protocol_mode=args.protocol_mode,
        enable_rte=enable_rte,
        startup_sync=args.startup_sync,
        echo_mode=args.echo_mode,
        verbose=args.verbose,
        debug=args.debug,
        heartbeat_seconds=args.heartbeat_seconds,
        no_response_warning_seconds=args.no_response_warning_seconds,
        wakeup_delay_ms=args.wakeup_delay_ms,
        read_timeout_ms=args.read_timeout_ms,
        inter_byte_timeout_ms=args.inter_byte_timeout_ms,
        accept_legacy_single_byte_events=(
            args.legacy_byte_events or args.protocol_mode == PROTOCOL_MODE_LEGACY
        ),
        poll_ms_overridden=poll_ms_overridden,
    )


def run_self_test() -> int:
    import io
    import os
    import re
    import tempfile
    from contextlib import redirect_stdout

    checks = 0

    def make_config(**overrides: object) -> ListenerConfig:
        base: dict[str, object] = {
            "port": "COM_TEST",
            "address": DEFAULT_ADDRESS,
            "poll_ms": SAFE_POLL_MS,
            "poll_profile": POLL_PROFILE_AUTO,
            "protocol_mode": PROTOCOL_MODE_AUTO,
            "enable_rte": True,
            "startup_sync": True,
            "echo_mode": ECHO_MODE_AUTO,
            "verbose": False,
            "debug": False,
            "heartbeat_seconds": 5,
            "no_response_warning_seconds": 10,
            "wakeup_delay_ms": DEFAULT_WAKEUP_DELAY_MS,
            "read_timeout_ms": DEFAULT_READ_TIMEOUT_MS,
            "inter_byte_timeout_ms": DEFAULT_INTER_BYTE_TIMEOUT_MS,
            "accept_legacy_single_byte_events": False,
            "poll_ms_overridden": False,
        }
        base.update(overrides)
        return ListenerConfig(**base)

    parser = build_parser()
    default_args = parser.parse_args([])
    assert default_args.mode == MODE_TCE
    assert default_args.state_poll_ms == DEFAULT_TCE_STATE_POLL_INTERVAL_MS
    default_sas_args = parser.parse_args(["--mode", "sas"])
    default_config = build_config(default_sas_args)
    assert default_config.poll_ms == SAFE_POLL_MS
    assert default_config.poll_profile == POLL_PROFILE_AUTO
    assert default_config.protocol_mode == PROTOCOL_MODE_AUTO
    assert default_config.enable_rte is True
    assert default_config.poll_ms_overridden is False
    assert default_config.read_timeout_ms == DEFAULT_READ_TIMEOUT_MS
    assert default_config.inter_byte_timeout_ms == DEFAULT_INTER_BYTE_TIMEOUT_MS

    legacy_args = parser.parse_args(["--mode", "sas", "--protocol-mode", "legacy"])
    legacy_config = build_config(legacy_args)
    assert legacy_config.enable_rte is False
    assert legacy_config.accept_legacy_single_byte_events is True
    assert legacy_config.poll_ms == SAFE_POLL_MS

    fast_args = parser.parse_args(
        ["--mode", "sas", "--protocol-mode", "rte", "--poll-profile", "fast"]
    )
    fast_config = build_config(fast_args)
    assert fast_config.enable_rte is True
    assert fast_config.poll_ms == FAST_POLL_MS

    override_args = parser.parse_args(
        ["--mode", "sas", "--poll-profile", "fast", "--poll-ms", "125"]
    )
    override_config = build_config(override_args)
    assert override_config.poll_ms == 125
    assert override_config.poll_ms_overridden is True
    checks += 1

    assert compute_crc_ccitt(bytes([0x01, 0x0E, 0x01])) == 0xD145
    assert compute_crc_ccitt(bytes([0x01, 0x0E, 0x00])) == 0xC0CC
    checks += 1

    rte_event_8f_frame = append_crc(bytes([0x01, 0xFF, 0x8F]))
    rte_event_4f_frame = append_crc(
        bytes([0x01, 0xFF, 0x4F, 0x00, 0x01, 0x00, 0x05, 0x00, 0x12])
    )
    rte_event_97_frame = append_crc(bytes([0x01, 0xFF, 0x97]))
    rte_event_3d_frame = append_crc(bytes([0x01, 0xFF, 0x3D]))
    unknown_command_frame = append_crc(bytes([0x01, 0x73, 0x01, 0x00]))

    rte_event_4f = parse_event(rte_event_4f_frame)
    rte_event_97 = parse_event(rte_event_97_frame)
    legacy_event_6c = parse_event(
        bytes([0x6C]),
        accept_legacy_single_byte_events=True,
    )
    assert rte_event_4f is not None and rte_event_4f.valid_crc is True
    assert rte_event_4f.name == "SAS event 0x4F"
    assert rte_event_4f.address == 0x01
    assert rte_event_4f.transport_kind == "rte_event"
    assert rte_event_97 is not None and rte_event_97.valid_crc is True
    assert rte_event_97.name == "SAS event 0x97"
    assert get_event_frame_length(rte_event_8f_frame) == GENERIC_RTE_EVENT_FRAME_LENGTH
    assert get_event_frame_length(rte_event_4f_frame) == 11
    assert parse_event(bytes([0x6C])) is None
    assert legacy_event_6c is not None
    assert legacy_event_6c.legacy is True
    assert legacy_event_6c.name == "SAS legacy event 0x6C"
    checks += 1

    extraction = extract_protocol_units(
        bytes([0x81]) + rte_event_4f_frame + bytes([0x6C]),
        address=1,
        echo_mode=ECHO_MODE_AUTO,
        expected_echoes=[bytes([0x81])],
    )
    assert extraction.dropped_echo_bytes == bytes([0x81])
    assert tuple(unit.status for unit in extraction.units) == ("frame", "frame")
    assert extraction.units[0].frame == rte_event_4f_frame
    assert extraction.units[1].frame == bytes([0x6C])
    assert extraction.remaining == b""

    unknown_extraction = extract_protocol_units(
        unknown_command_frame,
        address=1,
        echo_mode=ECHO_MODE_AUTO,
    )
    assert tuple(unit.status for unit in unknown_extraction.units) == ("unknown",)
    assert unknown_extraction.units[0].frame == unknown_command_frame

    mixed_extraction = extract_protocol_units(
        unknown_command_frame + rte_event_4f_frame + rte_event_3d_frame,
        address=1,
        echo_mode=ECHO_MODE_AUTO,
    )
    assert tuple(unit.status for unit in mixed_extraction.units) == (
        "unknown",
        "frame",
        "frame",
    )
    checks += 1

    printer = SASEventPrinter()
    decoded_printer = SASDecodedMessagePrinter()
    assert printer.format_transport("RX<=", bytes([0x6C])) == "RX<= 6C"
    assert "$4F = SAS event 0x4F" in printer.format_event(rte_event_4f)
    assert "repeat_count" not in printer.format_compact_event_with_raw(rte_event_4f)
    assert format_hex(rte_event_4f_frame) in printer.format_compact_event_with_raw(
        rte_event_4f
    )
    assert "RX<= 01" in decoded_printer.format_ack_with_raw(0x01, bytes([0x01]))
    assert "RX<= 81" in decoded_printer.format_nack_with_raw(0x01, bytes([0x81]))
    checks += 1

    strict_event_listener = SASListener(make_config())
    strict_event_output = io.StringIO()
    with redirect_stdout(strict_event_output):
        event_result = strict_event_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=rte_event_4f_frame),
            now=101.0,
        )
    assert event_result == "event"
    assert "DECODED | " not in strict_event_output.getvalue()
    assert "$4F = SAS event 0x4F" in strict_event_output.getvalue()
    assert f"RX<= {format_hex(rte_event_4f_frame)}" in strict_event_output.getvalue()
    assert strict_event_listener.runtime_event_count == 1
    checks += 1

    duplicate_listener = SASListener(make_config())
    duplicate_output = io.StringIO()
    with redirect_stdout(duplicate_output):
        first_result = duplicate_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=rte_event_4f_frame),
            now=102.0,
        )
        duplicate_result = duplicate_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=rte_event_4f_frame),
            now=103.0,
        )
    assert first_result == "event"
    assert duplicate_result == "event"
    duplicate_lines = [
        line
        for line in duplicate_output.getvalue().splitlines()
        if "$4F = SAS event 0x4F" in line
    ]
    assert len(duplicate_lines) == 1
    assert all("repeat_count" not in line for line in duplicate_lines)
    assert duplicate_listener.repeated_event_count == 1
    assert duplicate_listener.runtime_event_count == 2
    checks += 1

    debug_duplicate_listener = SASListener(make_config(debug=True))
    debug_duplicate_output = io.StringIO()
    with redirect_stdout(debug_duplicate_output):
        first_debug_result = debug_duplicate_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=rte_event_4f_frame),
            now=103.5,
        )
        second_debug_result = debug_duplicate_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=rte_event_4f_frame),
            now=104.0,
        )
    assert first_debug_result == "event"
    assert second_debug_result == "event"
    debug_lines = debug_duplicate_output.getvalue().splitlines()
    assert sum("$4F = SAS event 0x4F" in line for line in debug_lines) == 1
    assert sum(f"RX<= {format_hex(rte_event_4f_frame)}" in line for line in debug_lines) == 1
    assert debug_duplicate_listener.repeated_event_count == 1
    checks += 1

    legacy_duplicate_listener = SASListener(
        make_config(
            protocol_mode=PROTOCOL_MODE_LEGACY,
            enable_rte=False,
            accept_legacy_single_byte_events=True,
        )
    )
    legacy_output = io.StringIO()
    with redirect_stdout(legacy_output):
        first_legacy_result = legacy_duplicate_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=bytes([0x6C])),
            now=104.0,
        )
        second_legacy_result = legacy_duplicate_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=bytes([0x6C])),
            now=105.0,
        )
    assert first_legacy_result == "event"
    assert second_legacy_result == "event"
    legacy_lines = [
        line
        for line in legacy_output.getvalue().splitlines()
        if "$6C = SAS legacy event 0x6C" in line
    ]
    assert len(legacy_lines) == 1
    assert all("legacy=1" not in line for line in legacy_lines)
    assert all("repeat_count" not in line for line in legacy_lines)
    checks += 1

    mode_listener = SASListener(make_config())
    assert mode_listener.current_poll_ms == SAFE_POLL_MS
    assert mode_listener._allow_legacy_byte_events() is True
    with redirect_stdout(io.StringIO()):
        mode_listener._mark_rte_mode_active(reason="self-test")
    assert mode_listener.rte_mode_active is True
    assert mode_listener.current_poll_ms == FAST_POLL_MS
    assert mode_listener._allow_legacy_byte_events() is False

    mismatch_listener = SASListener(
        make_config(
            protocol_mode=PROTOCOL_MODE_RTE,
            poll_profile=POLL_PROFILE_FAST,
            poll_ms=FAST_POLL_MS,
        )
    )
    mismatch_output = io.StringIO()
    with redirect_stdout(mismatch_output):
        mismatch_result = mismatch_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=bytes([0x6C])),
            now=105.5,
        )
    assert mismatch_result == "event"
    assert "legacy exception received while RTE mode is active" in mismatch_output.getvalue()
    checks += 1

    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    class FakeConnection:
        def __init__(
            self,
            clock: FakeClock,
            read_events: Optional[list[tuple[float, bytes]]] = None,
        ) -> None:
            self.clock = clock
            self.port = "COM_TEST"
            self.baudrate = DEFAULT_BAUDRATE
            self.bytesize = SERIAL_BYTESIZE
            self.parity = SERIAL_PARITY_SPACE
            self.stopbits = SERIAL_STOPBITS_TWO
            self.dtr = False
            self.rts = False
            self.is_open = True
            self.writes: list[tuple[str, bytes]] = []
            self.read_events = list(read_events or [])
            self.input_resets = 0
            self.output_resets = 0

        @property
        def in_waiting(self) -> int:
            if not self.read_events:
                return 0
            available_at, payload = self.read_events[0]
            if self.clock.monotonic() < available_at:
                return 0
            return len(payload)

        def write(self, payload: bytes) -> int:
            self.writes.append((self.parity, bytes(payload)))
            return len(payload)

        def read(self, size: int) -> bytes:
            if not self.read_events:
                return b""
            available_at, payload = self.read_events[0]
            if self.clock.monotonic() < available_at:
                return b""
            chunk = payload[:size]
            remaining = payload[size:]
            if remaining:
                self.read_events[0] = (available_at, remaining)
            else:
                self.read_events.pop(0)
            return chunk

        def flush(self) -> None:
            return None

        def reset_input_buffer(self) -> None:
            self.input_resets += 1

        def reset_output_buffer(self) -> None:
            self.output_resets += 1

        def close(self) -> None:
            self.is_open = False

    def make_host(
        connection: FakeConnection,
        config: Optional[ListenerConfig] = None,
        *,
        clock: Optional[FakeClock] = None,
    ) -> SASSerialHost:
        host = object.__new__(SASSerialHost)
        host.config = config or make_config()
        host.debug_log = None
        host.read_timeout_seconds = 0.05
        host.inter_byte_timeout_seconds = 0.02
        host.wakeup_delay_seconds = 0.0
        local_clock = clock or FakeClock()
        host._monotonic = local_clock.monotonic
        host._sleep = local_clock.sleep
        host.connection = connection
        return host

    write_clock = FakeClock()
    host = make_host(FakeConnection(write_clock), clock=write_clock)
    host._enable_control_lines()
    host._reset_buffers()
    assert host.connection.dtr is True
    assert host.connection.rts is True
    assert host.connection.input_resets == 1
    assert host.connection.output_resets == 1
    assert host.write_frame(bytes([STARTUP_SYNC_BYTE]), context="TX STARTUP_SYNC") == 1
    assert host.connection.writes == [(SERIAL_PARITY_MARK, bytes([STARTUP_SYNC_BYTE]))]
    host.connection.writes.clear()
    assert host.write_frame(bytes([0x01, 0x0E, 0x01]), context="TX ENABLE_RTE") == 3
    assert host.connection.writes == [
        (SERIAL_PARITY_MARK, bytes([0x01])),
        (SERIAL_PARITY_SPACE, bytes([0x0E, 0x01])),
    ]
    checks += 1

    first_byte_timeout_clock = FakeClock()
    first_byte_timeout_host = make_host(
        FakeConnection(first_byte_timeout_clock, read_events=[(0.021, bytes([0x01]))]),
        clock=first_byte_timeout_clock,
    )
    first_byte_timeout_host.read_timeout_seconds = 0.02
    first_byte_timeout_host.inter_byte_timeout_seconds = 0.005
    assert first_byte_timeout_host.read_available("RX FIRST_BYTE_TIMEOUT") == b""

    first_byte_success_clock = FakeClock()
    first_byte_success_host = make_host(
        FakeConnection(first_byte_success_clock, read_events=[(0.019, bytes([0x01]))]),
        clock=first_byte_success_clock,
    )
    first_byte_success_host.read_timeout_seconds = 0.02
    first_byte_success_host.inter_byte_timeout_seconds = 0.005
    assert first_byte_success_host.read_available("RX FIRST_BYTE_SUCCESS") == bytes([0x01])
    checks += 1

    compact_transport_listener = SASListener(make_config())
    compact_transport_output = io.StringIO()
    with redirect_stdout(compact_transport_output):
        compact_transport_listener._emit_transport_line(
            "TX>=",
            bytes([0x81]),
        )
        compact_unknown_result = compact_transport_listener._handle_protocol_unit(
            ProtocolUnit(status="unknown", frame=bytes([0x99, 0x00])),
            now=109.5,
        )
    assert compact_unknown_result == "unknown"
    compact_transport_lines = compact_transport_output.getvalue().splitlines()
    assert compact_transport_lines == ["RX<= 99 00"]
    checks += 1

    combined_read_listener = SASListener(make_config())
    combined_read_clock = FakeClock()
    combined_read_host = make_host(
        FakeConnection(
            combined_read_clock,
            read_events=[(0.0, unknown_command_frame + rte_event_4f_frame)],
        ),
        config=combined_read_listener.config,
        clock=combined_read_clock,
    )
    combined_read_output = io.StringIO()
    with redirect_stdout(combined_read_output):
        combined_read_result = combined_read_listener._drain_receive_units(
            combined_read_host,
            context="RX COMBINED",
        )
        for unit in combined_read_result.units:
            combined_read_listener._handle_protocol_unit(
                unit,
                now=110.0,
                host=combined_read_host,
            )
    assert tuple(unit.status for unit in combined_read_result.units) == (
        "unknown",
        "frame",
    )
    combined_lines = [
        line
        for line in combined_read_output.getvalue().splitlines()
        if "RX<=" in line
    ]
    assert len(combined_lines) == 2
    assert combined_lines[0] == f"RX<= {format_hex(unknown_command_frame)}"
    assert "$4F = SAS event 0x4F" in combined_lines[1]
    assert f"RX<= {format_hex(rte_event_4f_frame)}" in combined_lines[1]
    checks += 1

    partial_read_listener = SASListener(make_config())
    partial_read_clock = FakeClock()
    partial_read_host = make_host(
        FakeConnection(partial_read_clock, read_events=[(0.0, bytes([0x01, 0xFF]))]),
        config=partial_read_listener.config,
        clock=partial_read_clock,
    )
    partial_read_output = io.StringIO()
    with redirect_stdout(partial_read_output):
        partial_read_result = partial_read_listener._drain_receive_units(
            partial_read_host,
            context="RX PARTIAL",
        )
    assert partial_read_result.units == ()
    assert partial_read_result.buffered_bytes == bytes([0x01, 0xFF])
    assert partial_read_output.getvalue().splitlines() == ["RX<= 01 FF"]

    heartbeat_output = io.StringIO()
    heartbeat_listener = SASListener(make_config())
    with redirect_stdout(heartbeat_output):
        heartbeat_event_result = heartbeat_listener._handle_protocol_unit(
            ProtocolUnit(status="frame", frame=rte_event_3d_frame),
            now=113.0,
        )
        heartbeat_listener._print_heartbeat()
        heartbeat_listener._print_no_response_warning(12.5)
    assert heartbeat_event_result == "event"
    assert "$3D = SAS event 0x3D" in heartbeat_output.getvalue()
    assert "Status | Waiting for SAS traffic" in heartbeat_output.getvalue()
    assert "No SAS protocol activity received" in heartbeat_output.getvalue()
    checks += 1

    def replay_log(path: str) -> tuple[int, int]:
        unit_count = 0
        event_count = 0
        rx_line_count = 0
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped.startswith("RX<="):
                    continue
                payload_text = stripped[4:].strip()
                if not payload_text:
                    continue
                rx_line_count += 1
                raw = bytes.fromhex(payload_text)
                extraction = extract_protocol_units(
                    raw,
                    address=DEFAULT_ADDRESS,
                    echo_mode=ECHO_MODE_AUTO,
                    accept_legacy_single_byte_events=True,
                )
                unit_count += len(extraction.units)
                for unit in extraction.units:
                    if unit.status in {"frame", "unknown_rte"}:
                        event = parse_event(
                            unit.frame,
                            accept_legacy_single_byte_events=True,
                        )
                        if event is not None:
                            event_count += 1
        if rx_line_count > 0:
            assert unit_count > 0
        return unit_count, event_count

    replay_paths = [
        os.path.join(
            os.path.dirname(__file__),
            "Gaming-Architecture.SasTest-main",
            "Gaming-Architecture.SasTest-main",
            "not_used",
            name,
        )
        for name in ("SasReport.txt", "8ferror.txt", "doubunreg.txt", "eftlog.txt")
    ]
    replay_results = [replay_log(path) for path in replay_paths]
    assert replay_results[0][0] > 0
    assert replay_results[1][0] > 0
    assert replay_results[2][0] > 0
    checks += 1

    fake_ports = (
        SerialPortInfo(
            device="COM1",
            description="USB Serial Port (COM1)",
            hwid="USB VID:PID=0403:6001 SER=TEST",
        ),
        SerialPortInfo(
            device="COM3",
            description="Intel(R) Active Management Technology - SOL (COM3)",
            hwid="PCI\\VEN_TEST",
        ),
    )
    listing = format_serial_port_listing(fake_ports)
    assert "Detected serial ports:" in listing
    assert "COM1: USB Serial Port (COM1)" in listing
    open_error_message = build_serial_open_error_message(
        "COM1",
        PermissionError(13, "Access is denied.", None, 5),
        fake_ports,
    )
    assert "Could not open serial port COM1." in open_error_message
    assert "Close any other serial tools using it" in open_error_message
    checks += 1

    with tempfile.TemporaryDirectory() as temp_dir:
        xml_path = os.path.join(temp_dir, "TCE-Checkwin_4.xml")
        cfg_path = os.path.join(temp_dir, "TCE-Checkwin.cfg")
        with open(xml_path, "w", encoding="utf-8") as handle:
            handle.write(
                """<?xml version="1.0" encoding="utf-8"?>
<CheckwinConfig>
  <VLT>
    <SOAP_LISTEN_IP>10.25.30.40</SOAP_LISTEN_IP>
    <SOAP_LISTEN_PORT>18082</SOAP_LISTEN_PORT>
  </VLT>
  <TCE>
    <SOAP_LISTEN_IP>10.25.30.50</SOAP_LISTEN_IP>
    <SOAP_LISTEN_PORT>19091</SOAP_LISTEN_PORT>
  </TCE>
</CheckwinConfig>
"""
            )
        with open(cfg_path, "w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    [
                        "IP ADDRESS=10.55.60.70",
                        "IP PORT=18082",
                        "SOAP LISTEN IP=10.55.60.80",
                        "SOAP LISTEN PORT=19092",
                    ]
                )
            )

        xml_tce_config = build_tce_config(parser.parse_args(["--config-file", xml_path]))
        assert xml_tce_config.vlt_ip == "10.25.30.40"
        assert xml_tce_config.vlt_port == 18082
        assert xml_tce_config.tce_port == 19091
        assert (
            xml_tce_config.state_poll_interval_ms
            == DEFAULT_TCE_STATE_POLL_INTERVAL_MS
        )
        assert xml_tce_config.tce_number == 4
        assert xml_tce_config.tce_label == "TCE4"
        assert xml_tce_config.configured_callback_ip == "10.25.30.50"

        cfg_tce_config = build_tce_config(parser.parse_args(["--config-file", cfg_path]))
        assert cfg_tce_config.vlt_ip == "10.55.60.70"
        assert cfg_tce_config.vlt_port == 18082
        assert cfg_tce_config.tce_port == 19092
        assert (
            cfg_tce_config.state_poll_interval_ms
            == DEFAULT_TCE_STATE_POLL_INTERVAL_MS
        )
        assert cfg_tce_config.tce_number == DEFAULT_TCE_TCE_NUMBER
        assert cfg_tce_config.tce_label == DEFAULT_TCE_LABEL
        assert cfg_tce_config.configured_callback_ip == "10.55.60.80"

        duplicate_xml_path = os.path.join(temp_dir, "TCE-Checkwin_1.xml_1.xml")
        with open(duplicate_xml_path, "w", encoding="utf-8") as handle:
            handle.write("<CheckwinConfig />\n")
        valid_xml_paths = list_valid_tce_config_xml_paths(
            os.path.join(temp_dir, "TCE-Checkwin_*.xml")
        )
        assert valid_xml_paths == [os.path.normpath(xml_path)]

        override_tce_config = build_tce_config(
            parser.parse_args(
                [
                    "--config-file",
                    xml_path,
                    "--vlt-ip",
                    "192.0.2.10",
                    "--vlt-port",
                    "18100",
                    "--tce-ip",
                    "192.0.2.20",
                    "--tce-port",
                    "19100",
                    "--state-poll-ms",
                    "40",
                ]
            )
        )
        assert override_tce_config.vlt_ip == "192.0.2.10"
        assert override_tce_config.vlt_port == 18100
        assert override_tce_config.tce_port == 19100
        assert override_tce_config.state_poll_interval_ms == 40
        assert override_tce_config.tce_number == 4
        assert override_tce_config.tce_ip_override == "192.0.2.20"

        original_default_tce_config_glob = DEFAULT_TCE_CONFIG_GLOB
        original_default_tce_primary_config_path = DEFAULT_TCE_PRIMARY_CONFIG_PATH
        original_default_tce_cfg_path = DEFAULT_TCE_CFG_PATH
        try:
            globals()["DEFAULT_TCE_CONFIG_GLOB"] = os.path.join(
                temp_dir,
                "TCE-Checkwin_*.xml",
            )
            globals()["DEFAULT_TCE_PRIMARY_CONFIG_PATH"] = xml_path
            globals()["DEFAULT_TCE_CFG_PATH"] = cfg_path
            default_tce_config = build_tce_config(parser.parse_args([]))
            assert default_tce_config.vlt_port == 18082
            assert default_tce_config.tce_port == 19091
            assert (
                default_tce_config.state_poll_interval_ms
                == DEFAULT_TCE_STATE_POLL_INTERVAL_MS
            )
            assert default_tce_config.tce_number == 4
            assert default_tce_config.config_path == os.path.normpath(xml_path)
        finally:
            globals()["DEFAULT_TCE_CONFIG_GLOB"] = original_default_tce_config_glob
            globals()["DEFAULT_TCE_PRIMARY_CONFIG_PATH"] = (
                original_default_tce_primary_config_path
            )
            globals()["DEFAULT_TCE_CFG_PATH"] = original_default_tce_cfg_path
        checks += 1

    class FakeRouteSocket:
        def __init__(self) -> None:
            self.connected_to: Optional[tuple[str, int]] = None

        def __enter__(self) -> "FakeRouteSocket":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def close(self) -> None:
            return None

        def connect(self, endpoint: tuple[str, int]) -> None:
            self.connected_to = endpoint

        def getsockname(self) -> tuple[str, int]:
            return ("172.22.51.102", 19091)

    class FakeFailingSocket(FakeRouteSocket):
        def connect(self, endpoint: tuple[str, int]) -> None:
            raise OSError("route lookup unavailable")

    route_ip = detect_local_ipv4(
        "10.25.30.40",
        18082,
        socket_factory=lambda *args, **kwargs: FakeRouteSocket(),
        hostname_lookup=lambda *args, **kwargs: [],
    )
    assert route_ip == "172.22.51.102"

    fallback_ip = detect_local_ipv4(
        "10.25.30.40",
        18082,
        socket_factory=lambda *args, **kwargs: FakeFailingSocket(),
        hostname_lookup=lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.88.77.66", 0)),
        ],
    )
    assert fallback_ip == "10.88.77.66"
    assert detect_local_ipv4("10.25.30.40", 18082, override="192.0.2.44") == "192.0.2.44"
    checks += 1

    detector_calls: list[tuple[str, int]] = []

    def fake_local_ip_detector(vlt_ip: str, vlt_port: int) -> str:
        detector_calls.append((vlt_ip, vlt_port))
        return "172.22.51.102"

    assert (
        resolve_tce_callback_ip(
            override_tce_config,
            local_ip_detector=fake_local_ip_detector,
        )
        == "192.0.2.20"
    )
    assert detector_calls == []

    xml_callback_resolution = resolve_tce_callback_resolution(
        xml_tce_config,
        local_ip_detector=fake_local_ip_detector,
    )
    assert xml_callback_resolution.callback_ip == "10.25.30.50"
    assert xml_callback_resolution.source == "configured"
    assert xml_callback_resolution.configured_callback_ip == "10.25.30.50"
    assert detector_calls == []

    detector_calls.clear()
    auto_detect_tce_config = TCEEndpointConfig(
        vlt_ip="10.25.30.40",
        vlt_port=18082,
        tce_port=19091,
    )
    assert (
        resolve_tce_callback_ip(
            auto_detect_tce_config,
            local_ip_detector=fake_local_ip_detector,
        )
        == "172.22.51.102"
    )
    assert detector_calls == [("10.25.30.40", 18082)]

    detector_calls.clear()
    try:
        resolve_tce_callback_ip(
            TCEEndpointConfig(
                vlt_ip="10.25.30.40",
                vlt_port=18082,
                tce_port=19091,
                configured_callback_ip="not-an-ip",
            ),
            local_ip_detector=fake_local_ip_detector,
        )
        raise AssertionError("Expected configured TCE callback IP validation failure")
    except RuntimeError as exc:
        assert "Invalid configured TCE callback IP" in str(exc)
    assert detector_calls == []
    checks += 1

    class FakePreflightConnection:
        def __init__(self, endpoint: tuple[str, int], timeout: float) -> None:
            self.endpoint = endpoint
            self.timeout = timeout
            self.closed = False

        def close(self) -> None:
            self.closed = True

    created_preflight_connections: list[FakePreflightConnection] = []

    def fake_preflight_connection_factory(
        endpoint: tuple[str, int],
        timeout: float,
    ) -> FakePreflightConnection:
        connection = FakePreflightConnection(endpoint, timeout)
        created_preflight_connections.append(connection)
        return connection

    probe_vlt_soap_service(
        "http://10.25.30.40:18082",
        "172.22.51.102:19091",
        connection_factory=fake_preflight_connection_factory,
    )
    assert len(created_preflight_connections) == 1
    assert created_preflight_connections[0].endpoint == ("10.25.30.40", 18082)
    assert (
        created_preflight_connections[0].timeout
        == DEFAULT_TCE_SERVICE_PREFLIGHT_TIMEOUT_SECONDS
    )
    assert created_preflight_connections[0].closed is True

    def fake_refusing_preflight_connection_factory(
        endpoint: tuple[str, int],
        timeout: float,
    ) -> socket.socket:
        raise OSError(
            "[WinError 10061] No connection could be made because the target machine actively refused it"
        )

    try:
        probe_vlt_soap_service(
            "http://10.25.30.40:18082",
            "172.22.51.102:19091",
            connection_factory=fake_refusing_preflight_connection_factory,
        )
        raise AssertionError("Expected VLT SOAP preflight failure")
    except RuntimeError as exc:
        error_text = str(exc)
        assert error_text.startswith("VLT SOAP preflight failed:")
        assert "service=http://10.25.30.40:18082" in error_text
        assert "callback=172.22.51.102:19091" in error_text
        assert "error=[WinError 10061]" in error_text

    def fake_timeout_preflight_connection_factory(
        endpoint: tuple[str, int],
        timeout: float,
    ) -> socket.socket:
        raise TimeoutError("timed out")

    try:
        probe_vlt_soap_service(
            "http://10.25.30.40:18082",
            "172.22.51.102:19091",
            connection_factory=fake_timeout_preflight_connection_factory,
        )
        raise AssertionError("Expected VLT SOAP preflight timeout")
    except RuntimeError as exc:
        error_text = str(exc)
        assert error_text.startswith("VLT SOAP preflight failed:")
        assert "service=http://10.25.30.40:18082" in error_text
        assert "callback=172.22.51.102:19091" in error_text
        assert "error=timed out" in error_text
    checks += 1

    assert derive_tce_label_from_path(r"C:\temp\TCE-Checkwin_4.xml") == "TCE4"
    assert derive_tce_number_from_path(r"C:\temp\TCE-Checkwin_4.xml") == 4
    assert derive_tce_label_from_path(r"C:\temp\TCE-Checkwin_1.xml_1.xml") == DEFAULT_TCE_LABEL
    assert (
        derive_tce_number_from_path(r"C:\temp\TCE-Checkwin_1.xml_1.xml")
        == DEFAULT_TCE_TCE_NUMBER
    )
    assert (
        format_tce_callback_emission(
            "UpdateVar",
            {"name": "STATE", "valstr": IDLE_STATE_VALUE},
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload=build_idle_terminal_payload(4),
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "UpdateVar",
            {
                "name": "GAMESTATE",
                "valstr": "MarketWrapperReelStateMachine::WithdrawWager",
            },
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload=build_tce_state_payload(
                4,
                "MarketWrapperReelStateMachine::WithdrawWager",
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "UpdateVar",
            {
                "name": "m-State",
                "valstr": "MarketWrapperReelStateMachine::PlayGame",
            },
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload=build_tce_state_payload(
                4,
                "MarketWrapperReelStateMachine::PlayGame",
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "BankTransition",
            {"amount": "117585"},
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload=build_tce_variable_payload(4, "BANK", "117585"),
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "StateTransition",
            {"name": "MarketWrapperReelStateMachine::WithdrawWager"},
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload=build_tce_state_payload(
                4,
                "MarketWrapperReelStateMachine::WithdrawWager",
            ),
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "BetTransition",
            {"amount": "25"},
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload=build_tce_variable_payload(4, "BET", "25"),
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "PaylineTransition",
            {"paylines": "20"},
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload="4|3|Number Of Lines: 20",
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "UpdateWinAmount",
            {"amount": "500"},
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload=build_tce_variable_payload(4, "WIN", "500"),
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "UpdateGameInfo",
            {
                "gameid": "7",
                "gamename": "Lucky Game",
                "creditsize": "5",
                "percentage": "92.4",
            },
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload="4|3||ID|7|GameName|Lucky Game|CreditSz|5|Percent|92.4",
            counts_as_live_activity=True,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "MessageQueueCount",
            {"queuecount": "3"},
            client_ip="10.25.30.40",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload="0|3|SOAP PUSH Event - Update Message Queue (Count) (3)",
            counts_as_live_activity=False,
            is_supported=True,
        )
    )
    assert (
        format_tce_callback_emission(
            "UpdateVar",
            {"name": "STATE", "valstr": "WithdrawWager"},
            client_ip="10.25.30.41",
            expected_vlt_ip="10.25.30.40",
            tce_number=4,
        )
        == TCECallbackEmission(
            payload=None,
            counts_as_live_activity=False,
            is_supported=True,
        )
    )
    assert is_idle_tce_terminal_payload(IDLE_TERMINAL_PAYLOAD) is True
    assert is_idle_tce_terminal_payload(build_idle_terminal_payload(4)) is True
    assert (
        extract_tce_state_from_payload(
            "4|3||STATE|MarketWrapperReelStateMachine::WithdrawWager"
        )
        == "MarketWrapperReelStateMachine::WithdrawWager"
    )
    assert extract_tce_state_from_payload("4|3|BET: 25") is None
    checks += 1

    output_session = TCEOutputSession()
    output_buffer = io.StringIO()
    with redirect_stdout(output_buffer):
        output_session.emit_live_payload(
            build_tce_state_payload(
                1,
                "MarketWrapperReelStateMachine::WithdrawWager",
            )
        )
        assert output_session.stop_event.is_set() is False
        output_session.emit_live_payload(
            build_tce_state_payload(
                1,
                "MarketWrapperReelStateMachine::WithdrawWager",
            )
        )
        output_session.emit_live_payload(IDLE_TERMINAL_PAYLOAD)
    printed_lines = [line for line in output_buffer.getvalue().splitlines() if line.strip()]
    assert len(printed_lines) == 2
    assert printed_lines[-1].endswith(f"---> {IDLE_TERMINAL_PAYLOAD}")
    assert output_session.stop_event.is_set() is True
    checks += 1

    debug_output_session = TCEOutputSession(emit_diagnostic_payloads=True)
    debug_output_buffer = io.StringIO()
    with redirect_stdout(debug_output_buffer):
        debug_output_session.emit_live_payload(
            build_tce_state_payload(
                1,
                "MarketWrapperReelStateMachine::WithdrawWager",
            )
        )
    debug_output_lines = [
        line for line in debug_output_buffer.getvalue().splitlines() if line.strip()
    ]
    assert len(debug_output_lines) == 1
    assert debug_output_lines[0].endswith(
        "---> 1|3||STATE|MarketWrapperReelStateMachine::WithdrawWager"
    )
    checks += 1

    idle_first_session = TCEOutputSession()
    idle_first_buffer = io.StringIO()
    with redirect_stdout(idle_first_buffer):
        idle_first_session.emit_live_payload(IDLE_TERMINAL_PAYLOAD)
    idle_first_lines = [
        line for line in idle_first_buffer.getvalue().splitlines() if line.strip()
    ]
    assert len(idle_first_lines) == 1
    assert idle_first_lines[0].endswith(f"---> {IDLE_TERMINAL_PAYLOAD}")
    assert idle_first_session.stop_event.is_set() is False
    checks += 1

    repeated_bank_session = TCEOutputSession()
    repeated_bank_buffer = io.StringIO()
    repeated_bank_emission = TCECallbackEmission(
        payload=build_tce_variable_payload(1, "BANK", "117585"),
        counts_as_live_activity=True,
        is_supported=True,
    )
    with redirect_stdout(repeated_bank_buffer):
        repeated_bank_session.emit_callback_emission(repeated_bank_emission)
        repeated_bank_session.emit_callback_emission(repeated_bank_emission)
    repeated_bank_lines = [
        line for line in repeated_bank_buffer.getvalue().splitlines() if line.strip()
    ]
    assert len(repeated_bank_lines) == 1
    assert repeated_bank_lines[0].endswith("---> 1|3||BANK|117585")
    checks += 1

    startup_listener = TCEListener(xml_tce_config)
    debug_xml_tce_config = TCEEndpointConfig(
        **{**vars(xml_tce_config), "debug": True}
    )
    debug_startup_listener = TCEListener(debug_xml_tce_config)
    startup_context_buffer = io.StringIO()
    with redirect_stdout(startup_context_buffer):
        startup_listener._emit_startup_context_line("10.25.30.50:19091")
    assert startup_context_buffer.getvalue().strip() == ""
    debug_startup_context_buffer = io.StringIO()
    with redirect_stdout(debug_startup_context_buffer):
        debug_startup_listener._emit_startup_context_line("10.25.30.50:19091")
    startup_context_lines = [
        line
        for line in debug_startup_context_buffer.getvalue().splitlines()
        if line.strip()
    ]
    assert len(startup_context_lines) == 1
    assert f"config={xml_tce_config.config_path}" in startup_context_lines[0]
    assert "vlt_service=http://10.25.30.40:18082" in startup_context_lines[0]
    assert "callback=10.25.30.50:19091" in startup_context_lines[0]
    assert f"python={sys.executable}" in startup_context_lines[0]
    assert (
        f"python_version={sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        in startup_context_lines[0]
    )
    checks += 1

    callback_warning_buffer = io.StringIO()
    with redirect_stdout(callback_warning_buffer):
        TCEListener(override_tce_config)._emit_configured_callback_ip_warning(
            resolve_tce_callback_resolution(override_tce_config),
            "192.0.2.20:19100",
        )
    callback_warning_lines = [
        line for line in callback_warning_buffer.getvalue().splitlines() if line.strip()
    ]
    assert len(callback_warning_lines) == 1
    assert "WARNING" in callback_warning_lines[0]
    assert f"config={xml_tce_config.config_path}" in callback_warning_lines[0]
    assert "configured_callback_ip=10.25.30.50" in callback_warning_lines[0]
    assert "override_callback_ip=192.0.2.20" in callback_warning_lines[0]
    assert "callback=192.0.2.20:19100" in callback_warning_lines[0]
    assert "vlt_service=http://192.0.2.10:18100" in callback_warning_lines[0]
    checks += 1

    startup_buffer = io.StringIO()
    with redirect_stdout(startup_buffer):
        startup_listener._emit_startup_lines(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    assert startup_buffer.getvalue().strip() == ""
    debug_startup_buffer = io.StringIO()
    with redirect_stdout(debug_startup_buffer):
        debug_startup_listener._emit_startup_lines(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    startup_lines = [line for line in startup_buffer.getvalue().splitlines() if line.strip()]
    startup_lines = [
        line for line in debug_startup_buffer.getvalue().splitlines() if line.strip()
    ]
    assert len(startup_lines) == 3
    assert re.match(
        r"^\d{4} \d{2} \d{2} \d{2}:\d{2}:\d{2} ---> 4\|0\|TCE4:1 runCheckwinFunction: settceendpoint\(10\.25\.30\.50:19091\)$",
        startup_lines[0],
    )
    assert startup_lines[1].endswith(
        "---> 4|0|VLT's TCE Endpoint updated to: 10.25.30.50:19091"
    )
    assert startup_lines[2].endswith("---> 4|0|settceendpoint success, status: 1")
    checks += 1

    attempt_buffer = io.StringIO()
    with redirect_stdout(attempt_buffer):
        startup_listener._emit_registration_attempt_line("10.25.30.50:19091")
    assert attempt_buffer.getvalue().strip() == ""
    debug_attempt_buffer = io.StringIO()
    with redirect_stdout(debug_attempt_buffer):
        debug_startup_listener._emit_registration_attempt_line("10.25.30.50:19091")
    attempt_lines = [
        line for line in debug_attempt_buffer.getvalue().splitlines() if line.strip()
    ]
    assert len(attempt_lines) == 1
    assert re.match(
        r"^\d{4} \d{2} \d{2} \d{2}:\d{2}:\d{2} ---> 4\|0\|TCE4:1 runCheckwinFunction: settceendpoint\(10\.25\.30\.50:19091\)$",
        attempt_lines[0],
    )
    checks += 1

    original_detect_local_ipv4 = detect_local_ipv4
    original_probe_vlt_soap_service = probe_vlt_soap_service
    original_tce_callback_server = TCECallbackServer
    original_run_tce_callback_self_probe = run_tce_callback_self_probe
    original_register_tce_endpoint = register_tce_endpoint
    try:
        fail_fast_state: dict[str, int] = {}

        def reset_fail_fast_state() -> None:
            fail_fast_state.clear()
            fail_fast_state.update(
                {
                    "callback_server_inits": 0,
                    "callback_server_starts": 0,
                    "self_probe_calls": 0,
                    "register_calls": 0,
                    "detect_local_ipv4_calls": 0,
                }
            )

        def fake_detect_local_ipv4(*args: object, **kwargs: object) -> str:
            fail_fast_state["detect_local_ipv4_calls"] += 1
            return "172.22.51.102"

        def fake_probe_vlt_soap_service(
            service_url: str,
            callback_endpoint: str,
            **kwargs: object,
        ) -> None:
            raise RuntimeError(
                "VLT SOAP preflight failed: "
                f"service={service_url} callback={callback_endpoint} "
                "error=[WinError 10061] No connection could be made because the target machine actively refused it"
            )

        class FakeTCECallbackServer:
            def __init__(self, **kwargs: object) -> None:
                fail_fast_state["callback_server_inits"] += 1
                self._host = str(kwargs.get("host", "10.25.30.50"))
                self._port = int(kwargs.get("port", 19091))

            def start(self) -> None:
                fail_fast_state["callback_server_starts"] += 1

            def stop(self) -> None:
                return None

            @property
            def host(self) -> str:
                return self._host

            @property
            def port(self) -> int:
                return self._port

        def fake_run_tce_callback_self_probe(*args: object, **kwargs: object) -> None:
            fail_fast_state["self_probe_calls"] += 1
            return None

        def fake_register_tce_endpoint(*args: object, **kwargs: object) -> TCERegistrationResult:
            fail_fast_state["register_calls"] += 1
            return TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )

        globals()["detect_local_ipv4"] = fake_detect_local_ipv4
        globals()["probe_vlt_soap_service"] = fake_probe_vlt_soap_service
        globals()["TCECallbackServer"] = FakeTCECallbackServer
        globals()["run_tce_callback_self_probe"] = fake_run_tce_callback_self_probe
        globals()["register_tce_endpoint"] = fake_register_tce_endpoint

        reset_fail_fast_state()
        fail_fast_output = io.StringIO()
        with redirect_stdout(fail_fast_output):
            try:
                TCEListener(xml_tce_config).run()
                raise AssertionError("Expected VLT SOAP preflight failure")
            except RuntimeError as exc:
                error_text = str(exc)
                assert error_text.startswith("VLT SOAP preflight failed:")
                assert "service=http://10.25.30.40:18082" in error_text
                assert "callback=10.25.30.50:19091" in error_text
                assert "error=[WinError 10061]" in error_text

        fail_fast_lines = [line for line in fail_fast_output.getvalue().splitlines() if line.strip()]
        assert fail_fast_lines == []
        assert fail_fast_state["callback_server_inits"] == 1
        assert fail_fast_state["callback_server_starts"] == 1
        assert fail_fast_state["self_probe_calls"] == 1
        assert fail_fast_state["register_calls"] == 0
        assert fail_fast_state["detect_local_ipv4_calls"] == 0

        reset_fail_fast_state()
        fail_fast_debug_output = io.StringIO()
        with redirect_stdout(fail_fast_debug_output):
            try:
                TCEListener(debug_xml_tce_config).run()
                raise AssertionError("Expected VLT SOAP preflight failure")
            except RuntimeError as exc:
                error_text = str(exc)
                assert error_text.startswith("VLT SOAP preflight failed:")
                assert "service=http://10.25.30.40:18082" in error_text
                assert "callback=10.25.30.50:19091" in error_text
                assert "error=[WinError 10061]" in error_text

        fail_fast_debug_lines = [
            line for line in fail_fast_debug_output.getvalue().splitlines() if line.strip()
        ]
        assert any("TCE startup config=" in line for line in fail_fast_debug_lines)
        assert any(
            "vlt_service=http://10.25.30.40:18082" in line
            for line in fail_fast_debug_lines
        )
        assert any("callback=10.25.30.50:19091" in line for line in fail_fast_debug_lines)
        assert any(
            "TCE callback listener bound to: 10.25.30.50:19091" in line
            for line in fail_fast_debug_lines
        )
        assert any(
            "TCE callback self-probe succeeded: 10.25.30.50:19091/__self_probe__"
            in line
            for line in fail_fast_debug_lines
        )
        assert fail_fast_state["callback_server_inits"] == 1
        assert fail_fast_state["callback_server_starts"] == 1
        assert fail_fast_state["self_probe_calls"] == 1
        assert fail_fast_state["register_calls"] == 0
        assert fail_fast_state["detect_local_ipv4_calls"] == 0
    finally:
        globals()["detect_local_ipv4"] = original_detect_local_ipv4
        globals()["probe_vlt_soap_service"] = original_probe_vlt_soap_service
        globals()["TCECallbackServer"] = original_tce_callback_server
        globals()["run_tce_callback_self_probe"] = original_run_tce_callback_self_probe
        globals()["register_tce_endpoint"] = original_register_tce_endpoint
    checks += 1

    original_send_soap_request = send_soap_request
    try:
        def fake_send_soap_request(*args: object, **kwargs: object) -> bytes:
            raise RuntimeError(
                "SOAP SetTCEEndPoint to http://172.22.51.108:18082 failed: "
                "[WinError 10061] No connection could be made because the target machine actively refused it"
            ) from OSError(
                "[WinError 10061] No connection could be made because the target machine actively refused it"
            )

        globals()["send_soap_request"] = fake_send_soap_request
        try:
            call_qatesting_set_tce_endpoint(
                "http://172.22.51.108:18082",
                "172.22.51.102:19091",
            )
            raise AssertionError("Expected SetTCEEndPoint failure")
        except RuntimeError as exc:
            error_text = str(exc)
            assert error_text.startswith("SOAP SetTCEEndPoint failed:")
            assert "service=http://172.22.51.108:18082" in error_text
            assert "callback=172.22.51.102:19091" in error_text
            assert "error=[WinError 10061]" in error_text
            assert "to http://172.22.51.108:18082 failed:" not in error_text
    finally:
        globals()["send_soap_request"] = original_send_soap_request
    checks += 1

    original_call_qatesting_set_tce_endpoint = call_qatesting_set_tce_endpoint
    original_call_qatesting_get_tce_endpoint = call_qatesting_get_tce_endpoint
    try:
        attempted_callbacks: list[str] = []

        def fake_call_qatesting_set_tce_endpoint(
            service_url: str,
            endpoint_value: str,
            *,
            debug: bool = False,
        ) -> int:
            attempted_callbacks.append(endpoint_value)
            return 1

        def fake_call_qatesting_get_tce_endpoint(
            service_url: str,
            *,
            debug: bool = False,
        ) -> tuple[str, int]:
            if attempted_callbacks[-1] == "172.22.51.102:19091":
                return ("not-yet-registered", 1)
            return ("http://172.22.51.102:19091", 1)

        globals()["call_qatesting_set_tce_endpoint"] = fake_call_qatesting_set_tce_endpoint
        globals()["call_qatesting_get_tce_endpoint"] = fake_call_qatesting_get_tce_endpoint

        registration_buffer = io.StringIO()
        with redirect_stdout(registration_buffer):
            registration_result = register_tce_endpoint(
                "http://172.22.51.108:18082",
                "172.22.51.102:19091",
                debug=True,
            )
        registration_lines = [
            line for line in registration_buffer.getvalue().splitlines() if line.strip()
        ]
        assert registration_result.requested_endpoint == "http://172.22.51.102:19091"
        assert registration_result.confirmed_endpoint == "http://172.22.51.102:19091"
        assert attempted_callbacks == [
            "172.22.51.102:19091",
            "http://172.22.51.102:19091",
        ]
        assert any(
            "Registering TCE endpoint service=http://172.22.51.108:18082 callback=172.22.51.102:19091"
            in line
            for line in registration_lines
        )
        assert any(
            "Registering TCE endpoint service=http://172.22.51.108:18082 callback=http://172.22.51.102:19091"
            in line
            for line in registration_lines
        )
        assert any(
            "Endpoint registration service=http://172.22.51.108:18082 callback=172.22.51.102:19091 "
            "set_status=1 get_status=1 confirmed=not-yet-registered"
            in line
            for line in registration_lines
        )
        assert any(
            "Endpoint registration service=http://172.22.51.108:18082 callback=http://172.22.51.102:19091 "
            "set_status=1 get_status=1 confirmed=http://172.22.51.102:19091"
            in line
            for line in registration_lines
        )
    finally:
        globals()["call_qatesting_set_tce_endpoint"] = original_call_qatesting_set_tce_endpoint
        globals()["call_qatesting_get_tce_endpoint"] = original_call_qatesting_get_tce_endpoint
    checks += 1

    original_send_soap_request = send_soap_request
    try:
        def fake_send_soap_request_for_state_helpers(
            service_url: str,
            envelope: bytes,
            *,
            debug: bool = False,
            operation_name: Optional[str] = None,
        ) -> bytes:
            del service_url, envelope, debug
            if operation_name == "GetGameState":
                return build_soap_envelope(
                    "QATesting",
                    QATESTING_NAMESPACE,
                    "GetGameStateResponse",
                    (
                        "<state>MarketWrapperReelStateMachine::WithdrawWager</state>"
                        "<status>0</status>"
                    ),
                )
            if operation_name == "InitTestClient":
                return build_soap_envelope(
                    "QATesting",
                    QATESTING_NAMESPACE,
                    "QAGameInfo",
                    (
                        f"<m-State>{IDLE_STATE_VALUE}</m-State>"
                        "<m-Status>0</m-Status>"
                    ),
                )
            raise AssertionError(f"Unexpected operation_name: {operation_name}")

        globals()["send_soap_request"] = fake_send_soap_request_for_state_helpers
        assert call_qatesting_get_game_state("http://172.22.51.108:18082") == (
            "MarketWrapperReelStateMachine::WithdrawWager",
            0,
        )
        assert call_qatesting_init_test_client_state(
            "http://172.22.51.108:18082"
        ) == (IDLE_STATE_VALUE, 0)
    finally:
        globals()["send_soap_request"] = original_send_soap_request
    checks += 1

    try:
        def fake_send_soap_request_for_get_game_state_qagameinfo(
            service_url: str,
            envelope: bytes,
            *,
            debug: bool = False,
            operation_name: Optional[str] = None,
        ) -> bytes:
            del service_url, envelope, debug
            if operation_name == "GetGameState":
                return build_soap_envelope(
                    "QATesting",
                    QATESTING_NAMESPACE,
                    "QAGameInfo",
                    (
                        "<m-State>MarketWrapperReelStateMachine::PlayGame</m-State>"
                        "<m-Status>0</m-Status>"
                    ),
                )
            raise AssertionError(f"Unexpected operation_name: {operation_name}")

        globals()["send_soap_request"] = fake_send_soap_request_for_get_game_state_qagameinfo
        assert call_qatesting_get_game_state("http://172.22.51.108:18082") == (
            "MarketWrapperReelStateMachine::PlayGame",
            0,
        )
    finally:
        globals()["send_soap_request"] = original_send_soap_request
    checks += 1

    try:
        def fake_send_soap_request_for_nested_get_game_state(
            service_url: str,
            envelope: bytes,
            *,
            debug: bool = False,
            operation_name: Optional[str] = None,
        ) -> bytes:
            del service_url, envelope, debug
            if operation_name == "GetGameState":
                return build_soap_envelope(
                    "QATesting",
                    QATESTING_NAMESPACE,
                    "GetGameStateResponse",
                    (
                        "<GetGameStateResult>"
                        "<state>MarketWrapperReelStateMachine::SpinReels</state>"
                        "<status>0</status>"
                        "</GetGameStateResult>"
                    ),
                )
            raise AssertionError(f"Unexpected operation_name: {operation_name}")

        globals()["send_soap_request"] = fake_send_soap_request_for_nested_get_game_state
        assert call_qatesting_get_game_state("http://172.22.51.108:18082") == (
            "MarketWrapperReelStateMachine::SpinReels",
            0,
        )
        nested_get_game_state_result = call_qatesting_get_game_state_result(
            "http://172.22.51.108:18082"
        )
        assert nested_get_game_state_result.fields_preview == (
            "wrapper=GetGameStateResult "
            "state=MarketWrapperReelStateMachine::SpinReels, status=0"
        )
    finally:
        globals()["send_soap_request"] = original_send_soap_request
    checks += 1

    try:
        def fake_send_soap_request_for_nested_init_test_client(
            service_url: str,
            envelope: bytes,
            *,
            debug: bool = False,
            operation_name: Optional[str] = None,
        ) -> bytes:
            del service_url, envelope, debug
            if operation_name == "InitTestClient":
                return build_soap_envelope(
                    "QATesting",
                    QATESTING_NAMESPACE,
                    "InitTestClientResponse",
                    (
                        "<InitTestClientResult>"
                        "<m-State>MarketWrapperReelStateMachine::WaitForRunning</m-State>"
                        "<m-Status>0</m-Status>"
                        "</InitTestClientResult>"
                    ),
                )
            raise AssertionError(f"Unexpected operation_name: {operation_name}")

        globals()["send_soap_request"] = fake_send_soap_request_for_nested_init_test_client
        assert call_qatesting_init_test_client_state(
            "http://172.22.51.108:18082"
        ) == ("MarketWrapperReelStateMachine::WaitForRunning", 0)
        nested_init_result = call_qatesting_init_test_client_state_result(
            "http://172.22.51.108:18082"
        )
        assert nested_init_result.fields_preview == (
            "wrapper=InitTestClientResult "
            "m-State=MarketWrapperReelStateMachine::WaitForRunning, m-Status=0"
        )
    finally:
        globals()["send_soap_request"] = original_send_soap_request
    checks += 1

    original_call_qatesting_get_game_state_result = call_qatesting_get_game_state_result
    original_call_qatesting_init_test_client_state_result = (
        call_qatesting_init_test_client_state_result
    )
    try:
        poller_fallback_state = {
            "get_game_state_calls": 0,
            "init_test_client_calls": 0,
        }

        def fake_call_qatesting_get_game_state_result(
            service_url: str,
        ) -> QATestingStateResult:
            del service_url
            poller_fallback_state["get_game_state_calls"] += 1
            return QATestingStateResult(
                state="",
                status=0,
                operation_name="GetGameStateResponse",
                fields_preview="state=<blank>, status=0",
            )

        def fake_call_qatesting_init_test_client_state_result(
            service_url: str,
        ) -> QATestingStateResult:
            del service_url
            poller_fallback_state["init_test_client_calls"] += 1
            return QATestingStateResult(
                state="MarketWrapperReelStateMachine::PlayGame",
                status=0,
                operation_name="QAGameInfo",
                fields_preview=(
                    "m-State=MarketWrapperReelStateMachine::PlayGame, m-Status=0"
                ),
            )

        globals()["call_qatesting_get_game_state_result"] = (
            fake_call_qatesting_get_game_state_result
        )
        globals()["call_qatesting_init_test_client_state_result"] = (
            fake_call_qatesting_init_test_client_state_result
        )

        poller_output_session = TCEOutputSession()
        poller_output_buffer = io.StringIO()
        with redirect_stdout(poller_output_buffer):
            TCEStatePoller(xml_tce_config, poller_output_session).poll_current_state()
        poller_output_lines = [
            line for line in poller_output_buffer.getvalue().splitlines() if line.strip()
        ]
        assert poller_fallback_state["get_game_state_calls"] == 1
        assert poller_fallback_state["init_test_client_calls"] == 1
        assert len(poller_output_lines) == 1
        assert poller_output_lines[0].endswith(
            "---> 4|3||STATE|MarketWrapperReelStateMachine::PlayGame"
        )
        poller_fallback_diagnostics = poller_output_session.diagnostics_snapshot()
        assert poller_fallback_diagnostics.state_pull_attempt_count == 1
        assert poller_fallback_diagnostics.state_pull_success_count == 1
        assert poller_fallback_diagnostics.state_pull_live_state_count == 1
        assert (
            poller_fallback_diagnostics.last_pulled_state
            == "MarketWrapperReelStateMachine::PlayGame"
        )
        assert poller_fallback_diagnostics.last_state_pull_operation_name == "QAGameInfo"
        assert (
            poller_fallback_diagnostics.last_state_pull_fields_preview
            == "m-State=MarketWrapperReelStateMachine::PlayGame, m-Status=0"
        )
        assert (
            poller_fallback_diagnostics.last_state_pull_context
            == "InitTestClient fallback after blank GetGameState"
        )
        assert poller_output_session.state_payload_seen is True
    finally:
        globals()["call_qatesting_get_game_state_result"] = (
            original_call_qatesting_get_game_state_result
        )
        globals()["call_qatesting_init_test_client_state_result"] = (
            original_call_qatesting_init_test_client_state_result
        )
    checks += 1

    original_call_qatesting_init_test_client_state_result = (
        call_qatesting_init_test_client_state_result
    )
    try:
        def fake_call_qatesting_init_test_client_state_result_crash(
            service_url: str,
        ) -> QATestingStateResult:
            del service_url
            raise ValueError("unexpected InitTestClient parse failure")

        globals()["call_qatesting_init_test_client_state_result"] = (
            fake_call_qatesting_init_test_client_state_result_crash
        )
        poller_crash_logs: list[str] = []
        poller_crash_output_session = TCEOutputSession()
        poller_crash = TCEStatePoller(
            xml_tce_config,
            poller_crash_output_session,
            poll_interval_seconds=0.01,
            debug_log=poller_crash_logs.append,
        )
        poller_crash.start()
        crash_deadline = time.monotonic() + 1.0
        while time.monotonic() < crash_deadline:
            crash_diagnostics = poller_crash_output_session.diagnostics_snapshot()
            if crash_diagnostics.state_poller_failure_count > 0:
                break
            time.sleep(0.01)
        poller_crash.stop()
        crash_diagnostics = poller_crash_output_session.diagnostics_snapshot()
        assert crash_diagnostics.state_poller_started is True
        assert crash_diagnostics.state_poller_running is False
        assert crash_diagnostics.state_poller_failure_count == 1
        assert (
            crash_diagnostics.last_state_poller_error
            == "Standalone STATE poller crashed: ValueError: unexpected InitTestClient parse failure"
        )
        assert crash_diagnostics.state_pull_attempt_count == 1
        assert crash_diagnostics.state_pull_success_count == 0
        assert crash_diagnostics.last_state_pull_context is None
        assert any(
            "Standalone STATE poller started" in message
            for message in poller_crash_logs
        )
        assert any(
            "Standalone STATE poller crashed: ValueError: unexpected InitTestClient parse failure"
            in message
            for message in poller_crash_logs
        )
        assert any(
            "Standalone STATE poller stopped" in message
            for message in poller_crash_logs
        )
    finally:
        globals()["call_qatesting_init_test_client_state_result"] = (
            original_call_qatesting_init_test_client_state_result
        )
    checks += 1

    warning_listener = TCEListener(xml_tce_config)
    warning_buffer = io.StringIO()
    with redirect_stdout(warning_buffer):
        warning_emitted = warning_listener._maybe_emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            ),
            5.0,
            False,
            now_monotonic=15.1,
        )
        warning_emitted = warning_listener._maybe_emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            ),
            5.0,
            warning_emitted,
            now_monotonic=35.1,
        )
    warning_lines = [line for line in warning_buffer.getvalue().splitlines() if line.strip()]
    assert warning_emitted is True
    assert len(warning_lines) == 3
    assert (
        f"No TCE callbacks received after {DEFAULT_TCE_NO_CALLBACK_WARNING_SECONDS:g} seconds."
        in warning_lines[0]
    )
    assert f"config={xml_tce_config.config_path}" in warning_lines[0]
    assert "vlt_service=http://10.25.30.40:18082" in warning_lines[0]
    assert "callback=10.25.30.50:19091" in warning_lines[0]
    assert "TCE callback diagnostics:" in warning_lines[1]
    assert "callback_deliveries=0" in warning_lines[1]
    assert "http_requests=0" in warning_lines[1]
    assert "self_probe_passed=0" in warning_lines[1]
    assert "state_poller_started=0" in warning_lines[1]
    assert "state_poller_failures=0" in warning_lines[1]
    assert "state_payload_seen=0" in warning_lines[1]
    assert "No inbound HTTP callback attempts reached the listener." in warning_lines[2]
    checks += 1

    pull_live_warning_listener = TCEListener(xml_tce_config)
    pull_live_warning_listener.output_session.note_state_pull_attempt()
    pull_live_warning_listener.output_session.note_state_pull_success(
        state="MarketWrapperReelStateMachine::WithdrawWager",
    )
    pull_live_seed_buffer = io.StringIO()
    with redirect_stdout(pull_live_seed_buffer):
        pull_live_warning_listener.output_session.emit_live_payload(
            build_tce_state_payload(
                4,
                "MarketWrapperReelStateMachine::WithdrawWager",
            )
        )
    assert pull_live_warning_listener.output_session.state_payload_seen is True
    pull_live_warning_buffer = io.StringIO()
    with redirect_stdout(pull_live_warning_buffer):
        pull_live_warning_emitted = pull_live_warning_listener._maybe_emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            ),
            5.0,
            False,
            now_monotonic=35.1,
        )
    assert pull_live_warning_emitted is False
    assert pull_live_warning_buffer.getvalue().strip() == ""
    checks += 1

    callback_state_warning_listener = TCEListener(xml_tce_config)
    callback_state_warning_listener.output_session.note_http_request(
        request_size=47,
        client_address="10.25.30.40:18082",
    )
    callback_state_warning_listener.output_session.note_parsed_callback("StateTransition")
    callback_state_seed_buffer = io.StringIO()
    with redirect_stdout(callback_state_seed_buffer):
        callback_state_warning_listener.output_session.emit_callback_emission(
            format_tce_callback_emission(
                "StateTransition",
                {"name": "MarketWrapperReelStateMachine::WithdrawWager"},
                client_ip="10.25.30.40",
                expected_vlt_ip="10.25.30.40",
                tce_number=4,
            )
        )
    callback_state_warning_buffer = io.StringIO()
    with redirect_stdout(callback_state_warning_buffer):
        callback_state_warning_emitted = callback_state_warning_listener._maybe_emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            ),
            5.0,
            False,
            now_monotonic=35.1,
        )
    assert callback_state_warning_listener.output_session.state_payload_seen is True
    assert callback_state_warning_emitted is False
    assert callback_state_warning_buffer.getvalue().strip() == ""
    checks += 1

    blank_state_warning_listener = TCEListener(xml_tce_config)
    blank_state_warning_listener.output_session.note_state_pull_attempt()
    blank_state_warning_listener.output_session.note_state_pull_success(
        state="",
        operation_name="GetGameStateResponse",
        fields_preview="state=<blank>, status=0",
    )
    blank_state_warning_buffer = io.StringIO()
    with redirect_stdout(blank_state_warning_buffer):
        blank_state_warning_listener._emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    blank_state_warning_lines = [
        line for line in blank_state_warning_buffer.getvalue().splitlines() if line.strip()
    ]
    assert any("state_pull_successes=1" in line for line in blank_state_warning_lines)
    assert any("state_pull_live_states=0" in line for line in blank_state_warning_lines)
    assert any(
        "no non-empty game state was returned" in line
        for line in blank_state_warning_lines
    )
    assert any("last_pulled_state=<blank>" in line for line in blank_state_warning_lines)
    assert any(
        "last_state_pull_op=GetGameStateResponse" in line
        for line in blank_state_warning_lines
    )
    assert any(
        "last_state_pull_fields=state=<blank>, status=0" in line
        for line in blank_state_warning_lines
    )
    checks += 1

    bank_blank_state_warning_listener = TCEListener(xml_tce_config)
    bank_blank_state_warning_listener.output_session.note_callback_delivery(
        request_size=33,
        client_address="10.25.30.40:18082",
    )
    bank_blank_state_warning_listener.output_session.note_parsed_callback(
        "UpdateVar",
        {"name": "BANK", "valstr": "117585"},
    )
    bank_blank_state_warning_listener.output_session.note_state_pull_attempt()
    bank_blank_state_warning_listener.output_session.note_state_pull_success(
        state="",
        operation_name="GetGameStateResponse",
        fields_preview="state=<blank>, status=0",
    )
    bank_blank_state_warning_buffer = io.StringIO()
    with redirect_stdout(bank_blank_state_warning_buffer):
        bank_blank_state_warning_listener.output_session.emit_callback_emission(
            format_tce_callback_emission(
                "UpdateVar",
                {"name": "BANK", "valstr": "117585"},
                client_ip="10.25.30.40",
                expected_vlt_ip="10.25.30.40",
                tce_number=4,
            )
        )
        bank_blank_state_warning_listener._emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    bank_blank_state_warning_lines = [
        line for line in bank_blank_state_warning_buffer.getvalue().splitlines() if line.strip()
    ]
    assert bank_blank_state_warning_lines[0].endswith("---> 4|3||BANK|117585")
    assert any(
        "No usable STATE payload emitted after" in line
        for line in bank_blank_state_warning_lines
    )
    assert any("callback_deliveries=1" in line for line in bank_blank_state_warning_lines)
    assert any("http_requests=0" in line for line in bank_blank_state_warning_lines)
    assert any("state_payload_seen=0" in line for line in bank_blank_state_warning_lines)
    assert any(
        "callback_variables=BANK:1" in line
        for line in bank_blank_state_warning_lines
    )
    assert any(
        "QA SOAP state pull remained blank" in line
        for line in bank_blank_state_warning_lines
    )
    assert any(
        "only non-state callback variables were seen (BANK:1)" in line
        for line in bank_blank_state_warning_lines
    )
    checks += 1

    state_pull_error_warning_listener = TCEListener(xml_tce_config)
    state_pull_error_warning_listener.output_session.note_state_pull_attempt()
    state_pull_error_warning_listener.output_session.note_state_pull_error(
        error_text="SOAP GetGameState to http://10.25.30.40:18082 timed out",
        operation_name="GetGameState",
    )
    state_pull_error_warning_buffer = io.StringIO()
    with redirect_stdout(state_pull_error_warning_buffer):
        state_pull_error_warning_listener._emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    state_pull_error_warning_lines = [
        line
        for line in state_pull_error_warning_buffer.getvalue().splitlines()
        if line.strip()
    ]
    assert any("state_pull_errors=1" in line for line in state_pull_error_warning_lines)
    assert any(
        "QA SOAP state pull failed" in line for line in state_pull_error_warning_lines
    )
    assert any(
        "timed out" in line for line in state_pull_error_warning_lines
    )
    checks += 1

    bank_state_pull_error_warning_listener = TCEListener(xml_tce_config)
    bank_state_pull_error_warning_listener.output_session.note_callback_delivery(
        request_size=33,
        client_address="10.25.30.40:18082",
    )
    bank_state_pull_error_warning_listener.output_session.note_parsed_callback(
        "UpdateVar",
        {"name": "BANK", "valstr": "117585"},
    )
    bank_state_pull_error_warning_listener.output_session.note_state_pull_attempt()
    bank_state_pull_error_warning_listener.output_session.note_state_pull_error(
        error_text="SOAP GetGameState to http://10.25.30.40:18082 timed out",
        operation_name="GetGameState",
    )
    bank_state_pull_error_warning_buffer = io.StringIO()
    with redirect_stdout(bank_state_pull_error_warning_buffer):
        bank_state_pull_error_warning_listener.output_session.emit_callback_emission(
            format_tce_callback_emission(
                "UpdateVar",
                {"name": "BANK", "valstr": "117585"},
                client_ip="10.25.30.40",
                expected_vlt_ip="10.25.30.40",
                tce_number=4,
            )
        )
        bank_state_pull_error_warning_listener._emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    bank_state_pull_error_warning_lines = [
        line
        for line in bank_state_pull_error_warning_buffer.getvalue().splitlines()
        if line.strip()
    ]
    assert bank_state_pull_error_warning_lines[0].endswith("---> 4|3||BANK|117585")
    assert any(
        "No usable STATE payload emitted after" in line
        for line in bank_state_pull_error_warning_lines
    )
    assert any(
        "callback_deliveries=1" in line
        for line in bank_state_pull_error_warning_lines
    )
    assert any("http_requests=0" in line for line in bank_state_pull_error_warning_lines)
    assert any("state_pull_errors=1" in line for line in bank_state_pull_error_warning_lines)
    assert any(
        "callback_variables=BANK:1" in line
        for line in bank_state_pull_error_warning_lines
    )
    assert any(
        "only non-state callback variables were seen (BANK:1); QA SOAP state pull failed"
        in line
        for line in bank_state_pull_error_warning_lines
    )
    assert any("timed out" in line for line in bank_state_pull_error_warning_lines)
    checks += 1

    poller_crash_warning_listener = TCEListener(xml_tce_config)
    poller_crash_warning_listener.output_session.note_state_poller_started()
    poller_crash_warning_listener.output_session.note_state_poller_failure(
        error_text=(
            "Standalone STATE poller crashed: ValueError: unexpected InitTestClient parse failure"
        )
    )
    poller_crash_warning_buffer = io.StringIO()
    with redirect_stdout(poller_crash_warning_buffer):
        poller_crash_warning_listener._emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    poller_crash_warning_lines = [
        line
        for line in poller_crash_warning_buffer.getvalue().splitlines()
        if line.strip()
    ]
    assert any(
        "state_poller_failures=1" in line for line in poller_crash_warning_lines
    )
    assert any(
        "last_state_poller_error=Standalone STATE poller crashed: ValueError: unexpected InitTestClient parse failure"
        in line
        for line in poller_crash_warning_lines
    )
    assert any(
        "standalone QA SOAP STATE poller stopped unexpectedly before any usable STATE was emitted"
        in line
        for line in poller_crash_warning_lines
    )
    checks += 1

    parse_failure_warning_listener = TCEListener(xml_tce_config)
    parse_failure_warning_listener.output_session.note_http_request(
        request_size=17,
        client_address="10.25.30.40:18082",
    )
    parse_failure_warning_listener.output_session.note_parse_error(
        request_size=17,
        client_address="10.25.30.40:18082",
        error_text="mismatched tag",
    )
    parse_failure_warning_buffer = io.StringIO()
    with redirect_stdout(parse_failure_warning_buffer):
        parse_failure_warning_listener._emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    parse_failure_warning_lines = [
        line for line in parse_failure_warning_buffer.getvalue().splitlines() if line.strip()
    ]
    assert any("parse_errors=1" in line for line in parse_failure_warning_lines)
    assert any("SOAP parsing failed" in line for line in parse_failure_warning_lines)
    assert any("last_error=mismatched tag" in line for line in parse_failure_warning_lines)
    checks += 1

    unhandled_warning_listener = TCEListener(xml_tce_config)
    unhandled_warning_listener.output_session.note_http_request(
        request_size=33,
        client_address="10.25.30.40:18082",
    )
    unhandled_warning_listener.output_session.note_parsed_callback("UnknownOperation")
    unhandled_warning_listener.output_session.note_unhandled_callback("UnknownOperation")
    unhandled_warning_buffer = io.StringIO()
    with redirect_stdout(unhandled_warning_buffer):
        unhandled_warning_listener._emit_no_callback_warning(
            TCERegistrationResult(
                requested_endpoint="10.25.30.50:19091",
                confirmed_endpoint="10.25.30.50:19091",
            )
        )
    unhandled_warning_lines = [
        line for line in unhandled_warning_buffer.getvalue().splitlines() if line.strip()
    ]
    assert any("unhandled_callbacks=1" in line for line in unhandled_warning_lines)
    assert any("no supported gameplay events were emitted" in line for line in unhandled_warning_lines)
    assert any("last_operation=UnknownOperation" in line for line in unhandled_warning_lines)
    checks += 1

    cross_source_session = TCEOutputSession()
    cross_source_output = io.StringIO()
    with redirect_stdout(cross_source_output):
        cross_source_session.emit_callback_emission(
            format_tce_callback_emission(
                "UpdateVar",
                {
                    "name": "STATE",
                    "valstr": "MarketWrapperReelStateMachine::WithdrawWager",
                },
                client_ip="10.25.30.40",
                expected_vlt_ip="10.25.30.40",
                tce_number=1,
            )
        )
        cross_source_session.note_state_pull_attempt()
        cross_source_session.note_state_pull_success(
            state="MarketWrapperReelStateMachine::WithdrawWager",
        )
        cross_source_session.emit_live_payload(
            build_tce_state_payload(
                1,
                "MarketWrapperReelStateMachine::WithdrawWager",
            )
        )
    cross_source_lines = [
        line for line in cross_source_output.getvalue().splitlines() if line.strip()
    ]
    assert len(cross_source_lines) == 1
    assert cross_source_lines[0].endswith(
        "---> 1|3||STATE|MarketWrapperReelStateMachine::WithdrawWager"
    )
    assert cross_source_session.callback_seen is True
    assert cross_source_session.live_payload_seen is True
    assert cross_source_session.state_payload_seen is True
    cross_source_diagnostics = cross_source_session.diagnostics_snapshot()
    assert cross_source_diagnostics.state_pull_attempt_count == 1
    assert cross_source_diagnostics.state_pull_success_count == 1
    assert cross_source_diagnostics.state_pull_live_state_count == 1
    assert cross_source_diagnostics.state_payload_seen is True
    checks += 1

    cross_source_transition_session = TCEOutputSession()
    cross_source_transition_output = io.StringIO()
    with redirect_stdout(cross_source_transition_output):
        cross_source_transition_session.emit_callback_emission(
            format_tce_callback_emission(
                "StateTransition",
                {"name": "MarketWrapperReelStateMachine::WithdrawWager"},
                client_ip="10.25.30.40",
                expected_vlt_ip="10.25.30.40",
                tce_number=1,
            )
        )
        cross_source_transition_session.note_state_pull_attempt()
        cross_source_transition_session.note_state_pull_success(
            state="MarketWrapperReelStateMachine::WithdrawWager",
        )
        cross_source_transition_session.emit_live_payload(
            build_tce_state_payload(
                1,
                "MarketWrapperReelStateMachine::WithdrawWager",
            )
        )
    cross_source_transition_lines = [
        line
        for line in cross_source_transition_output.getvalue().splitlines()
        if line.strip()
    ]
    assert len(cross_source_transition_lines) == 1
    assert cross_source_transition_lines[0].endswith(
        "---> 1|3||STATE|MarketWrapperReelStateMachine::WithdrawWager"
    )
    checks += 1

    def build_callback_request(operation_name: str, inner_xml: str) -> bytes:
        return build_soap_envelope(
            "Technology",
            TECHNOLOGY_NAMESPACE,
            operation_name,
            inner_xml,
        )

    callback_server = TCECallbackServer(
        host="127.0.0.1",
        port=0,
        output_session=TCEOutputSession(),
        expected_vlt_ip="127.0.0.1",
        debug=True,
    )
    callback_server.start()
    try:
        callback_session = callback_server.httpd.output_session
        callback_output = io.StringIO()
        with redirect_stdout(callback_output):
            run_tce_callback_self_probe("127.0.0.1", callback_server.port, debug=True)
            connection = http.client.HTTPConnection("127.0.0.1", callback_server.port, timeout=5)
            connection.request(
                "POST",
                "/",
                body=build_callback_request(
                    "UpdateVar",
                    (
                        "<name>STATE</name>"
                        "<valstr>MarketWrapperReelStateMachine::WithdrawWager</valstr>"
                    ),
                ),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            time.sleep(0.1)
        callback_lines = [line for line in callback_output.getvalue().splitlines() if line.strip()]
        assert response.status == 200
        callback_diagnostics = callback_session.diagnostics_snapshot()
        assert callback_diagnostics.self_probe_passed is True
        assert callback_diagnostics.callback_delivery_count == 1
        assert callback_diagnostics.http_request_count == 1
        assert callback_diagnostics.parsed_callback_count == 1
        assert callback_diagnostics.parse_error_count == 0
        assert any(
            "TCE callback self-probe from=127.0.0.1:" in line for line in callback_lines
        )
        assert any(
            "TCE callback from=127.0.0.1:" in line and "operation=UpdateVar" in line
            for line in callback_lines
        )
        assert any(
            line.endswith(
                "---> 1|3||STATE|MarketWrapperReelStateMachine::WithdrawWager"
            )
            for line in callback_lines
        )
        assert callback_session.callback_seen is True
    finally:
        callback_server.stop()
    checks += 1

    raw_xml_callback_server = TCECallbackServer(
        host="127.0.0.1",
        port=0,
        output_session=TCEOutputSession(),
        expected_vlt_ip="127.0.0.1",
        debug=True,
    )
    raw_xml_callback_server.start()
    try:
        raw_xml_callback_session = raw_xml_callback_server.httpd.output_session
        raw_xml_callback_output = io.StringIO()
        with redirect_stdout(raw_xml_callback_output):
            raw_xml_socket = socket.create_connection(
                ("127.0.0.1", raw_xml_callback_server.port),
                timeout=5,
            )
            try:
                raw_xml_socket.sendall(
                    build_callback_request(
                        "BankTransition",
                        "<amount>117585</amount>",
                    )
                )
                raw_xml_socket.shutdown(socket.SHUT_WR)
                raw_xml_response = b""
                while True:
                    raw_xml_chunk = raw_xml_socket.recv(4096)
                    if not raw_xml_chunk:
                        break
                    raw_xml_response += raw_xml_chunk
            finally:
                raw_xml_socket.close()
            time.sleep(0.1)
        raw_xml_callback_lines = [
            line for line in raw_xml_callback_output.getvalue().splitlines() if line.strip()
        ]
        assert b"BankTransitionResponse" in raw_xml_response
        raw_xml_callback_diagnostics = raw_xml_callback_session.diagnostics_snapshot()
        assert raw_xml_callback_diagnostics.callback_delivery_count == 1
        assert raw_xml_callback_diagnostics.http_request_count == 0
        assert raw_xml_callback_diagnostics.parsed_callback_count == 1
        assert raw_xml_callback_diagnostics.parse_error_count == 0
        assert raw_xml_callback_session.callback_seen is True
        assert any(
            "TCE callback raw XML from=127.0.0.1:" in line
            and "operation=BankTransition" in line
            for line in raw_xml_callback_lines
        )
        assert any(
            line.endswith("---> 1|3||BANK|117585")
            for line in raw_xml_callback_lines
        )
    finally:
        raw_xml_callback_server.stop()
    checks += 1

    message_queue_server = TCECallbackServer(
        host="127.0.0.1",
        port=0,
        output_session=TCEOutputSession(),
        expected_vlt_ip="127.0.0.1",
        debug=True,
    )
    message_queue_server.start()
    try:
        message_queue_session = message_queue_server.httpd.output_session
        message_queue_output = io.StringIO()
        with redirect_stdout(message_queue_output):
            connection = http.client.HTTPConnection("127.0.0.1", message_queue_server.port, timeout=5)
            connection.request(
                "POST",
                "/",
                body=build_callback_request(
                    "MessageQueueCount",
                    "<queuecount>3</queuecount>",
                ),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            time.sleep(0.1)
        message_queue_lines = [
            line for line in message_queue_output.getvalue().splitlines() if line.strip()
        ]
        assert response.status == 200
        message_queue_diagnostics = message_queue_session.diagnostics_snapshot()
        assert message_queue_diagnostics.http_request_count == 1
        assert message_queue_diagnostics.parsed_callback_count == 1
        assert message_queue_diagnostics.unhandled_callback_count == 0
        assert message_queue_session.callback_seen is False
        assert any(
            "TCE callback from=127.0.0.1:" in line and "operation=MessageQueueCount" in line
            for line in message_queue_lines
        )
        assert not any(
            line.endswith("---> 0|3|SOAP PUSH Event - Update Message Queue (Count) (3)")
            for line in message_queue_lines
        )
    finally:
        message_queue_server.stop()
    checks += 1

    message_queue_debug_server = TCECallbackServer(
        host="127.0.0.1",
        port=0,
        output_session=TCEOutputSession(emit_diagnostic_payloads=True),
        expected_vlt_ip="127.0.0.1",
        debug=True,
    )
    message_queue_debug_server.start()
    try:
        message_queue_debug_output = io.StringIO()
        with redirect_stdout(message_queue_debug_output):
            connection = http.client.HTTPConnection(
                "127.0.0.1",
                message_queue_debug_server.port,
                timeout=5,
            )
            connection.request(
                "POST",
                "/",
                body=build_callback_request(
                    "MessageQueueCount",
                    "<queuecount>3</queuecount>",
                ),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            time.sleep(0.1)
        message_queue_debug_lines = [
            line for line in message_queue_debug_output.getvalue().splitlines() if line.strip()
        ]
        assert response.status == 200
        assert any(
            line.endswith("---> 0|3|SOAP PUSH Event - Update Message Queue (Count) (3)")
            for line in message_queue_debug_lines
        )
    finally:
        message_queue_debug_server.stop()
    checks += 1

    mismatch_server = TCECallbackServer(
        host="127.0.0.1",
        port=0,
        output_session=TCEOutputSession(),
        expected_vlt_ip="127.0.0.2",
        debug=True,
    )
    mismatch_server.start()
    try:
        mismatch_session = mismatch_server.httpd.output_session
        mismatch_output = io.StringIO()
        with redirect_stdout(mismatch_output):
            connection = http.client.HTTPConnection("127.0.0.1", mismatch_server.port, timeout=5)
            connection.request(
                "POST",
                "/",
                body=build_callback_request(
                    "UpdateVar",
                    (
                        "<name>STATE</name>"
                        "<valstr>MarketWrapperReelStateMachine::WithdrawWager</valstr>"
                    ),
                ),
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            time.sleep(0.1)
        mismatch_lines = [line for line in mismatch_output.getvalue().splitlines() if line.strip()]
        assert response.status == 200
        mismatch_diagnostics = mismatch_session.diagnostics_snapshot()
        assert mismatch_diagnostics.http_request_count == 1
        assert mismatch_diagnostics.parsed_callback_count == 1
        assert mismatch_session.callback_seen is False
        assert any("TCE callback source mismatch" in line for line in mismatch_lines)
        assert not any(
            line.endswith(
                "---> 1|3||STATE|MarketWrapperReelStateMachine::WithdrawWager"
            )
            for line in mismatch_lines
        )
    finally:
        mismatch_server.stop()
    checks += 1

    malformed_server = TCECallbackServer(
        host="127.0.0.1",
        port=0,
        output_session=TCEOutputSession(),
        expected_vlt_ip="127.0.0.1",
        debug=True,
    )
    malformed_server.start()
    try:
        malformed_session = malformed_server.httpd.output_session
        malformed_output = io.StringIO()
        with redirect_stdout(malformed_output):
            connection = http.client.HTTPConnection("127.0.0.1", malformed_server.port, timeout=5)
            connection.request(
                "POST",
                "/",
                body=b"<not-xml",
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            time.sleep(0.1)
        malformed_lines = [line for line in malformed_output.getvalue().splitlines() if line.strip()]
        assert response.status == 500
        malformed_diagnostics = malformed_session.diagnostics_snapshot()
        assert malformed_diagnostics.http_request_count == 1
        assert malformed_diagnostics.parsed_callback_count == 0
        assert malformed_diagnostics.parse_error_count == 1
        assert malformed_diagnostics.last_parse_error is not None
        assert any(
            "TCE callback error from=127.0.0.1:" in line
            for line in malformed_lines
        )
    finally:
        malformed_server.stop()
    checks += 1

    print(f"Self-test passed ({checks} checks).")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.runtime_info or args.verbose:
        print(f"Runtime: {format_runtime_info()}")

    if args.list_ports:
        print(format_serial_port_listing())
        return 0

    if args.self_test:
        return run_self_test()

    try:
        if args.mode == MODE_TCE:
            config = build_tce_config(args)
            listener = TCEListener(config)
        else:
            config = build_config(args)
            listener = SASListener(config)
        return listener.run()
    except KeyboardInterrupt:
        if args.mode == MODE_SAS:
            print("Listener stopped.")
        return 0
    except Exception as exc:
        message = str(exc)
        if "\n" in message:
            print(f"Error:\n{message}", file=sys.stderr)
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
