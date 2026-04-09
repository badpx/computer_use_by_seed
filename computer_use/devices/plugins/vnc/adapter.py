"""Stub VNC device adapter."""

from __future__ import annotations

from typing import Any, Dict

from ...base import DeviceAdapter, DeviceCommand, DeviceFrame


class VncDeviceAdapter(DeviceAdapter):
    def __init__(self, plugin_config: Dict[str, Any]):
        self.plugin_config = dict(plugin_config or {})
        self.host = str(self.plugin_config.get('host') or '').strip()
        if not self.host:
            raise ValueError('vnc 设备配置缺少 host')
        raw_port = self.plugin_config.get('port', 5900)
        try:
            self.port = int(raw_port)
        except (TypeError, ValueError) as exc:
            raise ValueError('vnc 设备配置中的 port 无效') from exc
        self.password = self.plugin_config.get('password')
        self.prompt_profile = str(
            self.plugin_config.get('prompt_profile') or 'computer'
        ).strip() or 'computer'
        self.operating_system = str(
            self.plugin_config.get('operating_system') or 'Remote VNC Device'
        ).strip() or 'Remote VNC Device'
        self._client = None

    @property
    def device_name(self) -> str:
        return 'vnc'

    def connect(self) -> None:
        return None

    def close(self) -> None:
        self._client = None
        return None

    def capture_frame(self) -> DeviceFrame:
        raise NotImplementedError

    def execute_command(self, command: DeviceCommand):
        raise NotImplementedError

    def get_status(self) -> Dict[str, Any]:
        return {
            'device_name': self.device_name,
            'connected_via': 'vnc',
            'host': self.host,
            'port': self.port,
            'connected': self._client is not None,
        }

    def get_prompt_profile(self) -> str:
        return self.prompt_profile

    def get_environment_info(self) -> Dict[str, Any]:
        return {'operating_system': self.operating_system}
