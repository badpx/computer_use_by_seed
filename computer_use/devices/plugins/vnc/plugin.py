"""Plugin entrypoint for the built-in vnc device."""

from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter


def create_adapter(config):
    return VncDeviceAdapter(config or {})
