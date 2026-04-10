"""Local-only action execution for pixel-space commands."""

from __future__ import annotations

import ast
import re
import sys
import time
from typing import Any, Dict, List, Tuple, Union

import pyautogui

DOUBLE_CLICK_INTERVAL = 0.12


class LocalActionExecutor:
    """Execute already-normalized pixel-space actions on the local machine."""

    def __init__(
        self,
        *,
        verbose: bool = True,
        input_swap: bool = True,
        display_offset_x: int = 0,
        display_offset_y: int = 0,
    ):
        self.verbose = verbose
        self.input_swap = input_swap
        self.display_offset_x = int(display_offset_x)
        self.display_offset_y = int(display_offset_y)

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1

    def execute(self, action: Dict[str, Any]) -> Union[str, List[str]]:
        action_type = action.get('action_type', '').lower()
        action_inputs = action.get('action_inputs', {})

        if self.verbose:
            print(f"\n[执行动作] {action_type}")
            print(f"  参数: {action_inputs}")

        if action_type in ['click', 'left_single']:
            return self._execute_click(action_inputs, button='left', clicks=1)
        if action_type == 'left_double':
            return self._execute_click(action_inputs, button='left', clicks=2)
        if action_type == 'right_single':
            return self._execute_click(action_inputs, button='right', clicks=1)
        if action_type == 'hover':
            return self._execute_hover(action_inputs)
        if action_type == 'drag':
            return self._execute_drag(action_inputs)
        if action_type == 'hotkey':
            return self._execute_hotkey(action_inputs)
        if action_type in ['press', 'keydown']:
            return self._execute_key_press(action_inputs, 'down')
        if action_type in ['release', 'keyup']:
            return self._execute_key_press(action_inputs, 'up')
        if action_type == 'type':
            return self._execute_type(action_inputs)
        if action_type == 'scroll':
            return self._execute_scroll(action_inputs)
        if action_type == 'wait':
            return self._execute_wait(action_inputs)
        if action_type == 'finished':
            return self._execute_finished(action_inputs)

        result = f"未知动作类型: {action_type}"
        if self.verbose:
            print(f"  [错误] {result}")
        return result

    def _convert_coordinates(self, x: float, y: float) -> Tuple[int, int]:
        abs_x = int(round(float(x))) + self.display_offset_x
        abs_y = int(round(float(y))) + self.display_offset_y
        return abs_x, abs_y

    def _get_coordinates_from_box(self, box: Any) -> Tuple[int, int]:
        if isinstance(box, str):
            box = self._parse_coordinate_string(box)

        if isinstance(box, (list, tuple)):
            if len(box) == 2:
                return self._convert_coordinates(box[0], box[1])
            if len(box) == 4:
                x1, y1, x2, y2 = box
                x = (float(x1) + float(x2)) / 2
                y = (float(y1) + float(y2)) / 2
                return self._convert_coordinates(x, y)

        raise ValueError(f"无法解析坐标: {box}")

    def _parse_coordinate_string(
        self,
        coordinate_text: str,
    ) -> Union[List[float], Tuple[float, float]]:
        stripped = coordinate_text.strip()
        pair_match = re.fullmatch(
            r'[\[(]?\s*(-?(?:\d+(?:\.\d+)?|\.\d+))[\s,]+(-?(?:\d+(?:\.\d+)?|\.\d+))\s*[\])]?',
            stripped,
        )
        if pair_match:
            return [float(pair_match.group(1)), float(pair_match.group(2))]

        try:
            parsed = ast.literal_eval(stripped)
        except (SyntaxError, ValueError):
            raise ValueError(f"无法解析坐标: {coordinate_text}")

        if isinstance(parsed, (list, tuple)):
            return parsed

        raise ValueError(f"无法解析坐标: {coordinate_text}")

    def _execute_click(
        self,
        action_inputs: Dict[str, Any],
        button: str = 'left',
        clicks: int = 1,
    ) -> str:
        point = action_inputs.get('point')
        if point is None:
            point = action_inputs.get('start_box')

        if point is None:
            x = action_inputs.get('x')
            y = action_inputs.get('y')
            if x is None or y is None:
                raise ValueError("点击操作需要 point 或 x, y 参数")
            abs_x, abs_y = self._convert_coordinates(x, y)
        else:
            abs_x, abs_y = self._get_coordinates_from_box(point)

        if clicks == 2:
            pyautogui.click(
                abs_x,
                abs_y,
                button=button,
                clicks=2,
                interval=DOUBLE_CLICK_INTERVAL,
            )
            action_name = '双击'
        else:
            pyautogui.click(abs_x, abs_y, button=button, clicks=clicks)
            action_name = '单击' if button == 'left' else '右击'

        result = f"{action_name} ({abs_x}, {abs_y})"
        if self.verbose:
            print(f"  [完成] {result}")
        return result

    def _execute_hover(self, action_inputs: Dict[str, Any]) -> str:
        point = action_inputs.get('point')
        if point is None:
            point = action_inputs.get('start_box')

        if point is None:
            x = action_inputs.get('x')
            y = action_inputs.get('y')
            if x is None or y is None:
                raise ValueError("悬停操作需要 point 或 x, y 参数")
            abs_x, abs_y = self._convert_coordinates(x, y)
        else:
            abs_x, abs_y = self._get_coordinates_from_box(point)

        pyautogui.moveTo(abs_x, abs_y)
        result = f"悬停 ({abs_x}, {abs_y})"
        if self.verbose:
            print(f"  [完成] {result}")
        return result

    def _execute_drag(self, action_inputs: Dict[str, Any]) -> str:
        start_point = action_inputs.get('start_point')
        end_point = action_inputs.get('end_point')
        if start_point is None:
            start_point = action_inputs.get('start_box')
        if end_point is None:
            end_point = action_inputs.get('end_box')
        if start_point is None or end_point is None:
            raise ValueError("拖拽操作需要 start_point 和 end_point 参数")

        start_x, start_y = self._get_coordinates_from_box(start_point)
        end_x, end_y = self._get_coordinates_from_box(end_point)

        pyautogui.moveTo(start_x, start_y)
        pyautogui.dragTo(end_x, end_y, duration=0.5, button='left')

        result = f"拖拽 ({start_x}, {start_y}) -> ({end_x}, {end_y})"
        if self.verbose:
            print(f"  [完成] {result}")
        return result

    def _execute_hotkey(self, action_inputs: Dict[str, Any]) -> str:
        hotkey = action_inputs.get('hotkey') or action_inputs.get('key', '')
        if not hotkey:
            raise ValueError("热键操作需要 hotkey 或 key 参数")

        convert_keys = self._normalize_hotkey_keys(hotkey)
        pyautogui.hotkey(*convert_keys)

        result = f"热键: {' + '.join(convert_keys)}"
        if self.verbose:
            print(f"  [完成] {result}")
        return result

    def _execute_key_press(
        self,
        action_inputs: Dict[str, Any],
        press_type: str = 'down',
    ) -> str:
        key = action_inputs.get('key') or action_inputs.get('press', '')
        if not key:
            raise ValueError("按键操作需要 key 或 press 参数")

        key = self._normalize_key(key)
        if press_type == 'down':
            pyautogui.keyDown(key)
            action_name = '按下'
        else:
            pyautogui.keyUp(key)
            action_name = '释放'

        result = f"{action_name}按键: {key}"
        if self.verbose:
            print(f"  [完成] {result}")
        return result

    def _execute_type(self, action_inputs: Dict[str, Any]) -> str:
        content = action_inputs.get('content', '')
        content = content.replace("\\'", "'").replace('\\"', '"').replace('\\n', '\n')
        if not content:
            raise ValueError("文本输入操作需要 content 参数")

        need_submit = content.endswith('\n')
        if need_submit:
            content = content[:-1]

        if self._should_use_clipboard_input(content):
            try:
                import pyperclip
                pyperclip.copy(content)
                pyautogui.hotkey(*self._get_paste_hotkey())
                time.sleep(0.3)
                result = f"输入文本(剪贴板): {content[:50]}{'...' if len(content) > 50 else ''}"
            except ImportError:
                pyautogui.write(content, interval=0.01)
                result = f"输入文本: {content[:50]}{'...' if len(content) > 50 else ''}"
        else:
            pyautogui.write(content, interval=0.01)
            result = f"输入文本: {content[:50]}{'...' if len(content) > 50 else ''}"

        if need_submit:
            pyautogui.press('enter')
            result += ' + 回车'

        if self.verbose:
            print(f"  [完成] {result}")
        return result

    def _execute_scroll(self, action_inputs: Dict[str, Any]) -> str:
        direction = str(action_inputs.get('direction', 'down')).lower()
        steps = int(abs(float(action_inputs.get('steps', 50))))
        point = action_inputs.get('point') or action_inputs.get('start_box')
        if point is not None:
            abs_x, abs_y = self._get_coordinates_from_box(point)
            pyautogui.moveTo(abs_x, abs_y)
        else:
            abs_x = abs_y = None

        amount = steps if direction == 'down' else -steps
        pyautogui.scroll(amount)

        result = f"滚动{direction} {steps}步"
        if abs_x is not None and abs_y is not None:
            result += f": ({abs_x}, {abs_y})"
        if self.verbose:
            print(f"  [完成] {result}")
        return result

    def _execute_wait(self, action_inputs: Dict[str, Any]) -> str:
        seconds = float(action_inputs.get('seconds', 3))
        seconds = max(1.0, min(60.0, seconds))
        time.sleep(seconds)
        seconds_text = int(seconds) if seconds.is_integer() else seconds
        result = f"等待 {seconds_text} 秒"
        if self.verbose:
            print(f"  [完成] {result}")
        return result

    def _execute_finished(self, action_inputs: Dict[str, Any]) -> str:
        return action_inputs.get('content', '任务已完成')

    def _normalize_hotkey_keys(self, hotkey: str) -> List[str]:
        keys = []
        for raw in str(hotkey).replace('+', ' ').split():
            normalized = self._normalize_key(raw)
            if normalized:
                keys.append(normalized)
        return keys

    def _normalize_key(self, key: str) -> str:
        normalized = str(key).strip().lower()
        aliases = {
            'cmd': 'command',
            'return': 'enter',
            'esc': 'escape',
            'space': 'space',
        }
        return aliases.get(normalized, normalized)

    def _get_paste_hotkey(self) -> Tuple[str, str]:
        return ('command', 'v') if sys.platform == 'darwin' else ('ctrl', 'v')

    def _should_use_clipboard_input(self, content: str) -> bool:
        if not self.input_swap:
            return False
        if len(content) > 1:
            return True
        return any(ord(char) > 127 for char in content)
