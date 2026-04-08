"""Local machine device adapter."""

from __future__ import annotations

import base64
import importlib
import io
import platform
from typing import Any, Dict, List, Optional

from ...base import DeviceAdapter, DeviceCommand, DeviceFrame
from ....config import config, normalize_coordinate_space


class LocalDeviceAdapter(DeviceAdapter):
    """Built-in adapter for operating the local machine."""

    def __init__(self, plugin_config: Dict[str, Any]):
        self.plugin_config = dict(plugin_config or {})
        self.verbose = bool(self.plugin_config.get('verbose', True))
        self.coordinate_space = normalize_coordinate_space(
            self.plugin_config.get('coordinate_space', config.coordinate_space)
        )
        self.coordinate_scale = float(
            self.plugin_config.get('coordinate_scale', config.coordinate_scale)
        )
        self.natural_scroll = (
            config.natural_scroll
            if self.plugin_config.get('natural_scroll') is None
            else bool(self.plugin_config.get('natural_scroll'))
        )
        self.display_index = int(
            self.plugin_config.get('display_index', config.display_index)
        )
        if self.display_index < 0:
            raise ValueError('display_index 不能小于 0')
        self.current_display_info = self._resolve_display_info(
            self.display_index,
            allow_fallback=True,
        )

    @property
    def device_name(self) -> str:
        return 'local'

    @property
    def target_summary(self) -> Optional[Dict[str, Any]]:
        return self._build_target_payload(self.current_display_info)

    def connect(self) -> None:
        self.current_display_info = self._resolve_display_info(
            self.display_index,
            allow_fallback=True,
        )

    def close(self) -> None:
        return None

    def capture_frame(self) -> DeviceFrame:
        self.current_display_info = self._resolve_display_info(
            self.display_index,
            allow_fallback=True,
        )
        screenshot_module = self._screenshot_module()
        capture_screenshot = screenshot_module.capture_screenshot
        screenshot, _ = capture_screenshot(display_index=self.display_index)
        target_format = self._resolve_screenshot_format(screenshot)
        buffer = io.BytesIO()
        screenshot.save(buffer, format=target_format)
        image_bytes = buffer.getvalue()
        mime_type = self._infer_mime_type(image_bytes, fallback_format=target_format)
        return DeviceFrame(
            image_data_url=(
                f"data:{mime_type};base64,"
                f"{base64.b64encode(image_bytes).decode('utf-8')}"
            ),
            width=int(screenshot.size[0]),
            height=int(screenshot.size[1]),
            metadata={
                'device_name': self.device_name,
                'display': self._build_target_payload(self.current_display_info),
            },
        )

    def execute_command(self, command: DeviceCommand):
        metadata = dict(command.metadata or {})
        frame_width = int(metadata.get('image_width') or 0)
        frame_height = int(metadata.get('image_height') or 0)
        model_width = int(metadata.get('model_image_width') or frame_width or 0)
        model_height = int(metadata.get('model_image_height') or frame_height or 0)
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError('本地设备执行命令缺少截图尺寸')

        source_action_type = str(
            metadata.get('source_action_type') or command.command_type or ''
        ).lower()
        action_executor_module = importlib.import_module('computer_use.action_executor')
        ActionExecutor = action_executor_module.ActionExecutor
        executor = ActionExecutor(
            image_width=frame_width,
            image_height=frame_height,
            model_image_width=model_width,
            model_image_height=model_height,
            coordinate_space=metadata.get('coordinate_space', self.coordinate_space),
            coordinate_scale=metadata.get('coordinate_scale', self.coordinate_scale),
            verbose=metadata.get('verbose', self.verbose),
            natural_scroll=metadata.get('natural_scroll', self.natural_scroll),
            display_offset_x=int(self.current_display_info.get('x', 0)),
            display_offset_y=int(self.current_display_info.get('y', 0)),
        )
        action = {
            'action_type': source_action_type,
            'action_inputs': dict(command.payload or {}),
        }
        return executor.execute(action)

    def get_status(self) -> Dict[str, Any]:
        return {
            'device_name': self.device_name,
            'display_index': self.current_display_info['index'],
            'display_bounds': self._display_bounds_list(self.current_display_info),
            'display_is_primary': self.current_display_info['is_primary'],
        }

    def get_environment_info(self) -> Dict[str, Any]:
        return {
            'operating_system': self._get_operating_system_description(),
        }

    def supports_target_selection(self) -> bool:
        return True

    def list_targets(self) -> List[Dict[str, Any]]:
        screenshot_module = self._screenshot_module()
        list_displays = getattr(screenshot_module, 'list_displays', None)
        if callable(list_displays):
            return [self._build_target_payload(item.to_dict()) for item in list_displays()]
        return [self._build_target_payload(self.current_display_info)]

    def set_target(self, target_id):
        target_index = int(target_id)
        if target_index < 0:
            raise ValueError('display_index 不能小于 0')
        self.current_display_info = self._resolve_display_info(
            target_index,
            allow_fallback=False,
        )
        self.display_index = target_index
        return self._build_target_payload(self.current_display_info)

    def _resolve_display_info(
        self,
        display_index: Optional[int] = None,
        allow_fallback: bool = False,
    ) -> Dict[str, Any]:
        target_index = self.display_index if display_index is None else int(display_index)
        screenshot_module = self._screenshot_module()
        try:
            resolve_display = screenshot_module.resolve_display
            return self._normalize_display_info(resolve_display(target_index))
        except ValueError as exc:
            if not allow_fallback or target_index == 0:
                raise
            if '超出范围' not in str(exc):
                raise
            resolve_display = screenshot_module.resolve_display
            fallback_info = self._normalize_display_info(resolve_display(0))
            self.display_index = 0
            if self.verbose:
                print(
                    f"[警告] 目标显示器 {target_index} 不可用，已回退到主显示器 0"
                )
            return fallback_info

    def _normalize_display_info(self, display_info: Any) -> Dict[str, Any]:
        if hasattr(display_info, 'to_dict'):
            payload = display_info.to_dict()
        elif isinstance(display_info, dict):
            payload = dict(display_info)
        else:
            raise ValueError(f'无法解析显示器信息: {display_info}')
        payload['index'] = int(payload.get('index', 0))
        payload['x'] = int(payload.get('x', 0))
        payload['y'] = int(payload.get('y', 0))
        payload['width'] = int(payload.get('width', 0))
        payload['height'] = int(payload.get('height', 0))
        payload['is_primary'] = bool(payload.get('is_primary', payload['index'] == 0))
        payload['bounds'] = self._display_bounds_list(payload)
        return payload

    def _display_bounds_list(self, display_info: Dict[str, Any]) -> List[int]:
        return [
            int(display_info.get('x', 0)),
            int(display_info.get('y', 0)),
            int(display_info.get('width', 0)),
            int(display_info.get('height', 0)),
        ]

    def _build_target_payload(self, display_info: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'id': display_info['index'],
            'index': display_info['index'],
            'x': display_info['x'],
            'y': display_info['y'],
            'width': display_info['width'],
            'height': display_info['height'],
            'is_primary': display_info['is_primary'],
            'bounds': self._display_bounds_list(display_info),
        }

    def _screenshot_module(self):
        return importlib.import_module('computer_use.screenshot')

    def _get_operating_system_description(self) -> str:
        system_name = platform.system()

        if system_name == 'Darwin':
            macos_version = platform.mac_ver()[0]
            return f'macOS {macos_version}' if macos_version else 'macOS'

        if system_name == 'Windows':
            windows_release = platform.release()
            return f'Windows {windows_release}' if windows_release else 'Windows'

        if system_name == 'Linux':
            linux_name = self._read_linux_os_release_name()
            return linux_name or 'Linux'

        return system_name or 'Unknown'

    def _read_linux_os_release_name(self) -> Optional[str]:
        os_release_path = '/etc/os-release'
        try:
            with open(os_release_path, 'r', encoding='utf-8') as file_obj:
                for raw_line in file_obj:
                    line = raw_line.strip()
                    if line.startswith('PRETTY_NAME='):
                        return line.split('=', 1)[1].strip().strip('"')
        except OSError:
            return None

        return None

    def _resolve_screenshot_format(self, screenshot: Any) -> str:
        raw_format = str(getattr(screenshot, 'format', '') or '').strip().upper()
        if raw_format in {'PNG', 'JPEG'}:
            return raw_format
        return 'PNG'

    def _infer_mime_type(self, image_bytes: bytes, fallback_format: str = 'PNG') -> str:
        if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        if image_bytes.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if str(fallback_format).strip().upper() == 'JPEG':
            return 'image/jpeg'
        return 'image/png'
