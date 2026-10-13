"""The HID Devices integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .device import HidDevice

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type HidConfigEntry = ConfigEntry[HidDevice]


async def async_setup_entry(hass: HomeAssistant, entry: HidConfigEntry) -> bool:
    device = HidDevice(hass, entry)
    await device.async_setup()
    entry.runtime_data = device
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    device.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HidConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop()
    return unload_ok
