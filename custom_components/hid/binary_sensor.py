"""Binary sensors for HID buttons and keys."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HidConfigEntry
from .entity import HidEntity
from .hid_parser import BUTTON, KEY

# Keyboards report ~100 keys; only enable those by default for small key sets.
_KEY_DEFAULT_ENABLED_MAX = 32


async def async_setup_entry(
    hass: HomeAssistant, entry: HidConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    device = entry.runtime_data
    key_count = sum(1 for f in device.report_map.fields if f.kind == KEY)
    async_add_entities(
        HidBinarySensor(device, f, key_count <= _KEY_DEFAULT_ENABLED_MAX)
        for f in device.report_map.fields
        if f.kind in (BUTTON, KEY)
    )


class HidBinarySensor(HidEntity, BinarySensorEntity):
    """True while a button or key is held down."""

    def __init__(self, device, item, enabled_default: bool) -> None:
        super().__init__(device, item)
        self._attr_icon = "mdi:keyboard" if item.kind == KEY else "mdi:gesture-tap-button"
        self._attr_entity_registry_enabled_default = enabled_default or item.kind == BUTTON

    @property
    def is_on(self) -> bool | None:
        return self._device.state.get(self._field.key)
