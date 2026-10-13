"""Parser for USB HID report descriptors.

Turns a raw report descriptor into a flat list of input ``Field`` objects
(buttons, keys, axes/values, hat switches) and decodes input reports with them.
This module deliberately has no Home Assistant imports so it can be tested alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BUTTON = "button"
KEY = "key"
VALUE = "value"
HAT = "hat"

PAGE_GENERIC_DESKTOP = 0x01
PAGE_KEYBOARD = 0x07
PAGE_BUTTON = 0x09
PAGE_CONSUMER = 0x0C
USAGE_HAT_SWITCH = 0x39

MAX_FIELDS = 1024

_GENERIC_DESKTOP = {
    0x30: "X", 0x31: "Y", 0x32: "Z", 0x33: "Rx", 0x34: "Ry", 0x35: "Rz",
    0x36: "Slider", 0x37: "Dial", 0x38: "Wheel", 0x39: "Hat switch",
    0x40: "Vx", 0x41: "Vy", 0x42: "Vz", 0x80: "System control",
    0x81: "System power down", 0x82: "System sleep", 0x83: "System wake up",
    0x90: "D-pad up", 0x91: "D-pad down", 0x92: "D-pad right", 0x93: "D-pad left",
}
_CONSUMER = {
    0x30: "Power", 0x40: "Menu", 0x41: "Menu pick", 0x6F: "Brightness up",
    0x70: "Brightness down", 0xB0: "Play", 0xB1: "Pause", 0xB3: "Fast forward",
    0xB4: "Rewind", 0xB5: "Next track", 0xB6: "Previous track", 0xB7: "Stop",
    0xCD: "Play/Pause", 0xE2: "Mute", 0xE9: "Volume up", 0xEA: "Volume down",
    0x18A: "Email", 0x192: "Calculator", 0x223: "Home", 0x224: "Back",
}
_KEYBOARD = {
    40: "Enter", 41: "Escape", 42: "Backspace", 43: "Tab", 44: "Space",
    79: "Right", 80: "Left", 81: "Down", 82: "Up",
    224: "Left Ctrl", 225: "Left Shift", 226: "Left Alt", 227: "Left GUI",
    228: "Right Ctrl", 229: "Right Shift", 230: "Right Alt", 231: "Right GUI",
}


def usage_name(page: int, usage: int) -> str:
    """Return a human friendly name for a usage."""
    if page == PAGE_BUTTON:
        return f"Button {usage}"
    if page == PAGE_KEYBOARD:
        if 4 <= usage <= 29:
            return f"Key {chr(ord('A') + usage - 4)}"
        if 30 <= usage <= 38:
            return f"Key {usage - 29}"
        if usage == 39:
            return "Key 0"
        if 58 <= usage <= 69:
            return f"Key F{usage - 57}"
        return f"Key {_KEYBOARD.get(usage, usage)}"
    table = _GENERIC_DESKTOP if page == PAGE_GENERIC_DESKTOP else (
        _CONSUMER if page == PAGE_CONSUMER else {}
    )
    return table.get(usage, f"Usage {page:#x}:{usage:#x}")


def _extract(payload: bytes, bit_offset: int, bit_size: int) -> int | None:
    start = bit_offset >> 3
    end = (bit_offset + bit_size + 7) >> 3
    if end > len(payload):
        return None
    chunk = int.from_bytes(payload[start:end], "little")
    return (chunk >> (bit_offset & 7)) & ((1 << bit_size) - 1)


@dataclass
class Field:
    """One decodable piece of an input report."""

    report_id: int
    bit_offset: int
    bit_size: int
    usage_page: int
    usage: int
    logical_min: int
    logical_max: int
    kind: str
    key: str
    name: str
    count: int = 1  # array element count (KEY fields only)
    match_value: int | None = None  # array element value meaning "this key down"
    relative: bool = False

    @property
    def is_vendor_defined(self) -> bool:
        """True for vendor-specific usages (page 0xFF00+) and fields with no usage."""
        return self.usage_page >= 0xFF00 or self.usage == 0

    def decode(self, payload: bytes) -> bool | int | None:
        """Decode this field from a report payload (report id byte removed)."""
        if self.kind == KEY:
            for n in range(self.count):
                value = _extract(payload, self.bit_offset + n * self.bit_size, self.bit_size)
                if value is None:
                    return None
                if value == self.match_value:
                    return True
            return False
        value = _extract(payload, self.bit_offset, self.bit_size)
        if value is None:
            return None
        if self.logical_min < 0 and value & (1 << (self.bit_size - 1)):
            value -= 1 << self.bit_size
        if self.kind == BUTTON:
            return bool(value)
        return value


@dataclass
class ReportMap:
    """All input fields of a device, indexed by report id."""

    fields: list[Field] = field(default_factory=list)

    @property
    def uses_report_ids(self) -> bool:
        return any(f.report_id for f in self.fields)

    def by_report(self) -> dict[int, list[Field]]:
        result: dict[int, list[Field]] = {}
        for item in self.fields:
            result.setdefault(item.report_id, []).append(item)
        return result


@dataclass
class _Global:
    usage_page: int = 0
    logical_min: int = 0
    logical_max: int = 0
    report_size: int = 0
    report_count: int = 0
    report_id: int = 0


def _dedupe_names(fields: list[Field]) -> None:
    seen: dict[str, int] = {}
    for item in fields:
        count = seen.get(item.name, 0) + 1
        seen[item.name] = count
        if count > 1:
            item.name = f"{item.name} {count}"


def parse_descriptor(data: bytes) -> ReportMap:
    """Parse a HID report descriptor into a ``ReportMap`` of input fields."""
    glob = _Global()
    stack: list[_Global] = []
    usages: list[tuple[int, int]] = []
    usage_min: tuple[int, int] | None = None
    usage_max: int | None = None
    offsets: dict[int, int] = {}
    fields: list[Field] = []

    i = 0
    while i < len(data):
        prefix = data[i]
        if prefix == 0xFE:  # long item, skip
            i += 3 + (data[i + 1] if i + 1 < len(data) else 0)
            continue
        size = prefix & 3
        size = 4 if size == 3 else size
        item_type = (prefix >> 2) & 3
        tag = prefix >> 4
        raw = data[i + 1 : i + 1 + size]
        i += 1 + size
        unsigned = int.from_bytes(raw, "little")
        signed = int.from_bytes(raw, "little", signed=True) if size else 0

        if item_type == 1:  # global
            if tag == 0:
                glob.usage_page = unsigned
            elif tag == 1:
                glob.logical_min = signed
            elif tag == 2:
                # Some devices declare e.g. 0..255 in one byte; treat as unsigned.
                glob.logical_max = unsigned if glob.logical_min >= 0 and signed < glob.logical_min else signed
            elif tag == 7:
                glob.report_size = unsigned
            elif tag == 8:
                glob.report_id = unsigned
            elif tag == 9:
                glob.report_count = unsigned
            elif tag == 0xA:
                stack.append(_Global(**glob.__dict__))
            elif tag == 0xB and stack:
                glob = stack.pop()
        elif item_type == 2:  # local
            full = (unsigned >> 16, unsigned & 0xFFFF) if size == 4 else (glob.usage_page, unsigned)
            if tag == 0:
                usages.append(full)
            elif tag == 1:
                usage_min = full
            elif tag == 2:
                usage_max = full[1]
        elif item_type == 0:  # main
            if tag == 0x8:  # input
                flags = unsigned
                count, bits = glob.report_count, glob.report_size
                offset = offsets.get(glob.report_id, 0)
                if not flags & 1 and bits and 0 < count <= MAX_FIELDS:
                    fields.extend(
                        _build_fields(glob, flags, offset, usages, usage_min, usage_max)
                    )
                offsets[glob.report_id] = offset + bits * count
            usages = []
            usage_min = None
            usage_max = None

    _dedupe_names(fields)
    return ReportMap(fields=fields[:MAX_FIELDS])


def _expand_usages(
    glob: _Global,
    usages: list[tuple[int, int]],
    usage_min: tuple[int, int] | None,
    usage_max: int | None,
) -> list[tuple[int, int]]:
    if usage_min is not None and usage_max is not None:
        page = usage_min[0]
        return [(page, u) for u in range(usage_min[1], min(usage_max, usage_min[1] + MAX_FIELDS) + 1)]
    return list(usages)


def _build_fields(
    glob: _Global,
    flags: int,
    offset: int,
    usages: list[tuple[int, int]],
    usage_min: tuple[int, int] | None,
    usage_max: int | None,
) -> list[Field]:
    expanded = _expand_usages(glob, usages, usage_min, usage_max)
    rid, bits, count = glob.report_id, glob.report_size, glob.report_count
    out: list[Field] = []

    if flags & 2:  # variable: one field per element
        for n in range(count):
            if expanded:
                page, usage = expanded[n] if n < len(expanded) else expanded[-1]
            else:
                page, usage = glob.usage_page, 0
            if page == PAGE_BUTTON or (bits == 1 and glob.logical_min == 0 and glob.logical_max == 1):
                kind = BUTTON
            elif page == PAGE_GENERIC_DESKTOP and usage == USAGE_HAT_SWITCH:
                kind = HAT
            else:
                kind = VALUE
            name = usage_name(page, usage) if usage else f"Value {n + 1}"
            out.append(
                Field(
                    report_id=rid,
                    bit_offset=offset + n * bits,
                    bit_size=bits,
                    usage_page=page,
                    usage=usage,
                    logical_min=glob.logical_min,
                    logical_max=glob.logical_max,
                    kind=kind,
                    key=f"{rid}.{offset + n * bits}",
                    name=name,
                    relative=bool(flags & 4),
                )
            )
    else:  # array: elements hold the index of an active usage
        for idx, (page, usage) in enumerate(expanded):
            if usage == 0:
                continue
            out.append(
                Field(
                    report_id=rid,
                    bit_offset=offset,
                    bit_size=bits,
                    usage_page=page,
                    usage=usage,
                    logical_min=glob.logical_min,
                    logical_max=glob.logical_max,
                    kind=KEY,
                    key=f"{rid}.{offset}.k{page:x}.{usage:x}",
                    name=usage_name(page, usage),
                    count=count,
                    match_value=glob.logical_min + idx,
                )
            )
    return out
