"""VNC device adapter."""

from __future__ import annotations

import base64
import io
from typing import Any, Dict

try:
    from vncdotool import api
except ImportError:  # pragma: no cover - exercised via patched tests
    api = None

from ...base import DeviceAdapter, DeviceCommand, DeviceFrame
from ...helpers import detect_image_size


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

    def _address(self) -> str:
        return f'{self.host}::{self.port}'

    def connect(self) -> None:
        if self._client is not None:
            return None
        if api is None:
            raise RuntimeError('缺少 vncdotool 依赖，请先安装 vncdotool')

        kwargs = {}
        if self.password is not None:
            kwargs['password'] = self.password

        try:
            self._client = api.connect(self._address(), **kwargs)
        except Exception as exc:
            message = str(exc)
            if 'auth' in message.lower() or 'password' in message.lower():
                raise RuntimeError(f'vnc 认证失败: {message}') from exc
            raise RuntimeError(f'vnc connect 失败: {message}') from exc
        return None

    def close(self) -> None:
        client = self._client
        if client is None:
            return None

        self._client = None
        try:
            client.disconnect()
        except Exception:
            pass
        return None

    def _require_client(self):
        if self._client is None:
            self.connect()
        if self._client is None:
            raise RuntimeError('vnc connect 失败: 未建立连接')
        return self._client

    def capture_frame(self) -> DeviceFrame:
        client = self._require_client()
        try:
            image = client.captureScreen()
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            image_bytes = buffer.getvalue()
            width, height = detect_image_size(
                image_bytes, mime_type='image/png'
            )
        except Exception as exc:
            raise RuntimeError(f'vnc capture screenshot 失败: {exc}') from exc
        return DeviceFrame(
            image_data_url=(
                'data:image/png;base64,'
                + base64.b64encode(image_bytes).decode('utf-8')
            ),
            width=width,
            height=height,
            metadata={
                'device_name': self.device_name,
                'capture_method': 'vncdotool',
                'host': self.host,
                'port': self.port,
            },
        )

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
