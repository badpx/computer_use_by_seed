"""
动作执行器模块
基于 parse.py 重构，支持所有动作类型的执行
"""

import time
from typing import Dict, Any, List, Union

import pyautogui


class ActionExecutor:
    """动作执行器"""
    
    def __init__(
        self,
        image_width: int,
        image_height: int,
        scale_factor: int = 1000,
        verbose: bool = True,
        input_swap: bool = True
    ):
        """
        初始化执行器
        
        Args:
            image_width: 截图宽度
            image_height: 截图高度
            scale_factor: 坐标缩放比例
            verbose: 是否打印详细日志
            input_swap: 是否使用剪贴板输入长文本
        """
        self.image_width = image_width
        self.image_height = image_height
        self.scale_factor = scale_factor
        self.verbose = verbose
        self.input_swap = input_swap
        
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
    
    def _convert_coordinates(self, x: int, y: int) -> Tuple[int, int]:
        """
        将相对坐标转换为绝对屏幕坐标
        
        Args:
            x: 相对 X 坐标 (0-scale_factor)
            y: 相对 Y 坐标 (0-scale_factor)
            
        Returns:
            Tuple[int, int]: 绝对屏幕坐标
        """
        abs_x = int(int(x) / self.scale_factor * self.image_width)
        abs_y = int(int(y) / self.scale_factor * self.image_height)
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
                x = (x1 + x2) // 2
                y = (y1 + y2) // 2
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
            pyautogui.doubleClick(abs_x, abs_y, button=button)
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
        
        # 转换按键名称
        hotkey = self._normalize_key(hotkey)
        
        # 分割多个按键
        keys = hotkey.split()
        
        # 转换特殊按键
        convert_keys = []
        for key in keys:
            key = self._normalize_key(key)
            convert_keys.append(key)
        
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
                pyautogui.hotkey('ctrl', 'v')
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
        
        # 确定滚动方向和次数
        scroll_amount = 5
        if 'up' in direction or 'left' in direction:
            scroll_amount = -scroll_amount
        
        if start_box is not None:
            # 在指定位置滚动
            x, y = self._get_coordinates_from_box(start_box)
            pyautogui.scroll(scroll_amount, x=x, y=y)
            result = f"滚动{direction}: ({x}, {y})"
        else:
            # 在当前位置滚动
            pyautogui.scroll(scroll_amount)
            result = f"滚动{direction}"
        
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
    
    def _normalize_key(self, key: str) -> str:
        """标准化按键名称"""
        key = key.lower().strip()
        
        # 转换箭头键
        key_map = {
            'arrowleft': 'left',
            'arrowright': 'right',
            'arrowup': 'up',
            'arrowdown': 'down',
            'space': ' ',
        }
        
        return key_map.get(key, key)


def execute_action(
    action: Dict[str, Any],
    image_width: int,
    image_height: int,
    scale_factor: int = 1000,
    verbose: bool = True
) -> Union[str, List[str]]:
    """
    便捷函数：执行动作
    
    Args:
        action: 动作字典
        image_width: 图片宽度
        image_height: 图片高度
        scale_factor: 坐标缩放比例
        verbose: 是否打印详细日志
        
    Returns:
        Union[str, List[str]]: 执行结果
    """
    executor = ActionExecutor(
        image_width=image_width,
        image_height=image_height,
        scale_factor=scale_factor,
        verbose=verbose
    )
    return executor.execute(action)
