"""Plugin entrypoint for the built-in local device."""

from computer_use.devices.plugins.local.adapter import LocalDeviceAdapter


def create_adapter(config):
    return LocalDeviceAdapter(config or {})
