"""Config flow for HID Devices."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_DEVICE, CONF_PHYS, CONF_PID, CONF_UNIQ, CONF_VID, DOMAIN
from .hid_parser import parse_descriptor
from .hidraw import HidrawInfo, list_devices


def _discover() -> dict[str, HidrawInfo]:
    """Return hidraw devices that expose at least one input field."""
    found: dict[str, HidrawInfo] = {}
    for info in list_devices():
        try:
            if parse_descriptor(info.read_descriptor()).fields:
                found[info.node] = info
        except OSError:
            continue
    return found


class HidConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick a connected HID device."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        devices = await self.hass.async_add_executor_job(_discover)
        if user_input is not None and (info := devices.get(user_input[CONF_DEVICE])):
            await self.async_set_unique_id(info.unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=info.name,
                data={
                    CONF_VID: info.vid,
                    CONF_PID: info.pid,
                    CONF_PHYS: info.phys,
                    CONF_UNIQ: info.uniq,
                },
            )
        if not devices:
            return self.async_abort(reason="no_devices")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE): vol.In({n: d.label for n, d in devices.items()})}
            ),
        )
