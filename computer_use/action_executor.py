"""
动作执行器模块
基于 parse.py 重构，支持所有动作类型的执行
"""

import re
import sys
import time
from typing import Dict, Any, List, Optional, Tuple, Union

import pyautogui

from .config import config, normalize_coordinate_space

DOUBLE_CLICK_INTERVAL = 0.12


class ActionExecutor:
    """动作执行器"""
    
    def __init__(
        self,
        image_width: int,
        image_height: int,
        model_image_width: Optional[int] = None,
        model_image_height: Optional[int] = None,
        coordinate_space: str = 'relative',
        coordinate_scale: float = 1000,
        verbose: bool = True,
        input_swap: bool = True,
        natural_scroll: Optional[bool] = None
    ):
        """
        初始化执行器
        
        Args:
            image_width: 真实屏幕截图宽度
            image_height: 真实屏幕截图高度
            model_image_width: 传给模型的截图宽度
            model_image_height: 传给模型的截图高度
            coordinate_space: 坐标空间，relative / pixel
            coordinate_scale: 相对坐标量程
            verbose: 是否打印详细日志
            input_swap: 是否使用剪贴板输入长文本
            natural_scroll: 是否使用自然滚动方向
        """
        self.image_width = image_width
        self.image_height = image_height
        self.model_image_width = model_image_width or image_width
        self.model_image_height = model_image_height or image_height
        self.coordinate_space = normalize_coordinate_space(coordinate_space)
        self.coordinate_scale = float(coordinate_scale)
        if self.coordinate_scale <= 0:
            raise ValueError("coordinate_scale 必须大于 0")
        self.verbose = verbose
        self.input_swap = input_swap
        self.natural_scroll = (
            config.natural_scroll if natural_scroll is None else natural_scroll
        )
        
        # 配置 pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.1
    
    def execute(self, action: Dict[str, Any]) -> Union[str, List[str]]:
        """
        执行动作
        
        Args:
            action: 动作字典，包含 action_type 和 action_inputs
            
        Returns:
            Union[str, List[str]]: 执行结果
        """
        action_type = action.get('action_type', '').lower()
        action_inputs = action.get('action_inputs', {})
        
        if self.verbose:
            print(f"\n[执行动作] {action_type}")
            print(f"  参数: {action_inputs}")
        
        # 根据动作类型执行对应操作
        if action_type in ['click', 'left_single']:
            return self._execute_click(action_inputs, button='left', clicks=1)
        
        elif action_type == 'left_double':
            return self._execute_click(action_inputs, button='left', clicks=2)
        
        elif action_type == 'right_single':
            return self._execute_click(action_inputs, button='right', clicks=1)
        
        elif action_type == 'hover':
            return self._execute_hover(action_inputs)
        
        elif action_type == 'drag':
            return self._execute_drag(action_inputs)
        
        elif action_type == 'hotkey':
            return self._execute_hotkey(action_inputs)
        
        elif action_type in ['press', 'keydown']:
            return self._execute_key_press(action_inputs, 'down')
        
        elif action_type in ['release', 'keyup']:
            return self._execute_key_press(action_inputs, 'up')
        
        elif action_type == 'type':
            return self._execute_type(action_inputs)
        
        elif action_type == 'scroll':
            return self._execute_scroll(action_inputs)
        
        elif action_type == 'wait':
            return self._execute_wait()
        
        elif action_type == 'finished':
            return self._execute_finished(action_inputs)
        
        else:
            result = f"未知动作类型: {action_type}"
            if self.verbose:
                print(f"  [错误] {result}")
            return result
    
    def _convert_coordinates(self, x: float, y: float) -> Tuple[int, int]:
        """
        将模型坐标转换为绝对屏幕坐标
        
        Args:
            x: 模型 X 坐标
            y: 模型 Y 坐标
            
        Returns:
            Tuple[int, int]: 绝对屏幕坐标
        """
        x = float(x)
        y = float(y)
        if self.coordinate_space == 'pixel':
            abs_x = int(round(x / self.model_image_width * self.image_width))
            abs_y = int(round(y / self.model_image_height * self.image_height))
        else:
            abs_x = int(round(x / self.coordinate_scale * self.image_width))
            abs_y = int(round(y / self.coordinate_scale * self.image_height))
        return abs_x, abs_y
    
    def _get_coordinates_from_box(self, box: any) -> Tuple[int, int]:
        """
        从 box 参数中提取坐标
        
        Args:
            box: 坐标信息，可以是列表、元组或字符串
            
        Returns:
            Tuple[int, int]: 坐标
        """
        if isinstance(box, str):
            box = eval(box)
        
        if isinstance(box, (list, tuple)):
            if len(box) == 2:
                x, y = box
                return self._convert_coordinates(x, y)
            elif len(box) == 4:
                # 如果是 bbox (x1, y1, x2, y2)，取中心点
                x1, y1, x2, y2 = box
                x = (float(x1) + float(x2)) / 2
                y = (float(y1) + float(y2)) / 2
                return self._convert_coordinates(x, y)
        
        raise ValueError(f"无法解析坐标: {box}")
    
    def _execute_click(
        self,
        action_inputs: Dict[str, Any],
        button: str = 'left',
        clicks: int = 1
    ) -> str:
        """执行点击操作"""
        start_box = action_inputs.get('start_box')
        
        if start_box is None:
            # 尝试直接获取 x, y
            x = action_inputs.get('x')
            y = action_inputs.get('y')
            if x is None or y is None:
                raise ValueError("点击操作需要 start_box 或 x, y 参数")
            abs_x, abs_y = self._convert_coordinates(x, y)
        else:
            abs_x, abs_y = self._get_coordinates_from_box(start_box)
        
        # 执行点击
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
        """执行悬停操作"""
        start_box = action_inputs.get('start_box')
        
        if start_box is None:
            x = action_inputs.get('x')
            y = action_inputs.get('y')
            if x is None or y is None:
                raise ValueError("悬停操作需要 start_box 或 x, y 参数")
            abs_x, abs_y = self._convert_coordinates(x, y)
        else:
            abs_x, abs_y = self._get_coordinates_from_box(start_box)
        
        pyautogui.moveTo(abs_x, abs_y)
        
        result = f"悬停 ({abs_x}, {abs_y})"
        if self.verbose:
            print(f"  [完成] {result}")
        return result
    
    def _execute_drag(self, action_inputs: Dict[str, Any]) -> str:
        """执行拖拽操作"""
        start_box = action_inputs.get('start_box')
        end_box = action_inputs.get('end_box')
        
        if start_box is None or end_box is None:
            raise ValueError("拖拽操作需要 start_box 和 end_box 参数")
        
        start_x, start_y = self._get_coordinates_from_box(start_box)
        end_x, end_y = self._get_coordinates_from_box(end_box)
        
        # 执行拖拽
        pyautogui.moveTo(start_x, start_y)
        pyautogui.dragTo(end_x, end_y, duration=0.5)
        
        result = f"拖拽 ({start_x}, {start_y}) -> ({end_x}, {end_y})"
        if self.verbose:
            print(f"  [完成] {result}")
        return result
    
    def _execute_hotkey(self, action_inputs: Dict[str, Any]) -> str:
        """执行热键操作"""
        # 支持 hotkey 或 key 参数
        hotkey = action_inputs.get('hotkey') or action_inputs.get('key', '')
        
        if not hotkey:
            raise ValueError("热键操作需要 hotkey 或 key 参数")

        convert_keys = self._normalize_hotkey_keys(hotkey)
        
        # 执行热键
        pyautogui.hotkey(*convert_keys)
        
        result = f"热键: {' + '.join(convert_keys)}"
        if self.verbose:
            print(f"  [完成] {result}")
        return result
    
    def _execute_key_press(
        self,
        action_inputs: Dict[str, Any],
        press_type: str = 'down'
    ) -> str:
        """执行按键按下/释放操作"""
        key = action_inputs.get('key') or action_inputs.get('press', '')
        
        if not key:
            raise ValueError(f"按键操作需要 key 或 press 参数")
        
        # 转换按键名称
        key = self._normalize_key(key)
        
        # 执行按键操作
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
        """执行文本输入操作"""
        content = action_inputs.get('content', '')
        
        # 转义字符处理
        content = content.replace("\\'", "'").replace('\\"', '"').replace('\\n', '\n')
        
        if not content:
            raise ValueError("文本输入操作需要 content 参数")
        
        # 检查是否需要提交（以换行符结尾）
        need_submit = content.endswith('\n')
        if need_submit:
            content = content[:-1]
        
        # 根据输入方式选择输入方法
        if self.input_swap and len(content) > 1:
            # 使用剪贴板输入长文本
            try:
                import pyperclip
                pyperclip.copy(content)
                pyautogui.hotkey(*self._get_paste_hotkey())
                time.sleep(0.3)
                result = f"输入文本(剪贴板): {content[:50]}{'...' if len(content) > 50 else ''}"
            except ImportError:
                # 如果没有 pyperclip，直接输入
                pyautogui.write(content, interval=0.01)
                result = f"输入文本: {content[:50]}{'...' if len(content) > 50 else ''}"
        else:
            # 直接输入文本
            pyautogui.write(content, interval=0.01)
            result = f"输入文本: {content[:50]}{'...' if len(content) > 50 else ''}"
        
        # 如果需要提交，按回车键
        if need_submit:
            pyautogui.press('enter')
            result += " [已提交]"
        
        if self.verbose:
            print(f"  [完成] {result}")
        return result
    
    def _execute_scroll(self, action_inputs: Dict[str, Any]) -> str:
        """执行滚动操作"""
        start_box = action_inputs.get('start_box')
        direction = action_inputs.get('direction', 'down').lower()
        steps = action_inputs.get('steps', 50)
        
        # 确定滚动方向和次数
        scroll_amount = int(abs(float(steps)))
        reverse_direction = 'up' in direction or 'left' in direction
        if self.natural_scroll:
            scroll_amount = scroll_amount if reverse_direction else -scroll_amount
        else:
            scroll_amount = -scroll_amount if reverse_direction else scroll_amount
        
        if start_box is not None:
            # 在指定位置滚动
            x, y = self._get_coordinates_from_box(start_box)
            pyautogui.moveTo(x, y)
            pyautogui.scroll(scroll_amount)
            result = f"滚动{direction} {abs(scroll_amount)}步: ({x}, {y})"
        else:
            # 在当前位置滚动
            pyautogui.scroll(scroll_amount)
            result = f"滚动{direction} {abs(scroll_amount)}步"
        
        if self.verbose:
            print(f"  [完成] {result}")
        return result
    
    def _execute_wait(self) -> str:
        """执行等待操作"""
        wait_time = 5
        time.sleep(wait_time)
        result = f"等待 {wait_time} 秒"
        if self.verbose:
            print(f"  [完成] {result}")
        return result
    
    def _execute_finished(self, action_inputs: Dict[str, Any]) -> str:
        """执行完成操作"""
        content = action_inputs.get('content', '')
        result = f"任务完成: {content}"
        if self.verbose:
            print(f"  [完成] {result}")
        return "DONE"

    def _normalize_hotkey_keys(self, hotkey: str) -> List[str]:
        """将热键字符串标准化为 pyautogui 可识别的按键序列。"""
        raw_keys = re.split(r'\s*\+\s*|\s+', hotkey.strip())
        keys = []

        for raw_key in raw_keys:
            if not raw_key:
                continue
            normalized_key = self._normalize_key(raw_key)
            if normalized_key:
                keys.append(normalized_key)

        if not keys:
            raise ValueError("热键操作未解析出有效按键")

        return keys

    def _get_paste_hotkey(self) -> Tuple[str, str]:
        """根据当前平台返回粘贴快捷键。"""
        if sys.platform == 'darwin':
            return ('command', 'v')
        return ('ctrl', 'v')
    
    def _normalize_key(self, key: str) -> str:
        """标准化按键名称"""
        key = key.lower().strip()
        
        # 转换箭头键
        key_map = {
            'arrowleft': 'left',
            'arrowright': 'right',
            'arrowup': 'up',
            'arrowdown': 'down',
            'cmd': 'command',
            'commandorcontrol': 'command',
            'option': 'alt',
            'return': 'enter',
            'esc': 'escape',
            'spacebar': 'space',
            'space': 'space',
        }
        
        return key_map.get(key, key)


def execute_action(
    action: Dict[str, Any],
    image_width: int,
    image_height: int,
    coordinate_space: str = 'relative',
    coordinate_scale: float = 1000,
    verbose: bool = True
) -> Union[str, List[str]]:
    """
    便捷函数：执行动作
    
    Args:
        action: 动作字典
        image_width: 图片宽度
        image_height: 图片高度
        coordinate_space: 坐标空间
        coordinate_scale: 相对坐标量程
        verbose: 是否打印详细日志
        
    Returns:
        Union[str, List[str]]: 执行结果
    """
    executor = ActionExecutor(
        image_width=image_width,
        image_height=image_height,
        coordinate_space=coordinate_space,
        coordinate_scale=coordinate_scale,
        verbose=verbose
    )
    return executor.execute(action)
