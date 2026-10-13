# HID Devices for Home Assistant

A HACS custom integration that exposes USB HID devices (gamepads, joysticks, macro pads, stream decks-style button boxes, keyboards, media remotes, ...) as Home Assistant entities.

The integration reads the device's **HID report descriptor** and creates one entity per field automatically:

| HID field | Entity |
|---|---|
| Button (Button page, or any 1-bit field) | `binary_sensor` – on while held |
| Keyboard / consumer-control key (array fields) | `binary_sensor` – on while held (disabled by default when a device has more than 32 keys) |
| Axis / slider / wheel / other value | `sensor` – raw value, with `logical_min` / `logical_max` attributes |
| Hat switch / D-pad | `sensor` (enum: `center`, `n`, `ne`, `e`, `se`, `s`, `sw`, `w`, `nw`) |

Each device appears as one Home Assistant device, updates are push based (no polling), and entities go unavailable when the device is unplugged and recover automatically when it returns.

## Requirements

* Home Assistant **2024.11+** running on **Linux** (Home Assistant OS, Supervised, Container, Core). macOS/Windows hosts are not supported.
* The device must be visible to Home Assistant as `/dev/hidraw*`.
  * **Home Assistant OS / Supervised**: works out of the box with USB devices plugged into the host.
  * **Docker**: run the container privileged, or pass the node through (`--device /dev/hidraw0`) and mount `/sys` read-only (`-v /sys:/sys:ro`) so the descriptor can be read. Passing a specific node means a re-plug may require a container restart.
  * **Core/venv**: the user running HA needs read access to the node (e.g. a udev rule `KERNEL=="hidraw*", ATTRS{idVendor}=="xxxx", MODE="0660", GROUP="homeassistant"`).
* Devices attached to a remote host are out of scope (for now).

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/bfulham/ha-hid` as type **Integration**.
2. Install **HID Devices** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → HID Devices**, pick your device.

### Manual

Copy `custom_components/hid` into your Home Assistant `config/custom_components/` directory and restart.

## Notes and limitations

* The integration only **reads** input reports; it never writes to or grabs the device, so the host's normal handling still applies (e.g. a keyboard will still type on the host).
* Many devices expose several HID interfaces (e.g. keyboard + media keys + vendor). Each interface is added separately and shown in the picker as `hidrawN`.
* Relative axes (mouse movement/wheel) show the last reported delta; they don't return to 0 on their own.
* Devices are matched by VID/PID plus the USB port path, so moving a device to another port is tolerated if it is the only one of its kind.
* Vendor-specific data that isn't described as normal input fields (e.g. proprietary feature reports) isn't exposed.

## Development

```bash
python -m pip install pytest
python -m pytest tests     # parser tests, no Home Assistant required
```

## License

MIT
