"""Sensors for HID axes, values and hat switches."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HidConfigEntry
from .entity import HidEntity
from .hid_parser import HAT, VALUE

_HAT_8 = ["n", "ne", "e", "se", "s", "sw", "w", "nw"]
_HAT_4 = ["n", "e", "s", "w"]
HAT_OPTIONS = ["center", *_HAT_8]


async def async_setup_entry(
    hass: HomeAssistant, entry: HidConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    device = entry.runtime_data
    entities: list[HidEntity] = []
    for f in device.report_map.fields:
        if f.kind == VALUE:
            entities.append(HidValueSensor(device, f))
        elif f.kind == HAT:
            entities.append(HidHatSensor(device, f))
    async_add_entities(entities)


class HidValueSensor(HidEntity, SensorEntity):
    """Raw numeric value (axis, slider, wheel, ...)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, device, item) -> None:
        super().__init__(device, item)
        self._attr_icon = "mdi:axis-arrow"
        # Vendor-defined / unnamed fields are rarely meaningful; opt in via the UI.
        self._attr_entity_registry_enabled_default = not item.is_vendor_defined
        self._attr_extra_state_attributes = {
            "logical_min": item.logical_min,
            "logical_max": item.logical_max,
        }

    @property
    def native_value(self) -> int | None:
        return self._device.state.get(self._field.key)


class HidHatSensor(HidEntity, SensorEntity):
    """Hat switch / D-pad direction."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = HAT_OPTIONS
    _attr_icon = "mdi:gamepad-up"

    @property
    def native_value(self) -> str | None:
        value = self._device.state.get(self._field.key)
        if value is None:
            return None
        index = value - self._field.logical_min
        directions = _HAT_4 if self._field.logical_max - self._field.logical_min == 3 else _HAT_8
        return directions[index] if 0 <= index < len(directions) else "center"
