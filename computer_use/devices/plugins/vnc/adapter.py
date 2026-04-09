"""Stub VNC device adapter."""

from __future__ import annotations

from ...base import DeviceAdapter


class VncDeviceAdapter(DeviceAdapter):
    def __init__(self, config):
        self.config = dict(config)

    @property
    def device_name(self):
        return 'vnc'

    def connect(self):
        return None

    def close(self):
        return None

    def capture_frame(self):
        raise NotImplementedError

    def execute_command(self, command):
        raise NotImplementedError

    def get_status(self):
        return {'device_name': self.device_name}
