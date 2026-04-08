"""Android device adapter backed by adb."""

from __future__ import annotations

import base64
import subprocess
from typing import Any, Dict, List, Optional

from ...base import DeviceAdapter, DeviceCommand, DeviceFrame


_ADB_BINARY = 'adb'
_PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


class AndroidAdbDeviceAdapter(DeviceAdapter):
    """Device adapter for Android devices reachable through adb."""

    def __init__(self, plugin_config: Dict[str, Any]):
        self.plugin_config = dict(plugin_config or {})

    @property
    def device_name(self) -> str:
        return 'android_adb'

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def capture_frame(self) -> DeviceFrame:
        screenshot_result = self._run_adb(
            ['exec-out', 'screencap', '-p'],
            action_label='capture screenshot',
        )
        image_bytes, prefix_stripped = self._extract_png_bytes(screenshot_result.stdout)
        width, height = self._read_png_size(image_bytes)
        return DeviceFrame(
            image_data_url=(
                'data:image/png;base64,'
                + base64.b64encode(image_bytes).decode('utf-8')
            ),
            width=width,
            height=height,
            metadata={
                'device_name': self.device_name,
                'capture_method': 'adb exec-out screencap -p',
                'png_prefix_stripped': prefix_stripped,
            },
        )

    def execute_command(self, command: DeviceCommand):
        payload = dict(command.payload or {})
        command_type = str(command.command_type or '').strip().lower()

        if command_type == 'click':
            point = self._require_point(payload, 'point')
            self._run_adb(
                ['shell', 'input', 'tap', str(point[0]), str(point[1])],
                action_label='click',
            )
            return 'click 执行成功'

        if command_type == 'long_press':
            point = self._require_point(payload, 'point')
            duration_ms = self._resolve_duration_ms(payload)
            self._run_adb(
                [
                    'shell',
                    'input',
                    'swipe',
                    str(point[0]),
                    str(point[1]),
                    str(point[0]),
                    str(point[1]),
                    str(duration_ms),
                ],
                action_label='long_press',
            )
            return 'long_press 执行成功'

        if command_type == 'drag':
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
            duration_ms = self._resolve_duration_ms(payload)
            self._run_adb(
                [
                    'shell',
                    'input',
                    'draganddrop',
                    str(start_point[0]),
                    str(start_point[1]),
                    str(end_point[0]),
                    str(end_point[1]),
                    str(duration_ms),
                ],
                action_label='drag',
            )
            return 'drag 执行成功'

        if command_type == 'type_text':
            return self._execute_type_text(payload)

        if command_type == 'scroll':
            point = self._require_point(payload, 'point')
            axis_arg = self._resolve_scroll_axis(payload)
            self._run_adb(
                [
                    'shell',
                    'input',
                    'touchscreen',
                    'scroll',
                    str(point[0]),
                    str(point[1]),
                    '--axis',
                    axis_arg,
                ],
                action_label='scroll',
            )
            return 'scroll 执行成功'

        if command_type == 'open_app':
            package_name = str(
                payload.get('app_name')
                or payload.get('package')
                or payload.get('package_name')
                or ''
            ).strip()
            if not package_name:
                raise ValueError('android_adb open_app 需要 app_name')
            self._run_adb(
                [
                    'shell',
                    'monkey',
                    '-p',
                    package_name,
                    '-c',
                    'android.intent.category.LAUNCHER',
                    '1',
                ],
                action_label='open_app',
            )
            return 'open_app 执行成功'

        if command_type == 'press_home':
            self._run_adb(
                ['shell', 'input', 'keyevent', 'KEYCODE_HOME'],
                action_label='press_home',
            )
            return 'press_home 执行成功'

        if command_type == 'press_back':
            self._run_adb(
                ['shell', 'input', 'keyevent', 'KEYCODE_BACK'],
                action_label='press_back',
            )
            return 'press_back 执行成功'

        raise ValueError(f'android_adb 不支持命令类型: {command_type}')

    def get_status(self) -> Dict[str, Any]:
        return {
            'device_name': self.device_name,
            'connected_via': 'adb',
        }

    def get_prompt_profile(self) -> str:
        return 'cellphone'

    def get_environment_info(self) -> Dict[str, Any]:
        return {'operating_system': 'Android'}

    def _execute_type_text(self, payload: Dict[str, Any]):
        raw_content = str(payload.get('content', ''))
        has_trailing_newline = raw_content.endswith('\n')
        content = raw_content[:-1] if has_trailing_newline else raw_content
        results: List[str] = []

        if content:
            self._run_adb(
                ['shell', 'input', 'text', self._escape_text(content)],
                action_label='type_text',
            )
            results.append('type_text 执行成功')

        if has_trailing_newline:
            self._run_adb(
                ['shell', 'input', 'keyevent', 'KEYCODE_ENTER'],
                action_label='press_enter',
            )
            results.append('press_enter 执行成功')

        if not results:
            raise ValueError('android_adb type_text 需要 content')

        return results[0] if len(results) == 1 else results

    def _run_adb(
        self,
        adb_args: List[str],
        action_label: str,
    ) -> subprocess.CompletedProcess[bytes]:
        argv = [_ADB_BINARY] + list(adb_args)
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError('缺少 adb 依赖，请先安装 Android Platform Tools') from exc

        if result.returncode != 0:
            stderr_text = self._safe_preview(result.stderr, limit=200)
            details = f'，stderr: {stderr_text}' if stderr_text else ''
            raise RuntimeError(
                f'android_adb {action_label} 失败，退出码 {result.returncode}{details}'
            )
        return result

    def _extract_png_bytes(self, stdout: bytes) -> tuple[bytes, bool]:
        png_offset = bytes(stdout).find(_PNG_SIGNATURE)
        if png_offset < 0:
            preview = self._safe_preview(stdout, limit=80)
            raise RuntimeError(
                f'android_adb 截图输出中未找到 PNG 签名，输出预览: {preview}'
            )
        return bytes(stdout[png_offset:]), png_offset > 0

    def _read_png_size(self, png_bytes: bytes) -> tuple[int, int]:
        if len(png_bytes) < 24 or not png_bytes.startswith(_PNG_SIGNATURE):
            raise RuntimeError('android_adb 截图不是有效的 PNG 数据')
        width = int.from_bytes(png_bytes[16:20], 'big')
        height = int.from_bytes(png_bytes[20:24], 'big')
        if width <= 0 or height <= 0:
            raise RuntimeError('android_adb 截图 PNG 尺寸无效')
        return width, height

    def _require_point(
        self,
        payload: Dict[str, Any],
        key: str,
        fallback_keys: Optional[List[str]] = None,
    ) -> List[int]:
        value = payload.get(key)
        if value is None:
            for fallback_key in fallback_keys or []:
                value = payload.get(fallback_key)
                if value is not None:
                    break
        if value is None:
            raise ValueError(f'android_adb 命令缺少坐标: {key}')
        point = self._coerce_point(value)
        return point

    def _coerce_point(self, value: Any) -> List[int]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                return [int(float(value[0])), int(float(value[1]))]
            except (TypeError, ValueError) as exc:
                raise ValueError(f'android_adb 坐标格式无效: {value}') from exc
        if isinstance(value, str):
            parts = [part for part in value.replace(',', ' ').split() if part]
            if len(parts) == 2:
                try:
                    return [int(float(parts[0])), int(float(parts[1]))]
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'android_adb 坐标格式无效: {value}') from exc
        raise ValueError(f'android_adb 坐标格式无效: {value}')

    def _resolve_duration_ms(self, payload: Dict[str, Any], default: int = 800) -> int:
        raw_value = payload.get('duration_ms', payload.get('duration', default))
        try:
            duration_ms = int(float(raw_value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f'android_adb duration_ms 格式无效: {raw_value}') from exc
        if duration_ms <= 0:
            raise ValueError('android_adb duration_ms 必须大于 0')
        return duration_ms

    def _resolve_scroll_axis(self, payload: Dict[str, Any]) -> str:
        direction = str(payload.get('direction', 'down')).strip().lower()
        raw_steps = payload.get('steps', 50)
        try:
            steps = int(abs(float(raw_steps)))
        except (TypeError, ValueError) as exc:
            raise ValueError(f'android_adb scroll steps 格式无效: {raw_steps}') from exc
        if steps <= 0:
            raise ValueError('android_adb scroll steps 必须大于 0')
        if direction == 'down':
            return f'VSCROLL,{steps}'
        if direction == 'up':
            return f'VSCROLL,{-steps}'
        if direction == 'right':
            return f'HSCROLL,{steps}'
        if direction == 'left':
            return f'HSCROLL,{-steps}'
        raise ValueError(f'android_adb 不支持滚动方向: {direction}')

    def _escape_text(self, value: str) -> str:
        return value.replace('%', '%25').replace(' ', '%s')

    def _safe_preview(self, data: bytes, limit: int = 80) -> str:
        if not data:
            return '(empty)'
        preview = bytes(data[:limit]).decode('utf-8', errors='backslashreplace')
        if len(data) > limit:
            return preview + '...'
        return preview
