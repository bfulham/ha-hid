"""Linux hidraw discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SYSFS = Path("/sys/class/hidraw")


@dataclass
class HidrawInfo:
    """A hidraw node and its identity."""

    node: str
    vid: int
    pid: int
    name: str
    phys: str
    uniq: str

    @property
    def path(self) -> str:
        return f"/dev/{self.node}"

    @property
    def unique_id(self) -> str:
        return f"{self.vid:04x}:{self.pid:04x}:{self.phys or self.uniq}"

    @property
    def label(self) -> str:
        return f"{self.name} [{self.vid:04x}:{self.pid:04x}] ({self.node})"

    def read_descriptor(self) -> bytes:
        return (SYSFS / self.node / "device" / "report_descriptor").read_bytes()


def list_devices() -> list[HidrawInfo]:
    """List all hidraw devices currently present."""
    devices: list[HidrawInfo] = []
    if not SYSFS.is_dir():
        return devices
    for node in sorted(SYSFS.iterdir(), key=lambda p: p.name):
        try:
            props = dict(
                line.split("=", 1)
                for line in (node / "device" / "uevent").read_text().splitlines()
                if "=" in line
            )
            _, vid, pid = props["HID_ID"].split(":")
            devices.append(
                HidrawInfo(
                    node=node.name,
                    vid=int(vid, 16),
                    pid=int(pid, 16),
                    name=props.get("HID_NAME", node.name),
                    phys=props.get("HID_PHYS", ""),
                    uniq=props.get("HID_UNIQ", ""),
                )
            )
        except (OSError, KeyError, ValueError):
            continue
    return devices


def find_device(vid: int, pid: int, phys: str) -> HidrawInfo | None:
    """Find the hidraw node for a configured device (node numbers can change)."""
    candidates = [d for d in list_devices() if d.vid == vid and d.pid == pid]
    for candidate in candidates:
        if phys and candidate.phys == phys:
            return candidate
    if len(candidates) == 1:
        return candidates[0]
    return None
