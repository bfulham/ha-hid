"""Tests for the HID report descriptor parser (no Home Assistant needed)."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "hid_parser", Path(__file__).parent.parent / "custom_components/hid/hid_parser.py"
)
hp = importlib.util.module_from_spec(_spec)
import sys

sys.modules["hid_parser"] = hp  # dataclasses needs the module registered
_spec.loader.exec_module(hp)

# Gamepad: 4 buttons + 4 padding bits, X/Y (signed 8 bit), hat switch (0-7, null state)
GAMEPAD = bytes.fromhex(
    "05 01 09 05 a1 01"
    "05 09 19 01 29 04 15 00 25 01 75 01 95 04 81 02"
    "95 04 75 01 81 03"
    "05 01 09 30 09 31 15 81 25 7f 75 08 95 02 81 02"
    "09 39 15 00 25 07 75 08 95 01 81 42"
    "c0"
)

# Boot keyboard: 8 modifier bits, 1 reserved byte, 6-slot key array
KEYBOARD = bytes.fromhex(
    "05 01 09 06 a1 01"
    "05 07 19 e0 29 e7 15 00 25 01 75 01 95 08 81 02"
    "95 01 75 08 81 03"
    "95 06 75 08 15 00 25 65 05 07 19 00 29 65 81 00"
    "c0"
)


def test_gamepad_fields():
    fields = hp.parse_descriptor(GAMEPAD).fields
    kinds = [(f.name, f.kind) for f in fields]
    assert kinds[:4] == [(f"Button {i}", hp.BUTTON) for i in range(1, 5)]
    assert ("X", hp.VALUE) in kinds and ("Y", hp.VALUE) in kinds
    assert ("Hat switch", hp.HAT) in kinds


def test_gamepad_decode():
    fields = {f.name: f for f in hp.parse_descriptor(GAMEPAD).fields}
    # byte0: buttons 1 and 3 + padding, byte1: X=-1, byte2: Y=5, byte3: hat=2 (east)
    report = bytes([0b0101, 0xFF, 0x05, 0x02])
    assert fields["Button 1"].decode(report) is True
    assert fields["Button 2"].decode(report) is False
    assert fields["Button 3"].decode(report) is True
    assert fields["X"].decode(report) == -1
    assert fields["Y"].decode(report) == 5
    assert fields["Hat switch"].decode(report) == 2


def test_keyboard_keys():
    fields = hp.parse_descriptor(KEYBOARD).fields
    mods = [f for f in fields if f.name in ("Key Left Ctrl", "Key Right GUI")]
    assert len(mods) == 2 and all(f.kind == hp.BUTTON for f in mods)
    keys = {f.name: f for f in fields if f.kind == hp.KEY}
    assert "Key A" in keys
    # modifier byte 0b10 (left shift), reserved, key A (usage 4) in slot 2
    report = bytes([0x02, 0, 0x04, 0, 0, 0, 0, 0])
    assert keys["Key A"].decode(report) is True
    assert keys["Key B"].decode(report) is False
    assert next(f for f in fields if f.name == "Key Left Shift").decode(report) is True
