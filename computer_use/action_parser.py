"""
动作解析器模块
解析模型输出的 Thought 和 Action
"""

import json
import re
from typing import Dict, Any, Tuple, Optional, List

NUMBER_PATTERN = r"-?(?:\d+(?:\.\d+)?|\.\d+)"
NUMERIC_PARAM_KEYS = {'x', 'y', 'steps', 'seconds', 'duration', 'time', 'wait_time'}


class ActionParser:
    """动作解析器"""
    
    # 动作类型映射
    ACTION_TYPES = [
        'click',
        'left_double',
        'right_single',
        'drag',
        'swipe',
        'long_press',
        'open_app',
        'press_home',
        'press_back',
        'hotkey',
        'type',
        'scroll',
        'wait',
        'finished',
        'left_single',
    ]
    
    def __init__(self, coordinate_scale: int = 1000):
        """
        初始化解析器
        
        Args:
            coordinate_scale: 坐标缩放比例，默认1000
        """
        self.coordinate_scale = coordinate_scale
    
    def parse(self, response: str) -> Dict[str, Any]:
        """
        解析模型响应
        
        Args:
            response: 模型响应文本
            
        Returns:
            Dict[str, Any]: 解析结果，包含 thought, action_type, action_inputs
            
        Raises:
            ValueError: 当无法解析响应时
        """
        return self.parse_many(response)[0]

    def parse_many(self, response: str) -> List[Dict[str, Any]]:
        """
        解析模型响应中的一个或多个动作。

        Args:
            response: 模型响应文本

        Returns:
            List[Dict[str, Any]]: 解析结果列表

        Raises:
            ValueError: 当无法解析任何动作时
        """
        thought = self._extract_thought(response)

        function_call_actions = self._parse_function_call_wrapper(response, thought)
        if function_call_actions:
            return function_call_actions

        action_block = self._extract_action(response)
        action_calls = self._extract_action_calls(action_block)
        if not action_calls:
            raise ValueError(f"无法解析动作: {action_block}")

        actions = []
        for action_str in action_calls:
            action_type, action_inputs = self._parse_action(action_str)
            actions.append(
                {
                    'thought': thought,
                    'action_type': action_type,
                    'action_inputs': action_inputs,
                    'raw_response': response,
                    'action_str': action_str,
                }
            )
        return actions
    
    def _extract_thought(self, response: str) -> str:
        """提取 Thought 部分"""
        # 匹配 Thought: ... Action: 格式
        thought_match = re.search(
            r'Thought:\s*(.+?)(?=\n\s*Action:|$)',
            response,
            re.DOTALL | re.IGNORECASE
        )
        
        if thought_match:
            return thought_match.group(1).strip()
        
        # 如果没有匹配到，返回空字符串
        return ''
    
    def _extract_action(self, response: str) -> str:
        """提取 Action 部分"""
        # 匹配 Action: ... 格式
        action_match = re.search(
            r'Action:\s*(.+?)(?=\n\s*Thought:|$)',
            response,
            re.DOTALL | re.IGNORECASE
        )
        
        if action_match:
            return action_match.group(1).strip()

        # 如果没有匹配到 Action: 标记，尝试从整段文本中提取最后一个合法动作
        extracted_action = self._extract_last_action_call(response)
        if extracted_action:
            return extracted_action

        return response.strip()
    
    def _parse_action(self, action_str: str) -> Tuple[str, Dict[str, Any]]:
        """
        解析动作字符串
        
        Args:
            action_str: 动作字符串，如 "click(point='<point>100 200</point>')"
            
        Returns:
            Tuple[str, Dict]: (动作类型, 动作参数)
        """
        action_str = action_str.strip()
        
        # 匹配动作类型和参数
        match = re.match(r'(\w+)\s*\((.*)\)', action_str)
        
        if not match:
            # 尝试匹配无参数动作，如 wait()
            if action_str.endswith('()'):
                action_type = action_str[:-2].strip()
                return action_type, {}
            raise ValueError(f"无法解析动作: {action_str}")
        
        action_type = match.group(1).lower()
        params_str = match.group(2)
        
        # 解析参数
        action_inputs = self._parse_params(params_str)
        
        return action_type, action_inputs

    def _parse_function_call_wrapper(
        self,
        response: str,
        thought: str,
    ) -> List[Dict[str, Any]]:
        """解析 <|FunctionCallBegin|> 包装的一个或多个函数调用。"""
        wrapper_match = re.search(
            r'<\|FunctionCallBegin\|>(.+?)<\|FunctionCallEnd\|>',
            response,
            re.DOTALL,
        )
        if not wrapper_match:
            return []

        payload_text = wrapper_match.group(1).strip()
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"无法解析 function call JSON: {exc}") from exc

        calls = payload if isinstance(payload, list) else [payload]
        actions = []
        for call in calls:
            if not isinstance(call, dict):
                continue
            name = str(call.get('name') or '').strip()
            parameters = call.get('parameters', {})
            if not name:
                continue
            if isinstance(parameters, str):
                try:
                    parameters = json.loads(parameters)
                except json.JSONDecodeError:
                    parameters = {}
            if not isinstance(parameters, dict):
                parameters = {}

            action_str = self._format_function_call_action(name, parameters)
            action_type, action_inputs = self._parse_action(action_str)
            actions.append(
                {
                    'thought': thought,
                    'action_type': action_type,
                    'action_inputs': action_inputs,
                    'raw_response': response,
                    'action_str': action_str,
                }
            )
        return actions

    def _format_function_call_action(self, name: str, parameters: Dict[str, Any]) -> str:
        """将 function-call payload 格式化为普通动作调用，复用参数解析逻辑。"""
        if not parameters:
            return f'{name}()'
        params = ', '.join(
            f'{key}={repr(value)}'
            for key, value in parameters.items()
        )
        return f'{name}({params})'

    def _extract_action_calls(self, text: str) -> List[str]:
        """从文本中按顺序提取所有括号平衡的合法动作调用。"""
        action_pattern = '|'.join(re.escape(action) for action in self.ACTION_TYPES)
        calls = []
        for match in re.finditer(rf'\b(?:{action_pattern})\s*\(', text, re.IGNORECASE):
            if self._is_inside_quote(text, match.start()):
                continue
            action_call = self._extract_balanced_call(text, match.start())
            if action_call:
                calls.append(action_call.strip())
        return calls

    def _extract_last_action_call(self, response: str) -> Optional[str]:
        """从自然语言响应中提取最后一个动作调用。"""
        action_calls = self._extract_action_calls(response)
        return action_calls[-1] if action_calls else None

    def _extract_balanced_call(self, text: str, start_index: int) -> Optional[str]:
        """从指定位置开始提取括号平衡的动作调用。"""
        in_quote = None
        escaped = False
        depth = 0

        for index in range(start_index, len(text)):
            char = text[index]
            if in_quote is not None:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif self._is_in_word_apostrophe(text, index, in_quote):
                    pass
                elif char == in_quote:
                    in_quote = None
                continue

            if char in {'"', "'"}:
                in_quote = char
                continue

            if char == '(':
                depth += 1
                continue

            if char == ')':
                depth -= 1
                if depth == 0:
                    return text[start_index:index + 1]

        return None

    def _is_inside_quote(self, text: str, target_index: int) -> bool:
        """判断指定位置是否处于引号内部。"""
        in_quote = None
        escaped = False

        for index, char in enumerate(text[:target_index]):
            if in_quote is not None:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif self._is_in_word_apostrophe(text, index, in_quote):
                    pass
                elif char == in_quote:
                    in_quote = None
                continue

            if char in {'"', "'"}:
                in_quote = char

        return in_quote is not None
    
    def _parse_params(self, params_str: str) -> Dict[str, Any]:
        """
        解析参数字符串
        
        Args:
            params_str: 参数字符串，如 "point='<point>100 200</point>'"
            
        Returns:
            Dict[str, Any]: 参数字典
        """
        params = {}
        
        # 简单解析：按逗号分割，但需要考虑引号内的逗号
        param_pairs = self._split_params(params_str)
        
        for pair in param_pairs:
            pair = pair.strip()
            if not pair:
                continue
            
            # 匹配 key=value 格式
            match = re.match(r"(\w+)\s*=\s*(.+)", pair, re.DOTALL)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                
                # 移除引号
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                # 处理 point / start_point / end_point 坐标文本
                if key in {'point', 'start_point', 'end_point'}:
                    allowed_tags = ('point', key) if key != 'point' else ('point',)
                    point_value = self._extract_point_value(
                        value,
                        allowed_tags=allowed_tags,
                    )
                    if point_value is not None:
                        params[key] = point_value
                        continue

                if key in NUMERIC_PARAM_KEYS:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                
                params[key] = value
        
        return params


    def _extract_point_value(
        self,
        value: str,
        allowed_tags: Tuple[str, ...] = ('point',),
    ) -> Optional[list]:
        """从标签文本中提取坐标值。"""
        raw_point = self._extract_plain_point_value(value)
        if raw_point is not None:
            return raw_point

        for tag in allowed_tags:
            point_match = re.search(
                rf'<{tag}>({NUMBER_PATTERN})\s+({NUMBER_PATTERN})</{tag}>',
                value,
            )
            if point_match:
                return [
                    float(point_match.group(1)),
                    float(point_match.group(2)),
                ]
        return None

    def _extract_plain_point_value(self, value: str) -> Optional[list]:
        """从非 XML 标签的坐标文本中提取坐标值。"""
        stripped = value.strip()

        plain_match = re.fullmatch(
            rf'[\[(]?({NUMBER_PATTERN})[\s,]+({NUMBER_PATTERN})[\])]?',
            stripped,
        )
        if plain_match:
            return [
                float(plain_match.group(1)),
                float(plain_match.group(2)),
            ]

        return None
    
    def _split_params(self, params_str: str) -> list:
        """
        分割参数字符串，正确处理引号内的逗号
        """
        params = []
        current = ''
        in_quote = None

        for index, char in enumerate(params_str):
            if char in '"\'':
                if in_quote is None:
                    in_quote = char
                elif self._is_in_word_apostrophe(params_str, index, in_quote):
                    pass
                elif in_quote == char:
                    in_quote = None
                current += char
            elif char == ',' and in_quote is None:
                params.append(current)
                current = ''
            else:
                current += char
        
        if current:
            params.append(current)
        
        return params

    @staticmethod
    def _is_in_word_apostrophe(text: str, index: int, in_quote: Optional[str]) -> bool:
        """判断单引号是否只是单词内部的撇号，而不是字符串结束符。"""
        if in_quote != "'" or text[index] != "'":
            return False
        if index <= 0 or index >= len(text) - 1:
            return False
        return text[index - 1].isalnum() and text[index + 1].isalnum()


# 全局解析器实例
action_parser = ActionParser()


def parse_action(response: str) -> Dict[str, Any]:
    """
    便捷函数：解析动作
    
    Args:
        response: 模型响应文本
        
    Returns:
        Dict[str, Any]: 解析结果
    """
    return action_parser.parse(response)


def parse_actions(response: str) -> List[Dict[str, Any]]:
    """
    便捷函数：解析一个或多个动作。

    Args:
        response: 模型响应文本

    Returns:
        List[Dict[str, Any]]: 解析结果列表
    """
    return action_parser.parse_many(response)
