"""
本地上下文日志模块
按任务写入 JSONL，便于回放每轮模型调用与执行结果
"""

import json
import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class ContextLogger:
    """按任务写入上下文日志。"""

    def __init__(self, enabled: bool = True, log_dir: str = './logs'):
        self.enabled = enabled
        self.log_dir = Path(log_dir)
        self.screenshot_dir = self.log_dir / 'screenshots'
        self.task_id: Optional[str] = None
        self.log_path: Optional[Path] = None

        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def start_task(
        self,
        instruction: str,
        model: str,
        max_steps: int,
        temperature: float,
        thinking_mode: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        coordinate_space: Optional[str] = None,
        coordinate_scale: Optional[float] = None,
        screenshot_size: Optional[int] = None,
        max_context_screenshots: Optional[int] = None,
        include_execution_feedback: Optional[bool] = None,
        log_full_messages: Optional[bool] = None,
        display_index: Optional[int] = None,
        display_bounds: Optional[list[int]] = None,
        display_is_primary: Optional[bool] = None,
        device_name: Optional[str] = None,
        device_status: Optional[Dict[str, Any]] = None,
        device_target: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """开始一个新任务并创建日志文件。"""
        if not self.enabled:
            return None

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        self.task_id = f'task_{timestamp}'
        self.log_path = self.log_dir / f'{self.task_id}.jsonl'

        self.log_event(
            'task_start',
            instruction=instruction,
            model=model,
            max_steps=max_steps,
            temperature=temperature,
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
            coordinate_space=coordinate_space,
            coordinate_scale=coordinate_scale,
            screenshot_size=screenshot_size,
            max_context_screenshots=max_context_screenshots,
            include_execution_feedback=include_execution_feedback,
            log_full_messages=log_full_messages,
            display_index=display_index,
            display_bounds=display_bounds,
            display_is_primary=display_is_primary,
            device_name=device_name,
            device_status=device_status,
            device_target=device_target,
        )

        return self.task_id

    def save_screenshot(self, screenshot: Any, step: int) -> Optional[str]:
        """保存调试截图并返回相对于日志目录的路径。"""
        if not self.enabled or self.task_id is None:
            return None

        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        extension = self._resolve_screenshot_extension(screenshot)
        filename = f'{self.task_id}_step_{step:03d}.{extension}'
        screenshot_path = self.screenshot_dir / filename
        if hasattr(screenshot, 'image_data_url'):
            screenshot_path.write_bytes(
                base64.b64decode(self._extract_base64_payload(str(screenshot.image_data_url)))
            )
        else:
            screenshot.save(screenshot_path)
        return self.to_relative_path(screenshot_path)

    def to_relative_path(self, path: Path) -> str:
        """将日志产物路径转换为相对日志目录的稳定引用。"""
        return path.relative_to(self.log_dir).as_posix()

    def resolve_path(self, relative_path: Optional[str]) -> Optional[str]:
        """将相对日志路径转换为实际文件路径。"""
        if relative_path is None:
            return None
        return str(self.log_dir / relative_path)

    def log_event(self, event: str, **payload: Any) -> None:
        """写入一条 JSONL 记录。"""
        if not self.enabled or self.log_path is None:
            return

        record: Dict[str, Any] = {
            'event': event,
            'timestamp': datetime.now().isoformat(timespec='milliseconds'),
        }

        if self.task_id is not None:
            record['task_id'] = self.task_id

        record.update(payload)

        with self.log_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def end_task(
        self,
        success: bool,
        final_response: Optional[str] = None,
        error: Optional[str] = None,
        elapsed_seconds: Optional[float] = None,
        elapsed_time_text: Optional[str] = None,
    ) -> None:
        """结束当前任务。"""
        self.log_event(
            'task_end',
            success=success,
            final_response=final_response,
            error=error,
            elapsed_seconds=elapsed_seconds,
            elapsed_time_text=elapsed_time_text,
        )

    @property
    def current_log_path(self) -> Optional[str]:
        if self.log_path is None:
            return None
        return str(self.log_path)

    def _resolve_screenshot_extension(self, screenshot: Any) -> str:
        mime_type = self._extract_mime_type(screenshot)
        if mime_type == 'image/jpeg':
            return 'jpg'
        return 'png'

    def _extract_mime_type(self, screenshot: Any) -> Optional[str]:
        image_data_url = getattr(screenshot, 'image_data_url', None)
        if image_data_url:
            prefix = 'data:'
            marker = ';base64,'
            payload = str(image_data_url).strip()
            if payload.startswith(prefix) and marker in payload:
                return payload[len(prefix):].split(marker, 1)[0].strip().lower()
        return getattr(screenshot, 'mime_type', None)

    def _extract_base64_payload(self, image_data_url: str) -> str:
        marker = ';base64,'
        if marker in image_data_url:
            return image_data_url.split(marker, 1)[1].strip()
        return image_data_url.strip()
