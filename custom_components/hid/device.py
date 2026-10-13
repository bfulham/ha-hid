"""Runtime handling of a single HID device."""

from __future__ import annotations

import logging
import os
import select
import threading

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import CONF_PHYS, CONF_PID, CONF_VID, DOMAIN, RETRY_INTERVAL
from .hid_parser import BUTTON, KEY, Field, ReportMap, parse_descriptor
from .hidraw import find_device

_LOGGER = logging.getLogger(__name__)


class HidDevice:
    """Reads input reports from a hidraw node and fans values out to entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.vid: int = entry.data[CONF_VID]
        self.pid: int = entry.data[CONF_PID]
        self.phys: str = entry.data.get(CONF_PHYS, "")
        self.report_map = ReportMap()
        self.available = False
        self.state: dict[str, bool | int | None] = {}
        self._fields: dict[int, list[Field]] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake_r, self._wake_w = os.pipe()

    @property
    def signal_available(self) -> str:
        return f"{DOMAIN}_{self.entry.entry_id}_available"

    def signal_field(self, key: str) -> str:
        return f"{DOMAIN}_{self.entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            model=f"USB HID {self.vid:04x}:{self.pid:04x}",
        )

    async def async_setup(self) -> None:
        """Locate the device and parse its descriptor."""
        info = await self.hass.async_add_executor_job(
            find_device, self.vid, self.pid, self.phys
        )
        if info is None:
            raise ConfigEntryNotReady(
                f"HID device {self.vid:04x}:{self.pid:04x} not found"
            )
        try:
            descriptor = await self.hass.async_add_executor_job(info.read_descriptor)
        except OSError as err:
            raise ConfigEntryNotReady(f"Cannot read report descriptor: {err}") from err
        self.report_map = parse_descriptor(descriptor)
        if not self.report_map.fields:
            raise ConfigEntryError("Device has no readable input fields")
        self._fields = self.report_map.by_report()
        self.state = {f.key: self._default(f) for f in self.report_map.fields}

    @staticmethod
    def _default(item: Field) -> bool | None:
        return False if item.kind in (BUTTON, KEY) else None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"hid-{self.vid:04x}:{self.pid:04x}", daemon=True
        )
        self._thread.start()

    async def async_stop(self) -> None:
        self._stop.set()
        os.write(self._wake_w, b"x")
        if self._thread:
            await self.hass.async_add_executor_job(self._thread.join)
        os.close(self._wake_r)
        os.close(self._wake_w)

    # --- reader thread -------------------------------------------------

    def _run(self) -> None:
        warned = False
        while not self._stop.is_set():
            info = find_device(self.vid, self.pid, self.phys)
            fd = None
            if info is not None:
                try:
                    fd = os.open(info.path, os.O_RDONLY | os.O_NONBLOCK)
                except OSError as err:
                    if not warned:
                        _LOGGER.warning("Cannot open %s: %s", info.path, err)
                        warned = True
            if fd is None:
                self._stop.wait(RETRY_INTERVAL)
                continue
            warned = False
            self.hass.loop.call_soon_threadsafe(self._set_available, True)
            try:
                while not self._stop.is_set():
                    ready, _, _ = select.select([fd, self._wake_r], [], [])
                    if self._wake_r in ready:
                        break
                    try:
                        data = os.read(fd, 4096)
                    except BlockingIOError:
                        continue
                    if not data:
                        break
                    self.hass.loop.call_soon_threadsafe(self._handle_report, data)
            except OSError as err:
                _LOGGER.debug("Read error on %s: %s", info.path, err)
            finally:
                os.close(fd)
                self.hass.loop.call_soon_threadsafe(self._set_available, False)
            self._stop.wait(RETRY_INTERVAL)

    # --- event loop side -----------------------------------------------

    @callback
    def _set_available(self, available: bool) -> None:
        if self.available == available:
            return
        self.available = available
        if not available:
            self.state = {f.key: self._default(f) for f in self.report_map.fields}
        async_dispatcher_send(self.hass, self.signal_available)

    @callback
    def _handle_report(self, data: bytes) -> None:
        if self.report_map.uses_report_ids:
            report_id, payload = data[0], data[1:]
        else:
            report_id, payload = 0, data
        for item in self._fields.get(report_id, ()):
            value = item.decode(payload)
            if value is None or self.state.get(item.key) == value:
                continue
            self.state[item.key] = value
            async_dispatcher_send(self.hass, self.signal_field(item.key))
