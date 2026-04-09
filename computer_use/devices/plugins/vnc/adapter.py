"""Stub VNC device adapter."""

from __future__ import annotations

from typing import Any, Dict

from ...base import DeviceAdapter, DeviceCommand, DeviceFrame


class VncDeviceAdapter(DeviceAdapter):
    def __init__(self, plugin_config: Dict[str, Any]):
        self.plugin_config = dict(plugin_config or {})

    @property
    def device_name(self) -> str:
        return 'vnc'

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def capture_frame(self) -> DeviceFrame:
        raise NotImplementedError

    def execute_command(self, command: DeviceCommand):
        raise NotImplementedError

    def get_status(self) -> Dict[str, Any]:
        return {'device_name': self.device_name}
