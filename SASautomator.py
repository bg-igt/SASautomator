from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import os
import queue
import random
import re
import shlex
import shutil
import socket
import sys
import threading
import time
import traceback
import types
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Iterable
from xml.sax.saxutils import escape as xml_escape

try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:  # pragma: no cover - environment dependent
    tk = None  # type: ignore[assignment]
    filedialog = None  # type: ignore[assignment]

try:
    import pyquicktest as qt  # type: ignore
except Exception as exc:  # pragma: no cover - environment dependent
    qt = None  # type: ignore[assignment]
    PYQUICKTEST_IMPORT_ERROR = exc
else:
    PYQUICKTEST_IMPORT_ERROR = None

try:
    import pysaelib  # type: ignore
except Exception as exc:  # pragma: no cover - environment dependent
    pysaelib = None  # type: ignore[assignment]
    PYSAELIB_IMPORT_ERROR = exc
else:
    PYSAELIB_IMPORT_ERROR = None

try:
    import paramiko  # type: ignore
except Exception as exc:  # pragma: no cover - environment dependent
    paramiko = None  # type: ignore[assignment]
    PARAMIKO_IMPORT_ERROR = exc
else:
    PARAMIKO_IMPORT_ERROR = None

try:
    from CommandListener import CommandListener as tce_listener  # type: ignore
except Exception as exc:  # pragma: no cover - environment dependent
    tce_listener = None  # type: ignore[assignment]
    TCE_LISTENER_IMPORT_ERROR = exc
else:
    TCE_LISTENER_IMPORT_ERROR = None


CATEGORY_NAME = "generated"
UGF_VLT_PORT = 61000
SGF_VLT_PORT = 18082
UGF_CONNECT_TIMEOUT_SECONDS = 3.0
FORWARDER_TIMEOUT_MS = 5000
UGF_AUTOSPIN_BUTTON_ID = 15
SGF_QATESTING_VLT_PORT = SGF_VLT_PORT
SGF_PREFERRED_BUTTONPRESS_PORT = SGF_VLT_PORT
SGF_FALLBACK_BUTTONPRESS_PORTS = (SGF_VLT_PORT,)
SGF_SPIN_TOUCH_KEYWORDS = ("spin",)
SGF_STOP_TOUCH_KEYWORDS = ("stop",)
SGF_TOUCH_QUERY_RETRY_INTERVAL_SECONDS = 0.2
SGF_TOUCH_QUERY_MAX_RETRIES = 4
SGF_DEFAULT_SPIN_TOUCH_CANDIDATES = ("SpinButton", "Spin", "MainPlayButton", "PlayButton")
SGF_AUTOSPIN_BUTTON_NAME = "Mech - 15"
SGF_IDLE_WAIT_TIMEOUT_SECONDS = 120.0
# Callback delivery wakes this wait immediately; this cap only bounds checks needed for pending bonus idle.
SGF_IDLE_EVENT_WAIT_SECONDS = 0.05
# Periodically re-press spin to advance past persistent win animations.
SGF_WIN_AUTOSPIN_RETRY_INTERVAL_SECONDS = 10.0
# Slower poll reduces SOAP load on the VLT; callback push handles real-time state delivery.
SGF_STATE_POLL_INTERVAL_MS = 500
PICK_A_PRIZE_TOUCH_INTERVAL_SECONDS = 5.0
PICK_A_PRIZE_SSH_PORT = 22
PICK_A_PRIZE_SFTP_PORT = 22
PICK_A_PRIZE_SSH_USERNAME = "root"
PICK_A_PRIZE_SSH_PASSWORD = "root1234"
PICK_A_PRIZE_SCREENS_INFO_PATH = "/tmp/Screens.info"
PICK_A_PRIZE_MAIN_SCREEN_NAME = "Main"
PICK_A_PRIZE_XINPUT_DISPLAY = ":0"
PICK_A_PRIZE_SSH_CONNECT_TIMEOUT_SECONDS = 10
PICK_A_PRIZE_REMOTE_COMMAND_TIMEOUT_SECONDS = 10
PICK_A_PRIZE_TOOL_PRIORITY = ("evemu-event", "sendevent", "perl")
COMMAND_LOG_FILE_NAME = "command_log.txt"
PAP_STATE_MACHINE_KEYWORDS = ("PAP", "PICKAPRIZE")
SGF_BONUS_TRIGGER_STATE_VALUE = "MarketWrapperReelStateMachine::ShowBonusTrigger"
SGF_BONUS_STATE_VALUE = "Bonus::Bonus"
SGF_FREESPIN_IDLE_STATE_VALUE = "MarketWrapperFreeSpinStateMachine::Idle"
BONUS_STATE_MACHINE_KEYWORDS = ("BONUS", "FREESPIN")
# The main wrapper reports idle between bonus stages, so idle must be stable before a snippet completes.
SGF_BONUS_IDLE_CONFIRM_SECONDS = 5.0
SGF_BONUS_IDLE_WAIT_TIMEOUT_SECONDS = 600.0
SGF_STATE_EVENT_QUEUE_MAX = 256
UGF_DOTNET_RUNTIME_DIR_ENV_VAR = "SASAUTOMATOR_DOTNET_RUNTIME_DIR"
UGF_RUNTIME_DIR_NAME = "dotnet_runtime"
SGFHD_DOTNET_RUNTIME_DIR_ENV_VARS = (
    "SASAUTOMATOR_SGFHD_DOTNET_RUNTIME_DIR",
    "CHEAT_FORWARDER_SGFHD_DOTNET_RUNTIME_DIR",
)
SGFHD_RUNTIME_DIR_NAME = "dotnet_runtime_sgfhd"
REQUIRED_UGF_DOTNET_DLLS = (
    "Thrift.dll",
    "IGT.GSN.Thrift.dll",
)
REQUIRED_SGFHD_DOTNET_DLLS = (
    "Tools.Common.dll",
    "System.IO.Abstractions.dll",
    "SimpleInjector.dll",
    "SimpleInjector.Packaging.dll",
    "IGT.Ignite.Tools.Mpt.Common.dll",
    "IGT.Ignite.Tools.Mpt.Common.Snippet121.dll",
    "CommunicationPlugin.dll",
    "IGT.Spielo.Tools.Mpt.Runnr.SensysPlugin.dll",
)
DEPENDENCY_HELP = (
    "Install the SAE generator dependencies first. "
    "Workspace reference: "
    "'mfw.math_devkit.sae_snippet_generation_suite-develop"
    "\\mfw.math_devkit.sae_snippet_generation_suite-develop\\fetch_dependencies.bat'."
)

MANUAL_SEND_DIR_NAME = "manual_send"
CURRENT_SNIPPET_FILENAME = "current_snippet.xml"
SESSION_FILE_SUFFIX = "_manual_send_session.json"
PROGRESS_FILE_SUFFIX = "_manual_send_progress.json"
GUI_SETTINGS_FILE_NAME = "sas_automator_gui_settings.json"
LEGACY_GUI_SETTINGS_KEYS = frozenset({"pick_a_prize_enabled", "pick_a_prize_ssh_host"})
STATE_FILE_VERSION = 1
SEND_STATUS_PENDING = "pending"
SEND_STATUS_COMPLETED = "completed"
IMPORTED_SNIPPET_NAME = "imported_snippet"
LEGACY_METER_TOTAL_CASH_IN = "Total Cash In"
LEGACY_METER_TOTAL_CASH_OUT = "Total Cash Out"
METER_TOTAL_CASH_IN = "Coin In"
METER_TOTAL_CASH_OUT = "Coin Out"
METER_AMOUNT_WAGERED = "Amount Wagered"
METER_AMOUNT_WON = "Amount Won"
METER_NET = "Net"
METER_TOTAL_GAMES_PLAYED = "Games Played"
METER_GAMES_WON = "Games won"
METER_GAMES_LOST = "Games lost"
METER_PERCENT_GAMES_WON = "% Games won"
METER_BANK = "Bank"
METER_DISPLAY_ORDER = (
    METER_TOTAL_CASH_IN,
    METER_TOTAL_CASH_OUT,
    METER_NET,
    METER_TOTAL_GAMES_PLAYED,
    METER_GAMES_WON,
    METER_GAMES_LOST,
    METER_PERCENT_GAMES_WON,
)
GUI_WINDOW_WIDTH = 1180
GUI_WINDOW_HEIGHT = 820
GUI_WINDOW_MIN_WIDTH = 1080
GUI_WINDOW_MIN_HEIGHT = 720
GUI_BG = "#1e2126"
GUI_SURFACE = "#2a2f36"
GUI_ACCENT = "#343941"
GUI_TEXT = "#e3e6eb"
GUI_MUTED = "#8d96a2"
GUI_SUCCESS = "#2ecc71"
GUI_ERROR = "#ff4d4f"

WIN_TYPE_CREDIT = getattr(qt, "PTI_WIN_TYPE_CREDIT", 0)
WIN_AUTO_TYPE_JACKPOT = getattr(qt, "PTI_WIN_AUTO_TYPE_JACKPOT", 128)
WIN_AUTO_TYPE_WAGER = getattr(qt, "PTI_WIN_AUTO_TYPE_WAGER", 131)


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_state_machine_name(state_value: str) -> str:
    state_prefix = (state_value or "").split("::", 1)[0].strip()
    if "_" not in state_prefix:
        return state_prefix
    return state_prefix.rsplit("_", 1)[0].strip()


def is_pick_a_prize_state(state_value: str) -> bool:
    machine_name = _extract_state_machine_name(state_value)
    normalized_machine_name = re.sub(r"[^A-Z0-9]", "", machine_name.upper())
    return any(keyword in normalized_machine_name for keyword in PAP_STATE_MACHINE_KEYWORDS)


def is_bonus_state(state_value: str) -> bool:
    if state_value == SGF_BONUS_TRIGGER_STATE_VALUE:
        return True
    machine_name = _extract_state_machine_name(state_value)
    normalized_machine_name = re.sub(r"[^A-Z0-9]", "", machine_name.upper())
    return any(keyword in normalized_machine_name for keyword in BONUS_STATE_MACHINE_KEYWORDS)


def terminal_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _format_log_context(context: dict[str, Any] | None) -> str | None:
    if not context:
        return None
    parts = [f"{key}={value}" for key, value in context.items() if value is not None]
    return " ".join(parts) if parts else None


def log_terminal_error(
    message: str,
    *,
    exc: BaseException | None = None,
    context: dict[str, Any] | None = None,
    include_traceback: bool = False,
) -> None:
    prefix = f"[{terminal_timestamp()}] ERROR"
    print(f"{prefix} {message}", file=sys.stderr)

    formatted_context = _format_log_context(context)
    if formatted_context:
        print(f"{prefix} Context: {formatted_context}", file=sys.stderr)

    if exc is None:
        return

    seen: set[int] = set()
    current: BaseException | None = exc
    cause_index = 1
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        label = "Cause" if cause_index == 1 else f"Cause {cause_index}"
        print(f"{prefix} {label}: {type(current).__name__}: {current}", file=sys.stderr)
        current = current.__cause__ or current.__context__
        cause_index += 1

    if include_traceback:
        print(f"{prefix} Traceback:", file=sys.stderr)
        traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
        for line in traceback_text.splitlines():
            print(f"{prefix} {line}", file=sys.stderr)


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def format_meter_value(name: str, value: int | float) -> str:
    if name == METER_PERCENT_GAMES_WON:
        return f"{float(value):.2f}"
    return str(int(value))


def read_meter_int(payload: dict[str, Any], *names: str, default: int = 0) -> int:
    for name in names:
        if name in payload:
            return int(payload[name])
    return default


def _to_signed_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def _get_object_member(obj: object, *names: str) -> object:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    raise AttributeError(f"Unable to find expected member(s) {names!r} on {type(obj)!r}")


def _extract_sgfhd_feature_pot_pairs(feature_pots: Any) -> list[tuple[int, int]]:
    if not feature_pots:
        return []
    if isinstance(feature_pots, dict):
        items = list(feature_pots.items())
    elif hasattr(feature_pots, "Keys"):
        items = []
        for key in list(feature_pots.Keys):
            try:
                items.append((key, feature_pots[key]))
            except Exception:
                continue
    else:
        try:
            items = list(feature_pots)
        except TypeError:
            items = []

    pairs: list[tuple[int, int]] = []
    for item in items:
        if isinstance(item, tuple) and len(item) == 2:
            key, value = item
        elif hasattr(item, "Key") and hasattr(item, "Value"):
            key, value = item.Key, item.Value
        else:
            key = _get_object_member(item, "Index", "idx")
            value = _get_object_member(item, "Value", "value")
        pairs.append((int(key), int(value)))
    return pairs


def _extract_sgfhd_player_decision_values(player_decisions: Iterable[Any]) -> list[int]:
    values: list[int] = []
    for decision in player_decisions:
        values.append(int(_get_object_member(decision, "Value", "SelectedValue", "choice")))
    return values


def _xml_local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _xml_attribute_local_value(element: ET.Element, *names: str) -> str | None:
    wanted = set(names)
    for key, value in element.attrib.items():
        if _xml_local_name(key) in wanted:
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _read_xml_int_value(raw_value: str, field_name: str) -> int:
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"Imported XML contains a non-integer {field_name} value: {raw_value!r}.") from exc


def _xml_attribute_local_int(element: ET.Element, *names: str, default: int = 0) -> int:
    raw_value = _xml_attribute_local_value(element, *names)
    if raw_value is None:
        return default
    return _read_xml_int_value(raw_value, names[0])


def _count_sgfhd_nested_reel_randnums(snippet: str) -> int:
    try:
        root = ET.fromstring(snippet)
    except ET.ParseError:
        return 0

    def visit(element: Any, inside_reel: bool) -> int:
        local_name = _xml_local_name(element.tag)
        nested_inside_reel = inside_reel or local_name == "Reel"
        count = 1 if local_name == "RandNum" and inside_reel else 0
        for child in list(element):
            count += visit(child, nested_inside_reel)
        return count

    return visit(root, False)


def _build_snippet_math_summary(
    *,
    selected_bet_credits: int,
    credit_win_total: int,
    jackpot_credit_total: int = 0,
    wager_from_win_total: int = 0,
) -> "SnippetMathSummary":
    amount_wagered = int(selected_bet_credits) + int(wager_from_win_total)
    amount_won = int(credit_win_total) + int(jackpot_credit_total)
    games_won = 1 if amount_won > 0 else 0
    games_lost = 0 if games_won else 1
    expected_meter_delta = ExpectedMeterDelta(
        total_cash_in=amount_wagered,
        total_cash_out=amount_won,
        amount_wagered=amount_wagered,
        amount_won=amount_won,
        net=amount_won - amount_wagered,
        games_won=games_won,
        games_lost=games_lost,
    )
    return SnippetMathSummary(
        selected_bet_credits=int(selected_bet_credits),
        credit_win_total=int(credit_win_total),
        jackpot_credit_total=int(jackpot_credit_total),
        wager_from_win_total=int(wager_from_win_total),
        expected_meter_delta=expected_meter_delta,
    )


def _parse_imported_game_specific_settings(bet_situation: ET.Element) -> list[int]:
    game_specific_values: dict[int, int] = {}
    for child in list(bet_situation):
        if _xml_local_name(child.tag) != "GameSpecific":
            continue
        index = _xml_attribute_local_int(child, "idx", "index", default=0)
        value = _xml_attribute_local_int(child, "value", "Value", default=0)
        game_specific_values[index] = value

    if not game_specific_values:
        return []

    result = [0] * (max(game_specific_values) + 1)
    for index, value in game_specific_values.items():
        result[index] = value
    return result


def _parse_imported_feature_pots(snippet_element: ET.Element) -> list[int]:
    values: list[int] = []
    for element in snippet_element.iter():
        if _xml_local_name(element.tag) != "FeaturePot":
            continue
        raw_value = _xml_attribute_local_value(element, "value", "Value")
        if raw_value is None:
            raw_value = (element.text or "").strip() or None
        if raw_value is None:
            continue
        values.append(_read_xml_int_value(raw_value, "FeaturePot"))
    return values


def _parse_imported_credit_win_total(snippet_element: ET.Element) -> int:
    credit_win_values: list[int] = []
    for element in snippet_element.iter():
        if _xml_local_name(element.tag) != "CreditWin":
            continue
        raw_value = _xml_attribute_local_value(element, "value", "Value")
        if raw_value is None:
            raw_value = (element.text or "").strip() or None
        if raw_value is None:
            continue
        credit_win_values.append(_read_xml_int_value(raw_value, "CreditWin"))
    if credit_win_values:
        return sum(credit_win_values)

    total_win = _xml_attribute_local_value(snippet_element, "totalWin", "TotalWin")
    if total_win is not None:
        return _read_xml_int_value(total_win, "totalWin")

    for element in snippet_element.iter():
        if _xml_local_name(element.tag) != "TotalExternalWin":
            continue
        raw_value = _xml_attribute_local_value(element, "value", "Value")
        if raw_value is None:
            raw_value = (element.text or "").strip() or None
        if raw_value is not None:
            return _read_xml_int_value(raw_value, "TotalExternalWin")
    return 0


def _clone_xml_element(element: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(element, encoding="unicode"))


def _parse_imported_sae_xml_document(
    raw_xml: str,
) -> tuple[str, ET.Element, list[ET.Element], dict[ET.Element, ET.Element]]:
    snippet_xml = raw_xml.strip()
    if not snippet_xml:
        raise ValueError("Imported XML cannot be blank.")

    try:
        root = ET.fromstring(snippet_xml)
    except ET.ParseError as exc:
        raise ValueError(f"Imported XML is not well-formed: {exc}") from exc

    snippet_elements = [element for element in root.iter() if _xml_local_name(element.tag) == "Snippet"]
    parent_map = {
        child: parent
        for parent in root.iter()
        for child in list(parent)
    }
    return snippet_xml, root, snippet_elements, parent_map


def _build_single_imported_snippet_xml(
    document_xml: str,
    root: ET.Element,
    snippet_element: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    total_snippet_count: int,
) -> str:
    if total_snippet_count == 1:
        return document_xml

    snippet_clone = _clone_xml_element(snippet_element)
    root_clone = ET.Element(root.tag, dict(root.attrib))

    current = snippet_element
    category_ancestor: ET.Element | None = None
    while current in parent_map:
        current = parent_map[current]
        if _xml_local_name(current.tag) == "Category":
            category_ancestor = current
            break

    if category_ancestor is not None:
        category_clone = ET.Element(category_ancestor.tag, dict(category_ancestor.attrib))
        category_clone.append(snippet_clone)
        root_clone.append(category_clone)
    else:
        root_clone.append(snippet_clone)

    return ET.tostring(root_clone, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _parse_imported_sae_snippet_element(
    snippet_element: ET.Element,
    *,
    snippet_xml: str,
) -> "ImportedSnippetParseResult":
    snippet_name = _xml_attribute_local_value(snippet_element, "name", "Name") or IMPORTED_SNIPPET_NAME

    bet_situation = next(
        (element for element in snippet_element.iter() if _xml_local_name(element.tag) == "BetSituation"),
        None,
    )
    resolved_stake_fields: dict[str, int] = {}
    game_specific_settings: list[int] = []
    selected_bet_credits = 0
    if bet_situation is not None:
        resolved_stake_fields = {
            "lines": _xml_attribute_local_int(bet_situation, "lines", default=0),
            "bet_per_line": _xml_attribute_local_int(bet_situation, "betperline", default=0),
            "payment": _xml_attribute_local_int(bet_situation, "payment", default=1),
            "denomination_cents": _xml_attribute_local_int(bet_situation, "denomcents", default=0),
            "extra_credit": _xml_attribute_local_int(bet_situation, "extracredit", default=0),
            "side_bet": _xml_attribute_local_int(bet_situation, "sidebet", default=0),
        }
        selected_bet_credits = (
            resolved_stake_fields["lines"] * resolved_stake_fields["bet_per_line"] * resolved_stake_fields["payment"]
        ) + resolved_stake_fields["extra_credit"] + resolved_stake_fields["side_bet"]
        game_specific_settings = _parse_imported_game_specific_settings(bet_situation)

    feature_pots = _parse_imported_feature_pots(snippet_element)
    credit_win_total = _parse_imported_credit_win_total(snippet_element)
    math_summary = _build_snippet_math_summary(
        selected_bet_credits=selected_bet_credits,
        credit_win_total=credit_win_total,
    )
    player_decision_count = sum(
        1 for element in snippet_element.iter() if _xml_local_name(element.tag) == "PlayerDecision"
    )
    feature_pot_count = len(feature_pots)
    return ImportedSnippetParseResult(
        snippet_name=snippet_name,
        snippet_xml=snippet_xml,
        resolved_stake_fields=resolved_stake_fields,
        game_specific_settings=game_specific_settings,
        feature_pots=feature_pots,
        raw_random_count=_count_sgfhd_nested_reel_randnums(snippet_xml),
        player_decision_count=player_decision_count,
        feature_pot_count=feature_pot_count,
        selected_bet_credits=math_summary.selected_bet_credits,
        credit_win_total=math_summary.credit_win_total,
        jackpot_credit_total=math_summary.jackpot_credit_total,
        wager_from_win_total=math_summary.wager_from_win_total,
        expected_meter_delta=math_summary.expected_meter_delta,
    )


def parse_imported_sae_snippet_xml_batch(raw_xml: str) -> list["ImportedSnippetParseResult"]:
    document_xml, root, snippet_elements, parent_map = _parse_imported_sae_xml_document(raw_xml)
    if not snippet_elements:
        raise ValueError("Imported XML must contain at least one <Snippet> element; found 0.")

    total_snippet_count = len(snippet_elements)
    return [
        _parse_imported_sae_snippet_element(
            snippet_element,
            snippet_xml=_build_single_imported_snippet_xml(
                document_xml,
                root,
                snippet_element,
                parent_map,
                total_snippet_count,
            ),
        )
        for snippet_element in snippet_elements
    ]


def parse_imported_sae_snippet_xml(raw_xml: str) -> "ImportedSnippetParseResult":
    parsed_xmls = parse_imported_sae_snippet_xml_batch(raw_xml)
    if len(parsed_xmls) != 1:
        raise ValueError(
            f"Imported XML must contain exactly one <Snippet> element; found {len(parsed_xmls)}."
        )
    return parsed_xmls[0]


def _parse_sgf_soap_status_response(response_body: str, operation_name: str) -> None:
    try:
        root = ET.fromstring(response_body)
    except ET.ParseError as exc:
        raise RuntimeError(f"Invalid SOAP response: {exc}") from exc
    for element in root.iter():
        if _xml_local_name(element.tag) == "Fault":
            fault_text = next(
                (
                    (child.text or "").strip()
                    for child in element
                    if _xml_local_name(child.tag) in {"faultstring", "faultcode", "detail"}
                    and (child.text or "").strip()
                ),
                "Unknown SOAP fault",
            )
            raise RuntimeError(f"SOAP fault: {fault_text}")
    status_text = next(
        (
            (element.text or "").strip()
            for element in root.iter()
            if _xml_local_name(element.tag) == "status" and (element.text or "").strip()
        ),
        "",
    )
    if not status_text:
        return
    try:
        status = int(status_text)
    except ValueError as exc:
        raise RuntimeError(f"Invalid status value: {status_text}") from exc
    if status != 0:
        raise RuntimeError(f"{operation_name} returned status {status}.")


def _build_sgf_qatesting_uri(vlt_ip: str, port: int) -> str:
    return f"http://{vlt_ip}:{port}/"


def _build_sgf_qatesting_headers() -> dict[str, str]:
    return {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "",
    }


def _build_sgf_qatesting_payload(operation_name: str, inner_xml: str) -> bytes:
    payload = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" '
        'xmlns:QATesting="http://tempspielo.com">'
        "<SOAP-ENV:Body>"
        f"<QATesting:{operation_name}>"
        f"{inner_xml}"
        f"</QATesting:{operation_name}>"
        "</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    )
    return payload.encode("utf-8")


def _build_sgf_touch_invocation_payload(touch_name: str) -> bytes:
    escaped_touch_name = xml_escape(touch_name, {'"': "&quot;", "'": "&apos;"})
    return _build_sgf_qatesting_payload("TouchInvocation", f"<name>{escaped_touch_name}</name>")


def _build_sgf_get_touch_invocations_payload() -> bytes:
    return _build_sgf_qatesting_payload("GetTouchInvocations", "")


def _build_sgf_tce_buttonpress_payload(button_name: str) -> bytes:
    escaped_button_name = xml_escape(button_name, {'"': "&quot;", "'": "&apos;"})
    return _build_sgf_qatesting_payload("MechButtonPress", f"<buttonName>{escaped_button_name}</buttonName>")


class SgfQaTestingChannel:
    """Reuses one keep-alive HTTP connection per VLT destination instead of opening a fresh TCP connection per SOAP call."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._lock = threading.Lock()
        self._connection: http.client.HTTPConnection | None = None

    def _ensure_connection(self, timeout_seconds: float) -> http.client.HTTPConnection:
        if self._connection is None:
            self._connection = http.client.HTTPConnection(self.host, self.port, timeout=timeout_seconds)
        elif self._connection.sock is not None:
            self._connection.sock.settimeout(timeout_seconds)
        return self._connection

    def _close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    def request(self, payload: bytes, headers: dict[str, str], timeout_seconds: float) -> tuple[int, str, bytes]:
        with self._lock:
            last_exc: Exception = RuntimeError("no attempt made")
            # A dead keep-alive connection fails once; retry once on a fresh connection before giving up.
            for _attempt in range(2):
                connection = self._ensure_connection(timeout_seconds)
                try:
                    connection.request("POST", "/", body=payload, headers=headers)
                    response = connection.getresponse()
                    body = response.read()
                    return response.status, response.reason, body
                except (http.client.HTTPException, OSError) as exc:
                    self._close()
                    last_exc = exc
                    continue
            raise last_exc


_SGF_QA_CHANNELS: dict[tuple[str, int], SgfQaTestingChannel] = {}
_SGF_QA_CHANNELS_LOCK = threading.Lock()


def _get_sgf_qatesting_channel(vlt_ip: str, port: int) -> SgfQaTestingChannel:
    key = (vlt_ip, port)
    with _SGF_QA_CHANNELS_LOCK:
        channel = _SGF_QA_CHANNELS.get(key)
        if channel is None:
            channel = SgfQaTestingChannel(vlt_ip, port)
            _SGF_QA_CHANNELS[key] = channel
        return channel


def _send_sgf_qatesting_request(
    vlt_ip: str,
    operation_name: str,
    payload: bytes,
    port: int,
    timeout_ms: int = FORWARDER_TIMEOUT_MS,
) -> str:
    uri = _build_sgf_qatesting_uri(vlt_ip, port)
    _append_command_file_log(
        "SOAP POST",
        uri,
        f"operation={operation_name} payload_bytes={len(payload)}",
    )
    channel = _get_sgf_qatesting_channel(vlt_ip, port)
    try:
        status, reason, body_bytes = channel.request(payload, _build_sgf_qatesting_headers(), timeout_ms / 1000)
    except (http.client.HTTPException, OSError) as exc:
        raise RuntimeError(f"transport error to {uri}: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"unexpected SOAP request error to {uri}: {exc}") from exc
    body = body_bytes.decode("utf-8", errors="replace")
    if status >= 400:
        raise RuntimeError(f"HTTP {status} {reason}; body={body}")
    return body


def send_sgf_touch_invocation(
    vlt_ip: str,
    touch_name: str,
    port: int = SGF_QATESTING_VLT_PORT,
    timeout_ms: int = FORWARDER_TIMEOUT_MS,
) -> None:
    body = _send_sgf_qatesting_request(
        vlt_ip,
        "TouchInvocation",
        _build_sgf_touch_invocation_payload(touch_name),
        port=port,
        timeout_ms=timeout_ms,
    )
    try:
        _parse_sgf_soap_status_response(body, "TouchInvocation")
    except Exception as exc:
        raise RuntimeError(f"{exc} at {_build_sgf_qatesting_uri(vlt_ip, port)}") from exc


def send_sgf_tce_buttonpress(
    vlt_ip: str,
    button_name: str,
    port: int = SGF_PREFERRED_BUTTONPRESS_PORT,
    timeout_ms: int = FORWARDER_TIMEOUT_MS,
) -> None:
    body = _send_sgf_qatesting_request(
        vlt_ip,
        "MechButtonPress",
        _build_sgf_tce_buttonpress_payload(button_name),
        port=port,
        timeout_ms=timeout_ms,
    )
    try:
        _parse_sgf_soap_status_response(body, "MechButtonPress")
    except Exception as exc:
        raise RuntimeError(f"{exc} at {_build_sgf_qatesting_uri(vlt_ip, port)}") from exc


def get_sgf_touch_invocations(
    vlt_ip: str,
    port: int = SGF_QATESTING_VLT_PORT,
    timeout_ms: int = FORWARDER_TIMEOUT_MS,
) -> list[str]:
    body = _send_sgf_qatesting_request(
        vlt_ip,
        "GetTouchInvocations",
        _build_sgf_get_touch_invocations_payload(),
        port=port,
        timeout_ms=timeout_ms,
    )
    root = ET.fromstring(body)
    _parse_sgf_soap_status_response(body, "GetTouchInvocations")
    touches: list[str] = []
    for element in root.iter():
        if _xml_local_name(element.tag) == "m-Touches":
            text = (element.text or "").strip()
            if text:
                touches.append(text)
    return touches


def choose_sgf_spin_touch(touches: list[str]) -> str | None:
    for keyword in SGF_SPIN_TOUCH_KEYWORDS:
        for touch in touches:
            if keyword in touch.lower():
                return touch
    for touch in touches:
        if "play" in touch.lower():
            return touch
    return None


def _build_sgf_spin_touch_candidates(touches: list[str]) -> list[str]:
    candidates: list[str] = []
    primary = choose_sgf_spin_touch(touches)
    for touch in ([primary] if primary else []):
        if touch and touch not in candidates:
            candidates.append(touch)
    for touch in touches:
        if touch not in candidates and any(keyword in touch.lower() for keyword in SGF_SPIN_TOUCH_KEYWORDS) \
                and not any(k in touch.lower() for k in SGF_STOP_TOUCH_KEYWORDS):
            candidates.append(touch)
    for touch in SGF_DEFAULT_SPIN_TOUCH_CANDIDATES:
        if touch not in candidates:
            candidates.append(touch)
    return candidates


def try_sgf_tce_buttonpress_ports(
    vlt_ip: str,
    button_name: str,
    ports: tuple[int, ...] = SGF_FALLBACK_BUTTONPRESS_PORTS,
    timeout_ms: int = FORWARDER_TIMEOUT_MS,
) -> int:
    errors: list[str] = []
    for port in ports:
        try:
            send_sgf_tce_buttonpress(vlt_ip, button_name, port=port, timeout_ms=timeout_ms)
            return port
        except Exception as exc:
            errors.append(f"{port}: {exc}")
    if errors:
        raise RuntimeError("; ".join(errors))
    raise RuntimeError("No buttonpress ports configured.")


_SGF_SPIN_TOUCH_CACHE: dict[str, str] = {}
_SGF_SPIN_TOUCH_CACHE_LOCK = threading.Lock()


def _get_cached_sgf_spin_touch(vlt_ip: str) -> str | None:
    with _SGF_SPIN_TOUCH_CACHE_LOCK:
        return _SGF_SPIN_TOUCH_CACHE.get(vlt_ip)


def _set_cached_sgf_spin_touch(vlt_ip: str, touch_name: str) -> None:
    with _SGF_SPIN_TOUCH_CACHE_LOCK:
        _SGF_SPIN_TOUCH_CACHE[vlt_ip] = touch_name


def _clear_cached_sgf_spin_touch(vlt_ip: str) -> None:
    with _SGF_SPIN_TOUCH_CACHE_LOCK:
        _SGF_SPIN_TOUCH_CACHE.pop(vlt_ip, None)


def trigger_sgf_autospin_input(
    vlt_ip: str,
    button_name: str = SGF_AUTOSPIN_BUTTON_NAME,
    timeout_ms: int = FORWARDER_TIMEOUT_MS,
) -> str:
    cached_touch = _get_cached_sgf_spin_touch(vlt_ip)
    if cached_touch is not None:
        try:
            send_sgf_touch_invocation(
                vlt_ip,
                cached_touch,
                port=SGF_QATESTING_VLT_PORT,
                timeout_ms=timeout_ms,
            )
            return f"SGF autospin accepted: TouchInvocation on {SGF_QATESTING_VLT_PORT} for '{cached_touch}' (cached)."
        except Exception:
            # Cached touch no longer valid (e.g. game/snippet changed); fall back to a full re-resolve.
            _clear_cached_sgf_spin_touch(vlt_ip)

    touches: list[str] = []
    for attempt in range(SGF_TOUCH_QUERY_MAX_RETRIES + 1):
        try:
            touches = get_sgf_touch_invocations(vlt_ip, port=SGF_QATESTING_VLT_PORT, timeout_ms=timeout_ms)
        except Exception:
            touches = []
        if choose_sgf_spin_touch(touches) is not None:
            break
        if attempt < SGF_TOUCH_QUERY_MAX_RETRIES:
            # Game may not yet expose the spin button immediately after snippet load
            time.sleep(SGF_TOUCH_QUERY_RETRY_INTERVAL_SECONDS)
    touch_candidates = _build_sgf_spin_touch_candidates(touches)
    touch_errors: list[str] = []
    for touch_candidate in touch_candidates:
        try:
            send_sgf_touch_invocation(
                vlt_ip,
                touch_candidate,
                port=SGF_QATESTING_VLT_PORT,
                timeout_ms=timeout_ms,
            )
            _set_cached_sgf_spin_touch(vlt_ip, touch_candidate)
            return f"SGF autospin accepted: TouchInvocation on {SGF_QATESTING_VLT_PORT} for '{touch_candidate}'."
        except Exception as exc:
            touch_errors.append(f"{touch_candidate}: {exc}")
    accepted_port = try_sgf_tce_buttonpress_ports(
        vlt_ip,
        button_name,
        ports=SGF_FALLBACK_BUTTONPRESS_PORTS,
        timeout_ms=timeout_ms,
    )
    if touch_errors:
        return (
            f"SGF autospin accepted: MechButtonPress on {accepted_port} for '{button_name}' "
            f"after TouchInvocation attempts failed ({'; '.join(touch_errors)})."
        )
    return f"SGF autospin accepted: MechButtonPress on {accepted_port} for '{button_name}'."


@dataclass(frozen=True)
class TouchScreenInfo:
    name: str
    x: int
    y: int
    width: int
    height: int
    rotate: str = "normal"
    touchscreen_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class TouchBounds:
    min_x: int
    max_x: int
    min_y: int
    max_y: int
    bottom_exclusion: int


@dataclass(frozen=True)
class TouchRawAxisRange:
    label: str
    min_value: float
    max_value: float


@dataclass
class TouchXInputDevice:
    device_id: int
    name: str
    device_node: str | None = None
    coordinate_transform_matrix: list[float] = field(default_factory=list)
    axis_ranges: dict[str, TouchRawAxisRange] = field(default_factory=dict)
    has_touch_class: bool = False
    touch_mode: str | None = None
    max_touches: int | None = None


@dataclass(frozen=True)
class TouchProbeResult:
    backend: str
    available_backends: list[str]
    xinput_device_id: int
    device_path: str
    device_name: str
    coordinate_transform_matrix: list[float]
    x_axis: TouchRawAxisRange
    y_axis: TouchRawAxisRange
    supports_mt_axes: bool
    supports_classic_axes: bool


@dataclass(frozen=True)
class TouchCommandResult:
    exit_status: int
    stdout: str
    stderr: str


def _require_paramiko() -> Any:
    if paramiko is None:
        base_message = (
            f"paramiko is required for Pick-a-Prize touching but could not be imported: {PARAMIKO_IMPORT_ERROR}"
        )
        if getattr(sys, "frozen", False):
            raise RuntimeError(
                f"{base_message} The packaged executable is missing the bundled 'paramiko' dependency. "
                "Rebuild dist\\SASautomator.exe from SASautomator.spec after confirming paramiko is installed in "
                "the build environment."
            )
        raise RuntimeError(
            f"{base_message} Install it into the active '.venv311' environment used by "
            "run_sasautomator.ps1/run_sasautomator.cmd, for example: "
            r".venv311\Scripts\python.exe -m pip install paramiko"
        )
    return paramiko


def _open_pick_a_prize_ssh_client(host: str) -> Any:
    paramiko_module = _require_paramiko()
    client = paramiko_module.SSHClient()
    client.set_missing_host_key_policy(paramiko_module.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=PICK_A_PRIZE_SSH_PORT,
        username=PICK_A_PRIZE_SSH_USERNAME,
        password=PICK_A_PRIZE_SSH_PASSWORD,
        timeout=PICK_A_PRIZE_SSH_CONNECT_TIMEOUT_SECONDS,
        banner_timeout=PICK_A_PRIZE_SSH_CONNECT_TIMEOUT_SECONDS,
        auth_timeout=PICK_A_PRIZE_SSH_CONNECT_TIMEOUT_SECONDS,
    )
    transport = client.get_transport()
    if transport is not None:
        transport.set_keepalive(30)
    return client


def _run_pick_a_prize_remote_command(
    client: Any,
    shell_script: str,
    timeout_seconds: int = PICK_A_PRIZE_REMOTE_COMMAND_TIMEOUT_SECONDS,
) -> TouchCommandResult:
    wrapped_command = f"sh -lc {shlex.quote(shell_script)}"
    _append_command_file_log(
        "SSH command",
        "pick-a-prize",
        f"command={wrapped_command}",
    )
    stdin, stdout, stderr = client.exec_command(wrapped_command, timeout=timeout_seconds)
    del stdin
    exit_status = stdout.channel.recv_exit_status()
    stdout_text = stdout.read().decode("utf-8", errors="replace")
    stderr_text = stderr.read().decode("utf-8", errors="replace")
    return TouchCommandResult(exit_status=exit_status, stdout=stdout_text, stderr=stderr_text)


def _read_pick_a_prize_remote_file(sftp: Any, remote_path: str) -> str:
    with sftp.file(remote_path, "r") as remote_file:
        return remote_file.read().decode("utf-8", errors="replace")


def _parse_pick_a_prize_screens_info(text: str) -> dict[str, TouchScreenInfo]:
    screens: dict[str, TouchScreenInfo] = {}
    lines = text.splitlines()
    key_pattern = re.compile(r"^(x|y|width|height)\s+(-?\d+)$")
    rotate_pattern = re.compile(r"^rotate\s+(.+)$")
    touchscreen_id_pattern = re.compile(r'^(\d+)\s+".*"$')
    index = 0

    while index < len(lines):
        current = lines[index].strip()
        if not current or current in {"{", "}"}:
            index += 1
            continue

        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if next_line != "{":
            index += 1
            continue

        block_name = current
        index += 2
        depth = 1
        block_values: dict[str, int | str] = {}
        touchscreen_ids: list[int] = []

        while index < len(lines) and depth > 0:
            raw_line = lines[index].strip()
            if raw_line == "{":
                depth += 1
                index += 1
                continue
            if raw_line == "}":
                depth -= 1
                index += 1
                continue

            if depth == 1:
                match = key_pattern.match(raw_line)
                if match:
                    block_values[match.group(1)] = int(match.group(2))
                    index += 1
                    continue

                rotate_match = rotate_pattern.match(raw_line)
                if rotate_match:
                    block_values["rotate"] = rotate_match.group(1).strip()
                    index += 1
                    continue

                if (
                    raw_line == "Touchscreens"
                    and index + 1 < len(lines)
                    and lines[index + 1].strip() == "{"
                ):
                    index += 2
                    nested_depth = 1
                    while index < len(lines) and nested_depth > 0:
                        nested_line = lines[index].strip()
                        if nested_line == "{":
                            nested_depth += 1
                        elif nested_line == "}":
                            nested_depth -= 1
                        elif nested_depth == 1:
                            nested_match = touchscreen_id_pattern.match(nested_line)
                            if nested_match:
                                touchscreen_ids.append(int(nested_match.group(1)))
                        index += 1
                    continue

            index += 1

        if {"x", "y", "width", "height"}.issubset(block_values):
            screens[block_name] = TouchScreenInfo(
                name=block_name,
                x=int(block_values["x"]),
                y=int(block_values["y"]),
                width=int(block_values["width"]),
                height=int(block_values["height"]),
                rotate=str(block_values.get("rotate", "normal")),
                touchscreen_ids=touchscreen_ids,
            )

    return screens


def _compute_pick_a_prize_touch_bounds(screen: TouchScreenInfo) -> TouchBounds:
    bottom_exclusion = 180 if screen.height >= 2160 else 120
    top_exclusion = 280 if screen.height >= 2160 else 170
    min_x = 0
    max_x = screen.width - 1
    min_y = top_exclusion
    max_y = screen.height - bottom_exclusion - 1
    if min_x > max_x or min_y > max_y:
        raise ValueError(
            f"Computed invalid touch bounds for {screen.name}: x={min_x}..{max_x}, y={min_y}..{max_y}"
        )
    return TouchBounds(
        min_x=min_x,
        max_x=max_x,
        min_y=min_y,
        max_y=max_y,
        bottom_exclusion=bottom_exclusion,
    )


def _transform_pick_a_prize_touch_coordinates(
    screen: TouchScreenInfo,
    local_x: int,
    local_y: int,
) -> tuple[int, int, int, int, str]:
    if screen.height >= 3840:
        if screen.rotate == "right":
            transformed_x = screen.height - 1 - local_y
            transformed_y = local_x
            orientation_mode = "portrait-right"
        else:
            transformed_x = local_y
            transformed_y = screen.width - 1 - local_x
            orientation_mode = "portrait-left"
        return (
            transformed_x,
            transformed_y,
            screen.height,
            screen.width,
            orientation_mode,
        )
    return (local_x, local_y, screen.width, screen.height, "landscape")


def _parse_pick_a_prize_available_backends(stdout_text: str) -> list[str]:
    found_paths: dict[str, str] = {}
    pattern = re.compile(r"^TOOL:([^=]+)=(.*)$")
    for line in stdout_text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        tool_name = match.group(1)
        tool_path = match.group(2).strip()
        if tool_path:
            found_paths[tool_name] = tool_path
    return [tool for tool in PICK_A_PRIZE_TOOL_PRIORITY if tool in found_paths]


def _parse_pick_a_prize_xinput_devices(stdout_text: str) -> dict[int, TouchXInputDevice]:
    marker = "__XINPUT_LIST_LONG__"
    marker_index = stdout_text.find(marker)
    if marker_index == -1:
        raise RuntimeError("Remote probe output did not include the xinput device list section.")

    remainder = stdout_text[marker_index + len(marker):]
    lines = remainder.splitlines()
    devices: dict[int, TouchXInputDevice] = {}
    current_device: TouchXInputDevice | None = None
    pending_axis_label: str | None = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("__XINPUT_PROPS__:"):
            break

        device_match = re.search(r"\bid=(\d+)\b", raw_line)
        if device_match:
            device_id = int(device_match.group(1))
            name_prefix = raw_line[: device_match.start()].rstrip()
            name = re.sub(r"^[^A-Za-z0-9]+", "", name_prefix).strip()
            current_device = TouchXInputDevice(device_id=device_id, name=name)
            devices[device_id] = current_device
            pending_axis_label = None
            continue

        if current_device is None:
            continue

        if "Type: XITouchClass" in stripped:
            current_device.has_touch_class = True
            continue
        if stripped.startswith("Touch mode:"):
            current_device.touch_mode = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("Max number of touches:"):
            value = stripped.split(":", 1)[1].strip()
            if value.isdigit():
                current_device.max_touches = int(value)
            continue
        if stripped.startswith("Label:"):
            pending_axis_label = stripped.split(":", 1)[1].strip().strip('"')
            continue
        if stripped.startswith("Range:") and pending_axis_label:
            range_match = re.match(r"Range:\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)$", stripped)
            if range_match:
                current_device.axis_ranges[pending_axis_label] = TouchRawAxisRange(
                    label=pending_axis_label,
                    min_value=float(range_match.group(1)),
                    max_value=float(range_match.group(2)),
                )
            pending_axis_label = None

    return devices


def _apply_pick_a_prize_xinput_properties(stdout_text: str, devices: dict[int, TouchXInputDevice]) -> None:
    props_pattern = re.compile(r"^__XINPUT_PROPS__:(\d+)$")
    current_device: TouchXInputDevice | None = None

    for raw_line in stdout_text.splitlines():
        stripped = raw_line.strip()
        section_match = props_pattern.match(stripped)
        if section_match:
            current_device = devices.get(int(section_match.group(1)))
            continue
        if current_device is None:
            continue
        if "Device Node" in stripped:
            node_match = re.search(r'"([^"]+)"', stripped)
            if node_match:
                current_device.device_node = node_match.group(1)
            continue
        if stripped.startswith("Coordinate Transformation Matrix"):
            matrix_values = stripped.split(":", 1)[1].strip()
            current_device.coordinate_transform_matrix = [
                float(value.strip())
                for value in matrix_values.split(",")
                if value.strip()
            ]


def _resolve_pick_a_prize_main_touch_device(
    screen: TouchScreenInfo,
    xinput_devices: dict[int, TouchXInputDevice],
) -> TouchXInputDevice:
    candidates: list[tuple[int, TouchXInputDevice]] = []
    for device_id in screen.touchscreen_ids:
        device = xinput_devices.get(device_id)
        if device is None or not device.device_node:
            continue
        score = 0
        lowered_name = device.name.lower()
        supports_mt = (
            "Abs MT Position X" in device.axis_ranges
            and "Abs MT Position Y" in device.axis_ranges
        )
        supports_classic = "Abs X" in device.axis_ranges and "Abs Y" in device.axis_ranges
        if device.has_touch_class:
            score += 100
        if device.touch_mode == "direct":
            score += 40
        if device.max_touches and device.max_touches > 1:
            score += 20
        if supports_mt:
            score += 40
        if supports_classic:
            score += 10
        if len(device.coordinate_transform_matrix) == 9:
            score += 10
        if "unknown" in lowered_name:
            score -= 50
        candidates.append((score, device))

    if not candidates:
        raise RuntimeError(
            f"Could not resolve a usable xinput device node for {screen.name}. "
            f"Touchscreen IDs from {PICK_A_PRIZE_SCREENS_INFO_PATH}: {screen.touchscreen_ids}"
        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _probe_pick_a_prize_remote_environment(client: Any, screen: TouchScreenInfo) -> TouchProbeResult:
    if not screen.touchscreen_ids:
        raise RuntimeError(
            f"{screen.name} in {PICK_A_PRIZE_SCREENS_INFO_PATH} does not list any touchscreen IDs."
        )

    touch_ids = " ".join(str(device_id) for device_id in screen.touchscreen_ids)
    probe_script = f"""
if ! command -v xinput >/dev/null 2>&1; then
  echo "xinput is required for touchscreen mapping" >&2
  exit 1
fi
for tool in evemu-event sendevent perl; do
  path="$(command -v "$tool" 2>/dev/null || true)"
  printf 'TOOL:%s=%s\\n' "$tool" "$path"
done
printf '__XINPUT_LIST_LONG__\\n'
DISPLAY={shlex.quote(PICK_A_PRIZE_XINPUT_DISPLAY)} xinput list --long 2>/dev/null || true
for id in {touch_ids}; do
  printf '\\n__XINPUT_PROPS__:%s\\n' "$id"
  DISPLAY={shlex.quote(PICK_A_PRIZE_XINPUT_DISPLAY)} xinput list-props "$id" 2>/dev/null || true
done
""".strip()

    result = _run_pick_a_prize_remote_command(client, probe_script)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote xinput probe failed with exit code {result.exit_status}.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    available_backends = _parse_pick_a_prize_available_backends(result.stdout)
    if not available_backends:
        raise RuntimeError(
            "No supported device-specific touch backend was found. Expected one of: evemu-event, sendevent, perl."
        )

    xinput_devices = _parse_pick_a_prize_xinput_devices(result.stdout)
    if not xinput_devices:
        raise RuntimeError(
            f"xinput list --long returned no parsable devices for DISPLAY={PICK_A_PRIZE_XINPUT_DISPLAY}."
        )

    _apply_pick_a_prize_xinput_properties(result.stdout, xinput_devices)
    selected_device = _resolve_pick_a_prize_main_touch_device(screen, xinput_devices)
    mt_x = selected_device.axis_ranges.get("Abs MT Position X")
    mt_y = selected_device.axis_ranges.get("Abs MT Position Y")
    classic_x = selected_device.axis_ranges.get("Abs X")
    classic_y = selected_device.axis_ranges.get("Abs Y")
    supports_mt_axes = mt_x is not None and mt_y is not None
    supports_classic_axes = classic_x is not None and classic_y is not None
    if supports_mt_axes:
        x_axis = mt_x
        y_axis = mt_y
    elif supports_classic_axes:
        x_axis = classic_x
        y_axis = classic_y
    else:
        raise RuntimeError(
            f"Resolved xinput device id={selected_device.device_id} "
            f"({selected_device.name}) does not expose usable X/Y axes."
        )
    return TouchProbeResult(
        backend=available_backends[0],
        available_backends=available_backends,
        xinput_device_id=selected_device.device_id,
        device_path=selected_device.device_node or "",
        device_name=selected_device.name,
        coordinate_transform_matrix=selected_device.coordinate_transform_matrix,
        x_axis=x_axis,
        y_axis=y_axis,
        supports_mt_axes=supports_mt_axes,
        supports_classic_axes=supports_classic_axes,
    )


def _choose_pick_a_prize_random_coordinate(bounds: TouchBounds) -> tuple[int, int]:
    return (
        random.randint(bounds.min_x, bounds.max_x),
        random.randint(bounds.min_y, bounds.max_y),
    )


def _scale_pick_a_prize_pixel_to_raw(pixel: int, pixel_span: int, axis: TouchRawAxisRange) -> int:
    if pixel_span <= 1:
        return int(round(axis.min_value))
    clamped_pixel = max(0, min(pixel, pixel_span - 1))
    scaled = axis.min_value + (
        clamped_pixel * (axis.max_value - axis.min_value) / (pixel_span - 1)
    )
    return int(round(scaled))


def _build_pick_a_prize_touch_script(
    backend: str,
    device_path: str,
    raw_x: int,
    raw_y: int,
    supports_mt_axes: bool,
    supports_classic_axes: bool,
) -> str:
    if backend == "evemu-event":
        return _build_pick_a_prize_evemu_script(
            device_path=device_path,
            raw_x=raw_x,
            raw_y=raw_y,
            supports_mt_axes=supports_mt_axes,
            supports_classic_axes=supports_classic_axes,
        )
    if backend == "sendevent":
        return _build_pick_a_prize_sendevent_script(
            device_path=device_path,
            raw_x=raw_x,
            raw_y=raw_y,
            supports_mt_axes=supports_mt_axes,
            supports_classic_axes=supports_classic_axes,
        )
    if backend == "perl":
        return _build_pick_a_prize_perl_script(
            device_path=device_path,
            raw_x=raw_x,
            raw_y=raw_y,
            supports_mt_axes=supports_mt_axes,
            supports_classic_axes=supports_classic_axes,
        )
    raise ValueError(f"Unsupported backend: {backend}")


def _build_pick_a_prize_evemu_script(
    device_path: str,
    raw_x: int,
    raw_y: int,
    supports_mt_axes: bool,
    supports_classic_axes: bool,
) -> str:
    quoted_device = shlex.quote(device_path)
    mt_lines = ""
    if supports_mt_axes:
        mt_lines = """
try_evemu --type EV_ABS --code ABS_MT_SLOT --value 0 || true
try_evemu --type EV_ABS --code ABS_MT_TRACKING_ID --value 1 || true
try_evemu --type EV_ABS --code ABS_MT_POSITION_X --value "$RAW_X" || true
try_evemu --type EV_ABS --code ABS_MT_POSITION_Y --value "$RAW_Y" || true
""".strip()
    classic_lines = ""
    if supports_classic_axes:
        classic_lines = """
try_evemu --type EV_ABS --code ABS_X --value "$RAW_X" || true
try_evemu --type EV_ABS --code ABS_Y --value "$RAW_Y" || true
""".strip()
    release_mt_lines = ""
    if supports_mt_axes:
        release_mt_lines = 'try_evemu --type EV_ABS --code ABS_MT_TRACKING_ID --value -1 || true'

    command_parts = [
        f"DEVICE={quoted_device}",
        f"RAW_X={raw_x}",
        f"RAW_Y={raw_y}",
        "SUCCESS_COUNT=0",
        """
try_evemu() {
  if evemu-event "$DEVICE" "$@" >/dev/null 2>&1; then
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    return 0
  fi
  return 1
}
""".strip(),
    ]
    if mt_lines:
        command_parts.append(mt_lines)
    if classic_lines:
        command_parts.append(classic_lines)
    command_parts.append(
        """
try_evemu --type EV_KEY --code BTN_TOOL_FINGER --value 1 || true
try_evemu --type EV_KEY --code BTN_TOUCH --value 1 || true
try_evemu --sync || true
sleep 0.05
""".strip()
    )
    if release_mt_lines:
        command_parts.append(release_mt_lines)
    command_parts.append(
        """
try_evemu --type EV_KEY --code BTN_TOUCH --value 0 || true
try_evemu --type EV_KEY --code BTN_TOOL_FINGER --value 0 || true
try_evemu --sync || true
if [ "$SUCCESS_COUNT" -eq 0 ]; then
  echo "evemu-event did not accept any injected touch steps" >&2
  exit 1
fi
""".strip()
    )
    return "\n".join(command_parts)


def _build_pick_a_prize_sendevent_script(
    device_path: str,
    raw_x: int,
    raw_y: int,
    supports_mt_axes: bool,
    supports_classic_axes: bool,
) -> str:
    quoted_device = shlex.quote(device_path)
    command_parts = [
        f"DEVICE={quoted_device}",
        f"RAW_X={raw_x}",
        f"RAW_Y={raw_y}",
        "SUCCESS_COUNT=0",
        """
try_send() {
  if sendevent "$DEVICE" "$1" "$2" "$3" >/dev/null 2>&1; then
    SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    return 0
  fi
  return 1
}
""".strip(),
    ]
    if supports_mt_axes:
        command_parts.append(
            """
try_send 3 47 0 || true
try_send 3 57 1 || true
try_send 3 53 "$RAW_X" || true
try_send 3 54 "$RAW_Y" || true
""".strip()
        )
    if supports_classic_axes:
        command_parts.append(
            """
try_send 3 0 "$RAW_X" || true
try_send 3 1 "$RAW_Y" || true
""".strip()
        )
    command_parts.append(
        """
try_send 1 325 1 || true
try_send 1 330 1 || true
try_send 0 0 0 || true
sleep 0.05
""".strip()
    )
    if supports_mt_axes:
        command_parts.append('try_send 3 57 -1 || true')
    command_parts.append(
        """
try_send 1 330 0 || true
try_send 1 325 0 || true
try_send 0 0 0 || true
if [ "$SUCCESS_COUNT" -eq 0 ]; then
  echo "sendevent did not accept any injected touch steps" >&2
  exit 1
fi
""".strip()
    )
    return "\n".join(command_parts)


def _build_pick_a_prize_perl_script(
    device_path: str,
    raw_x: int,
    raw_y: int,
    supports_mt_axes: bool,
    supports_classic_axes: bool,
) -> str:
    quoted_device = shlex.quote(device_path)
    return f"""
DEVICE={quoted_device}
RAW_X={raw_x}
RAW_Y={raw_y}
USE_MT={1 if supports_mt_axes else 0}
USE_CLASSIC={1 if supports_classic_axes else 0}
perl - "$DEVICE" "$RAW_X" "$RAW_Y" "$USE_MT" "$USE_CLASSIC" <<'PERL'
use strict;
use warnings;
use Fcntl qw(O_RDWR);

my ($device, $raw_x, $raw_y, $use_mt, $use_classic) = @ARGV;
sysopen(my $fh, $device, O_RDWR) or die "Failed to open $device for writing: $!";

sub emit_event {{
    my ($type, $code, $value) = @_;
    my $payload = pack("l!l!s!s!i!", 0, 0, $type, $code, $value);
    my $written = syswrite($fh, $payload);
    die "Failed to write touch event: $!" unless defined $written and $written == length($payload);
}}

my @press = ();
if ($use_mt) {{
    push @press,
        [3, 47, 0],
        [3, 57, 1],
        [3, 53, $raw_x],
        [3, 54, $raw_y];
}}
if ($use_classic) {{
    push @press,
        [3, 0, $raw_x],
        [3, 1, $raw_y];
}}
push @press,
    [1, 325, 1],
    [1, 330, 1],
    [0, 0, 0];

my @release = ();
if ($use_mt) {{
    push @release, [3, 57, -1];
}}
push @release,
    [1, 330, 0],
    [1, 325, 0],
    [0, 0, 0];

for my $event (@press) {{
    emit_event(@$event);
}}

select(undef, undef, undef, 0.05);

for my $event (@release) {{
    emit_event(@$event);
}}
PERL
""".strip()


def _send_pick_a_prize_touch(client: Any, probe: TouchProbeResult, raw_x: int, raw_y: int) -> None:
    shell_script = _build_pick_a_prize_touch_script(
        backend=probe.backend,
        device_path=probe.device_path,
        raw_x=raw_x,
        raw_y=raw_y,
        supports_mt_axes=probe.supports_mt_axes,
        supports_classic_axes=probe.supports_classic_axes,
    )
    result = _run_pick_a_prize_remote_command(client, shell_script)
    if result.exit_status != 0:
        raise RuntimeError(
            f"Remote touch command failed for backend '{probe.backend}' "
            f"on xinput id={probe.xinput_device_id} ({probe.device_path}) "
            f"with exit code {result.exit_status}.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


class PickAPrizeTouchSession:
    def __init__(self, host: str) -> None:
        self.host = host
        self.client: Any | None = None
        self.sftp: Any | None = None
        self.screen: TouchScreenInfo | None = None
        self.bounds: TouchBounds | None = None
        self.probe: TouchProbeResult | None = None

    def connect(self) -> None:
        if self.client is not None and self.sftp is not None and self.probe is not None and self.bounds is not None:
            return
        self.client = _open_pick_a_prize_ssh_client(self.host)
        self.sftp = self.client.open_sftp()
        screens_info_text = _read_pick_a_prize_remote_file(self.sftp, PICK_A_PRIZE_SCREENS_INFO_PATH)
        screens = _parse_pick_a_prize_screens_info(screens_info_text)
        if PICK_A_PRIZE_MAIN_SCREEN_NAME not in screens:
            raise RuntimeError(
                f"Could not find the '{PICK_A_PRIZE_MAIN_SCREEN_NAME}' screen in {PICK_A_PRIZE_SCREENS_INFO_PATH}."
            )
        self.screen = screens[PICK_A_PRIZE_MAIN_SCREEN_NAME]
        self.bounds = _compute_pick_a_prize_touch_bounds(self.screen)
        self.probe = _probe_pick_a_prize_remote_environment(self.client, self.screen)

    def send_random_touch(self) -> str:
        self.connect()
        if self.screen is None or self.bounds is None or self.probe is None or self.client is None:
            raise RuntimeError("Pick-a-Prize touch session is not initialized.")
        local_x, local_y = _choose_pick_a_prize_random_coordinate(self.bounds)
        transformed_x, transformed_y, x_span, y_span, orientation_mode = _transform_pick_a_prize_touch_coordinates(
            self.screen,
            local_x,
            local_y,
        )
        raw_x = _scale_pick_a_prize_pixel_to_raw(transformed_x, x_span, self.probe.x_axis)
        raw_y = _scale_pick_a_prize_pixel_to_raw(transformed_y, y_span, self.probe.y_axis)
        _send_pick_a_prize_touch(self.client, self.probe, raw_x, raw_y)
        return (
            f"Pick-a-Prize touch sent: mode={orientation_mode} "
            f"local=({local_x}, {local_y}) raw=({raw_x}, {raw_y}) via {self.probe.device_path}."
        )

    def close(self) -> None:
        if self.sftp is not None:
            self.sftp.close()
            self.sftp = None
        if self.client is not None:
            self.client.close()
            self.client = None
        self.screen = None
        self.bounds = None
        self.probe = None


class PickAPrizeTouchController:
    def __init__(
        self,
        host: str,
        *,
        on_running_changed: Callable[[bool], None] | None = None,
        on_touch_message: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self._on_running_changed = on_running_changed
        self._on_touch_message = on_touch_message
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._errors: list[Exception] = []
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        with self._lock:
            if self._running or self._errors:
                return
            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run,
                args=(self._stop_event,),
                daemon=True,
                name="PickAPrizeTouchController",
            )
            self._running = True
            thread = self._thread
        self._emit_running_changed(True)
        thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread is None or thread is threading.current_thread():
            return
        try:
            thread.join(timeout=2.0)
        except RuntimeError:
            pass

    def raise_if_failed(self) -> None:
        with self._lock:
            if not self._errors:
                return
            error = self._errors[0]
        raise RuntimeError(f"Pick-a-Prize touch loop failed: {error}") from error

    def _run(self, stop_event: threading.Event) -> None:
        touch_count = 0
        session = PickAPrizeTouchSession(self.host)
        try:
            session.connect()
            while not stop_event.is_set():
                touch_count += 1
                touch_message = session.send_random_touch()
                if touch_count == 1 or touch_count % 10 == 0:
                    self._emit_touch_message(f"{touch_message} (touch #{touch_count})")
                if stop_event.wait(PICK_A_PRIZE_TOUCH_INTERVAL_SECONDS):
                    break
        except Exception as exc:
            with self._lock:
                self._errors.append(exc)
        finally:
            session.close()
            with self._lock:
                self._running = False
                if self._thread is threading.current_thread():
                    self._thread = None
            self._emit_running_changed(False)

    def _emit_running_changed(self, is_running: bool) -> None:
        if self._on_running_changed is None:
            return
        try:
            self._on_running_changed(is_running)
        except Exception:
            pass

    def _emit_touch_message(self, message: str) -> None:
        if self._on_touch_message is None:
            return
        try:
            self._on_touch_message(message)
        except Exception:
            pass


def _find_dotnet_type(system_module: Any, *candidate_names: str) -> Any:
    type_class = getattr(system_module, "Type", None)
    short_names = {name.rsplit(".", 1)[-1] for name in candidate_names}
    if type_class is not None:
        for name in candidate_names:
            try:
                found = type_class.GetType(name, False)
            except TypeError:
                found = type_class.GetType(name)
            except Exception:
                found = None
            if found is not None:
                return found
    try:
        assemblies = list(system_module.AppDomain.CurrentDomain.GetAssemblies())
    except Exception:
        assemblies = []
    for assembly in assemblies:
        try:
            types = list(assembly.GetTypes())
        except Exception:
            continue
        for dotnet_type in types:
            full_name = getattr(dotnet_type, "FullName", "")
            name = getattr(dotnet_type, "Name", "")
            if full_name in candidate_names or name in short_names:
                return dotnet_type
    return None


class ReplayValueType(IntEnum):
    RANDOM_NUMBER = 1
    PLAYER_DECISION = 2


class GameType:
    UGF = "UGF"
    SGF = "SGF"
    ALL = (UGF, SGF)


@dataclass(frozen=True)
class StakeFieldDefinition:
    name: str
    qt_constant_name: str
    prompt_label: str


STAKE_FIELD_DEFINITIONS = (
    StakeFieldDefinition("lines", "PTI_STAKE_ITEM_SEL_LINES", "Lines"),
    StakeFieldDefinition("bet_per_line", "PTI_STAKE_ITEM_SEL_BPLN", "Bet per line"),
    StakeFieldDefinition("payment", "PTI_STAKE_ITEM_SEL_PAYMENT", "Payment"),
    StakeFieldDefinition("denomination_cents", "PTI_STAKE_ITEM_SEL_DENOM_CENTS", "Denomination cents"),
    StakeFieldDefinition("extra_credit", "PTI_STAKE_ITEM_EXTRA_CREDIT", "Extra credit"),
    StakeFieldDefinition("side_bet", "PTI_STAKE_ITEM_SIDE_BET", "Side bet"),
)


@dataclass
class GenerationConfig:
    paytable_path: Path
    qtpti_path: Path
    snippet_count: int
    game_type: str
    variant_index: int
    stake_overrides: dict[str, int | None]
    game_specific_stake_items: dict[int, int]
    output_xml_path: Path
    audit_jsonl_path: Path
    run_id: str
    category_name: str = CATEGORY_NAME
    seed: int | None = None
    vlt_connection: "VltConnectionConfig | None" = None
    vlt_connection_verified: bool = False


@dataclass(frozen=True)
class VltConnectionConfig:
    ip_address: str
    port: int = UGF_VLT_PORT
    timeout_seconds: float = UGF_CONNECT_TIMEOUT_SECONDS


@dataclass
class ManualSendPaths:
    manual_send_dir: Path
    current_snippet_xml_path: Path
    session_json_path: Path
    progress_json_path: Path


@dataclass
class SnippetCaptureState:
    replay_values: list[tuple[ReplayValueType, int]] = field(default_factory=list)
    feature_pots: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.replay_values.clear()
        self.feature_pots.clear()
        self.errors.clear()

    @property
    def raw_random_count(self) -> int:
        return sum(1 for replay_type, _ in self.replay_values if replay_type == ReplayValueType.RANDOM_NUMBER)

    @property
    def player_decision_count(self) -> int:
        return sum(1 for replay_type, _ in self.replay_values if replay_type == ReplayValueType.PLAYER_DECISION)

    @property
    def feature_pot_count(self) -> int:
        return len(self.feature_pots)


@dataclass
class ExpectedMeterDelta:
    total_cash_in: int
    total_cash_out: int
    amount_wagered: int
    amount_won: int
    net: int
    games_won: int
    games_lost: int

    def to_display_dict(self) -> dict[str, int]:
        return {
            METER_TOTAL_CASH_IN: self.total_cash_in,
            METER_TOTAL_CASH_OUT: self.total_cash_out,
            METER_AMOUNT_WAGERED: self.amount_wagered,
            METER_AMOUNT_WON: self.amount_won,
            METER_NET: self.net,
            METER_GAMES_WON: self.games_won,
            METER_GAMES_LOST: self.games_lost,
        }

    @classmethod
    def from_display_dict(cls, payload: dict[str, Any]) -> "ExpectedMeterDelta":
        return cls(
            total_cash_in=read_meter_int(payload, METER_TOTAL_CASH_IN, LEGACY_METER_TOTAL_CASH_IN),
            total_cash_out=read_meter_int(payload, METER_TOTAL_CASH_OUT, LEGACY_METER_TOTAL_CASH_OUT),
            amount_wagered=read_meter_int(payload, METER_AMOUNT_WAGERED),
            amount_won=read_meter_int(payload, METER_AMOUNT_WON),
            net=read_meter_int(payload, METER_NET),
            games_won=read_meter_int(payload, METER_GAMES_WON),
            games_lost=read_meter_int(payload, METER_GAMES_LOST),
        )


@dataclass
class TrackedMeters:
    total_cash_in: int = 0
    total_cash_out: int = 0
    amount_wagered: int = 0
    amount_won: int = 0
    net: int = 0
    total_games_played: int = 0
    games_won: int = 0
    games_lost: int = 0

    def clone(self) -> "TrackedMeters":
        return TrackedMeters(
            total_cash_in=self.total_cash_in,
            total_cash_out=self.total_cash_out,
            amount_wagered=self.amount_wagered,
            amount_won=self.amount_won,
            net=self.net,
            total_games_played=self.total_games_played,
            games_won=self.games_won,
            games_lost=self.games_lost,
        )

    def apply_delta(self, delta: ExpectedMeterDelta) -> None:
        self.total_cash_in += delta.total_cash_in
        self.total_cash_out += delta.total_cash_out
        self.amount_wagered += delta.amount_wagered
        self.amount_won += delta.amount_won
        self.net += delta.net
        self.total_games_played += delta.games_won + delta.games_lost
        self.games_won += delta.games_won
        self.games_lost += delta.games_lost

    def projected_after(self, delta: ExpectedMeterDelta) -> "TrackedMeters":
        clone = self.clone()
        clone.apply_delta(delta)
        return clone

    @property
    def percent_games_won(self) -> float:
        total_games = self.total_games_played
        if total_games <= 0:
            return 0.0
        return round((self.games_won / total_games) * 100.0, 4)

    def to_display_dict(self) -> dict[str, int | float]:
        return {
            METER_TOTAL_CASH_IN: self.total_cash_in,
            METER_TOTAL_CASH_OUT: self.total_cash_out,
            METER_AMOUNT_WAGERED: self.amount_wagered,
            METER_AMOUNT_WON: self.amount_won,
            METER_NET: self.net,
            METER_TOTAL_GAMES_PLAYED: self.total_games_played,
            METER_GAMES_WON: self.games_won,
            METER_GAMES_LOST: self.games_lost,
            METER_PERCENT_GAMES_WON: self.percent_games_won,
        }

    @classmethod
    def from_display_dict(cls, payload: dict[str, Any] | None) -> "TrackedMeters":
        payload = payload or {}
        games_won = read_meter_int(payload, METER_GAMES_WON)
        games_lost = read_meter_int(payload, METER_GAMES_LOST)
        return cls(
            total_cash_in=read_meter_int(payload, METER_TOTAL_CASH_IN, LEGACY_METER_TOTAL_CASH_IN),
            total_cash_out=read_meter_int(payload, METER_TOTAL_CASH_OUT, LEGACY_METER_TOTAL_CASH_OUT),
            amount_wagered=read_meter_int(payload, METER_AMOUNT_WAGERED),
            amount_won=read_meter_int(payload, METER_AMOUNT_WON),
            net=read_meter_int(payload, METER_NET),
            total_games_played=read_meter_int(payload, METER_TOTAL_GAMES_PLAYED, default=games_won + games_lost),
            games_won=games_won,
            games_lost=games_lost,
        )


@dataclass
class SnippetMathSummary:
    selected_bet_credits: int
    credit_win_total: int
    jackpot_credit_total: int
    wager_from_win_total: int
    expected_meter_delta: ExpectedMeterDelta


@dataclass(frozen=True)
class ImportedSnippetParseResult:
    snippet_name: str
    snippet_xml: str
    resolved_stake_fields: dict[str, int]
    game_specific_settings: list[int]
    feature_pots: list[int]
    raw_random_count: int
    player_decision_count: int
    feature_pot_count: int
    selected_bet_credits: int
    credit_win_total: int
    jackpot_credit_total: int
    wager_from_win_total: int
    expected_meter_delta: ExpectedMeterDelta


@dataclass(frozen=True)
class ImportedSnippetLoadResult:
    game_type: str
    parsed_xml: ImportedSnippetParseResult
    parsed_xmls: list[ImportedSnippetParseResult]
    record: "SnippetRecord"
    records: list["SnippetRecord"]
    total_snippet_count: int
    source_description: str
    runner: "ImportedSnippetRunner"


@dataclass
class SnippetRecord:
    run_id: str
    snippet_id: str
    snippet_index: int
    snippet_name: str
    selected_bet_credits: int
    resolved_stake_fields: dict[str, int]
    game_specific_settings: list[int]
    feature_pots: list[int]
    replay_values: list[tuple[ReplayValueType, int]]
    raw_random_count: int
    player_decision_count: int
    feature_pot_count: int
    win_infos: list[dict[str, Any]]
    credit_win_total: int
    jackpot_credit_total: int
    wager_from_win_total: int
    expected_meter_delta: ExpectedMeterDelta
    snippets_generated_total: int
    games_generated_total: int
    cumulative_selected_bet: int
    timestamp_utc: str

    def replay_summary(self) -> str:
        return (
            f"raw_randoms={self.raw_random_count} "
            f"player_decisions={self.player_decision_count} "
            f"feature_pots={self.feature_pot_count}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "snippet_id": self.snippet_id,
            "snippet_index": self.snippet_index,
            "snippet_name": self.snippet_name,
            "selected_bet_credits": self.selected_bet_credits,
            "resolved_stake_fields": self.resolved_stake_fields,
            "game_specific_settings": self.game_specific_settings,
            "feature_pots": self.feature_pots,
            "replay_values": [
                {"type": replay_type.name, "value": value}
                for replay_type, value in self.replay_values
            ],
            "raw_random_count": self.raw_random_count,
            "player_decision_count": self.player_decision_count,
            "feature_pot_count": self.feature_pot_count,
            "win_infos": self.win_infos,
            "credit_win_total": self.credit_win_total,
            "jackpot_credit_total": self.jackpot_credit_total,
            "wager_from_win_total": self.wager_from_win_total,
            "expected_meter_delta": self.expected_meter_delta.to_display_dict(),
            "snippets_generated_total": self.snippets_generated_total,
            "games_generated_total": self.games_generated_total,
            "cumulative_selected_bet": self.cumulative_selected_bet,
            "timestamp_utc": self.timestamp_utc,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SnippetRecord":
        replay_values = [
            (ReplayValueType[item["type"]], int(item["value"]))
            for item in payload.get("replay_values", [])
        ]
        return cls(
            run_id=str(payload["run_id"]),
            snippet_id=str(payload["snippet_id"]),
            snippet_index=int(payload["snippet_index"]),
            snippet_name=str(payload["snippet_name"]),
            selected_bet_credits=int(payload["selected_bet_credits"]),
            resolved_stake_fields={str(key): int(value) for key, value in payload["resolved_stake_fields"].items()},
            game_specific_settings=[int(value) for value in payload.get("game_specific_settings", [])],
            feature_pots=[int(value) for value in payload.get("feature_pots", [])],
            replay_values=replay_values,
            raw_random_count=int(payload["raw_random_count"]),
            player_decision_count=int(payload["player_decision_count"]),
            feature_pot_count=int(payload["feature_pot_count"]),
            win_infos=list(payload.get("win_infos", [])),
            credit_win_total=int(payload["credit_win_total"]),
            jackpot_credit_total=int(payload["jackpot_credit_total"]),
            wager_from_win_total=int(payload["wager_from_win_total"]),
            expected_meter_delta=ExpectedMeterDelta.from_display_dict(payload["expected_meter_delta"]),
            snippets_generated_total=int(payload["snippets_generated_total"]),
            games_generated_total=int(payload["games_generated_total"]),
            cumulative_selected_bet=int(payload["cumulative_selected_bet"]),
            timestamp_utc=str(payload["timestamp_utc"]),
        )


@dataclass
class CompletedSnippetState:
    snippet_id: str
    snippet_index: int
    send_status: str
    completed_timestamp_utc: str
    cumulative_meter_totals_after_completion: dict[str, int | float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CompletedSnippetState":
        return cls(
            snippet_id=str(payload["snippet_id"]),
            snippet_index=int(payload["snippet_index"]),
            send_status=str(payload["send_status"]),
            completed_timestamp_utc=str(payload["completed_timestamp_utc"]),
            cumulative_meter_totals_after_completion=dict(payload["cumulative_meter_totals_after_completion"]),
        )


@dataclass
class ManualSendProgress:
    version: int
    run_id: str
    session_json_path: str
    current_snippet_xml_path: str
    next_snippet_index: int
    completed_count: int
    tracked_meters: TrackedMeters
    latest_completed_bank: int | None = None
    completion_history: list[CompletedSnippetState] = field(default_factory=list)
    last_updated_utc: str = field(default_factory=utc_timestamp)

    @classmethod
    def new(cls, run_id: str, session_json_path: Path, current_snippet_xml_path: Path) -> "ManualSendProgress":
        return cls(
            version=STATE_FILE_VERSION,
            run_id=run_id,
            session_json_path=str(session_json_path.resolve()),
            current_snippet_xml_path=str(current_snippet_xml_path.resolve()),
            next_snippet_index=1,
            completed_count=0,
            tracked_meters=TrackedMeters(),
        )

    def mark_completed(
        self,
        record: SnippetRecord,
        completed_timestamp_utc: str | None = None,
        latest_completed_bank: int | None = None,
    ) -> CompletedSnippetState:
        if record.snippet_index != self.next_snippet_index:
            raise RuntimeError(
                f"Progress is at snippet {self.next_snippet_index}, but tried to complete snippet {record.snippet_index}."
            )

        self.tracked_meters.apply_delta(record.expected_meter_delta)
        completed = CompletedSnippetState(
            snippet_id=record.snippet_id,
            snippet_index=record.snippet_index,
            send_status=SEND_STATUS_COMPLETED,
            completed_timestamp_utc=completed_timestamp_utc or utc_timestamp(),
            cumulative_meter_totals_after_completion=self.tracked_meters.to_display_dict(),
        )
        self.completion_history.append(completed)
        self.completed_count += 1
        self.next_snippet_index = record.snippet_index + 1
        if latest_completed_bank is not None:
            self.latest_completed_bank = int(latest_completed_bank)
        self.last_updated_utc = utc_timestamp()
        return completed

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "run_id": self.run_id,
            "session_json_path": self.session_json_path,
            "current_snippet_xml_path": self.current_snippet_xml_path,
            "next_snippet_index": self.next_snippet_index,
            "completed_count": self.completed_count,
            "tracked_meters": self.tracked_meters.to_display_dict(),
            "latest_completed_bank": self.latest_completed_bank,
            "completion_history": [entry.to_dict() for entry in self.completion_history],
            "last_updated_utc": self.last_updated_utc,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ManualSendProgress":
        return cls(
            version=int(payload.get("version", STATE_FILE_VERSION)),
            run_id=str(payload["run_id"]),
            session_json_path=str(payload["session_json_path"]),
            current_snippet_xml_path=str(payload["current_snippet_xml_path"]),
            next_snippet_index=int(payload["next_snippet_index"]),
            completed_count=int(payload["completed_count"]),
            tracked_meters=TrackedMeters.from_display_dict(payload.get("tracked_meters")),
            latest_completed_bank=(
                int(payload["latest_completed_bank"])
                if payload.get("latest_completed_bank") is not None
                else None
            ),
            completion_history=[
                CompletedSnippetState.from_dict(entry)
                for entry in payload.get("completion_history", [])
            ],
            last_updated_utc=str(payload.get("last_updated_utc", utc_timestamp())),
        )

    def save(self, progress_path: Path) -> None:
        self.last_updated_utc = utc_timestamp()
        write_json_file(progress_path, self.to_dict())

    @classmethod
    def load(cls, progress_path: Path) -> "ManualSendProgress":
        payload = json.loads(progress_path.read_text(encoding="utf-8"))
        return cls.from_dict(payload)


@dataclass
class GeneratedRunSession:
    version: int
    run_id: str
    category_name: str
    paytable_path: str
    paytable_name: str
    game_type: str
    variant_index: int
    seed: int | None
    qt_version: str
    output_xml_path: str
    audit_jsonl_path: str
    vlt_ip: str | None
    vlt_port: int | None
    manual_send_dir: str
    current_snippet_xml_path: str
    session_json_path: str
    progress_json_path: str
    snippet_records: list[SnippetRecord] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: GenerationConfig, paths: ManualSendPaths) -> "GeneratedRunSession":
        return cls(
            version=STATE_FILE_VERSION,
            run_id=config.run_id,
            category_name=config.category_name,
            paytable_path=str(config.paytable_path.resolve()),
            paytable_name=config.paytable_path.name,
            game_type=config.game_type,
            variant_index=config.variant_index,
            seed=config.seed,
            qt_version="",
            output_xml_path=str(config.output_xml_path.resolve()),
            audit_jsonl_path=str(config.audit_jsonl_path.resolve()),
            vlt_ip=config.vlt_connection.ip_address if config.vlt_connection else None,
            vlt_port=config.vlt_connection.port if config.vlt_connection else None,
            manual_send_dir=str(paths.manual_send_dir.resolve()),
            current_snippet_xml_path=str(paths.current_snippet_xml_path.resolve()),
            session_json_path=str(paths.session_json_path.resolve()),
            progress_json_path=str(paths.progress_json_path.resolve()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "run_id": self.run_id,
            "category_name": self.category_name,
            "paytable_path": self.paytable_path,
            "paytable_name": self.paytable_name,
            "game_type": self.game_type,
            "variant_index": self.variant_index,
            "seed": self.seed,
            "qt_version": self.qt_version,
            "output_xml_path": self.output_xml_path,
            "audit_jsonl_path": self.audit_jsonl_path,
            "vlt_ip": self.vlt_ip,
            "vlt_port": self.vlt_port,
            "manual_send_dir": self.manual_send_dir,
            "current_snippet_xml_path": self.current_snippet_xml_path,
            "session_json_path": self.session_json_path,
            "progress_json_path": self.progress_json_path,
            "snippet_records": [record.to_dict() for record in self.snippet_records],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GeneratedRunSession":
        return cls(
            version=int(payload.get("version", STATE_FILE_VERSION)),
            run_id=str(payload["run_id"]),
            category_name=str(payload["category_name"]),
            paytable_path=str(payload["paytable_path"]),
            paytable_name=str(payload["paytable_name"]),
            game_type=str(payload["game_type"]),
            variant_index=int(payload["variant_index"]),
            seed=int(payload["seed"]) if payload.get("seed") is not None else None,
            qt_version=str(payload["qt_version"]),
            output_xml_path=str(payload["output_xml_path"]),
            audit_jsonl_path=str(payload["audit_jsonl_path"]),
            vlt_ip=str(payload["vlt_ip"]) if payload.get("vlt_ip") is not None else None,
            vlt_port=int(payload["vlt_port"]) if payload.get("vlt_port") is not None else None,
            manual_send_dir=str(payload["manual_send_dir"]),
            current_snippet_xml_path=str(payload["current_snippet_xml_path"]),
            session_json_path=str(payload["session_json_path"]),
            progress_json_path=str(payload["progress_json_path"]),
            snippet_records=[
                SnippetRecord.from_dict(record_payload)
                for record_payload in payload.get("snippet_records", [])
            ],
        )

    def save(self) -> None:
        write_json_file(Path(self.session_json_path), self.to_dict())

    @classmethod
    def load(cls, session_json_path: Path) -> "GeneratedRunSession":
        payload = json.loads(session_json_path.read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    def write_current_snippet_xml(self, record: SnippetRecord) -> None:
        writer = SaeSnippetWriter()
        writer.set_egv_index(self.variant_index)
        writer.set_paytable_dll_path(str(Path(self.paytable_path).resolve()))
        writer.set_qt_version(self.qt_version)
        writer.add_category(writer.create_category(self.category_name))
        snippet = writer.create_snippet(
            snippet_name=record.snippet_name,
            resolved_stake_fields=record.resolved_stake_fields,
            game_specific_settings=record.game_specific_settings,
            replay_values=record.replay_values,
            feature_pots=record.feature_pots,
        )
        writer.add_snippet_to_category(self.category_name, snippet)
        output_path = Path(self.current_snippet_xml_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer.write_xml(output_path)


@dataclass
class SnippetAuditRecord:
    run_id: str
    snippet_id: str
    snippet_index: int
    snippet_name: str
    category: str
    paytable_path: str
    paytable_name: str
    game_type: str
    variant_index: int
    seed: int | None
    selected_bet_credits: int
    resolved_stake_fields: dict[str, int]
    game_specific_stake_items: dict[str, int]
    feature_pots: list[int]
    raw_random_count: int
    player_decision_count: int
    feature_pot_count: int
    win_infos: list[dict[str, Any]]
    credit_win_total: int
    jackpot_credit_total: int
    wager_from_win_total: int
    expected_meter_delta: dict[str, int]
    output_xml_path: str
    audit_jsonl_path: str
    current_snippet_xml_path: str
    progress_json_path: str
    vlt_ip: str | None
    vlt_port: int | None
    snippets_generated_total: int
    games_generated_total: int
    cumulative_selected_bet: int
    timestamp_utc: str
    send_status: str = SEND_STATUS_PENDING
    completion_timestamp_utc: str | None = None
    cumulative_meter_totals_after_completion: dict[str, int | float] | None = None
    meter_before: dict[str, Any] | None = None
    meter_after: dict[str, Any] | None = None
    meter_match: bool | None = None
    stop_reason: str | None = None


def build_manual_send_paths(output_xml_path: Path, run_id: str) -> ManualSendPaths:
    manual_send_dir = output_xml_path.resolve().parent / MANUAL_SEND_DIR_NAME
    return ManualSendPaths(
        manual_send_dir=manual_send_dir,
        current_snippet_xml_path=manual_send_dir / CURRENT_SNIPPET_FILENAME,
        session_json_path=manual_send_dir / f"{run_id}{SESSION_FILE_SUFFIX}",
        progress_json_path=manual_send_dir / f"{run_id}{PROGRESS_FILE_SUFFIX}",
    )


def serialize_win_info(win_info: Any) -> dict[str, Any]:
    sender = getattr(win_info, "Sender", None)
    sender_game_index = None
    sender_game_argument = None
    if sender is not None:
        sender_game_index = int(getattr(sender, "GameIndex", 0))
        sender_game_argument = int(getattr(sender, "GameArgument", 0))

    to_python_string = ""
    try:
        to_python_string = str(win_info.ToPythonString())
    except Exception:
        to_python_string = str(getattr(win_info, "InfoString", ""))

    return {
        "credit_win": int(getattr(win_info, "CreditWin", 0)),
        "sender_game_index": sender_game_index,
        "sender_game_argument": sender_game_argument,
        "type": int(getattr(win_info, "Type", 0)),
        "basic_win": int(getattr(win_info, "BasicWin", 0)),
        "multiplier1": int(getattr(win_info, "Multiplier1", 0)),
        "multiplier2": int(getattr(win_info, "Multiplier2", 0)),
        "index": int(getattr(win_info, "Index", 0)),
        "argument": int(getattr(win_info, "Argument", 0)),
        "info": int(getattr(win_info, "Info", 0)),
        "condition_id": int(getattr(win_info, "ConditionId", 0)),
        "line": int(getattr(win_info, "Line", 0)),
        "auto_info": int(getattr(win_info, "AutoInfo", 0)),
        "info_string": str(getattr(win_info, "InfoString", "")),
        "win_level_index": int(getattr(win_info, "WinLevelIndex", 0)),
        "num_joker_substitutions": int(getattr(win_info, "NumJokerSubstitutions", 0)),
        "flags": int(getattr(win_info, "Flags", 0)),
        "r_symbol": int(getattr(win_info, "RSymbol", 0)),
        "r_param": int(getattr(win_info, "RParam", 0)),
        "r_joker": int(getattr(win_info, "RJoker", 0)),
        "uint64_version": int(getattr(win_info, "Uint64Version", 0)),
        "info_offset": int(getattr(win_info, "InfoOffset", 0)),
        "python_string": to_python_string,
    }


def summarize_win_infos(win_infos: Iterable[Any], selected_bet_credits: int) -> SnippetMathSummary:
    credit_win_total = 0
    jackpot_credit_total = 0
    wager_from_win_total = 0

    for win_info in win_infos:
        win_type = int(getattr(win_info, "Type", 0))
        credit_win = int(getattr(win_info, "CreditWin", 0))
        if win_type == WIN_TYPE_CREDIT:
            credit_win_total += credit_win
        elif win_type == WIN_AUTO_TYPE_JACKPOT:
            jackpot_credit_total += credit_win
        elif win_type == WIN_AUTO_TYPE_WAGER:
            wager_from_win_total += credit_win

    return _build_snippet_math_summary(
        selected_bet_credits=selected_bet_credits,
        credit_win_total=credit_win_total,
        jackpot_credit_total=jackpot_credit_total,
        wager_from_win_total=wager_from_win_total,
    )


def build_zero_expected_meter_delta() -> ExpectedMeterDelta:
    return ExpectedMeterDelta(
        total_cash_in=0,
        total_cash_out=0,
        amount_wagered=0,
        amount_won=0,
        net=0,
        games_won=0,
        games_lost=0,
    )


def build_imported_snippet_record(parsed_xml: ImportedSnippetParseResult) -> SnippetRecord:
    return build_indexed_imported_snippet_record(parsed_xml, snippet_index=1, cumulative_selected_bet=None)


def build_indexed_imported_snippet_record(
    parsed_xml: ImportedSnippetParseResult,
    *,
    snippet_index: int,
    cumulative_selected_bet: int | None,
    run_id: str = "imported",
) -> SnippetRecord:
    return SnippetRecord(
        run_id=run_id,
        snippet_id=f"{run_id}:{snippet_index:06d}:{parsed_xml.snippet_name}",
        snippet_index=snippet_index,
        snippet_name=parsed_xml.snippet_name,
        selected_bet_credits=parsed_xml.selected_bet_credits,
        resolved_stake_fields=dict(parsed_xml.resolved_stake_fields),
        game_specific_settings=list(parsed_xml.game_specific_settings),
        feature_pots=list(parsed_xml.feature_pots),
        replay_values=[],
        raw_random_count=parsed_xml.raw_random_count,
        player_decision_count=parsed_xml.player_decision_count,
        feature_pot_count=parsed_xml.feature_pot_count,
        win_infos=[],
        credit_win_total=parsed_xml.credit_win_total,
        jackpot_credit_total=parsed_xml.jackpot_credit_total,
        wager_from_win_total=parsed_xml.wager_from_win_total,
        expected_meter_delta=parsed_xml.expected_meter_delta,
        snippets_generated_total=snippet_index,
        games_generated_total=snippet_index,
        cumulative_selected_bet=(
            parsed_xml.selected_bet_credits if cumulative_selected_bet is None else cumulative_selected_bet
        ),
        timestamp_utc=utc_timestamp(),
    )


def write_audit_jsonl(session: GeneratedRunSession, progress: ManualSendProgress | None) -> None:
    completion_by_index = {}
    if progress is not None:
        completion_by_index = {
            entry.snippet_index: entry
            for entry in progress.completion_history
        }

    rows: list[str] = []
    for record in session.snippet_records:
        completion = completion_by_index.get(record.snippet_index)
        audit_record = SnippetAuditRecord(
            run_id=session.run_id,
            snippet_id=record.snippet_id,
            snippet_index=record.snippet_index,
            snippet_name=record.snippet_name,
            category=session.category_name,
            paytable_path=session.paytable_path,
            paytable_name=session.paytable_name,
            game_type=session.game_type,
            variant_index=session.variant_index,
            seed=session.seed,
            selected_bet_credits=record.selected_bet_credits,
            resolved_stake_fields=dict(record.resolved_stake_fields),
            game_specific_stake_items={
                str(index): value for index, value in enumerate(record.game_specific_settings)
            },
            feature_pots=list(record.feature_pots),
            raw_random_count=record.raw_random_count,
            player_decision_count=record.player_decision_count,
            feature_pot_count=record.feature_pot_count,
            win_infos=list(record.win_infos),
            credit_win_total=record.credit_win_total,
            jackpot_credit_total=record.jackpot_credit_total,
            wager_from_win_total=record.wager_from_win_total,
            expected_meter_delta=record.expected_meter_delta.to_display_dict(),
            output_xml_path=session.output_xml_path,
            audit_jsonl_path=session.audit_jsonl_path,
            current_snippet_xml_path=session.current_snippet_xml_path,
            progress_json_path=session.progress_json_path,
            vlt_ip=session.vlt_ip,
            vlt_port=session.vlt_port,
            snippets_generated_total=record.snippets_generated_total,
            games_generated_total=record.games_generated_total,
            cumulative_selected_bet=record.cumulative_selected_bet,
            timestamp_utc=record.timestamp_utc,
            send_status=completion.send_status if completion else SEND_STATUS_PENDING,
            completion_timestamp_utc=completion.completed_timestamp_utc if completion else None,
            cumulative_meter_totals_after_completion=(
                completion.cumulative_meter_totals_after_completion if completion else None
            ),
            meter_before=None,
            meter_after=None,
            meter_match=None,
            stop_reason=None,
        )
        rows.append(json.dumps(asdict(audit_record), sort_keys=True))

    audit_path = Path(session.audit_jsonl_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        audit_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    else:
        audit_path.write_text("", encoding="utf-8")


class SaeSnippetWriter:
    def __init__(self) -> None:
        self.egv_idx = 0
        self.pt_path = ""
        self.qt_version = ""
        self.content = None
        self.categories: list[Any] = []

    def set_egv_index(self, egv_idx: int) -> None:
        self.egv_idx = egv_idx

    def set_paytable_dll_path(self, pt_path: str) -> None:
        self.pt_path = pt_path

    def set_qt_version(self, qt_version: str) -> None:
        self.qt_version = qt_version

    def create_category(self, category_name: str) -> Any:
        category = pysaelib.Category()
        category.SetName(category_name)
        return category

    def add_category(self, category: Any) -> None:
        self.categories.append(category)

    def add_snippet_to_category(self, category_name: str, snippet: Any) -> None:
        for category in self.categories:
            if category.GetName() == category_name:
                category.AddSnippet(snippet)
                return
        category = self.create_category(category_name)
        category.AddSnippet(snippet)
        self.categories.append(category)

    def create_snippet(
        self,
        snippet_name: str,
        resolved_stake_fields: dict[str, int],
        game_specific_settings: list[int],
        replay_values: list[tuple[ReplayValueType, int]],
        feature_pots: list[int],
    ) -> Any:
        bet = pysaelib.BetSituation()
        for definition in STAKE_FIELD_DEFINITIONS:
            setter_name = {
                "lines": "SetSelectedLines",
                "bet_per_line": "SetSelectedBetPerLine",
                "payment": "SetSelectedPayment",
                "denomination_cents": "SetSelectedDenomCents",
                "extra_credit": "SetSelectedExtraCredit",
                "side_bet": "SetSelectedSideBet",
            }[definition.name]
            getattr(bet, setter_name)(resolved_stake_fields.get(definition.name, 0))

        for index, value in enumerate(game_specific_settings):
            bet.SetSelectedGameSpecificSetting(index, value)

        sub_game = pysaelib.SubGame()
        sub_game.SetBetSituation(pysaelib.BetSituation(bet))

        raw_a = None
        for replay_type, value in replay_values:
            if replay_type == ReplayValueType.RANDOM_NUMBER:
                if raw_a is None:
                    raw_a = value
                else:
                    sub_game.AddElement(pysaelib.RandNum(0, 0, 0, raw_a, value))
                    raw_a = None
            else:
                sub_game.AddElement(pysaelib.PlayerDecision(value))

        if raw_a is not None:
            raise RuntimeError(
                "Recorded raw random numbers did not end in a pair; the replay capture is incomplete."
            )

        configuration = None
        if feature_pots:
            configuration = pysaelib.Configuration()
            for index, value in enumerate(feature_pots):
                configuration.SetFeaturePot(index, value)

        snippet = pysaelib.Snippet()
        snippet.SetName(snippet_name)
        snippet.AddSubGame(sub_game)
        if configuration is not None:
            snippet.SetConfiguration(configuration)
        return snippet

    def write_xml(self, output_path: Path) -> None:
        content = pysaelib.Content()
        content.SetPaytableDll(self.pt_path)
        content.SetVariantIndex(self.egv_idx)
        content.SetQtptiVersion(str(self.qt_version))
        content.SetDate(str(datetime.now()))
        content.SetContextAware(False)
        content.SetUseScaledRandoms(False)
        for category in self.categories:
            content.AddCategory(category)

        writer = pysaelib.IXmlWriter.CreateInstance()
        serialized_data = writer.ToXml(content)
        output_path.write_bytes(serialized_data)


def summarize_connection_error(exc: BaseException) -> str:
    """Collapse verbose .NET/WCF exception dumps to the first meaningful line plus a hint."""
    text = str(exc).strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), text)
    lowered = text.lower()
    if "did not properly respond" in lowered or "timed out" in lowered or "timeout" in lowered:
        hint = (
            "the VLT is powered on and reachable on the network (VPN/firewall may be blocking the port)"
        )
    elif "refused" in lowered or "actively refused" in lowered:
        hint = "the MPT SensysPlugin QA testing service is started on the VLT"
    else:
        hint = "the VLT IP address and that the QA testing service is running"
    return f"{first_line} Verify {hint}."


def probe_tcp_endpoint(
    ip_address: str,
    port: int,
    timeout_seconds: float,
    connection_factory: Callable[..., Any] = socket.create_connection,
) -> None:
    connection = connection_factory((ip_address, port), timeout_seconds)
    close = getattr(connection, "close", None)
    if callable(close):
        close()


class VltConnectionProbe:
    @staticmethod
    def normalize_ip_address(raw_value: str) -> str:
        try:
            return str(ipaddress.ip_address(raw_value.strip()))
        except ValueError as exc:
            raise ValueError(f"Invalid VLT IP address: {raw_value}") from exc

    @staticmethod
    def verify(
        game_type: str,
        config: VltConnectionConfig,
        sink: WorkflowEventSink | None = None,
        connection_factory: Callable[..., Any] = socket.create_connection,
    ) -> None:
        if game_type == GameType.SGF:
            SgfVltConnectionProbe.verify(config, sink=sink, connection_factory=connection_factory)
            return
        if game_type != GameType.UGF:
            raise ValueError(f"Unsupported game type: {game_type}")
        endpoint = f"{config.ip_address}:{config.port}"
        if sink is None:
            print(f"Checking {game_type} VLT connection to {endpoint}...")
        else:
            sink.log(f"Checking {game_type} VLT connection to {endpoint}...")
        try:
            probe_tcp_endpoint(
                config.ip_address,
                config.port,
                config.timeout_seconds,
                connection_factory=connection_factory,
            )
        except OSError as exc:
            raise RuntimeError(
                f"Connection failed to {endpoint}: {summarize_connection_error(exc)}"
            ) from exc
        if sink is None:
            print(f"Connected to VLT at {endpoint}.")
        else:
            sink.log(f"Connected to VLT at {endpoint}.")


class SgfVltConnectionProbe:
    _runtime: dict[str, Any] | None = None

    @classmethod
    def verify(
        cls,
        config: VltConnectionConfig,
        sink: WorkflowEventSink | None = None,
        connection_factory: Callable[..., Any] = socket.create_connection,
    ) -> None:
        endpoint = f"{config.ip_address}:{config.port}"
        if sink is None:
            print(f"Checking {GameType.SGF} VLT connection to {endpoint}...")
        else:
            sink.log(f"Checking {GameType.SGF} VLT connection to {endpoint}...")
        # WCF ignores config.timeout_seconds (it uses ~21s .NET defaults), so gate on a TCP preflight first.
        try:
            probe_tcp_endpoint(
                config.ip_address,
                config.port,
                config.timeout_seconds,
                connection_factory=connection_factory,
            )
        except OSError as exc:
            raise RuntimeError(
                f"Connection failed to {endpoint}: {summarize_connection_error(exc)}"
            ) from exc
        runtime = cls._ensure_runtime()
        client = runtime["ClientFactory"]().CreateClient(f"http://{config.ip_address}:{config.port}/")
        try:
            client.GetBankBalance()
        except Exception as exc:
            raise RuntimeError(
                f"Connection failed to {endpoint}: {summarize_connection_error(exc)}"
            ) from exc
        finally:
            cls._close_wcf_client(client)
        if sink is None:
            print(f"Connected to VLT at {endpoint}.")
        else:
            sink.log(f"Connected to VLT at {endpoint}.")

    @classmethod
    def _ensure_runtime(cls) -> dict[str, Any]:
        if cls._runtime is not None:
            return cls._runtime

        try:
            import clr  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                f"pythonnet is required for {GameType.SGF} connections but could not be imported: {exc}"
            ) from exc

        runtime_dir = cls._prepare_runtime_dir()
        try:
            for dll_name in REQUIRED_SGFHD_DOTNET_DLLS:
                clr.AddReference(str(runtime_dir / dll_name))
        except Exception as exc:
            raise RuntimeError(f"Failed to load {GameType.SGF} .NET assemblies: {exc}") from exc

        SensysContracts = __import__(
            "IGT.Spielo.Tools.Mpt.SensysPlugin.Contracts",
            fromlist=["QATestingServiceClientFactory"],
        )
        cls._runtime = {
            "ClientFactory": SensysContracts.QATestingServiceClientFactory,
        }
        return cls._runtime

    @classmethod
    def _prepare_runtime_dir(cls) -> Path:
        source_dir = cls._resolve_runtime_source_dir()
        cache_dir = Path(__file__).resolve().parent / ".runtime_cache" / SGFHD_RUNTIME_DIR_NAME
        cache_dir.mkdir(parents=True, exist_ok=True)
        for dll_name in REQUIRED_SGFHD_DOTNET_DLLS:
            src = source_dir / dll_name
            dst = cache_dir / dll_name
            if not src.exists():
                raise FileNotFoundError(f"Required {GameType.SGF} DLL missing: {src}")
            if not dst.exists() or src.stat().st_mtime_ns > dst.stat().st_mtime_ns:
                shutil.copyfile(src, dst)
                try:
                    os.remove(f"{dst}:Zone.Identifier")
                except OSError:
                    pass
        return cache_dir

    @classmethod
    def _resolve_runtime_source_dir(cls) -> Path:
        for env_var in SGFHD_DOTNET_RUNTIME_DIR_ENV_VARS:
            raw_value = os.environ.get(env_var, "").strip()
            if not raw_value:
                continue
            source_dir = Path(raw_value).expanduser()
            cls._validate_runtime_dir(source_dir, source=f"environment variable {env_var}")
            return source_dir

        search_root = Path(__file__).resolve().parent
        candidate_dirs = [
            search_root / SGFHD_RUNTIME_DIR_NAME,
            search_root / "runtime" / SGFHD_RUNTIME_DIR_NAME,
            search_root / "qa-tool-cheatforwarder - Copy" / SGFHD_RUNTIME_DIR_NAME,
            search_root / "qa-tool-cheatforwarder - Copy" / "dist" / "CheatForwarder" / "_internal" / SGFHD_RUNTIME_DIR_NAME,
        ]
        # When frozen, also search next to the exe so users can drop in DLLs manually.
        if getattr(sys, "frozen", False):
            candidate_dirs.insert(0, Path(sys.executable).resolve().parent / SGFHD_RUNTIME_DIR_NAME)
        for directory in candidate_dirs:
            if directory.exists() and cls._runtime_dir_has_required_dlls(directory):
                return directory

        raise FileNotFoundError(
            "Unable to locate required SGF runtime DLLs. "
            f"Expected files: {', '.join(REQUIRED_SGFHD_DOTNET_DLLS)}. "
            f"Set {SGFHD_DOTNET_RUNTIME_DIR_ENV_VARS[0]} to a valid runtime folder if needed."
        )

    @staticmethod
    def _runtime_dir_has_required_dlls(directory: Path) -> bool:
        return all((directory / dll_name).exists() for dll_name in REQUIRED_SGFHD_DOTNET_DLLS)

    @classmethod
    def _validate_runtime_dir(cls, directory: Path, source: str) -> None:
        if not directory.exists():
            raise FileNotFoundError(f"{GameType.SGF} runtime directory not found via {source}: {directory}")
        if not cls._runtime_dir_has_required_dlls(directory):
            raise FileNotFoundError(
                f"{GameType.SGF} runtime directory '{directory}' from {source} is missing required DLLs: "
                f"{', '.join(REQUIRED_SGFHD_DOTNET_DLLS)}"
            )

    @staticmethod
    def _close_wcf_client(client: Any) -> None:
        try:
            channel_factory = getattr(client, "ChannelFactory", None)
            if channel_factory is not None and str(channel_factory.State) == "Faulted":
                client.Abort()
                return
            client.Close()
        except Exception:
            try:
                client.Abort()
            except Exception:
                pass


@dataclass(frozen=True)
class SGFSendResult:
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnippetAutomationCycleResult:
    completed_record: SnippetRecord
    next_record: SnippetRecord | None
    stop_requested: bool = False

    @property
    def finished(self) -> bool:
        return self.next_record is None


@dataclass(frozen=True)
class SGFIdleWaitResult:
    reached_idle: bool
    latest_bank: int | None
    reason: str | None = None
    wait_seconds: float | None = None
    idle_detected_after_seconds: float | None = None
    idle_completed_after_seconds: float | None = None


class SGFCallbackModeStatePoller:
    """Pure callback mode — settceendpoint causes the VLT to push all state; no outbound polling."""

    def __init__(self, base_poller: Any) -> None:
        self._base_poller = base_poller
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="SGFCallbackModeStatePoller",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        try:
            self._base_poller.output_session.note_state_poller_started()
            self._base_poller._log_debug(
                "SGF callback-mode state poller started (pure callback, no polling); "
                f"service={self._base_poller.config.vlt_service_url}"
            )
            self._base_poller._stop_requested.wait()
        except Exception as exc:
            error_text = (
                f"SGF callback-mode poller error: {type(exc).__name__}: "
                f"{getattr(exc, '__cause__', str(exc))}"
            )
            self._base_poller.output_session.note_state_poller_failure(error_text=error_text)
            self._base_poller._log_debug(error_text)
        finally:
            self._base_poller.output_session.note_state_poller_stopped()
            self._base_poller._log_debug("SGF callback-mode state poller stopped")

    def stop(self) -> None:
        self._base_poller._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


class SGFInProcessListenerSession:
    def __init__(
        self,
        *,
        vlt_ip: str,
        vlt_port: int = SGF_VLT_PORT,
        timeout_seconds: float = SGF_IDLE_WAIT_TIMEOUT_SECONDS,
        state_poll_interval_ms: int = SGF_STATE_POLL_INTERVAL_MS,
        on_command_payload: Callable[[str], None] | None = None,
        on_pick_a_prize_state_change: Callable[[bool, str], None] | None = None,
    ) -> None:
        self.vlt_ip = vlt_ip
        self.vlt_port = int(vlt_port)
        self.timeout_seconds = float(timeout_seconds)
        self.state_poll_interval_ms = int(state_poll_interval_ms)
        self.latest_state: str | None = None
        self.latest_active_bank: int | None = None
        self.latest_active_bet: int | None = None
        self.latest_win_amount: int | None = None
        # Avoids fragile string duplication if the module constant ever changes
        self._idle_state_value: str = getattr(tce_listener, "IDLE_STATE_VALUE", "MarketWrapperReelStateMachine::Idle")
        self.saw_non_idle = False
        self.idle_reached = False
        self.startup_error: str | None = None
        self.wait_error: str | None = None
        self.stop_requested = False
        self._state_lock = threading.Lock()
        self._idle_event = threading.Event()
        self._module: types.ModuleType | None = None
        self._output_session: Any = None
        self._callback_server: Any = None
        self._state_poller: Any = None
        self._emit_patch_applied = False
        self._original_emit_func: Callable[[str], str] | None = None
        self._on_command_payload = on_command_payload
        self._on_pick_a_prize_state_change = on_pick_a_prize_state_change
        self._last_payload_time: float = time.monotonic()
        self._reconnect_attempted: bool = False
        self.pick_a_prize_active = False
        self._state_events: list[str] = []
        self._bonus_active = False
        self._pending_idle_since: float | None = None
        self._wait_started_at: float | None = None
        self._idle_detected_at: float | None = None
        self._idle_completed_at: float | None = None

    @property
    def idle_state_value(self) -> str:
        return self._idle_state_value

    @property
    def bonus_active(self) -> bool:
        with self._state_lock:
            return self._bonus_active

    def drain_state_events(self) -> list[str]:
        with self._state_lock:
            events = self._state_events
            self._state_events = []
        return events

    @property
    def latest_completed_bank(self) -> int | None:
        with self._state_lock:
            return self.latest_active_bank

    def start(self) -> None:
        module = tce_listener
        if module is None:
            raise RuntimeError(
                "CommandListener import failed. "
                f"Cause: {TCE_LISTENER_IMPORT_ERROR}"
            )
        self._module = module
        callback_ip = module.detect_local_ipv4(self.vlt_ip, self.vlt_port)
        config = module.TCEEndpointConfig(
            vlt_ip=self.vlt_ip,
            vlt_port=self.vlt_port,
            tce_port=0,
            state_poll_interval_ms=self.state_poll_interval_ms,
            tce_ip_override=callback_ip,
            configured_callback_ip=None,
            debug=False,
        )

        original_emit = module.emit_tce_terminal_line

        def _silent_emit(payload: str) -> str:
            self._consume_payload(payload)
            return payload

        self._original_emit_func = original_emit
        module.emit_tce_terminal_line = _silent_emit
        self._emit_patch_applied = True
        output_session = module.TCEOutputSession(emit_diagnostic_payloads=False)

        try:
            callback_server = module.TCECallbackServer(
                host=callback_ip,
                port=0,
                output_session=output_session,
                expected_vlt_ip=self.vlt_ip,
                tce_number=config.tce_number,
                debug=False,
            )
            callback_server.start()
            output_session.note_listener_bound()

            requested_endpoint = f"{callback_ip}:{callback_server.port}"
            module.run_tce_callback_self_probe(callback_ip, callback_server.port, debug=False)
            module.probe_vlt_soap_service(config.vlt_service_url, requested_endpoint)
            module.register_tce_endpoint(config.vlt_service_url, requested_endpoint, debug=False)

            runtime_config = module.TCEEndpointConfig(
                vlt_ip=config.vlt_ip,
                vlt_port=config.vlt_port,
                tce_port=callback_server.port,
                state_poll_interval_ms=config.state_poll_interval_ms,
                tce_number=config.tce_number,
                tce_label=config.tce_label,
                config_path=config.config_path,
                tce_ip_override=config.tce_ip_override,
                configured_callback_ip=config.configured_callback_ip,
                debug=False,
            )
            base_poller = module.TCEStatePoller(
                runtime_config,
                output_session,
                poll_interval_seconds=self.state_poll_interval_ms / 1000.0,
                debug_log=None,
            )
            state_poller = SGFCallbackModeStatePoller(base_poller)
            state_poller.start()
        except Exception as exc:
            self.startup_error = str(exc)
            self.stop()
            raise RuntimeError(f"SGF listener startup failed: {exc}") from exc

        self._output_session = output_session
        self._callback_server = callback_server
        self._state_poller = state_poller

    def begin_snippet_wait(self) -> None:
        with self._state_lock:
            self.latest_state = None
            self.latest_active_bank = None
            self.latest_active_bet = None
            self.latest_win_amount = None
            self.saw_non_idle = False
            self.idle_reached = False
            self.wait_error = None
            self.stop_requested = False
            self.pick_a_prize_active = False
            self._state_events = []
            self._bonus_active = False
            self._pending_idle_since = None
            self._wait_started_at = time.monotonic()
            self._idle_detected_at = None
            self._idle_completed_at = None
        self._reset_output_session_emission_state()
        self._idle_event.clear()
        self.wait_error = None  # Clear any previous error

    def _reset_output_session_emission_state(self) -> None:
        output_session = self._output_session
        if output_session is None:
            return

        session_lock = getattr(output_session, "_lock", None)
        if session_lock is None:
            self._reset_output_session_emission_state_unlocked(output_session)
            return

        with session_lock:
            self._reset_output_session_emission_state_unlocked(output_session)

    @staticmethod
    def _reset_output_session_emission_state_unlocked(output_session: Any) -> None:
        # Ensure each snippet wait starts fresh so repeated idle payloads are not deduplicated away.
        if hasattr(output_session, "_last_emitted_payload"):
            output_session._last_emitted_payload = None
        if hasattr(output_session, "_last_emitted_state"):
            output_session._last_emitted_state = None
        if hasattr(output_session, "_non_idle_state_seen"):
            output_session._non_idle_state_seen = False

    def request_stop(self) -> None:
        with self._state_lock:
            self.stop_requested = True

    def get_listener_health(self) -> dict[str, Any]:
        """Check if listener is receiving payloads and return health info."""
        with self._state_lock:
            time_since_payload = time.monotonic() - self._last_payload_time
            is_receiving = time_since_payload < (self.timeout_seconds / 2)
            return {
                "is_receiving_payloads": is_receiving,
                "time_since_last_payload": time_since_payload,
                "latest_state": self.latest_state,
            }

    def reconnect(self) -> None:
        """Gracefully restart callback server and state poller to restore subscription."""
        try:
            # Stop existing components
            if self._state_poller is not None:
                try:
                    self._state_poller.stop()
                except Exception:
                    pass
                self._state_poller = None
            
            if self._callback_server is not None:
                try:
                    self._callback_server.stop()
                except Exception:
                    pass
                self._callback_server = None
            
            # Small delay to allow graceful shutdown
            time.sleep(0.5)
            
            # Restart callback server and poller
            if self._module is None:
                raise RuntimeError("Module not initialized")
            
            module = self._module
            output_session = self._output_session
            if output_session is None:
                raise RuntimeError("Output session not initialized")
            
            # Detect callback IP
            callback_ip = module.detect_local_ipv4(self.vlt_ip, self.vlt_port)
            
            # Start new callback server
            callback_server = module.TCECallbackServer(
                host=callback_ip,
                port=0,
                output_session=output_session,
                expected_vlt_ip=self.vlt_ip,
                tce_number=1,
                debug=False,
            )
            callback_server.start()
            
            # Re-register endpoint with VLT
            requested_endpoint = f"{callback_ip}:{callback_server.port}"
            module.run_tce_callback_self_probe(callback_ip, callback_server.port, debug=False)
            config = module.TCEEndpointConfig(
                vlt_ip=self.vlt_ip,
                vlt_port=self.vlt_port,
                tce_port=callback_server.port,
                state_poll_interval_ms=self.state_poll_interval_ms,
            )
            module.probe_vlt_soap_service(config.vlt_service_url, requested_endpoint)
            module.register_tce_endpoint(config.vlt_service_url, requested_endpoint, debug=False)
            
            # Start new state poller
            runtime_config = module.TCEEndpointConfig(
                vlt_ip=self.vlt_ip,
                vlt_port=self.vlt_port,
                tce_port=callback_server.port,
                state_poll_interval_ms=self.state_poll_interval_ms,
            )
            base_poller = module.TCEStatePoller(
                runtime_config,
                output_session,
                poll_interval_seconds=self.state_poll_interval_ms / 1000.0,
                debug_log=None,
            )
            state_poller = SGFCallbackModeStatePoller(base_poller)
            state_poller.start()
            
            self._callback_server = callback_server
            self._state_poller = state_poller
            self._reconnect_attempted = True
            
        except Exception as exc:
            raise RuntimeError(f"SGF listener reconnect failed: {exc}") from exc

    def wait_for_idle(self, on_tick: Callable[[], None] | None = None) -> SGFIdleWaitResult:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            if on_tick is not None:
                on_tick()
            with self._state_lock:
                self._promote_pending_idle_locked()
                if self.idle_reached:
                    completed_at = self._idle_completed_at or time.monotonic()
                    wait_started_at = self._wait_started_at
                    return SGFIdleWaitResult(
                        reached_idle=True,
                        latest_bank=self.latest_active_bank,
                        reason=None,
                        wait_seconds=(completed_at - wait_started_at) if wait_started_at is not None else None,
                        idle_detected_after_seconds=(
                            self._idle_detected_at - wait_started_at
                            if self._idle_detected_at is not None and wait_started_at is not None
                            else None
                        ),
                        idle_completed_after_seconds=(
                            completed_at - wait_started_at
                            if wait_started_at is not None
                            else None
                        ),
                    )
                wait_error = self.wait_error
                bonus_active = self._bonus_active
            if wait_error:
                return SGFIdleWaitResult(
                    reached_idle=False,
                    latest_bank=self.latest_completed_bank,
                    reason=wait_error,
                )
            if bonus_active:
                # Bonuses can run far longer than a base spin, so fall back to an inactivity deadline.
                effective_deadline = self._last_payload_time + SGF_BONUS_IDLE_WAIT_TIMEOUT_SECONDS
                timeout_seconds = SGF_BONUS_IDLE_WAIT_TIMEOUT_SECONDS
            else:
                effective_deadline = deadline
                timeout_seconds = self.timeout_seconds
            remaining = effective_deadline - time.monotonic()
            if remaining <= 0:
                return SGFIdleWaitResult(
                    reached_idle=False,
                    latest_bank=self.latest_completed_bank,
                    reason=(
                        "Timed out waiting for SGF idle transition "
                        f"after {timeout_seconds:g} seconds."
                    ),
                )
            self._idle_event.wait(min(remaining, SGF_IDLE_EVENT_WAIT_SECONDS))

    def _promote_pending_idle_locked(self) -> None:
        if self.idle_reached or self._pending_idle_since is None:
            return
        if time.monotonic() - self._pending_idle_since < SGF_BONUS_IDLE_CONFIRM_SECONDS:
            return
        self._pending_idle_since = None
        self._bonus_active = False
        self.idle_reached = True
        self._idle_completed_at = time.monotonic()
        self._idle_event.set()

    def stop(self) -> None:
        if self._state_poller is not None:
            try:
                self._state_poller.stop()
            except Exception:
                pass
            self._state_poller = None
        if self._callback_server is not None:
            try:
                self._callback_server.stop()
            except Exception:
                pass
            self._callback_server = None
        if self._emit_patch_applied and self._module is not None and self._original_emit_func is not None:
            self._module.emit_tce_terminal_line = self._original_emit_func
        self._emit_patch_applied = False
        self._original_emit_func = None

    def _consume_payload(self, payload: str) -> None:
        self._last_payload_time = time.monotonic()  # Track payload receipt
        match = re.fullmatch(r"\d+\|\d+\|\|([^|]+)\|(.*)", (payload or "").strip())
        if not match:
            return
        variable_name = match.group(1).strip().upper()
        variable_value = match.group(2).strip()
        if variable_name == "STATE":
            self._consume_state_payload(variable_value)
            self._emit_command_payload(variable_name, variable_value)
            return
        if variable_name == "BANK":
            self._consume_bank_payload(variable_value)
            self._emit_command_payload(variable_name, variable_value)
            return
        if variable_name == "BET":
            self._consume_bet_payload(variable_value)
            self._emit_command_payload(variable_name, variable_value)
            return
        if variable_name == "WIN":
            self._consume_win_payload(variable_value)
            self._emit_command_payload(variable_name, variable_value)

    def _emit_command_payload(self, variable_name: str, variable_value: str) -> None:
        if self._on_command_payload is None:
            return
        try:
            self._on_command_payload(f"{variable_name}: {variable_value}")
        except Exception:
            # Logging callback failures must not break SGF listener processing.
            pass

    def _emit_pick_a_prize_state_change(self, is_active: bool, state_value: str) -> None:
        if self._on_pick_a_prize_state_change is None:
            return
        try:
            self._on_pick_a_prize_state_change(is_active, state_value)
        except Exception:
            # Listener state transition callbacks must not break SGF listener processing.
            pass

    def _consume_state_payload(self, state_value: str) -> None:
        pick_a_prize_transition: tuple[bool, str] | None = None
        with self._state_lock:
            previous_state = self.latest_state
            self.latest_state = state_value
            if not state_value:
                return
            if state_value != previous_state:
                self._state_events.append(state_value)
                if len(self._state_events) > SGF_STATE_EVENT_QUEUE_MAX:
                    del self._state_events[:-SGF_STATE_EVENT_QUEUE_MAX]
            pick_a_prize_active = is_pick_a_prize_state(state_value)
            if pick_a_prize_active or is_bonus_state(state_value):
                self._bonus_active = True
            if state_value == self._idle_state_value:
                if self.saw_non_idle:
                    if self._bonus_active:
                        if self._pending_idle_since is None:
                            self._idle_detected_at = time.monotonic()
                            self._pending_idle_since = self._idle_detected_at
                    else:
                        self._idle_detected_at = time.monotonic()
                        self.idle_reached = True
                        self._idle_completed_at = self._idle_detected_at
                        self._idle_event.set()
                pick_a_prize_active = False
            else:
                self.saw_non_idle = True
                self._pending_idle_since = None
            if pick_a_prize_active != self.pick_a_prize_active:
                self.pick_a_prize_active = pick_a_prize_active
                pick_a_prize_transition = (pick_a_prize_active, state_value)
        if pick_a_prize_transition is not None:
            self._emit_pick_a_prize_state_change(*pick_a_prize_transition)

    def _consume_bank_payload(self, bank_value: str) -> None:
        if not bank_value:
            return
        try:
            parsed_bank = int(float(bank_value))
        except ValueError:
            return
        with self._state_lock:
            self.latest_active_bank = parsed_bank

    def _consume_bet_payload(self, bet_value: str) -> None:
        if not bet_value:
            return
        try:
            parsed_bet = int(float(bet_value))
        except ValueError:
            return
        with self._state_lock:
            self.latest_active_bet = parsed_bet

    def _consume_win_payload(self, win_value: str) -> None:
        if not win_value:
            return
        try:
            parsed_win = int(float(win_value))
        except ValueError:
            return
        with self._state_lock:
            self.latest_win_amount = parsed_win


class WorkflowEventSink:
    def log(self, message: str, *, is_error: bool = False) -> None:
        del message, is_error

    def generation_started(self, config: GenerationConfig) -> None:
        del config

    def generation_completed(self, session: GeneratedRunSession, progress: ManualSendProgress) -> None:
        del session, progress

    def generation_failed(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        del message, exc, context

    def snippet_prepared(
        self,
        session: GeneratedRunSession,
        progress: ManualSendProgress,
        record: SnippetRecord,
    ) -> None:
        del session, progress, record

    def snippet_completed(
        self,
        session: GeneratedRunSession,
        progress: ManualSendProgress,
        record: SnippetRecord,
    ) -> None:
        del session, progress, record

    def final_summary(self, session: GeneratedRunSession, progress: ManualSendProgress) -> None:
        del session, progress

    def request_completion_input(self, prompt: str) -> str:
        del prompt
        return ""


class TerminalWorkflowEventSink(WorkflowEventSink):
    def log(self, message: str, *, is_error: bool = False) -> None:
        print(message, file=sys.stderr if is_error else sys.stdout)

    def generation_failed(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        log_terminal_error(message, exc=exc, context=context, include_traceback=True)

    def request_completion_input(self, prompt: str) -> str:
        return input(prompt)


def _get_app_base_dir() -> Path:
    return Path(__file__).resolve().parent


def _append_command_file_log(operation: str, destination: str, details: str) -> None:
    log_path = _get_app_base_dir() / COMMAND_LOG_FILE_NAME
    safe_details = " ".join(details.splitlines()).strip()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{terminal_timestamp()}] {operation} destination={destination} {safe_details}\n")
    except OSError:
        pass


def _get_gui_settings_path() -> Path:
    return _get_app_base_dir() / GUI_SETTINGS_FILE_NAME


def _sanitize_gui_settings_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if key not in LEGACY_GUI_SETTINGS_KEYS}


def load_gui_settings() -> dict[str, Any]:
    path = _get_gui_settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return _sanitize_gui_settings_payload(payload)


def save_gui_settings(payload: dict[str, Any]) -> None:
    write_json_file(_get_gui_settings_path(), _sanitize_gui_settings_payload(payload))


def format_meter_block(meters: dict[str, int | float]) -> str:
    lines = []
    for meter_name in METER_DISPLAY_ORDER:
        if meter_name not in meters:
            continue
        lines.append(f"{meter_name}: {format_meter_value(meter_name, meters[meter_name])}")
    return "\n".join(lines)


def format_current_meter_block(record: "SnippetRecord", latest_bank: int | None = None) -> str:
    values = record.expected_meter_delta.to_display_dict()
    lines: list[str] = []
    for meter_name in METER_DISPLAY_ORDER:
        if meter_name not in values:
            continue
        lines.append(f"{meter_name}: {format_meter_value(meter_name, values[meter_name])}")
    if latest_bank is not None:
        lines.append(f"{METER_BANK}: {latest_bank}")
    return "\n".join(lines)


def format_cumulative_meter_block(meters: "TrackedMeters", latest_completed_bank: int | None = None) -> str:
    values = meters.to_display_dict()
    lines: list[str] = []
    for meter_name in METER_DISPLAY_ORDER:
        if meter_name not in values:
            continue
        lines.append(f"{meter_name}: {format_meter_value(meter_name, values[meter_name])}")
    if latest_completed_bank is not None:
        lines.append(f"{METER_BANK}: {latest_completed_bank}")
    return "\n".join(lines)


def _build_dotnet_runtime_candidate_dirs(runtime_dir_name: str) -> list[Path]:
    base_dir = _get_app_base_dir()
    return [
        base_dir / runtime_dir_name,
        base_dir / "runtime" / runtime_dir_name,
        base_dir / "qa-tool-cheatforwarder - Copy" / runtime_dir_name,
        base_dir / "qa-tool-cheatforwarder - Copy" / "dist" / "CheatForwarder" / "_internal" / runtime_dir_name,
    ]


class UgfVltSnippetSender:
    def __init__(self) -> None:
        self._gsn_runtime: dict[str, Any] | None = None
        self._gsn_runtime_cache_dir = _get_app_base_dir() / ".runtime_cache" / UGF_RUNTIME_DIR_NAME

    def send(self, vlt_ip: str, snippet: str) -> None:
        gsn = self._ensure_gsn_runtime()
        token = 0
        guest_created = False
        connection_transport = None
        platform_transport = None
        connection_client = None
        try:
            connection_transport = gsn["TSocket"](vlt_ip, UGF_VLT_PORT, FORWARDER_TIMEOUT_MS)
            connection_transport.TcpClient.NoDelay = True
            connection_protocol = gsn["TBinaryProtocol"](connection_transport)
            connection_client = gsn["sGuestConnection"].Client(connection_protocol)
            connection_transport.Open()
            token = connection_client.CreateGuest()
            guest_created = True
            request = gsn["ConnectionRequest_t"]()
            request.DesiredTransport = gsn["eThriftTransport"].Binary
            request.TokenID = token
            services = gsn["List_Service_t"]()
            service = gsn["Service_t"]()
            service.Name = gsn["GSN_TestV1Constants"].SERVICE
            version = gsn["Version_t"]()
            version.Major = gsn["GSN_TestV1Constants"].MAJOR_VERSION
            version.Minor = gsn["GSN_TestV1Constants"].MINOR_VERSION
            service.Version = version
            services.Add(service)
            request.FeaturesRequested = services
            offer = connection_client.Connect(request)
            has_required_service = any(
                svc.Name == gsn["GSN_TestV1Constants"].SERVICE
                for svc in offer.PlatformService.Services
            )
            if not has_required_service:
                raise RuntimeError(f"Required service '{gsn['GSN_TestV1Constants'].SERVICE}' is not available")
            accept_args = gsn["OfferAcceptArgs_t"]()
            accept_args.Token = token
            if not connection_client.OfferAccepted(accept_args):
                raise RuntimeError("Platform refused accepted offer")
            platform_transport = gsn["TSocket"](vlt_ip, int(offer.PlatformService.Port), FORWARDER_TIMEOUT_MS)
            platform_transport.TcpClient.NoDelay = True
            platform_protocol = gsn["TBinaryProtocol"](platform_transport)
            test_client = gsn["sTestV1"].Client(
                gsn["TMultiplexedProtocol"](platform_protocol, gsn["GSN_TestV1Constants"].SERVICE)
            )
            platform_transport.Open()
            the_event = gsn["CustomEvent_t"]()
            the_event.ID = "CheatMPTFile"
            the_event.Data = gsn["DotNetByteArray"](snippet.encode("utf-8"))
            the_event.Source = token
            event_args = gsn["CustomEventParam_t"]()
            event_args.Event = the_event
            _append_command_file_log(
                "UGF SendCustomEvent",
                f"{vlt_ip}:{UGF_VLT_PORT}",
                f"event={the_event.ID} payload_bytes={len(snippet.encode('utf-8'))}",
            )
            test_client.SendCustomEvent(event_args)
        finally:
            if connection_client is not None and guest_created:
                try:
                    disconnect_args = gsn["DisconnectArgs_t"]()
                    disconnect_args.Token = token
                    connection_client.Disconnect(disconnect_args)
                except Exception:
                    pass
            if platform_transport is not None:
                try:
                    platform_transport.Close()
                except Exception:
                    pass
            if connection_transport is not None:
                try:
                    connection_transport.Close()
                except Exception:
                    pass

    def press_button(self, vlt_ip: str, button_id: int) -> None:
        gsn = self._ensure_gsn_runtime()
        token = 0
        guest_created = False
        connection_transport = None
        platform_transport = None
        connection_client = None
        try:
            connection_transport = gsn["TSocket"](vlt_ip, UGF_VLT_PORT, FORWARDER_TIMEOUT_MS)
            connection_transport.TcpClient.NoDelay = True
            connection_protocol = gsn["TBinaryProtocol"](connection_transport)
            connection_client = gsn["sGuestConnection"].Client(connection_protocol)
            connection_transport.Open()
            token = connection_client.CreateGuest()
            guest_created = True
            request = gsn["ConnectionRequest_t"]()
            request.DesiredTransport = gsn["eThriftTransport"].Binary
            request.TokenID = token
            services = gsn["List_Service_t"]()
            service = gsn["Service_t"]()
            service.Name = gsn["GSN_TestV1Constants"].SERVICE
            version = gsn["Version_t"]()
            version.Major = gsn["GSN_TestV1Constants"].MAJOR_VERSION
            version.Minor = gsn["GSN_TestV1Constants"].MINOR_VERSION
            service.Version = version
            services.Add(service)
            request.FeaturesRequested = services
            offer = connection_client.Connect(request)
            has_required_service = any(
                svc.Name == gsn["GSN_TestV1Constants"].SERVICE
                for svc in offer.PlatformService.Services
            )
            if not has_required_service:
                raise RuntimeError(f"Required service '{gsn['GSN_TestV1Constants'].SERVICE}' is not available")
            accept_args = gsn["OfferAcceptArgs_t"]()
            accept_args.Token = token
            if not connection_client.OfferAccepted(accept_args):
                raise RuntimeError("Platform refused accepted offer")
            platform_transport = gsn["TSocket"](vlt_ip, int(offer.PlatformService.Port), FORWARDER_TIMEOUT_MS)
            platform_transport.TcpClient.NoDelay = True
            platform_protocol = gsn["TBinaryProtocol"](platform_transport)
            test_client = gsn["sTestV1"].Client(
                gsn["TMultiplexedProtocol"](platform_protocol, gsn["GSN_TestV1Constants"].SERVICE)
            )
            platform_transport.Open()
            _append_command_file_log(
                "UGF ButtonPress",
                f"{vlt_ip}:{UGF_VLT_PORT}",
                f"button_id={button_id}",
            )
            test_client.ButtonPress(button_id)
        finally:
            if connection_client is not None and guest_created:
                try:
                    disconnect_args = gsn["DisconnectArgs_t"]()
                    disconnect_args.Token = token
                    connection_client.Disconnect(disconnect_args)
                except Exception:
                    pass
            if platform_transport is not None:
                try:
                    platform_transport.Close()
                except Exception:
                    pass
            if connection_transport is not None:
                try:
                    connection_transport.Close()
                except Exception:
                    pass

    def _runtime_dir_has_required_dlls(self, directory: Path) -> bool:
        return all((directory / dll_name).exists() for dll_name in REQUIRED_UGF_DOTNET_DLLS)

    def _resolve_dotnet_runtime_source_dir(self) -> Path:
        env_runtime_dir = os.environ.get(UGF_DOTNET_RUNTIME_DIR_ENV_VAR, "").strip()
        if env_runtime_dir:
            source_dir = Path(env_runtime_dir)
            if not source_dir.exists():
                raise FileNotFoundError(
                    f"Runtime directory not found: {source_dir}. Set {UGF_DOTNET_RUNTIME_DIR_ENV_VAR} to a valid folder containing required DLLs."
                )
            if not self._runtime_dir_has_required_dlls(source_dir):
                raise FileNotFoundError(
                    f"Runtime directory '{source_dir}' is missing one or more required DLLs: {', '.join(REQUIRED_UGF_DOTNET_DLLS)}"
                )
            return source_dir
        for directory in _build_dotnet_runtime_candidate_dirs(UGF_RUNTIME_DIR_NAME):
            if directory.exists() and self._runtime_dir_has_required_dlls(directory):
                return directory
        raise FileNotFoundError(
            "Unable to locate required runtime DLLs locally. Place "
            f"{', '.join(REQUIRED_UGF_DOTNET_DLLS)} next to this app (or in runtime/{UGF_RUNTIME_DIR_NAME}), "
            f"or set {UGF_DOTNET_RUNTIME_DIR_ENV_VAR} to a folder that contains them."
        )

    def _prepare_dotnet_runtime_dir(self) -> Path:
        source_dir = self._resolve_dotnet_runtime_source_dir()
        self._gsn_runtime_cache_dir.mkdir(parents=True, exist_ok=True)
        for dll_name in REQUIRED_UGF_DOTNET_DLLS:
            src = source_dir / dll_name
            dst = self._gsn_runtime_cache_dir / dll_name
            if not src.exists():
                raise FileNotFoundError(f"Required DLL missing: {src}")
            if not dst.exists() or src.stat().st_mtime_ns > dst.stat().st_mtime_ns:
                shutil.copyfile(src, dst)
                try:
                    os.remove(f"{dst}:Zone.Identifier")
                except OSError:
                    pass
        return self._gsn_runtime_cache_dir

    def _ensure_gsn_runtime(self) -> dict[str, Any]:
        if self._gsn_runtime is not None:
            return self._gsn_runtime
        runtime_dir = self._prepare_dotnet_runtime_dir()
        try:
            import clr  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                f"pythonnet is required but could not be imported: {exc}. "
                "Please ensure pythonnet is installed."
            ) from exc
        try:
            clr.AddReference(str(runtime_dir / "Thrift.dll"))
            clr.AddReference(str(runtime_dir / "IGT.GSN.Thrift.dll"))
        except Exception as exc:
            raise RuntimeError(f"Failed to load .NET assemblies: {exc}") from exc
        GSN_Connection_V1 = __import__("GSN_Connection_V1")
        GSN_GuestConnection = __import__("GSN_GuestConnection")
        GSN_Test_V1 = __import__("GSN_Test_V1")
        System = __import__("System")
        generic = __import__("System.Collections.Generic", fromlist=["List"])
        thrift_protocol = __import__("Thrift.Protocol", fromlist=["TBinaryProtocol", "TMultiplexedProtocol"])
        thrift_transport = __import__("Thrift.Transport", fromlist=["TSocket"])
        List = generic.List
        TBinaryProtocol = thrift_protocol.TBinaryProtocol
        TMultiplexedProtocol = thrift_protocol.TMultiplexedProtocol
        TSocket = thrift_transport.TSocket
        self._gsn_runtime = {
            "TSocket": TSocket,
            "TBinaryProtocol": TBinaryProtocol,
            "TMultiplexedProtocol": TMultiplexedProtocol,
            "sGuestConnection": GSN_GuestConnection.sGuestConnection,
            "sTestV1": GSN_Test_V1.sTestV1,
            "GSN_TestV1Constants": GSN_Test_V1.GSN_TestV1Constants,
            "ConnectionRequest_t": GSN_Connection_V1.ConnectionRequest_t,
            "eThriftTransport": GSN_Connection_V1.eThriftTransport,
            "Service_t": GSN_Connection_V1.Service_t,
            "Version_t": GSN_Connection_V1.Version_t,
            "OfferAcceptArgs_t": GSN_Connection_V1.OfferAcceptArgs_t,
            "DisconnectArgs_t": GSN_Connection_V1.DisconnectArgs_t,
            "CustomEvent_t": GSN_Test_V1.CustomEvent_t,
            "CustomEventParam_t": GSN_Test_V1.CustomEventParam_t,
            "List_Service_t": List[GSN_Connection_V1.Service_t],
            "DotNetByteArray": System.Array[System.Byte],
        }
        return self._gsn_runtime


class SgfVltSnippetSender:
    def __init__(self) -> None:
        self._sgf_runtime: dict[str, Any] | None = None
        self._sgf_runtime_cache_dir = _get_app_base_dir() / ".runtime_cache" / SGFHD_RUNTIME_DIR_NAME

    def send(self, vlt_ip: str, snippet: str, port: int = SGF_VLT_PORT) -> SGFSendResult:
        runtime = self._ensure_sgf_runtime()
        game = self._deserialize_first_gameplay(runtime, snippet)
        random_number_actions = self._get_actions(game, runtime["RandomNumberType"], "RandomNumber")
        raw_ints = self._get_raw_ints(runtime, random_number_actions)
        feature_pot_pairs = _extract_sgfhd_feature_pot_pairs(getattr(game, "FeaturePots", None))
        player_decisions = self._get_actions(game, runtime["PlayerDecisionType"], "PlayerDecision")
        client = runtime["ClientFactory"]().CreateClient(f"http://{vlt_ip}:{port}/")
        try:
            destination = f"http://{vlt_ip}:{port}/"
            _append_command_file_log("SGF ClearCheatQueue", destination, "")
            client.ClearCheatQueueAsync().GetAwaiter().GetResult()
            self._send_random_numbers(runtime, client, raw_ints)
            if feature_pot_pairs:
                self._send_feature_pots(runtime, client, feature_pot_pairs)
            warnings: list[str] = []
            if player_decisions:
                try:
                    self._send_player_decisions(runtime, client, player_decisions)
                except Exception as exc:
                    if "setplayerdecisions" in str(exc).lower():
                        warnings.append(
                            "SGF player decisions skipped: endpoint does not support SetPlayerDecisions."
                        )
                    else:
                        raise
        finally:
            SgfVltConnectionProbe._close_wcf_client(client)
        return SGFSendResult(warnings=tuple(warnings))

    def _deserialize_first_gameplay(self, runtime: dict[str, Any], snippet: str) -> Any:
        serializer = runtime["SaeContentSerializer"]()
        dotnet_bytes = runtime["DotNetByteArray"](snippet.encode("utf-8"))
        stream = runtime["MemoryStream"](dotnet_bytes)
        try:
            test_plan = serializer.DeserializeTestPlan(stream)
        finally:
            try:
                stream.Close()
            except Exception:
                pass
        collections = list(getattr(test_plan, "GamePlayCollections", []) or [])
        if not collections:
            raise RuntimeError("SGF snippet did not contain any gameplay collections.")
        games = list(getattr(collections[0], "Games", []) or [])
        if not games:
            raise RuntimeError("SGF snippet did not contain any games.")
        return games[0]

    def _get_actions(self, game: Any, action_type: Any, action_type_name: str) -> list[Any]:
        if action_type is None:
            raise RuntimeError(f"Unable to resolve SGF {action_type_name} type from the loaded runtime.")
        try:
            get_actions = game.GetType().GetMethod("GetActions")
        except Exception as exc:
            raise RuntimeError(f"Unable to resolve GamePlay.GetActions<{action_type_name}>(): {exc}") from exc
        if get_actions is None:
            raise RuntimeError(f"GamePlay.GetActions<{action_type_name}>() is unavailable in the loaded runtime.")
        try:
            generic_method = get_actions.MakeGenericMethod(action_type)
            values = generic_method.Invoke(game, None)
        except Exception as exc:
            raise RuntimeError(f"Failed invoking GamePlay.GetActions<{action_type_name}>(): {exc}") from exc
        return list(values or [])

    def _get_raw_ints(self, runtime: dict[str, Any], random_number_actions: list[Any]) -> list[int]:
        random_number_values = self._to_dotnet_random_number_sequence(runtime, random_number_actions)
        get_raws = getattr(runtime["RandomNumberExtensionsType"], "GetRaws", None)
        if callable(get_raws):
            raw_values = get_raws(random_number_values)
        else:
            raw_values = runtime["RandomNumberExtensionsType"].GetMethod("GetRaws").Invoke(None, [random_number_values])
        return [_to_signed_int32(int(value)) for value in raw_values or []]

    def _to_dotnet_random_number_sequence(self, runtime: dict[str, Any], random_number_actions: list[Any]) -> Any:
        dotnet_random_number_array = runtime.get("DotNetRandomNumberArray")
        if dotnet_random_number_array is None:
            return random_number_actions
        try:
            return dotnet_random_number_array(random_number_actions)
        except Exception as exc:
            raise RuntimeError(f"Failed converting RandomNumber actions to a .NET sequence: {exc}") from exc

    def _send_random_numbers(self, runtime: dict[str, Any], client: Any, raw_ints: list[int]) -> None:
        rand_numbers = runtime["QARandNumbers"]()
        rand_numbers.Numbers = runtime["DotNetIntArray"](raw_ints)
        _append_command_file_log("SGF SetRandomNumbers", "SGF VLT", f"count={len(raw_ints)}")
        client.SetRandomNumbers(rand_numbers)

    def _send_feature_pots(self, runtime: dict[str, Any], client: Any, feature_pot_pairs: list[tuple[int, int]]) -> None:
        feature_pot_items = []
        for index, value in feature_pot_pairs:
            item = runtime["QAFeaturePotValue"]()
            item.Index = int(index)
            item.Value = int(value)
            feature_pot_items.append(item)
        values = runtime["QAFeaturePotValues"]()
        values.Values = runtime["DotNetFeaturePotArray"](feature_pot_items)
        _append_command_file_log("SGF SetFeaturePots", "SGF VLT", f"count={len(feature_pot_pairs)}")
        client.SetFeaturePots(values)

    def _send_player_decisions(self, runtime: dict[str, Any], client: Any, player_decisions: list[Any]) -> None:
        decision_values = _extract_sgfhd_player_decision_values(player_decisions)
        if not decision_values:
            return
        decisions = runtime["QAPlayerDecisions"]()
        decisions.Decisions = runtime["DotNetUIntArray"](decision_values)
        _append_command_file_log("SGF SetPlayerDecisions", "SGF VLT", f"count={len(decision_values)}")
        client.SetPlayerDecisions(decisions)

    def _ensure_sgf_runtime(self) -> dict[str, Any]:
        if self._sgf_runtime is not None:
            return self._sgf_runtime
        runtime_dir = SgfVltConnectionProbe._prepare_runtime_dir()
        try:
            import clr  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                f"pythonnet is required but could not be imported: {exc}. "
                "Please ensure pythonnet is installed."
            ) from exc
        try:
            for dll_name in REQUIRED_SGFHD_DOTNET_DLLS:
                clr.AddReference(str(runtime_dir / dll_name))
        except Exception as exc:
            raise RuntimeError(f"Failed to load SGF .NET assemblies: {exc}") from exc
        MptCommon = __import__("IGT.Ignite.Tools.Mpt.Common", fromlist=["RandomNumber", "PlayerDecision"])
        Snippet121 = __import__("IGT.Ignite.Tools.Mpt.Common.Snippet121", fromlist=["SaeContentSerializer"])
        SensysPlugin = __import__("IGT.Spielo.Tools.Mpt.SensysPlugin", fromlist=["RandomNumberExtensions"])
        SensysContracts = __import__(
            "IGT.Spielo.Tools.Mpt.SensysPlugin.Contracts",
            fromlist=[
                "QATestingServiceClientFactory",
                "QARandNumbers",
                "QAFeaturePotValues",
                "QAFeaturePotValue",
                "QAPlayerDecisions",
            ],
        )
        System = __import__("System")
        SystemIO = __import__("System.IO", fromlist=["MemoryStream"])
        self._sgf_runtime = {
            "SaeContentSerializer": Snippet121.SaeContentSerializer,
            "ClientFactory": SensysContracts.QATestingServiceClientFactory,
            "QARandNumbers": SensysContracts.QARandNumbers,
            "QAFeaturePotValues": SensysContracts.QAFeaturePotValues,
            "QAFeaturePotValue": SensysContracts.QAFeaturePotValue,
            "QAPlayerDecisions": SensysContracts.QAPlayerDecisions,
            "RandomNumberType": getattr(MptCommon, "RandomNumber", None),
            "PlayerDecisionType": getattr(MptCommon, "PlayerDecision", None),
            "RandomNumberExtensionsType": getattr(SensysPlugin, "RandomNumberExtensions", None),
            "MemoryStream": SystemIO.MemoryStream,
            "DotNetByteArray": System.Array[System.Byte],
            "DotNetIntArray": System.Array[System.Int32],
            "DotNetUIntArray": System.Array[System.UInt32],
            "DotNetFeaturePotArray": System.Array[SensysContracts.QAFeaturePotValue],
        }
        if self._sgf_runtime["RandomNumberType"] is None:
            self._sgf_runtime["RandomNumberType"] = _find_dotnet_type(
                System,
                "IGT.Ignite.Tools.Mpt.Common.RandomNumber",
                "RandomNumber",
            )
        if self._sgf_runtime["PlayerDecisionType"] is None:
            self._sgf_runtime["PlayerDecisionType"] = _find_dotnet_type(
                System,
                "IGT.Ignite.Tools.Mpt.Common.PlayerDecision",
                "PlayerDecision",
            )
        if self._sgf_runtime["RandomNumberExtensionsType"] is None:
            self._sgf_runtime["RandomNumberExtensionsType"] = _find_dotnet_type(
                System,
                "IGT.Spielo.Tools.Mpt.SensysPlugin.RandomNumberExtensions",
                "RandomNumberExtensions",
            )
        self._sgf_runtime["DotNetRandomNumberArray"] = System.Array[self._sgf_runtime["RandomNumberType"]]
        return self._sgf_runtime


class BulkSnippetGenerator:
    def __init__(
        self,
        config: GenerationConfig,
        *,
        sink: WorkflowEventSink | None = None,
        start_manual_send: bool = True,
    ) -> None:
        self.config = config
        self.sink = sink or TerminalWorkflowEventSink()
        self.start_manual_send = start_manual_send
        self.manual_send_paths = build_manual_send_paths(config.output_xml_path, config.run_id)
        self.session = GeneratedRunSession.from_config(config, self.manual_send_paths)
        self.app = None
        self.writer = SaeSnippetWriter()
        self.writer.set_egv_index(config.variant_index)
        self.writer.set_paytable_dll_path(str(config.paytable_path.resolve()))

        self.capture_state = SnippetCaptureState()
        self._hook_funcs: list[Any] = []
        self._hook_wrappers: dict[int, Callable[..., Any]] = {}
        self._have_error_message_hook = False
        self._qt_version = ""
        self._selected_bet = 0
        self._game_specific_settings: list[int] = []
        self._resolved_stake_fields: dict[str, int] = {}
        self._seed = config.seed
        self._games_generated = 0
        self._snippets_generated = 0
        self._cumulative_selected_bet = 0
        self._error_code = 0
        self._stop_reason: str | None = None

    def run(self) -> int:
        self.sink.generation_started(self.config)
        self._print_startup_log()
        self._validate_config()
        self._validate_runtime_dependencies()
        self._verify_vlt_connection_if_requested()
        self.config.output_xml_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self.manual_send_paths.manual_send_dir.mkdir(parents=True, exist_ok=True)

        self.writer.add_category(self.writer.create_category(self.config.category_name))
        self.app = qt.QTD_Application()
        self._hook_wrappers = {
            qt.PTI_HOOK_PLAYER_DECISION_32: qt.WrapHookPlayerDecision32,
            qt.PTI_HOOK_GET_RAW_32BIT_RANDOM_NUMBERS: qt.WrapHookGetRaw32BitRandomNumbers,
            qt.PTI_HOOK_PENG_LOAD_BASE_GAME: qt.WrapHookPengLoadBaseGame,
            qt.PTI_HOOK_PENG_POST_GAME_LOOP: qt.WrapHookPengPostGameLoop,
            qt.PTI_HOOK_SET_ERROR: qt.WrapHookSetError,
            qt.PTI_HOOK_SET_ERROR_MESSAGE: qt.WrapHookSetErrorMessage,
        }

        try:
            self._setup_app()
            self._register_hooks()
            self._seed_rng()
            self._load_paytable_binary()
            self._apply_stakes()
            self.writer.set_qt_version(self._qt_version)
            self.app.StartMainLoop()
            if not self._error_code and self._snippets_generated != self.config.snippet_count:
                raise RuntimeError(
                    f"Generation stopped after {self._snippets_generated} of "
                    f"{self.config.snippet_count} requested snippets."
                )
        except Exception as exc:
            if not self._error_code:
                self._error_code = 1
            if not self._stop_reason:
                self._stop_reason = str(exc)
            self.sink.generation_failed(
                "Snippet generation failed.",
                exc=exc,
                context=self._build_error_context(),
            )
        finally:
            self._write_partial_or_final_xml()

        if self._error_code:
            return self._error_code

        progress = self._create_manual_send_progress()
        self.sink.generation_completed(self.session, progress)
        if not self.start_manual_send:
            return 0
        try:
            return ManualSendRunner(self.session, progress, sink=self.sink).run()
        except Exception as exc:
            self.sink.generation_failed(
                "Manual send workflow failed.",
                exc=exc,
                context=self._build_error_context(),
            )
            return 1

    def _validate_runtime_dependencies(self) -> None:
        missing = []
        if qt is None:
            missing.append(f"pyquicktest import failed: {PYQUICKTEST_IMPORT_ERROR}")
        if pysaelib is None:
            missing.append(f"pysaelib import failed: {PYSAELIB_IMPORT_ERROR}")
        if missing:
            raise RuntimeError("\n".join([*missing, DEPENDENCY_HELP]))

    def _validate_config(self) -> None:
        if not self.config.paytable_path.is_file():
            raise FileNotFoundError(f"Paytable binary not found: {self.config.paytable_path}")
        if not self.config.qtpti_path.is_file():
            raise FileNotFoundError(f"QTPTI DLL not found: {self.config.qtpti_path}")
        if self.config.snippet_count <= 0:
            raise ValueError("Snippet count must be a positive integer.")
        if self.config.game_type not in GameType.ALL:
            raise ValueError(f"Game type must be one of: {', '.join(GameType.ALL)}")
        if self.config.variant_index < 0:
            raise ValueError("Variant index must be zero or greater.")
        if self.config.vlt_connection is not None:
            if not 1 <= self.config.vlt_connection.port <= 65535:
                raise ValueError("VLT port must be between 1 and 65535.")
            if self.config.vlt_connection.timeout_seconds <= 0:
                raise ValueError("VLT connection timeout must be greater than zero.")
        for name, value in self.config.stake_overrides.items():
            if value is not None and value < 0:
                raise ValueError(f"Stake override '{name}' must be zero or greater.")
        for key, value in self.config.game_specific_stake_items.items():
            if key < 0 or value < 0:
                raise ValueError("Game-specific stake items must use non-negative integer keys and values.")

    def _verify_vlt_connection_if_requested(self) -> None:
        if self.config.vlt_connection is None or self.config.vlt_connection_verified:
            return
        VltConnectionProbe.verify(self.config.game_type, self.config.vlt_connection)

    def _setup_app(self) -> None:
        ret = self.app.Initialize(str(self.config.qtpti_path))
        self._qt_version = self.app.GetQtptiVersion()
        self.session.qt_version = self._qt_version
        if ret:
            message = self.app.GetAppErrorMessage(ret)
            raise RuntimeError(f"Error while loading QTPTI '{self.config.qtpti_path}':\n{message}")

    def _register_hooks(self) -> None:
        def wrap_callback(method: Callable[..., Any]) -> Callable[..., Any]:
            def wrapped(*args: Any) -> Any:
                try:
                    return method(*args)
                except Exception:
                    self._handle_hook_exception(method.__name__, sys.exc_info()[1])
                    return 0

            return wrapped

        hooks = (
            (qt.PTI_HOOK_PLAYER_DECISION_32, self._on_hook_player_decision_32),
            (qt.PTI_HOOK_GET_RAW_32BIT_RANDOM_NUMBERS, self._on_hook_get_raw_32bit_random_numbers),
            (qt.PTI_HOOK_PENG_LOAD_BASE_GAME, self._on_hook_peng_load_base_game),
            (qt.PTI_HOOK_PENG_POST_GAME_LOOP, self._on_hook_peng_post_game_loop),
            (qt.PTI_HOOK_SET_ERROR, self._on_hook_set_error),
            (qt.PTI_HOOK_SET_ERROR_MESSAGE, self._on_hook_set_error_message),
        )
        for hook_id, method in hooks:
            hook_method = self._hook_wrappers[hook_id](wrap_callback(method))
            self._hook_funcs.append(hook_method)
            result = self.app.RegisterCallback(hook_id, hook_method, 0)
            if result:
                raise RuntimeError(f"Could not register hook '{method.__name__}' (hook id {hook_id}, error {result}).")

    def _seed_rng(self) -> None:
        if self._seed is None:
            self._seed = int(time.time_ns()) & 0xFFFFFFFF
        self.session.seed = self._seed
        self.app.SeedRng(self._seed)

    def _load_paytable_binary(self) -> None:
        ret = self.app.LoadPaytableBinary(str(self.config.paytable_path), False, self.config.variant_index)
        if ret:
            message = self.app.GetAppErrorMessage(ret)
            raise RuntimeError(
                f"Error while loading paytable '{self.config.paytable_path}' "
                f"(with QTPTI '{self.config.qtpti_path}'):\n{message}"
            )

    def _apply_stakes(self) -> None:
        for definition in STAKE_FIELD_DEFINITIONS:
            value = self.config.stake_overrides.get(definition.name)
            if value is None:
                continue
            self.app.SetCurrentStakeSetting(getattr(qt, definition.qt_constant_name), value)

        num_game_specific = self.app.GetNumGameSpecificStakeItems()
        for key, value in self.config.game_specific_stake_items.items():
            if key not in range(num_game_specific):
                raise ValueError(f"Invalid game-specific stake item index {key}.")
            self.app.SetGameSpecificStakeSetting(key, value)

        for definition in STAKE_FIELD_DEFINITIONS:
            qt_key = getattr(qt, definition.qt_constant_name)
            self._resolved_stake_fields[definition.name] = int(self.app.GetCurrentStakeSetting(qt_key))

        self._game_specific_settings = [
            int(self.app.GetGameSpecificStakeSetting(index)) for index in range(num_game_specific)
        ]
        self._selected_bet = int(self.app.GetSelectedBet())

    def _build_error_context(self) -> dict[str, Any]:
        return {
            "run_id": self.config.run_id,
            "paytable": self.config.paytable_path.name,
            "game_type": self.config.game_type,
            "variant": self.config.variant_index,
            "snippets_generated": self._snippets_generated,
            "snippet_target": self.config.snippet_count,
        }

    def _print_startup_log(self) -> None:
        if self.config.vlt_connection is None:
            vlt_value = "Not provided"
        else:
            vlt_value = f"{self.config.vlt_connection.ip_address}:{self.config.vlt_connection.port}"

        self.sink.log("Run Configuration")
        self.sink.log(f"VLT IP: {vlt_value}")
        self.sink.log(f"SGF/UGF Selection: {self.config.game_type}")
        self.sink.log(f"Paytable Binary: {self.config.paytable_path}")
        self.sink.log(f"DLL File: {self.config.qtpti_path}")
        self.sink.log(f"Number of Snippets: {self.config.snippet_count}")
        self.sink.log("Run Logs:")

    def _handle_hook_exception(self, hook_name: str, exc: BaseException | None) -> None:
        log_terminal_error(
            f"Hook '{hook_name}' raised an exception.",
            exc=exc,
            context={**self._build_error_context(), "hook": hook_name},
            include_traceback=True,
        )
        if exc is None:
            message = f"Exception in hook '{hook_name}'."
        else:
            message = f"Exception in hook '{hook_name}': {traceback.format_exc().strip()}"
        if self.app.IsMethodSupported("SetHookException"):
            self.app.SetHookException(message, 0)
        else:
            self._fail(message, 1, already_logged=True)

    def _on_hook_player_decision_32(self, env: Any, def_param: Any, num_choices: int, condition_id: int, context: int) -> None:
        del env, num_choices, condition_id, context
        if len(self.capture_state.replay_values) < 2:
            raise RuntimeError("Player decision hook fired before two raw random numbers were recorded.")
        self.capture_state.replay_values = self.capture_state.replay_values[:-2]
        self.capture_state.replay_values.append(
            (ReplayValueType.PLAYER_DECISION, int(def_param.contents.value))
        )

    def _on_hook_get_raw_32bit_random_numbers(self, env: Any, count: int, def_param: Any, context: int) -> None:
        del env, context
        for random_number in def_param[0:count]:
            self.capture_state.replay_values.append((ReplayValueType.RANDOM_NUMBER, int(random_number)))

    def _on_hook_peng_load_base_game(self, env: Any, context: int) -> None:
        del env, context
        self.capture_state.feature_pots = [
            int(self.app.GetFeaturePot(index)) for index in range(self.app.GetNumFeaturePots())
        ]

    def _on_hook_peng_post_game_loop(self, env: Any, context: int) -> None:
        del env, context
        self._games_generated += 1
        self._snippets_generated += 1
        self._cumulative_selected_bet += self._selected_bet
        snippet_name = f"snippet_{self._snippets_generated:06d}"
        snippet_id = f"{self.config.run_id}:{snippet_name}"

        all_win_infos = list(self.app.GetWinInfos())
        win_infos = [serialize_win_info(win_info) for win_info in all_win_infos]
        math_summary = summarize_win_infos(all_win_infos, self._selected_bet)

        snippet = self.writer.create_snippet(
            snippet_name=snippet_name,
            resolved_stake_fields=self._resolved_stake_fields,
            game_specific_settings=self._game_specific_settings,
            replay_values=list(self.capture_state.replay_values),
            feature_pots=list(self.capture_state.feature_pots),
        )
        self.writer.add_snippet_to_category(self.config.category_name, snippet)

        record = SnippetRecord(
            run_id=self.config.run_id,
            snippet_id=snippet_id,
            snippet_index=self._snippets_generated,
            snippet_name=snippet_name,
            selected_bet_credits=math_summary.selected_bet_credits,
            resolved_stake_fields=dict(self._resolved_stake_fields),
            game_specific_settings=list(self._game_specific_settings),
            feature_pots=list(self.capture_state.feature_pots),
            replay_values=list(self.capture_state.replay_values),
            raw_random_count=self.capture_state.raw_random_count,
            player_decision_count=self.capture_state.player_decision_count,
            feature_pot_count=self.capture_state.feature_pot_count,
            win_infos=win_infos,
            credit_win_total=math_summary.credit_win_total,
            jackpot_credit_total=math_summary.jackpot_credit_total,
            wager_from_win_total=math_summary.wager_from_win_total,
            expected_meter_delta=math_summary.expected_meter_delta,
            snippets_generated_total=self._snippets_generated,
            games_generated_total=self._games_generated,
            cumulative_selected_bet=self._cumulative_selected_bet,
            timestamp_utc=utc_timestamp(),
        )
        self.session.snippet_records.append(record)
        write_audit_jsonl(self.session, progress=None)
        self._print_snippet_log(record)

        self.capture_state.reset()
        if self._snippets_generated >= self.config.snippet_count:
            self.app.QuitMainLoop()

    def _on_hook_set_error(self, env: Any, error: int, arg: int, context: int) -> None:
        del env, context
        if self._have_error_message_hook:
            return
        self._fail(f"MPT Error (code={error}, arg={arg})", 1)

    def _on_hook_set_error_message(self, env: Any, msg: str, error: int, arg: int, context: int) -> None:
        del env, error, arg, context
        self._have_error_message_hook = True
        self._fail(f"MPT Error: {msg}", 1)

    def _fail(self, message: str, exit_code: int, *, already_logged: bool = False) -> None:
        self.capture_state.errors.append(message)
        self._error_code = exit_code
        self._stop_reason = message
        if not already_logged:
            log_terminal_error(message, context=self._build_error_context())
        if self.app is not None:
            self.app.QuitMainLoop()

    def _write_partial_or_final_xml(self) -> None:
        if not self.writer.categories:
            return
        if self._snippets_generated == 0:
            return
        self.writer.write_xml(self.config.output_xml_path)
        if self._error_code:
            self._write_stop_message(
                f"Partial XML written to '{self.config.output_xml_path}' after failure.",
                self.sink,
            )
        else:
            self._write_stop_message(f"Bulk XML written to '{self.config.output_xml_path}'.", self.sink)
        self._write_stop_message(f"Audit JSONL written to '{self.config.audit_jsonl_path}'.", self.sink)

    def _format_stake_log(self) -> str:
        fields = [f"{name}={value}" for name, value in self._resolved_stake_fields.items()]
        if self._game_specific_settings:
            game_specific = ",".join(
                f"{index}:{value}" for index, value in enumerate(self._game_specific_settings)
            )
            fields.append(f"game_specific={game_specific}")
        fields.append(f"selected_bet={self._selected_bet}")
        return " ".join(fields)

    def _print_snippet_log(self, record: SnippetRecord) -> None:
        delta = record.expected_meter_delta
        self.sink.log(
            f"[{record.snippet_index}/{self.config.snippet_count}] "
            f"{record.snippet_name} "
            f"paytable={self.config.paytable_path.name} "
            f"game_type={self.config.game_type} "
            f"variant={self.config.variant_index} "
            f"{self._format_stake_log()} "
            f"raw_randoms={record.raw_random_count} "
            f"player_decisions={record.player_decision_count} "
            f"feature_pots={record.feature_pot_count} "
            f"coin_in={delta.total_cash_in} "
            f"coin_out={delta.total_cash_out} "
            f"net={delta.net} "
            f"running_snippets={record.snippets_generated_total} "
            f"games_generated={record.games_generated_total} "
            f"cumulative_selected_bet={record.cumulative_selected_bet}"
        )

    def _create_manual_send_progress(self) -> ManualSendProgress:
        if not self.session.snippet_records:
            raise RuntimeError("Generation completed without any snippet records to send.")
        self.session.save()
        progress = ManualSendProgress.new(
            self.session.run_id,
            Path(self.session.session_json_path),
            Path(self.session.current_snippet_xml_path),
        )
        progress.save(Path(self.session.progress_json_path))
        write_audit_jsonl(self.session, progress)
        self.sink.log(f"Manual send session saved to: {self.session.session_json_path}")
        self.sink.log(f"Manual send progress file: {self.session.progress_json_path}")
        self.sink.log(f"Resume later with: python SASautomator.py --resume \"{self.session.progress_json_path}\"")
        return progress

    @staticmethod
    def _write_stop_message(message: str, sink: WorkflowEventSink | None = None) -> None:
        if message:
            lowered = message.lower()
            is_error = any(token in lowered for token in ("traceback", "failed", "error", "exception"))
            if sink is None:
                print(message, file=sys.stderr if is_error else sys.stdout)
            else:
                sink.log(message, is_error=is_error)


class ManualSendRunner:
    def __init__(
        self,
        session: GeneratedRunSession,
        progress: ManualSendProgress,
        *,
        sink: WorkflowEventSink | None = None,
    ) -> None:
        self.session = session
        self.progress = progress
        self.sink = sink or TerminalWorkflowEventSink()
        self.progress_path = Path(self.session.progress_json_path)

    @classmethod
    def load_from_progress_file(cls, progress_path: Path) -> "ManualSendRunner":
        progress = ManualSendProgress.load(progress_path)
        session = GeneratedRunSession.load(Path(progress.session_json_path))
        if session.run_id != progress.run_id:
            raise RuntimeError(
                f"Progress run_id '{progress.run_id}' does not match session run_id '{session.run_id}'."
            )
        return cls(session, progress)

    def run(self) -> int:
        self._validate_runtime_dependencies()
        self._validate_progress_state()
        self.session.save()
        self._persist_state()
        return self._run_loop()

    def _validate_runtime_dependencies(self) -> None:
        if pysaelib is None:
            raise RuntimeError(
                "\n".join(
                    [
                        f"pysaelib import failed: {PYSAELIB_IMPORT_ERROR}",
                        DEPENDENCY_HELP,
                    ]
                )
            )

    def _validate_progress_state(self) -> None:
        if self.progress.completed_count != len(self.progress.completion_history):
            raise RuntimeError(
                "Progress file is inconsistent: completed_count does not match completion history length."
            )
        if self.progress.next_snippet_index != self.progress.completed_count + 1:
            raise RuntimeError(
                "Progress file is inconsistent: next_snippet_index does not align with completed_count."
            )

    def _current_record(self) -> SnippetRecord | None:
        if self.progress.next_snippet_index < 1:
            return None
        if self.progress.next_snippet_index > len(self.session.snippet_records):
            return None
        return self.session.snippet_records[self.progress.next_snippet_index - 1]

    def peek_current_record(self) -> SnippetRecord | None:
        return self._current_record()

    def _persist_state(self) -> None:
        self.progress.save(self.progress_path)
        write_audit_jsonl(self.session, self.progress)

    def _print_meter_block(self, title: str, meters: dict[str, int | float]) -> None:
        self.sink.log(title)
        for meter_name in METER_DISPLAY_ORDER:
            if meter_name not in meters:
                continue
            self.sink.log(f"  {meter_name}: {format_meter_value(meter_name, meters[meter_name])}")

    def _print_current_record(self, record: SnippetRecord) -> None:
        self.sink.log("")
        self.sink.log(
            f"Prepared snippet {record.snippet_index}/{len(self.session.snippet_records)}: "
            f"{record.snippet_name}"
        )
        self.sink.log(f"Current snippet XML: {self.session.current_snippet_xml_path}")
        self.sink.log(f"Replay summary: {record.replay_summary()}")
        self.sink.log(
            "Win info totals: "
            f"selected_bet_credits={record.selected_bet_credits} "
            f"credit_win_total={record.credit_win_total} "
            f"jackpot_credit_total={record.jackpot_credit_total} "
            f"wager_from_win_total={record.wager_from_win_total}"
        )
        self._print_meter_block(
            "Snippet Meter:",
            record.expected_meter_delta.to_display_dict(),
        )
        self._print_meter_block(
            "Cumulative Meters:",
            self.progress.tracked_meters.to_display_dict(),
        )
        self.sink.log(
            "Send this snippet with your existing manual workflow, then press Enter only "
            "after the VLT is fully done. Type 'q' to save and quit."
        )

    def _print_completion(self, record: SnippetRecord) -> None:
        self.sink.log(
            f"Completed snippet {record.snippet_index}/{len(self.session.snippet_records)}: "
            f"{record.snippet_name}"
        )
        self._print_meter_block(
            "Cumulative Meters:",
            self.progress.tracked_meters.to_display_dict(),
        )
        self.sink.log(f"Progress saved to: {self.session.progress_json_path}")

    def _print_final_summary(self) -> None:
        self.sink.log("")
        self.sink.log("Manual send session complete.")
        self._print_meter_block(
            "Cumulative Meters:",
            self.progress.tracked_meters.to_display_dict(),
        )
        self.sink.log(f"Bulk XML: {self.session.output_xml_path}")
        self.sink.log(f"Audit JSONL: {self.session.audit_jsonl_path}")
        self.sink.log(f"Progress file: {self.session.progress_json_path}")

    def prepare_current_snippet(self) -> SnippetRecord | None:
        current_record = self._current_record()
        if current_record is None:
            self._persist_state()
            self._print_final_summary()
            self.sink.final_summary(self.session, self.progress)
            return None
        self.session.write_current_snippet_xml(current_record)
        self._persist_state()
        self._print_current_record(current_record)
        self.sink.snippet_prepared(self.session, self.progress, current_record)
        return current_record

    def complete_current_snippet(self, latest_completed_bank: int | None = None) -> SnippetRecord:
        current_record = self._current_record()
        if current_record is None:
            raise RuntimeError("There is no current snippet to complete.")
        self.progress.mark_completed(current_record, latest_completed_bank=latest_completed_bank)
        self._persist_state()
        self._print_completion(current_record)
        self.sink.snippet_completed(self.session, self.progress, current_record)
        return current_record

    def _run_loop(self) -> int:
        while True:
            current_record = self.prepare_current_snippet()
            if current_record is None:
                return 0

            try:
                response = self.sink.request_completion_input(
                    "Press Enter after the send fully completes, or type 'q' to save and quit: "
                ).strip().lower()
            except KeyboardInterrupt:
                self.sink.log("")
                self._persist_state()
                self.sink.log("Manual send session interrupted.")
                self.sink.log(f"Resume later with: python SASautomator.py --resume \"{self.session.progress_json_path}\"")
                return 130

            if response in {"q", "quit", "exit"}:
                self._persist_state()
                self.sink.log("Manual send session paused.")
                self.sink.log(f"Resume later with: python SASautomator.py --resume \"{self.session.progress_json_path}\"")
                return 0

            if response:
                self.sink.log("Press Enter to confirm completion, or type 'q' to quit.")
                continue

            self.complete_current_snippet()


class ImportedSnippetRunner(ManualSendRunner):
    def __init__(
        self,
        game_type: str,
        snippet_xmls: list[str],
        records: list[SnippetRecord],
        *,
        source_description: str = "Imported SAE XML",
        sink: WorkflowEventSink | None = None,
    ) -> None:
        if not records:
            raise ValueError("Imported snippet runner requires at least one record.")
        if len(snippet_xmls) != len(records):
            raise ValueError("Imported snippet runner requires one XML payload per record.")
        manual_send_dir = _get_app_base_dir() / MANUAL_SEND_DIR_NAME
        current_snippet_xml_path = manual_send_dir / CURRENT_SNIPPET_FILENAME
        session = GeneratedRunSession(
            version=STATE_FILE_VERSION,
            run_id=records[0].run_id,
            category_name="imported",
            paytable_path="",
            paytable_name="",
            game_type=game_type,
            variant_index=0,
            seed=None,
            qt_version="",
            output_xml_path="",
            audit_jsonl_path="",
            vlt_ip=None,
            vlt_port=None,
            manual_send_dir=str(manual_send_dir.resolve()),
            current_snippet_xml_path=str(current_snippet_xml_path.resolve()),
            session_json_path=str((manual_send_dir / "imported_session.json").resolve()),
            progress_json_path=str((manual_send_dir / "imported_progress.json").resolve()),
            snippet_records=list(records),
        )
        progress = ManualSendProgress.new(
            run_id=session.run_id,
            session_json_path=Path(session.session_json_path),
            current_snippet_xml_path=Path(session.current_snippet_xml_path),
        )
        super().__init__(session, progress, sink=sink)
        self.snippet_xml = snippet_xmls[0]
        self.snippet_xmls_by_index = {
            record.snippet_index: snippet_xml
            for record, snippet_xml in zip(records, snippet_xmls)
        }
        self.source_description = source_description
        self._final_summary_emitted = False

    def _persist_state(self) -> None:
        return

    def _print_final_summary(self) -> None:
        self.sink.log("")
        if len(self.session.snippet_records) == 1:
            self.sink.log(f"{self.source_description} complete.")
        else:
            self.sink.log(f"{self.source_description} complete: {len(self.session.snippet_records)} snippets.")
        self._print_meter_block(
            "Cumulative Meters:",
            self.progress.tracked_meters.to_display_dict(),
        )
        self.sink.log(f"Current snippet XML: {self.session.current_snippet_xml_path}")

    def prepare_current_snippet(self) -> SnippetRecord | None:
        current_record = self._current_record()
        if current_record is None:
            if not self._final_summary_emitted:
                self._print_final_summary()
                self.sink.final_summary(self.session, self.progress)
                self._final_summary_emitted = True
            return None

        output_path = Path(self.session.current_snippet_xml_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        snippet_xml = self.snippet_xmls_by_index.get(current_record.snippet_index)
        if snippet_xml is None:
            raise RuntimeError(f"Imported XML payload missing for snippet index {current_record.snippet_index}.")
        output_path.write_text(snippet_xml, encoding="utf-8")
        self._print_current_record(current_record)
        self.sink.snippet_prepared(self.session, self.progress, current_record)
        return current_record


def _build_imported_snippet_load_result(
    game_type: str,
    parsed_xmls: list[ImportedSnippetParseResult],
    *,
    source_description: str,
    run_id: str = "imported",
) -> ImportedSnippetLoadResult:
    if not parsed_xmls:
        raise ValueError("Imported SAE XML batch cannot be empty.")
    cumulative_selected_bet = 0
    records: list[SnippetRecord] = []
    for snippet_index, parsed_xml in enumerate(parsed_xmls, start=1):
        cumulative_selected_bet += parsed_xml.selected_bet_credits
        records.append(
            build_indexed_imported_snippet_record(
                parsed_xml,
                snippet_index=snippet_index,
                cumulative_selected_bet=cumulative_selected_bet,
                run_id=run_id,
            )
        )
    runner = ImportedSnippetRunner(
        game_type=game_type,
        snippet_xmls=[parsed_xml.snippet_xml for parsed_xml in parsed_xmls],
        records=records,
        source_description=source_description,
    )
    return ImportedSnippetLoadResult(
        game_type=game_type,
        parsed_xml=parsed_xmls[0],
        parsed_xmls=list(parsed_xmls),
        record=records[0],
        records=records,
        total_snippet_count=len(records),
        source_description=source_description,
        runner=runner,
    )


def prepare_imported_snippet_load(raw_game_type: str, raw_xml: str) -> ImportedSnippetLoadResult:
    game_type = normalize_game_type(raw_game_type)
    parsed_xmls = parse_imported_sae_snippet_xml_batch(raw_xml)
    return _build_imported_snippet_load_result(
        game_type,
        parsed_xmls,
        source_description="Imported SAE snippet",
    )


def is_valid_snippet_count(raw_value: str) -> bool:
    try:
        return int(raw_value) > 0
    except (TypeError, ValueError):
        return False


class SASAutomatorGuiApp(WorkflowEventSink):
    def __init__(self, root: Any) -> None:
        if tk is None:
            raise RuntimeError("tkinter is not available in this Python environment.")
        self.root = root
        self.root.title("SAS Automator")
        self.root.configure(bg=GUI_BG)
        self.root.geometry(f"{GUI_WINDOW_WIDTH}x{GUI_WINDOW_HEIGHT}")
        self.root.minsize(GUI_WINDOW_MIN_WIDTH, GUI_WINDOW_MIN_HEIGHT)

        settings = load_gui_settings()
        self.ui_queue: "queue.Queue[tuple[Callable[..., None], tuple[Any, ...], dict[str, Any]]]" = queue.Queue()
        self.is_connected = False
        self.is_generating = False
        self.is_sending = False
        self.is_auto_running = False
        self.stop_requested = False
        self.is_pick_a_prize_touching = False
        self.connected_ip = ""
        self.current_snippet_bank_value: int | None = None
        self.latest_completed_bank_value: int | None = None
        self._pick_a_prize_touch_controller: PickAPrizeTouchController | None = None
        self._pick_a_prize_machine_name: str | None = None
        self._bonus_touch_active = False
        self.current_record: SnippetRecord | None = None
        self.manual_runner: ManualSendRunner | None = None
        self.ugf_sender = UgfVltSnippetSender()
        self.sgf_sender = SgfVltSnippetSender()

        self.ip_var = tk.StringVar(value=str(settings.get("ip_address", "")))
        self.game_type_var = tk.StringVar(value=str(settings.get("game_type", "")))
        self.paytable_var = tk.StringVar(value=str(settings.get("paytable_path", "")))
        self.qtpti_var = tk.StringVar(value=str(settings.get("qtpti_path", "")))
        self.snippet_count_var = tk.StringVar(value=str(settings.get("snippet_count", "1")))

        self.connect_btn = None
        self.generate_btn = None
        self.load_xml_btn = None
        self.run_btn = None
        self.stop_btn = None
        self.reset_btn = None
        self.ip_entry = None
        self.ugf_btn = None
        self.sgf_btn = None
        self.status_canvas = None
        self.status_indicator = None
        self.current_meter_text = None
        self.cumulative_meter_text = None
        self.log_text = None
        self.command_log_text = None
        self.log_panes = None
        self.is_loading_xml = False
        self.import_xml_row = None
        self.import_xml_text = None
        self.import_xml_load_btn = None
        self.import_xml_cancel_btn = None
        self.import_xml_row_visible = False
        self.snippet_count_row = None
        self.snippet_spinbox = None
        self.snippet_count_row_visible = False

        self._build_ui()
        self._render_meter_panels(None, TrackedMeters())
        self._append_log("Ready.")
        self._set_status_indicator(False)
        self._refresh_controls()
        self.root.after(75, self._drain_ui_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=GUI_BG, padx=12, pady=12)
        outer.pack(fill="both", expand=True)

        header = tk.Label(
            outer,
            text="SAS Automator",
            bg=GUI_BG,
            fg=GUI_TEXT,
            font=("Consolas", 18, "bold"),
            anchor="w",
        )
        header.pack(fill="x", pady=(0, 10))

        connect_row = tk.Frame(outer, bg=GUI_BG)
        connect_row.pack(fill="x", pady=(0, 8))
        tk.Label(connect_row, text="IP address", bg=GUI_BG, fg=GUI_TEXT, font=("Consolas", 10, "bold")).pack(
            side="left",
            padx=(0, 8),
        )
        self.ip_entry = tk.Entry(
            connect_row,
            textvariable=self.ip_var,
            width=16,
            bg=GUI_SURFACE,
            fg=GUI_TEXT,
            insertbackground=GUI_TEXT,
            relief="flat",
            bd=0,
            font=("Consolas", 11, "bold"),
        )
        self.ip_entry.pack(side="left")
        self.ip_entry.bind("<KeyRelease>", lambda _event: self._refresh_controls())

        mode_row = tk.Frame(connect_row, bg=GUI_BG)
        mode_row.pack(side="left", padx=(12, 0))
        self.ugf_btn = tk.Radiobutton(
            mode_row,
            text="UGF",
            variable=self.game_type_var,
            value=GameType.UGF,
            command=self._refresh_controls,
            indicatoron=False,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            selectcolor=GUI_ACCENT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            width=6,
            font=("Consolas", 9, "bold"),
        )
        self.ugf_btn.pack(side="left", padx=(0, 4))
        self.sgf_btn = tk.Radiobutton(
            mode_row,
            text="SGF",
            variable=self.game_type_var,
            value=GameType.SGF,
            command=self._refresh_controls,
            indicatoron=False,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            selectcolor=GUI_ACCENT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            width=6,
            font=("Consolas", 9, "bold"),
        )
        self.sgf_btn.pack(side="left")

        self.connect_btn = tk.Button(
            connect_row,
            text="Connect",
            command=self._toggle_connection,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=10,
        )
        self.connect_btn.pack(side="left", padx=(12, 10))
        self.status_canvas = tk.Canvas(connect_row, width=16, height=16, bg=GUI_BG, highlightthickness=0, bd=0)
        self.status_canvas.pack(side="left")
        self.status_indicator = self.status_canvas.create_oval(2, 2, 14, 14, fill=GUI_ERROR, outline=GUI_ERROR)

        self._build_file_row(outer, "Paytable Binary", self.paytable_var, self._browse_paytable)
        self._build_file_row(outer, "Paytable Interpreter", self.qtpti_var, self._browse_qtpti)
        self._build_import_xml_panel(outer)

        action_row = tk.Frame(outer, bg=GUI_BG)
        action_row.pack(fill="x", pady=(0, 8))
        snippet_count_row = tk.Frame(action_row, bg=GUI_BG)
        tk.Label(
            snippet_count_row,
            text="Snippet Amount",
            bg=GUI_BG,
            fg=GUI_TEXT,
            font=("Consolas", 10, "bold"),
        ).pack(side="left", padx=(0, 8))
        self.snippet_spinbox = tk.Spinbox(
            snippet_count_row,
            from_=1,
            to=999999,
            textvariable=self.snippet_count_var,
            width=8,
            bg=GUI_SURFACE,
            fg=GUI_TEXT,
            insertbackground=GUI_TEXT,
            relief="flat",
            bd=0,
            font=("Consolas", 10, "bold"),
            command=self._refresh_controls,
        )
        self.snippet_spinbox.pack(side="left")
        self.snippet_spinbox.bind("<KeyRelease>", lambda _event: self._refresh_controls())
        self.generate_btn = tk.Button(
            action_row,
            text="Generate Bulk XML",
            command=self._start_generate,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=14,
        )
        self.generate_btn.pack(side="left", padx=(16, 10))
        self.snippet_count_row = snippet_count_row
        self.load_xml_btn = tk.Button(
            action_row,
            text="Load SAE XML",
            command=self._toggle_load_xml_input,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=14,
        )
        self.load_xml_btn.pack(side="left", padx=(0, 10))
        self.run_btn = tk.Button(
            action_row,
            text="Run",
            command=self._start_run,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=14,
        )
        self.run_btn.pack(side="left", padx=(0, 10))
        self.stop_btn = tk.Button(
            action_row,
            text="Stop",
            command=self._request_stop,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=14,
        )
        self.stop_btn.pack(side="left", padx=(0, 10))
        self.reset_btn = tk.Button(
            action_row,
            text="Reset",
            command=self._reset_active_cheats_and_meters,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 10, "bold"),
            padx=14,
        )
        self.reset_btn.pack(side="left")

        middle_row = tk.Frame(outer, bg=GUI_BG)
        middle_row.pack(fill="x", pady=(0, 8))
        self.current_meter_text = self._build_meter_panel(middle_row, "Current Snippet Meters")
        self.cumulative_meter_text = self._build_meter_panel(middle_row, "Cumulative Snippet Meters")

        log_frame = tk.Frame(outer, bg=GUI_BG)
        log_frame.pack(fill="both", expand=True)
        self.log_panes = tk.PanedWindow(log_frame, orient="horizontal", bg=GUI_BG, sashwidth=8, bd=0, relief="flat")
        self.log_panes.pack(fill="both", expand=True)

        snippet_log_frame = tk.Frame(self.log_panes, bg=GUI_BG)
        tk.Label(
            snippet_log_frame,
            text="Snippet Log",
            bg=GUI_BG,
            fg=GUI_TEXT,
            font=("Consolas", 10, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        snippet_log_surface = tk.Frame(snippet_log_frame, bg=GUI_SURFACE)
        snippet_log_surface.pack(fill="both", expand=True)
        snippet_scrollbar = tk.Scrollbar(snippet_log_surface)
        snippet_scrollbar.pack(side="right", fill="y")
        self.log_text = tk.Text(
            snippet_log_surface,
            bg="#1a1f26",
            fg="#cfd6de",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",
            yscrollcommand=snippet_scrollbar.set,
            state="disabled",
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        snippet_scrollbar.config(command=self.log_text.yview)

        command_log_frame = tk.Frame(self.log_panes, bg=GUI_BG)
        tk.Label(
            command_log_frame,
            text="Game Log",
            bg=GUI_BG,
            fg=GUI_TEXT,
            font=("Consolas", 10, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))
        command_log_surface = tk.Frame(command_log_frame, bg=GUI_SURFACE)
        command_log_surface.pack(fill="both", expand=True)
        command_scrollbar = tk.Scrollbar(command_log_surface)
        command_scrollbar.pack(side="right", fill="y")
        self.command_log_text = tk.Text(
            command_log_surface,
            bg="#1a1f26",
            fg="#cfd6de",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",
            yscrollcommand=command_scrollbar.set,
            state="disabled",
        )
        self.command_log_text.pack(side="left", fill="both", expand=True)
        command_scrollbar.config(command=self.command_log_text.yview)

        self.log_panes.add(snippet_log_frame, stretch="always", minsize=250)
        self.log_panes.add(command_log_frame, stretch="always", minsize=250)
        self.root.after(100, self._set_default_log_pane_split)

    def _build_file_row(self, parent: Any, label_text: str, variable: Any, browse_command: Callable[[], None]) -> None:
        row = tk.Frame(parent, bg=GUI_BG)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text=label_text, bg=GUI_BG, fg=GUI_TEXT, font=("Consolas", 10, "bold"), width=24, anchor="w").pack(
            side="left",
            padx=(0, 8),
        )
        entry = tk.Entry(
            row,
            textvariable=variable,
            bg=GUI_SURFACE,
            fg=GUI_TEXT,
            insertbackground=GUI_TEXT,
            relief="flat",
            bd=0,
            font=("Consolas", 10),
        )
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<KeyRelease>", lambda _event: self._refresh_controls())
        tk.Button(
            row,
            text="Browse",
            command=browse_command,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 9, "bold"),
            padx=10,
        ).pack(side="left", padx=(8, 0))

    def _build_import_xml_panel(self, parent: Any) -> None:
        row = tk.Frame(parent, bg=GUI_BG)
        tk.Label(
            row,
            text="Imported SAE XML",
            bg=GUI_BG,
            fg=GUI_TEXT,
            font=("Consolas", 10, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        panel = tk.Frame(row, bg=GUI_SURFACE, padx=1, pady=1)
        panel.pack(fill="both", expand=True)

        text_container = tk.Frame(panel, bg=GUI_SURFACE)
        text_container.pack(fill="both", expand=True)

        y_scrollbar = tk.Scrollbar(text_container)
        y_scrollbar.pack(side="right", fill="y")
        x_scrollbar = tk.Scrollbar(text_container, orient="horizontal")
        x_scrollbar.pack(side="bottom", fill="x")

        text = tk.Text(
            text_container,
            bg="#1a1f26",
            fg="#cfd6de",
            font=("Consolas", 10),
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="none",
            height=16,
            undo=False,
            yscrollcommand=y_scrollbar.set,
            xscrollcommand=x_scrollbar.set,
        )
        text.pack(side="left", fill="both", expand=True)
        y_scrollbar.config(command=text.yview)
        x_scrollbar.config(command=text.xview)

        button_row = tk.Frame(row, bg=GUI_BG)
        button_row.pack(fill="x", pady=(6, 0))
        self.import_xml_load_btn = tk.Button(
            button_row,
            text="Load XML (s)",
            command=self._submit_inline_imported_xml,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 9, "bold"),
            padx=12,
        )
        self.import_xml_load_btn.pack(side="left", padx=(0, 8))
        self.import_xml_cancel_btn = tk.Button(
            button_row,
            text="Cancel",
            command=self._cancel_import_xml_input,
            bg=GUI_ACCENT,
            fg=GUI_TEXT,
            activebackground=GUI_ACCENT,
            activeforeground=GUI_TEXT,
            relief="flat",
            font=("Consolas", 9, "bold"),
            padx=12,
        )
        self.import_xml_cancel_btn.pack(side="left")

        row.pack_forget()
        self.import_xml_row = row
        self.import_xml_text = text

    def _build_meter_panel(self, parent: Any, title: str) -> Any:
        panel = tk.Frame(parent, bg=GUI_BG)
        panel.pack(side="left", fill="both", expand=True, padx=(0, 6) if "Current" in title else (6, 0))
        tk.Label(panel, text=title, bg=GUI_BG, fg=GUI_TEXT, font=("Consolas", 10, "bold"), anchor="w").pack(
            fill="x",
            pady=(0, 4),
        )
        text = tk.Text(
            panel,
            bg="#1a1f26",
            fg="#cfd6de",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="none",
            state="disabled",
            height=10,
        )
        text.pack(fill="both", expand=True)
        return text

    def log(self, message: str, *, is_error: bool = False) -> None:
        self._post_ui(self._append_log, message, is_error=is_error)

    def generation_failed(
        self,
        message: str,
        *,
        exc: BaseException | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.log(message, is_error=True)
        formatted_context = _format_log_context(context)
        if formatted_context:
            self.log(f"Context: {formatted_context}", is_error=True)
        seen: set[int] = set()
        current = exc
        cause_index = 1
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            label = "Cause" if cause_index == 1 else f"Cause {cause_index}"
            self.log(f"{label}: {type(current).__name__}: {current}", is_error=True)
            current = current.__cause__ or current.__context__
            cause_index += 1

    def snippet_prepared(
        self,
        session: GeneratedRunSession,
        progress: ManualSendProgress,
        record: SnippetRecord,
    ) -> None:
        self._post_ui(self._on_snippet_prepared, session, progress, record)

    def snippet_completed(
        self,
        session: GeneratedRunSession,
        progress: ManualSendProgress,
        record: SnippetRecord,
    ) -> None:
        self._post_ui(self._on_snippet_completed, session, progress, record)

    def final_summary(self, session: GeneratedRunSession, progress: ManualSendProgress) -> None:
        self._post_ui(self._on_final_summary, session, progress)

    def _post_ui(self, callback: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        self.ui_queue.put((callback, args, kwargs))

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                callback, args, kwargs = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            callback(*args, **kwargs)
        self.root.after(75, self._drain_ui_queue)

    def _append_log(self, message: str, is_error: bool = False) -> None:
        if self.log_text is None:
            return
        prefix = "[ERROR] " if is_error else ""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{prefix}{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _append_command_log(self, message: str, is_error: bool = False) -> None:
        if self.command_log_text is None:
            return
        prefix = "[ERROR] " if is_error else ""
        self.command_log_text.configure(state="normal")
        self.command_log_text.insert("end", f"[{terminal_timestamp()}] {prefix}{message}\n")
        self.command_log_text.see("end")
        self.command_log_text.configure(state="disabled")

    def _append_command_log_via_queue(self, message: str, is_error: bool = False) -> None:
        self._post_ui(self._append_command_log, message, is_error=is_error)

    def _set_default_log_pane_split(self) -> None:
        if self.log_panes is None:
            return
        try:
            pane_width = self.log_panes.winfo_width()
            if pane_width > 1:
                self.log_panes.sashpos(0, pane_width // 2)
                return
        except Exception:
            pass
        self.root.after(100, self._set_default_log_pane_split)

    def _set_status_indicator(self, connected: bool) -> None:
        if self.status_canvas is not None and self.status_indicator is not None:
            color = GUI_SUCCESS if connected else GUI_ERROR
            self.status_canvas.itemconfig(self.status_indicator, fill=color, outline=color)

    def _render_meter_text(self, widget: Any, content: str) -> None:
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def _render_meter_panels(self, record: SnippetRecord | None, meters: TrackedMeters) -> None:
        current_text = "No snippet prepared."
        if record is not None:
            current_text = format_current_meter_block(record, self.current_snippet_bank_value)
        self._render_meter_text(self.current_meter_text, current_text)
        self._render_meter_text(
            self.cumulative_meter_text,
            format_cumulative_meter_block(meters, self.latest_completed_bank_value),
        )

    def _refresh_controls(self) -> None:
        if self.connect_btn is not None:
            self.connect_btn.configure(
                state="normal" if self._can_connect() or self.is_connected else "disabled",
                text="Disconnect" if self.is_connected else "Connect",
            )
        if self.generate_btn is not None:
            self.generate_btn.configure(state="normal" if self._can_show_generate_options() else "disabled")
        if self.load_xml_btn is not None:
            self.load_xml_btn.configure(
                state="normal" if self._can_load_xml() else "disabled",
                text="Hide SAE XML" if self.import_xml_row_visible else "Load SAE XML",
            )
        if self.import_xml_load_btn is not None:
            self.import_xml_load_btn.configure(state="normal" if self._can_submit_imported_xml() else "disabled")
        if self.import_xml_cancel_btn is not None:
            self.import_xml_cancel_btn.configure(state="disabled" if self.is_loading_xml else "normal")
        if self.run_btn is not None:
            self.run_btn.configure(state="normal" if self._can_run() else "disabled")
        if self.stop_btn is not None:
            self.stop_btn.configure(state="normal" if self._can_stop() else "disabled")
        if self.reset_btn is not None:
            self.reset_btn.configure(state="normal" if self._can_reset() else "disabled")
        entry_state = "disabled" if self.is_connected or self.is_loading_xml else "normal"
        if self.ip_entry is not None:
            self.ip_entry.configure(state=entry_state)
        if self.import_xml_text is not None:
            self.import_xml_text.configure(state="disabled" if self.is_loading_xml else "normal")
        if self.snippet_spinbox is not None:
            self.snippet_spinbox.configure(
                state="disabled"
                if self.is_generating or self.is_sending or self.is_loading_xml or not self.snippet_count_row_visible
                else "normal"
            )
        for widget in (self.ugf_btn, self.sgf_btn):
            if widget is not None:
                widget.configure(
                    state="disabled" if self.is_connected or self.is_sending or self.is_loading_xml else "normal"
                )

    def _can_connect(self) -> bool:
        try:
            VltConnectionProbe.normalize_ip_address(self.ip_var.get())
            return (
                not self.is_generating
                and not self.is_sending
                and not self.is_loading_xml
                and self.game_type_var.get() in GameType.ALL
            )
        except ValueError:
            return False

    def _can_generate(self) -> bool:
        return (
            self.snippet_count_row_visible
            and
            not self.is_generating
            and not self.is_sending
            and not self.is_loading_xml
            and self.game_type_var.get() in GameType.ALL
            and bool(self.paytable_var.get().strip())
            and bool(self.qtpti_var.get().strip())
            and is_valid_snippet_count(self.snippet_count_var.get())
        )

    def _can_show_generate_options(self) -> bool:
        return (
            not self.is_generating
            and not self.is_sending
            and not self.is_loading_xml
            and self.game_type_var.get() in GameType.ALL
            and bool(self.paytable_var.get().strip())
            and bool(self.qtpti_var.get().strip())
        )

    def _can_load_xml(self) -> bool:
        return (
            not self.is_generating
            and not self.is_sending
            and not self.is_loading_xml
            and self.game_type_var.get() in GameType.ALL
            and self.current_record is None
            and self.manual_runner is None
        )

    def _can_submit_imported_xml(self) -> bool:
        return self.import_xml_row_visible and not self.is_loading_xml and self._can_load_xml()

    def _clear_import_xml_text(self) -> None:
        if self.import_xml_text is None:
            return
        self.import_xml_text.delete("1.0", "end")

    def _get_import_xml_text(self) -> str:
        if self.import_xml_text is None:
            return ""
        return self.import_xml_text.get("1.0", "end-1c")

    def _set_import_xml_row_visible(self, visible: bool) -> None:
        row = getattr(self, "import_xml_row", None)
        if row is None:
            self.import_xml_row_visible = False
            return
        if visible and not self.import_xml_row_visible:
            row.pack(fill="x", pady=(0, 8), before=self.generate_btn.master)
        elif not visible and self.import_xml_row_visible:
            row.pack_forget()
        self.import_xml_row_visible = visible
        if not visible:
            self._clear_import_xml_text()

    def _set_snippet_count_row_visible(self, visible: bool) -> None:
        row = getattr(self, "snippet_count_row", None)
        if row is None:
            self.snippet_count_row_visible = False
            return
        if visible and not self.snippet_count_row_visible:
            row.pack(side="left", padx=(0, 16), before=self.generate_btn)
        elif not visible and self.snippet_count_row_visible:
            row.pack_forget()
        self.snippet_count_row_visible = visible

    def _cancel_import_xml_input(self) -> None:
        if self.is_loading_xml:
            return
        self._set_import_xml_row_visible(False)
        self._refresh_controls()

    def _toggle_load_xml_input(self) -> None:
        if not self.import_xml_row_visible:
            if not self._can_load_xml():
                return
            self._set_import_xml_row_visible(True)
            if self.import_xml_text is not None:
                self.import_xml_text.focus_set()
            self._refresh_controls()
            return
        self._cancel_import_xml_input()

    def _can_run(self) -> bool:
        return (
            self.is_connected
            and not self.is_generating
            and not self.is_sending
            and not self.is_loading_xml
            and self.current_record is not None
        )

    def _can_stop(self) -> bool:
        return self.is_sending and (self.is_pick_a_prize_touching or self.is_auto_running)

    def _can_reset(self) -> bool:
        return not self.is_generating and not self.is_sending and not self.is_loading_xml and (
            self.current_record is not None or self.manual_runner is not None
        )

    def _can_send(self) -> bool:
        return self._can_run()

    def _save_settings(self) -> None:
        save_gui_settings(
            {
                "ip_address": self.ip_var.get().strip(),
                "game_type": self.game_type_var.get(),
                "paytable_path": self.paytable_var.get().strip(),
                "qtpti_path": self.qtpti_var.get().strip(),
                "snippet_count": self.snippet_count_var.get().strip(),
            }
        )

    def _browse_paytable(self) -> None:
        if filedialog is None:
            return
        path = filedialog.askopenfilename(
            title="Select Paytable Binary",
            filetypes=[("Paytable binaries", "*.ia32 *.metampt *.bin"), ("All Files", "*.*")],
        )
        if path:
            self.paytable_var.set(path)
            self._save_settings()
            self._refresh_controls()

    def _browse_qtpti(self) -> None:
        if filedialog is None:
            return
        path = filedialog.askopenfilename(
            title="Select Paytable Interpreter DLL",
            filetypes=[("DLL Files", "*.dll"), ("All Files", "*.*")],
        )
        if path:
            self.qtpti_var.set(path)
            self._save_settings()
            self._refresh_controls()

    def _submit_inline_imported_xml(self, event: Any | None = None) -> str:
        del event
        self._start_imported_xml_load()
        return "break"

    def _load_imported_xml(self, raw_xml: str) -> bool:
        if self.current_record is not None or self.manual_runner is not None:
            self.log("A snippet is already loaded. Use Reset before importing XML.", is_error=True)
            return False

        try:
            load_result = prepare_imported_snippet_load(self.game_type_var.get(), raw_xml)
        except ValueError as exc:
            message = str(exc)
            if message.startswith("Game type must"):
                self.log("Select SGF or UGF before importing XML.", is_error=True)
                return False
            self.log(f"Import failed: {message}", is_error=True)
            return False

        self.manual_runner = load_result.runner
        self.manual_runner.sink = self
        self.manual_runner.prepare_current_snippet()
        self._log_imported_xml_success(load_result)
        self._refresh_controls()
        return True

    def _log_imported_xml_success(self, load_result: ImportedSnippetLoadResult) -> None:
        if load_result.total_snippet_count == 1:
            self.log(f"Imported XML loaded and ready to run: {load_result.record.snippet_name}")
            return
        self.log(
            f"Imported {load_result.total_snippet_count} snippets and prepared: {load_result.record.snippet_name}"
        )

    def _start_imported_xml_load(self) -> None:
        if not self._can_submit_imported_xml():
            return
        raw_game_type = self.game_type_var.get()
        raw_xml = self._get_import_xml_text()
        self.is_loading_xml = True
        self._refresh_controls()
        worker = threading.Thread(
            target=self._run_imported_xml_worker,
            args=(raw_game_type, raw_xml),
            daemon=True,
            name="SASAutomatorImportXML",
        )
        worker.start()

    def _run_imported_xml_worker(self, raw_game_type: str, raw_xml: str) -> None:
        try:
            load_result = prepare_imported_snippet_load(raw_game_type, raw_xml)
        except ValueError as exc:
            self._post_ui(self._finish_imported_xml_load_failure, str(exc))
            return
        except Exception as exc:
            self._post_ui(self._finish_imported_xml_load_failure, f"Unexpected import error: {exc}")
            return
        self._post_ui(self._finish_imported_xml_load_success, load_result)

    def _finish_imported_xml_load_success(self, load_result: ImportedSnippetLoadResult) -> None:
        self.is_loading_xml = False
        self.manual_runner = load_result.runner
        self.manual_runner.sink = self
        self.manual_runner.prepare_current_snippet()
        self._set_import_xml_row_visible(False)
        self._log_imported_xml_success(load_result)
        self._refresh_controls()

    def _finish_imported_xml_load_failure(self, message: str) -> None:
        self.is_loading_xml = False
        if message.startswith("Game type must"):
            self.log("Select SGF or UGF before importing XML.", is_error=True)
        else:
            self.log(f"Import failed: {message}", is_error=True)
        self._refresh_controls()

    def _toggle_connection(self) -> None:
        if self.is_connected:
            self.is_connected = False
            self.connected_ip = ""
            self._set_status_indicator(False)
            self.log(f"Disconnected from {self.game_type_var.get()}.")
            self._refresh_controls()
            return
        if not self._can_connect():
            return
        try:
            ip = VltConnectionProbe.normalize_ip_address(self.ip_var.get())
            config = VltConnectionConfig(
                ip_address=ip,
                port=SGF_VLT_PORT if self.game_type_var.get() == GameType.SGF else UGF_VLT_PORT,
                timeout_seconds=UGF_CONNECT_TIMEOUT_SECONDS,
            )
            VltConnectionProbe.verify(self.game_type_var.get(), config, sink=self)
        except Exception as exc:
            detail = str(exc)
            self.log(detail if detail.startswith("Connection failed") else f"Connection failed: {detail}", is_error=True)
            self.is_connected = False
            self._set_status_indicator(False)
            self._refresh_controls()
            return
        self.connected_ip = ip
        self.is_connected = True
        self._set_status_indicator(True)
        self._save_settings()
        self._refresh_controls()

    def _start_generate(self) -> None:
        if not self.snippet_count_row_visible:
            if not self._can_show_generate_options():
                return
            self._set_snippet_count_row_visible(True)
            if self.snippet_spinbox is not None:
                self.snippet_spinbox.focus_set()
            self._refresh_controls()
            return
        if not self._can_generate():
            return
        self._save_settings()
        self.is_generating = True
        self.is_auto_running = False
        self.stop_requested = False
        self.current_record = None
        self.manual_runner = None
        self._set_snippet_count_row_visible(False)
        self._render_meter_panels(None, TrackedMeters())
        self._refresh_controls()
        worker = threading.Thread(target=self._run_generate_worker, daemon=True, name="SASAutomatorGenerate")
        worker.start()

    def _run_generate_worker(self) -> None:
        try:
            game_type = normalize_game_type(self.game_type_var.get())
            paytable_path = Path(self.paytable_var.get().strip()).expanduser()
            qtpti_path = Path(self.qtpti_var.get().strip()).expanduser()
            output_xml_path, audit_jsonl_path, run_id = choose_output_paths(paytable_path)
            config = GenerationConfig(
                paytable_path=paytable_path,
                qtpti_path=qtpti_path,
                snippet_count=int(self.snippet_count_var.get()),
                game_type=game_type,
                variant_index=0,
                stake_overrides={},
                game_specific_stake_items={},
                output_xml_path=output_xml_path,
                audit_jsonl_path=audit_jsonl_path,
                run_id=run_id,
            )
            generator = BulkSnippetGenerator(config, sink=self, start_manual_send=False)
            exit_code = generator.run()
            if exit_code == 0:
                progress = ManualSendProgress.load(Path(generator.session.progress_json_path))
                self.manual_runner = ManualSendRunner(generator.session, progress, sink=self)
                self.manual_runner.prepare_current_snippet()
        except Exception as exc:
            self.generation_failed("GUI generation failed.", exc=exc)
        finally:
            self._post_ui(self._finish_generate)

    def _finish_generate(self) -> None:
        self.is_generating = False
        self._refresh_controls()

    def _start_run(self) -> None:
        if not self._can_run() or self.manual_runner is None or not self.connected_ip:
            return
        self._save_settings()
        self.stop_requested = False
        self.is_sending = True
        session_game_type = getattr(getattr(self.manual_runner, "session", None), "game_type", None)
        self.is_auto_running = session_game_type == GameType.SGF
        self.is_pick_a_prize_touching = False
        self._pick_a_prize_machine_name = None
        self.log("Running current snippet.")
        self._refresh_controls()
        worker = threading.Thread(target=self._run_single_snippet_worker, daemon=True, name="SASAutomatorRunCurrent")
        worker.start()

    def _start_send_current_snippet(self) -> None:
        self._start_run()

    def _request_stop(self) -> None:
        if not self._can_stop():
            return
        self.stop_requested = True
        if self.is_auto_running:
            self.log("Stop requested. SGF auto-run will pause after the current snippet completes.")
        elif self.is_pick_a_prize_touching:
            self.log("Stopping Pick-a-Prize touch loop...")
        self._refresh_controls()

    def _reset_active_cheats_and_meters(self) -> None:
        if not self._can_reset():
            return
        self.current_record = None
        self.manual_runner = None
        self.stop_requested = False
        self.is_auto_running = False
        self.is_pick_a_prize_touching = False
        self._pick_a_prize_machine_name = None
        self.current_snippet_bank_value = None
        self.latest_completed_bank_value = None
        self._set_import_xml_row_visible(False)
        self._set_snippet_count_row_visible(False)
        self._render_meter_panels(None, TrackedMeters())
        self.log("Reset cleared the active cheats and meters.")
        self._refresh_controls()

    def _run_single_snippet_worker(self) -> None:
        try:
            if self.manual_runner is None:
                return
            if self.manual_runner.session.game_type == GameType.SGF:
                self._run_sgf_auto_worker()
            else:
                cycle_result = self._run_single_snippet_cycle()
                if cycle_result.next_record is not None:
                    self.log("Next snippet prepared and ready to run.")
        except Exception as exc:
            self.log(f"Send error: {exc}", is_error=True)
        finally:
            self._post_ui(self._finish_run)

    def _run_sgf_auto_worker(self) -> None:
        if self.manual_runner is None:
            return
        if not self.connected_ip:
            raise RuntimeError("There is no connected VLT IP.")

        self.is_auto_running = True
        self._post_ui(self._refresh_controls)
        self.log("Running SGF auto-advance session.")
        controller = PickAPrizeTouchController(
            self.connected_ip,
            on_running_changed=self._handle_pick_a_prize_touch_running_change,
            on_touch_message=self.log,
        )
        self._pick_a_prize_touch_controller = controller
        self._pick_a_prize_machine_name = None
        listener = SGFInProcessListenerSession(
            vlt_ip=self.connected_ip,
            vlt_port=SGF_VLT_PORT,
            on_command_payload=self._append_command_log_via_queue,
            on_pick_a_prize_state_change=self._on_pap_state_change,
        )
        try:
            listener.start()
            while True:
                cycle_result = self._run_single_sgf_auto_snippet_cycle(listener, controller)
                if cycle_result.next_record is None:
                    self.log("SGF auto-run completed all prepared snippets.")
                    return
                if cycle_result.stop_requested:
                    self.log("SGF auto-run paused after current snippet completion.")
                    return
        finally:
            controller.stop()
            self._pick_a_prize_touch_controller = None
            self._pick_a_prize_machine_name = None
            listener.stop()

    def _run_single_sgf_auto_snippet_cycle(
        self,
        listener: SGFInProcessListenerSession,
        controller: PickAPrizeTouchController,
    ) -> SnippetAutomationCycleResult:
        if self.manual_runner is None:
            raise RuntimeError("There is no active manual send session.")
        if not self.connected_ip:
            raise RuntimeError("There is no connected VLT IP.")
        current_record = self.manual_runner.peek_current_record()
        if current_record is None:
            raise RuntimeError("There is no current snippet to run.")

        listener.begin_snippet_wait()
        self._bonus_touch_active = False
        self.current_snippet_bank_value = None
        snippet_xml = Path(self.manual_runner.session.current_snippet_xml_path).read_text(encoding="utf-8")
        result = self.sgf_sender.send(self.connected_ip, snippet_xml)
        for warning in result.warnings:
            self.log(warning)
        self.log("SGF snippet sent successfully.")
        self.log(self._trigger_autospin())
        last_autospin_time = [time.monotonic()]

        wait_result: SGFIdleWaitResult
        try:
            def _on_wait_tick() -> None:
                controller.raise_if_failed()
                if self.stop_requested:
                    controller.stop()
                    listener.request_stop()
                    return
                self._handle_sgf_bonus_state_events(listener, controller, last_autospin_time)
                now = time.monotonic()
                if now - last_autospin_time[0] >= SGF_WIN_AUTOSPIN_RETRY_INTERVAL_SECONDS:
                    last_autospin_time[0] = now
                    # Only retry when the VLT itself has gone quiet; a long but active animation
                    # is not "stuck" and an extra press just adds an unnecessary round trip.
                    if listener.get_listener_health()["time_since_last_payload"] < SGF_WIN_AUTOSPIN_RETRY_INTERVAL_SECONDS:
                        return
                    try:
                        msg = self._trigger_autospin()
                        self.log(f"[WIN ANIMATION] Autospin retry: {msg}")
                    except Exception as exc:
                        self.log(f"[WIN ANIMATION] Autospin retry failed: {exc}", is_error=True)

            wait_result = listener.wait_for_idle(on_tick=_on_wait_tick)
            if not wait_result.reached_idle:
                # Listener timeout - attempt reconnect before failing
                health = listener.get_listener_health()
                if not health["is_receiving_payloads"] and not listener._reconnect_attempted:
                    self.log(
                        f"[RECONNECT] Listener not receiving payloads "
                        f"(no update for {health['time_since_last_payload']:.1f}s). "
                        f"Attempting to restore callback subscription..."
                    )
                    try:
                        listener.begin_snippet_wait()  # Reset for retry
                        listener.reconnect()
                        # Retry idle wait with fresh connection
                        wait_result = listener.wait_for_idle(on_tick=_on_wait_tick)
                        if wait_result.reached_idle:
                            self.log("[RECONNECT] Successfully restored subscription and completed snippet.")
                        else:
                            raise RuntimeError(
                                f"[RECONNECT FAILED] {wait_result.reason or 'SGF listener wait failed after reconnect.'}"
                            )
                    except Exception as reconnect_error:
                        raise RuntimeError(
                            f"{wait_result.reason or 'SGF listener wait failed.'} "
                            f"Reconnect attempt failed: {reconnect_error}"
                        ) from reconnect_error
                else:
                    raise RuntimeError(wait_result.reason or "SGF listener wait failed.")
        finally:
            self._bonus_touch_active = False
            controller.stop()

        if wait_result.wait_seconds is not None:
            idle_detected_after = wait_result.idle_detected_after_seconds
            idle_completed_after = wait_result.idle_completed_after_seconds
            self.log(
                "[STATE TIMING] "
                f"wait={wait_result.wait_seconds:.3f}s "
                f"idle-detected={idle_detected_after:.3f}s "
                f"idle-completed={idle_completed_after:.3f}s"
                if idle_detected_after is not None and idle_completed_after is not None
                else f"[STATE TIMING] wait={wait_result.wait_seconds:.3f}s"
            )
        self.current_snippet_bank_value = wait_result.latest_bank
        self.latest_completed_bank_value = wait_result.latest_bank
        completed_record = self.manual_runner.complete_current_snippet(latest_completed_bank=wait_result.latest_bank)
        self.current_snippet_bank_value = None
        next_record = self.manual_runner.prepare_current_snippet()
        should_pause = self.stop_requested and next_record is not None
        return SnippetAutomationCycleResult(
            completed_record=completed_record,
            next_record=next_record,
            stop_requested=should_pause,
        )

    def _run_single_snippet_cycle(self) -> SnippetAutomationCycleResult:
        if self.manual_runner is None:
            raise RuntimeError("There is no active manual send session.")
        if not self.connected_ip:
            raise RuntimeError("There is no connected VLT IP.")
        current_record = self.manual_runner.peek_current_record()
        if current_record is None:
            raise RuntimeError("There is no current snippet to run.")
        snippet_xml = Path(self.manual_runner.session.current_snippet_xml_path).read_text(encoding="utf-8")
        if self.manual_runner.session.game_type == GameType.SGF:
            result = self.sgf_sender.send(self.connected_ip, snippet_xml)
            for warning in result.warnings:
                self.log(warning)
        else:
            self.ugf_sender.send(self.connected_ip, snippet_xml)
        self.log(f"{self.manual_runner.session.game_type} snippet sent successfully.")
        self.log(self._trigger_autospin())
        completed_record = self.manual_runner.complete_current_snippet()
        next_record = self.manual_runner.prepare_current_snippet()
        should_pause = self.stop_requested and next_record is not None
        return SnippetAutomationCycleResult(
            completed_record=completed_record,
            next_record=next_record,
            stop_requested=should_pause,
        )

    def _trigger_autospin(self) -> str:
        if not self.connected_ip:
            raise RuntimeError("There is no connected VLT IP.")
        if self.manual_runner is None:
            raise RuntimeError("There is no active manual send session.")
        if self.manual_runner.session.game_type == GameType.SGF:
            return trigger_sgf_autospin_input(self.connected_ip, SGF_AUTOSPIN_BUTTON_NAME)
        self.ugf_sender.press_button(self.connected_ip, UGF_AUTOSPIN_BUTTON_ID)
        return f"UGF autospin accepted: ButtonPress({UGF_AUTOSPIN_BUTTON_ID})."

    def _finish_run(self) -> None:
        self.is_sending = False
        self.is_auto_running = False
        self.is_pick_a_prize_touching = False
        self.stop_requested = False
        self._bonus_touch_active = False
        self._pick_a_prize_machine_name = None
        self._refresh_controls()

    def _handle_sgf_bonus_state_events(
        self,
        listener: SGFInProcessListenerSession,
        controller: PickAPrizeTouchController,
        last_autospin_time: list[float],
    ) -> None:
        for state_value in listener.drain_state_events():
            if state_value == SGF_BONUS_TRIGGER_STATE_VALUE:
                self._start_bonus_auto_touch(controller)
            elif state_value == SGF_BONUS_STATE_VALUE:
                self._send_bonus_mech_press()
            elif state_value == SGF_FREESPIN_IDLE_STATE_VALUE:
                try:
                    message = self._trigger_autospin()
                    last_autospin_time[0] = time.monotonic()
                    self.log(f"[BONUS] Free spin idle detected. {message}")
                except Exception as exc:
                    self.log(f"[BONUS] Free spin autospin failed: {exc}", is_error=True)
            elif state_value == listener.idle_state_value and self._bonus_touch_active:
                self._bonus_touch_active = False
                controller.stop()
                self.log("[BONUS] Main game idle detected. Stopping bonus auto-touch.")
                self._post_ui(self._refresh_controls)

    def _start_bonus_auto_touch(self, controller: PickAPrizeTouchController) -> None:
        if self._bonus_touch_active:
            return
        try:
            _require_paramiko()
        except RuntimeError as exc:
            self.log(f"[BONUS] Bonus trigger detected, but auto-touch is unavailable: {exc}", is_error=True)
            return
        self._bonus_touch_active = True
        self.log("[BONUS] Bonus trigger detected. Auto-touching through the intro screen and Pick-a-Prize.")
        controller.start()
        self._post_ui(self._refresh_controls)

    def _send_bonus_mech_press(self) -> None:
        if not self.connected_ip:
            return
        try:
            accepted_port = try_sgf_tce_buttonpress_ports(self.connected_ip, SGF_AUTOSPIN_BUTTON_NAME)
        except Exception as exc:
            self.log(f"[BONUS] Bonus mech press failed: {exc}", is_error=True)
            return
        self.log(
            f"[BONUS] Bonus state detected. MechButtonPress '{SGF_AUTOSPIN_BUTTON_NAME}' "
            f"accepted on {accepted_port}."
        )

    def _handle_pick_a_prize_touch_running_change(self, is_running: bool) -> None:
        self.is_pick_a_prize_touching = is_running
        self._post_ui(self._refresh_controls)

    def _on_pap_state_change(self, active: bool, state_value: str) -> None:
        controller = self._pick_a_prize_touch_controller
        if controller is None:
            return

        if active:
            machine_name = _extract_state_machine_name(state_value) or self._pick_a_prize_machine_name or "unknown"
            self._pick_a_prize_machine_name = machine_name
            try:
                _require_paramiko()
            except RuntimeError as exc:
                self.log(
                    f"Pick-a-Prize detected in state machine '{machine_name}', but auto-touch is unavailable: {exc}",
                    is_error=True,
                )
                self._post_ui(self._refresh_controls)
                return
            self.log(f"Pick-a-Prize detected in state machine '{machine_name}'. Starting auto-touch.")
            controller.start()
        else:
            machine_name = self._pick_a_prize_machine_name or _extract_state_machine_name(state_value) or "unknown"
            if self._bonus_touch_active:
                # Bonus auto-touch must keep running past the Pick-a-Prize stage until the main game is idle.
                self.log(f"Pick-a-Prize state machine '{machine_name}' exited. Bonus auto-touch continues.")
                self._pick_a_prize_machine_name = None
                self._post_ui(self._refresh_controls)
                return
            was_running = controller.is_running
            controller.stop()
            if was_running:
                self.log(f"Pick-a-Prize state machine '{machine_name}' exited. Stopping auto-touch.")
            else:
                self.log(f"Pick-a-Prize state machine '{machine_name}' exited.")
            self._pick_a_prize_machine_name = None
        self._post_ui(self._refresh_controls)

    def _on_snippet_prepared(
        self,
        session: GeneratedRunSession,
        progress: ManualSendProgress,
        record: SnippetRecord,
    ) -> None:
        del session
        self.current_record = record
        self.current_snippet_bank_value = None
        self.latest_completed_bank_value = progress.latest_completed_bank
        self._render_meter_panels(record, progress.tracked_meters)
        self._refresh_controls()

    def _on_snippet_completed(
        self,
        session: GeneratedRunSession,
        progress: ManualSendProgress,
        record: SnippetRecord,
    ) -> None:
        del session, record
        self.latest_completed_bank_value = progress.latest_completed_bank
        self._render_meter_panels(self.current_record, progress.tracked_meters)
        self._refresh_controls()

    def _on_final_summary(self, session: GeneratedRunSession, progress: ManualSendProgress) -> None:
        del session
        self.current_record = None
        self.current_snippet_bank_value = None
        self.latest_completed_bank_value = progress.latest_completed_bank
        self._render_meter_panels(None, progress.tracked_meters)
        self._refresh_controls()

    def _on_close(self) -> None:
        self._save_settings()
        self.root.destroy()


def launch_gui_app() -> int:
    if tk is None:
        raise RuntimeError("tkinter is not available in this Python environment.")
    root = tk.Tk()
    SASAutomatorGuiApp(root)
    root.mainloop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bulk SAE snippet generator with a manual-send meter ledger workflow. "
            "Prompts for required inputs when arguments are omitted."
        )
    )
    parser.add_argument("--cli", action="store_true", help="Run the existing command-line workflow instead of the GUI.")
    parser.add_argument("--resume", dest="resume_path", help="Resume a manual-send session from a progress JSON file.")
    parser.add_argument("--paytable", dest="paytable_path")
    parser.add_argument("--qtpti", dest="qtpti_path")
    parser.add_argument("--count", dest="snippet_count", type=int)
    parser.add_argument("--game-type", dest="game_type")
    parser.add_argument("--variant", dest="variant_index", type=int)
    parser.add_argument("--lines", type=int)
    parser.add_argument("--bet-per-line", dest="bet_per_line", type=int)
    parser.add_argument("--payment", type=int)
    parser.add_argument("--denomination-cents", dest="denomination_cents", type=int)
    parser.add_argument("--extra-credit", dest="extra_credit", type=int)
    parser.add_argument("--side-bet", dest="side_bet", type=int)
    parser.add_argument("--game-specific", dest="game_specific")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--vlt-ip", dest="vlt_ip")
    parser.add_argument("--vlt-port", dest="vlt_port", type=int)
    parser.add_argument(
        "--vlt-timeout-seconds",
        dest="vlt_timeout_seconds",
        type=float,
        default=UGF_CONNECT_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Require command-line inputs and fail instead of prompting.",
    )
    return parser


def should_launch_gui(args: argparse.Namespace) -> bool:
    if getattr(args, "cli", False):
        return False
    if getattr(args, "resume_path", None):
        return False
    cli_fields = (
        "paytable_path",
        "qtpti_path",
        "snippet_count",
        "game_type",
        "variant_index",
        "lines",
        "bet_per_line",
        "payment",
        "denomination_cents",
        "extra_credit",
        "side_bet",
        "game_specific",
        "seed",
        "vlt_ip",
        "vlt_port",
    )
    return not any(getattr(args, field, None) is not None for field in cli_fields)


def prompt_string(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("A value is required.")


def prompt_optional_string(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    if value:
        return value
    return default


def prompt_int(prompt: str, default: int | None = None, allow_blank: bool = False) -> int | None:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if not value:
            if allow_blank:
                return default
            if default is not None:
                return default
            print("A value is required.")
            continue
        try:
            return int(value)
        except ValueError:
            print("Please enter an integer.")


def build_vlt_connection_config(
    game_type: str,
    raw_vlt_ip: str | None,
    vlt_port: int | None,
    vlt_timeout_seconds: float,
) -> VltConnectionConfig | None:
    if not raw_vlt_ip:
        return None

    config = VltConnectionConfig(
        ip_address=VltConnectionProbe.normalize_ip_address(raw_vlt_ip),
        port=vlt_port if vlt_port is not None else (
            SGF_VLT_PORT if game_type == GameType.SGF else UGF_VLT_PORT
        ),
        timeout_seconds=float(vlt_timeout_seconds),
    )
    if not 1 <= config.port <= 65535:
        raise ValueError("VLT port must be between 1 and 65535.")
    if config.timeout_seconds <= 0:
        raise ValueError("VLT connection timeout must be greater than zero.")
    return config


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    value = input(f"{prompt}{suffix}: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes"}


def normalize_game_type(raw_value: str) -> str:
    normalized = raw_value.strip().lower()
    if normalized in {"u", "ugf"}:
        return GameType.UGF
    if normalized in {"s", "sgf", "sgfhd"}:
        return GameType.SGF
    raise ValueError("Game type must be 'u' for UGF or 's' for SGF.")


def prompt_game_type() -> str:
    while True:
        raw_value = input("SGF/UGF: ").strip()
        try:
            return normalize_game_type(raw_value)
        except ValueError as exc:
            print(exc)


def parse_game_specific_items(raw_value: str | None) -> dict[int, int]:
    if raw_value is None:
        return {}
    raw_value = raw_value.strip()
    if not raw_value:
        return {}

    result: dict[int, int] = {}
    for pair in raw_value.split(","):
        try:
            key_text, value_text = pair.split(":", maxsplit=1)
            key = int(key_text.strip())
            value = int(value_text.strip())
        except ValueError as exc:
            raise ValueError(
                "Game-specific stake items must use 'key:value,key:value' formatting."
            ) from exc
        result[key] = value
    return result


def choose_output_paths(paytable_path: Path) -> tuple[Path, Path, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_run_id = f"{paytable_path.stem}_bulk_{timestamp}"
    run_id = base_run_id
    attempt = 0
    while True:
        suffix = "" if attempt == 0 else f"_{attempt}"
        xml_path = paytable_path.with_name(f"{base_run_id}{suffix}.xml")
        jsonl_path = paytable_path.with_name(f"{base_run_id}{suffix}.jsonl")
        if not xml_path.exists() and not jsonl_path.exists():
            return xml_path, jsonl_path, f"{run_id}{suffix}"
        attempt += 1


def resolve_config(args: argparse.Namespace) -> GenerationConfig:
    paytable_arg = args.paytable_path
    qtpti_arg = args.qtpti_path
    count_arg = args.snippet_count
    game_type_arg = args.game_type
    vlt_ip_arg = args.vlt_ip

    if not args.no_prompt:
        if vlt_ip_arg is None:
            vlt_ip_arg = prompt_optional_string("VLT IP")
        if game_type_arg is None:
            game_type_arg = prompt_game_type()

    if game_type_arg is None:
        raise ValueError("Game type is required.")

    game_type = normalize_game_type(game_type_arg)
    vlt_connection = build_vlt_connection_config(
        game_type,
        vlt_ip_arg,
        args.vlt_port,
        args.vlt_timeout_seconds,
    )
    vlt_connection_verified = False
    if vlt_connection is not None:
        VltConnectionProbe.verify(game_type, vlt_connection)
        vlt_connection_verified = True

    if not args.no_prompt:
        if not paytable_arg:
            paytable_arg = prompt_string("Paytable Binary")
        if not qtpti_arg:
            qtpti_arg = prompt_string("DLL File")
        if count_arg is None:
            count_arg = prompt_int("Number of Snippets")  # type: ignore[assignment]

    if not paytable_arg or not qtpti_arg or count_arg is None or game_type_arg is None:
        raise ValueError("Paytable path, QTPTI path, snippet count, and game type are required.")

    variant_index = args.variant_index
    stake_overrides = {
        "lines": args.lines,
        "bet_per_line": args.bet_per_line,
        "payment": args.payment,
        "denomination_cents": args.denomination_cents,
        "extra_credit": args.extra_credit,
        "side_bet": args.side_bet,
    }
    game_specific = parse_game_specific_items(args.game_specific)

    advanced_values_supplied = variant_index is not None or any(
        value is not None for value in stake_overrides.values()
    ) or bool(game_specific)

    if not args.no_prompt and not advanced_values_supplied and prompt_yes_no("Use advanced stake options?", False):
        variant_index = prompt_int("Variant index", default=0)  # type: ignore[assignment]
        for definition in STAKE_FIELD_DEFINITIONS:
            stake_overrides[definition.name] = prompt_int(
                f"{definition.prompt_label} override",
                allow_blank=True,
            )
        game_specific = parse_game_specific_items(
            prompt_string(
                "Game-specific stake items (key:value,key:value or blank)",
                default="",
            )
        )

    if variant_index is None:
        variant_index = 0

    paytable_path = Path(paytable_arg).expanduser()
    qtpti_path = Path(qtpti_arg).expanduser()
    output_xml_path, audit_jsonl_path, run_id = choose_output_paths(paytable_path)

    return GenerationConfig(
        paytable_path=paytable_path,
        qtpti_path=qtpti_path,
        snippet_count=int(count_arg),
        game_type=game_type,
        variant_index=int(variant_index),
        stake_overrides=stake_overrides,
        game_specific_stake_items=game_specific,
        output_xml_path=output_xml_path,
        audit_jsonl_path=audit_jsonl_path,
        run_id=run_id,
        seed=args.seed,
        vlt_connection=vlt_connection,
        vlt_connection_verified=vlt_connection_verified,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if should_launch_gui(args):
            return launch_gui_app()
        if args.resume_path:
            runner = ManualSendRunner.load_from_progress_file(Path(args.resume_path).expanduser())
            return runner.run()
        config = resolve_config(args)
        generator = BulkSnippetGenerator(config, sink=TerminalWorkflowEventSink(), start_manual_send=True)
        return generator.run()
    except KeyboardInterrupt:
        print(f"[{terminal_timestamp()}] ERROR Generation cancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        log_terminal_error("SASautomator terminated unexpectedly.", exc=exc, include_traceback=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
