"""
动作解析器模块
解析模型输出的 Thought 和 Action
"""

import re
from typing import Dict, Any, Tuple, Optional

NUMBER_PATTERN = r"-?(?:\d+(?:\.\d+)?|\.\d+)"


class ActionParser:
    """动作解析器"""
    
    # 动作类型映射
    ACTION_TYPES = [
        'click',
        'left_double',
        'right_single',
        'drag',
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
        # 提取 Thought
        thought = self._extract_thought(response)
        
        # 提取 Action
        action_str = self._extract_action(response)
        
        # 解析动作
        action_type, action_inputs = self._parse_action(action_str)
        
        return {
            'thought': thought,
            'action_type': action_type,
            'action_inputs': action_inputs,
            'raw_response': response,
            'action_str': action_str
        }
    
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
        
        # 如果没有匹配到 Action: 标记，尝试直接解析动作
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
                
                # 处理 point 标记
                if '<point>' in value and '</point>' in value:
                    point_match = re.search(
                        rf'<point>({NUMBER_PATTERN})\s+({NUMBER_PATTERN})</point>',
                        value,
                    )
                    if point_match:
                        value = [
                            float(point_match.group(1)),
                            float(point_match.group(2)),
                        ]
                        params['start_box'] = value
                        continue
                
                # 处理 start_point/end_point
                if '<start_point>' in value or '<end_point>' in value:
                    point_match = re.search(
                        rf'<(?:start|end)_point>({NUMBER_PATTERN})\s+({NUMBER_PATTERN})</(?:start|end)_point>',
                        value,
                    )
                    if point_match:
                        value = [
                            float(point_match.group(1)),
                            float(point_match.group(2)),
                        ]
                        if key == 'start_point':
                            params['start_box'] = value
                            continue
                        if key == 'end_point':
                            params['end_box'] = value
                            continue

                if key in {'x', 'y', 'steps'}:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
                
                params[key] = value
        
        return params
    
    def _split_params(self, params_str: str) -> list:
        """
        分割参数字符串，正确处理引号内的逗号
        """
        params = []
        current = ''
        in_quote = None
        
        for char in params_str:
            if char in '"\'':
                if in_quote is None:
                    in_quote = char
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
