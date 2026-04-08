"""Plugin entrypoint for the built-in android_adb device."""

from computer_use.devices.plugins.android_adb.adapter import AndroidAdbDeviceAdapter


def create_adapter(config):
    return AndroidAdbDeviceAdapter(config or {})
