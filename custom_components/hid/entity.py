"""Base entity for HID fields."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .device import HidDevice
from .hid_parser import Field


class HidEntity(Entity):
    """An entity bound to one field of a HID device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: HidDevice, item: Field) -> None:
        self._device = device
        self._field = item
        self._attr_name = item.name
        self._attr_unique_id = f"{device.entry.entry_id}_{item.key}"
        self._attr_device_info = device.device_info

    @property
    def available(self) -> bool:
        return self._device.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._device.signal_field(self._field.key), self._update
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._device.signal_available, self._update
            )
        )

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()
