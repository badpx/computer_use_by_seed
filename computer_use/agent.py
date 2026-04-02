"""
核心代理模块
多轮自动执行直到任务完成
"""

import time
import base64
from typing import Dict, Any, List, Optional, Generator
from pathlib import Path

from volcenginesdkarkruntime import Ark

from .config import config
from .screenshot import screenshot_manager, capture_screenshot
from .action_parser import parse_action
from .action_executor import ActionExecutor
from .prompts import COMPUTER_USE_DOUBAO


class ComputerUseAgent:
    """
    Computer Use 代理
    支持多轮自动执行直到任务完成
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        max_steps: Optional[int] = None,
        language: str = 'Chinese',
        verbose: bool = True
    ):
        """
        初始化代理
        
        Args:
            model: 模型名称，默认从配置读取
            api_key: API密钥，默认从配置读取
            base_url: API基础URL，默认从配置读取
            temperature: 温度参数，默认从配置读取
            max_steps: 最大执行步数，默认从配置读取
            language: 提示词语言
            verbose: 是否打印详细日志
        """
        # 配置参数
        self.model = model or config.model
        self.api_key = api_key or config.api_key
        self.base_url = base_url or config.base_url
        self.temperature = temperature if temperature is not None else config.temperature
        self.max_steps = max_steps if max_steps is not None else config.max_steps
        self.language = language
        self.verbose = verbose
        
        # 初始化客户端
        self.client = Ark(
            base_url=self.base_url,
            api_key=self.api_key
        )
        
        # 执行历史
        self.history: List[Dict[str, Any]] = []
        
        # 当前步骤
        self.current_step = 0
        
        if self.verbose:
            print(f"[初始化] Computer Use Agent")
            print(f"  模型: {self.model}")
            print(f"  最大步数: {self.max_steps}")
            print(f"  语言: {self.language}")
    
    def run(self, instruction: str) -> Dict[str, Any]:
        """
        执行任务
        
        Args:
            instruction: 任务指令
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"[开始任务] {instruction}")
            print(f"{'='*60}")
        
        result = {
            'success': False,
            'instruction': instruction,
            'steps': [],
            'error': None,
            'final_response': None
        }
        
        try:
            # 多轮执行循环
            for step in range(self.max_steps):
                self.current_step = step + 1
                
                if self.verbose:
                    print(f"\n[步骤 {self.current_step}/{self.max_steps}]")
                
                # 1. 截图
                screenshot, screenshot_path = capture_screenshot()
                img_width, img_height = screenshot.size
                
                if self.verbose and screenshot_path:
                    print(f"  截图: {screenshot_path}")
                
                # 2. 调用模型
                response = self._call_model(
                    instruction=instruction,
                    screenshot=screenshot,
                    img_width=img_width,
                    img_height=img_height
                )
                
                if self.verbose:
                    print(f"  模型响应:\n{response}")
                
                # 3. 解析动作
                action = parse_action(response)
                
                if self.verbose:
                    print(f"  解析结果: {action['action_type']}")
                
                # 记录步骤
                step_record = {
                    'step': self.current_step,
                    'screenshot': screenshot_path,
                    'response': response,
                    'action': action
                }
                result['steps'].append(step_record)
                
                # 4. 检查是否完成
                if action['action_type'] == 'finished':
                    result['success'] = True
                    result['final_response'] = action['action_inputs'].get('content', '')
                    
                    if self.verbose:
                        print(f"\n{'='*60}")
                        print(f"[任务完成] {result['final_response']}")
                        print(f"{'='*60}")
                    break
                
                # 5. 执行动作
                executor = ActionExecutor(
                    image_width=img_width,
                    image_height=img_height,
                    scale_factor=config.coordinate_scale,
                    verbose=self.verbose
                )
                
                exec_result = executor.execute(action)
                
                if exec_result == 'DONE':
                    result['success'] = True
                    if self.verbose:
                        print(f"\n{'='*60}")
                        print(f"[任务完成]")
                        print(f"{'='*60}")
                    break
                
                # 等待一小段时间，让操作生效
                time.sleep(0.5)
            
            else:
                # 达到最大步数
                result['error'] = f"达到最大步数限制 ({self.max_steps})"
                if self.verbose:
                    print(f"\n[警告] 达到最大步数限制")
        
        except Exception as e:
            result['error'] = str(e)
            if self.verbose:
                print(f"\n[错误] {e}")
                import traceback
                traceback.print_exc()
        
        return result
    
    def _call_model(
        self,
        instruction: str,
        screenshot,
        img_width: int,
        img_height: int
    ) -> str:
        """
        调用模型进行推理
        
        Args:
            instruction: 任务指令
            screenshot: 截图对象
            img_width: 截图宽度
            img_height: 截图高度
            
        Returns:
            str: 模型响应
        """
        # 编码截图
        import io
        import base64
        
        img_buffer = io.BytesIO()
        screenshot.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        base64_image = base64.b64encode(img_buffer.read()).decode('utf-8')
        
        # 构建系统提示词
        system_prompt = COMPUTER_USE_DOUBAO.format(
            instruction=instruction,
            language=self.language
        )
        
        # 构建消息
        messages = [
            {
                'role': 'user',
                'content': system_prompt
            },
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': f'data:image/png;base64,{base64_image}'
                        }
                    }
                ]
            }
        ]
        
        # 调用模型
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature
        )
        
        return response.choices[0].message.content
