"""VNC device adapter."""

from __future__ import annotations

import base64
import io
import time
from typing import Any, Dict

try:
    from vncdotool import api
except ImportError:  # pragma: no cover - exercised via patched tests
    api = None

from ...base import DeviceAdapter, DeviceCommand, DeviceFrame
from ...helpers import detect_image_size


class VncDeviceAdapter(DeviceAdapter):
    _KEY_ALIASES = {
        'backspace': 'bsp',
        'cmd': 'meta',
        'command': 'meta',
        'control': 'ctrl',
        'escape': 'esc',
        'pageup': 'pgup',
        'pagedown': 'pgdn',
        'page_up': 'pgup',
        'page_down': 'pgdn',
        'return': 'enter',
        'super': 'super',
    }

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
        self._client = None
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass
        if api is not None and hasattr(api, 'shutdown'):
            try:
                api.shutdown()
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
            buffer = io.BytesIO()
            client.captureScreen(buffer, format='PNG')
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
        payload = dict(command.payload or {})
        command_type = str(command.command_type or '').strip().lower()

        if command_type == 'type_text':
            try:
                client = self._require_client()
                content = str(payload.get('content') or '')
                if not content:
                    raise ValueError('vnc type_text 需要 content')
                if not content.isascii():
                    raise ValueError(
                        'vnc type_text 暂不支持非 ASCII 文本输入'
                    )
                for char in content:
                    client.keyPress(char)
                return 'type_text 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc type_text 失败: {exc}') from exc

        if command_type == 'click':
            try:
                client = self._require_client()
                point = self._require_point(payload, 'point')
                client.mouseMove(point[0], point[1])
                client.mousePress(1)
                return 'click 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc click 失败: {exc}') from exc

        if command_type == 'double_click':
            try:
                client = self._require_client()
                point = self._require_point(payload, 'point')
                client.mouseMove(point[0], point[1])
                client.mousePress(1)
                client.mousePress(1)
                return 'double_click 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc double_click 失败: {exc}') from exc

        if command_type == 'right_click':
            try:
                client = self._require_client()
                point = self._require_point(payload, 'point')
                client.mouseMove(point[0], point[1])
                client.mousePress(3)
                return 'right_click 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc right_click 失败: {exc}') from exc

        if command_type == 'move':
            try:
                client = self._require_client()
                point = self._require_point(payload, 'point')
                client.mouseMove(point[0], point[1])
                return 'move 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc move 失败: {exc}') from exc

        if command_type == 'drag':
            try:
                client = self._require_client()
                start_point = self._require_point(
                    payload,
                    'start_point',
                    fallback_keys=['start_box'],
                )
                end_point = self._require_point(
                    payload,
                    'end_point',
                    fallback_keys=['end_box'],
                )
                client.mouseMove(start_point[0], start_point[1])
                client.mouseDown(1)
                try:
                    client.mouseMove(end_point[0], end_point[1])
                finally:
                    client.mouseUp(1)
                return 'drag 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc drag 失败: {exc}') from exc

        if command_type == 'hotkey':
            try:
                client = self._require_client()
                keys = self._normalize_keys(payload.get('key'))
                main_key = keys[-1]
                modifiers = keys[:-1]

                pressed_modifiers = []
                primary_error = None
                try:
                    for key in modifiers:
                        client.keyDown(key)
                        pressed_modifiers.append(key)
                    client.keyPress(main_key)
                except Exception as exc:
                    primary_error = exc
                    raise
                finally:
                    release_error = None
                    for key in reversed(pressed_modifiers):
                        try:
                            client.keyUp(key)
                        except Exception as exc:
                            if release_error is None:
                                release_error = exc

                    if primary_error is None and release_error is not None:
                        raise release_error

                return 'hotkey 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc hotkey 失败: {exc}') from exc

        if command_type == 'key_down':
            try:
                client = self._require_client()
                key = self._require_key(payload)
                client.keyDown(key)
                return 'key_down 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc key_down 失败: {exc}') from exc

        if command_type == 'key_up':
            try:
                client = self._require_client()
                key = self._require_key(payload)
                client.keyUp(key)
                return 'key_up 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc key_up 失败: {exc}') from exc

        if command_type == 'scroll':
            try:
                client = self._require_client()
                point = self._require_point(payload, 'point')
                direction = str(payload.get('direction') or '').strip().lower()
                button = self._scroll_button(direction)
                steps = self._resolve_scroll_steps(payload)
                client.mouseMove(point[0], point[1])
                for _ in range(steps):
                    client.mousePress(button)
                return 'scroll 执行成功'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc scroll 失败: {exc}') from exc

        if command_type == 'wait':
            try:
                seconds = self._resolve_wait_seconds(payload)
                time.sleep(seconds)
                seconds_text = int(seconds) if seconds.is_integer() else seconds
                return f'等待 {seconds_text} 秒'
            except ValueError:
                raise
            except Exception as exc:
                raise RuntimeError(f'vnc wait 失败: {exc}') from exc

        raise ValueError(f'vnc 不支持命令类型: {command_type}')

    @staticmethod
    def _normalize_keys(raw_value):
        value = '' if raw_value is None else str(raw_value)
        normalized = value.replace('+', ' ').strip().lower()
        keys = [part for part in normalized.split() if part]
        if not keys:
            raise ValueError('vnc hotkey 需要 key')
        return [VncDeviceAdapter._normalize_key_name(key) for key in keys]

    @staticmethod
    def _require_key(payload):
        try:
            raw_value = payload['key']
        except KeyError as exc:
            raise ValueError('vnc key event 需要 key') from exc
        key = str(raw_value).strip().lower()
        if not key:
            raise ValueError('vnc key event 需要 key')
        return VncDeviceAdapter._normalize_key_name(key)

    @classmethod
    def _normalize_key_name(cls, key):
        normalized = str(key).strip().lower()
        if not normalized:
            return normalized
        return cls._KEY_ALIASES.get(normalized, normalized)

    @staticmethod
    def _scroll_button(direction):
        mapping = {'up': 4, 'down': 5, 'left': 6, 'right': 7}
        if direction in mapping:
            return mapping[direction]
        raise ValueError(f'vnc 不支持滚动方向: {direction}')

    @staticmethod
    def _resolve_scroll_steps(payload):
        raw_steps = payload.get('steps', 5)
        try:
            steps = int(raw_steps)
        except (TypeError, ValueError) as exc:
            raise ValueError('vnc scroll steps 必须大于 0') from exc
        if steps <= 0:
            raise ValueError('vnc scroll steps 必须大于 0')
        return steps

    @staticmethod
    def _resolve_wait_seconds(payload, default=3):
        raw_value = payload.get('seconds', payload.get('duration', default))
        try:
            seconds = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'vnc wait seconds 格式无效: {raw_value}') from exc
        return max(1.0, min(seconds, 60.0))

    def _require_point(self, payload, key, fallback_keys=()):
        if key in payload:
            value = payload[key]
        else:
            value = None
            for fallback_key in fallback_keys:
                if fallback_key in payload:
                    value = payload[fallback_key]
                    break
            else:
                raise ValueError(f'vnc 命令缺少坐标: {key}')

        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return [int(value[0]), int(value[1])]
            except (TypeError, ValueError) as exc:
                raise ValueError(f'vnc 坐标格式无效: {value}') from exc

        raise ValueError(f'vnc 坐标格式无效: {value}')

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
