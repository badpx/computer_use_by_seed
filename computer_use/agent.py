"""
核心代理模块
多轮自动执行直到任务完成
"""

import io
import time
import base64
from typing import Dict, Any, List, Optional

from volcenginesdkarkruntime import Ark

from .config import config, resolve_thinking_settings
from .screenshot import capture_screenshot
from .action_parser import parse_action
from .action_executor import ActionExecutor
from .logging_utils import ContextLogger
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
        thinking_mode: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        max_steps: Optional[int] = None,
        natural_scroll: Optional[bool] = None,
        save_context_log: Optional[bool] = None,
        context_log_dir: Optional[str] = None,
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
            thinking_mode: 方舟思考模式，enabled / disabled / auto
            reasoning_effort: 方舟思考档位，minimal / low / medium / high
            max_steps: 最大执行步数，默认从配置读取
            natural_scroll: 是否使用自然滚动
            save_context_log: 是否保存上下文日志
            context_log_dir: 上下文日志目录
            language: 提示词语言
            verbose: 是否打印详细日志
        """
        # 配置参数
        self.model = model or config.model
        self.api_key = api_key or config.api_key
        self.base_url = base_url or config.base_url
        self.temperature = temperature if temperature is not None else config.temperature
        reasoning_effort_explicit = (
            reasoning_effort is not None or config.has_explicit_value('REASONING_EFFORT')
        )
        self.requested_thinking_mode = thinking_mode or config.thinking_mode
        self.requested_reasoning_effort = (
            reasoning_effort or config.reasoning_effort
        )
        self.thinking_mode, self.reasoning_effort = resolve_thinking_settings(
            self.requested_thinking_mode,
            self.requested_reasoning_effort,
            reasoning_effort_explicit=reasoning_effort_explicit,
        )
        self.max_steps = max_steps if max_steps is not None else config.max_steps
        self.natural_scroll = (
            natural_scroll if natural_scroll is not None else config.natural_scroll
        )
        self.save_context_log = (
            save_context_log if save_context_log is not None else config.save_context_log
        )
        self.context_log_dir = context_log_dir or config.context_log_dir
        self.language = language
        self.verbose = verbose

        config.validate()

        # 初始化客户端
        self.client = Ark(
            base_url=self.base_url,
            api_key=self.api_key
        )
        
        # 执行历史
        self.history: List[Dict[str, Any]] = []
        self.conversation_messages: List[Dict[str, Any]] = []

        # 上下文日志
        self.context_logger = ContextLogger(
            enabled=self.save_context_log,
            log_dir=self.context_log_dir,
        )

        # 当前步骤
        self.current_step = 0
        
        if self.verbose:
            print(f"[初始化] Computer Use Agent")
            print(f"  模型: {self.model}")
            print(f"  最大步数: {self.max_steps}")
            print(f"  思考模式: {self.thinking_mode}")
            print(f"  思考档位: {self.reasoning_effort}")
            print(f"  自然滚动: {'启用' if self.natural_scroll else '禁用'}")
            print(f"  上下文日志: {'启用' if self.save_context_log else '禁用'}")
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
            'final_response': None,
            'context_log_path': None,
            'elapsed_seconds': None,
            'elapsed_time_text': None,
        }
        task_start_time = time.perf_counter()

        self.history = []
        self.conversation_messages = []
        self.current_step = 0
        self.context_logger = ContextLogger(
            enabled=self.save_context_log,
            log_dir=self.context_log_dir,
        )

        self.context_logger.start_task(
            instruction=instruction,
            model=self.model,
            max_steps=self.max_steps,
            temperature=self.temperature,
            thinking_mode=self.thinking_mode,
            reasoning_effort=self.reasoning_effort,
        )
        result['context_log_path'] = self.context_logger.current_log_path
        
        try:
            # 多轮执行循环
            for step in range(self.max_steps):
                self.current_step = step + 1
                step_start_time = time.perf_counter()
                
                if self.verbose:
                    print(f"\n[步骤 {self.current_step}/{self.max_steps}]")
                
                # 1. 截图
                screenshot, screenshot_path = capture_screenshot()
                img_width, img_height = screenshot.size
                
                if self.verbose and screenshot_path:
                    print(f"  截图: {screenshot_path}")
                
                # 2. 调用模型
                text_input = self._build_text_input(
                    instruction=instruction,
                    step_no=self.current_step,
                )

                self.context_logger.log_event(
                    'model_call',
                    instruction=instruction,
                    step=self.current_step,
                    model=self.model,
                    thinking_mode=self.thinking_mode,
                    reasoning_effort=self.reasoning_effort,
                    text_input=text_input,
                    message_summary='1 system + text history + 1 current screenshot',
                    screenshot_path=screenshot_path,
                    screenshot_size=[img_width, img_height],
                )

                response_obj, response = self._call_model(
                    text_input=text_input,
                    screenshot=screenshot,
                )

                self.context_logger.log_event(
                    'model_response',
                    instruction=instruction,
                    step=self.current_step,
                    **self._build_logged_model_response(response_obj),
                    raw_response=response,
                    usage=self._extract_usage(response_obj),
                )
                self._append_user_input_message(text_input)
                
                if self.verbose:
                    print(f"  模型响应:\n{response}")
                
                # 3. 解析动作
                try:
                    action = parse_action(response)
                    thought_summary = action.get('thought', '')
                    parsed_action = self._format_action(action)
                except Exception as e:
                    failure_reason = self._format_parse_failure_reason(e, response)
                    step_elapsed_seconds = time.perf_counter() - step_start_time
                    step_record = self._build_step_record(
                        step=self.current_step,
                        screenshot_path=screenshot_path,
                        model_input=text_input,
                        response=response,
                        action=None,
                        thought_summary='',
                        execution_status='failed',
                        execution_result=None,
                        failure_reason=failure_reason,
                        elapsed_seconds=step_elapsed_seconds,
                    )
                    result['steps'].append(step_record)
                    self._record_history_entry(step_record, parsed_action='')
                    self._append_assistant_message(response)
                    self._append_execution_feedback(step_record, parsed_action='')
                    self.context_logger.log_event(
                        'step_result',
                        instruction=instruction,
                        step=self.current_step,
                        thought_summary='',
                        parsed_action='',
                        execution_status='failed',
                        execution_result=None,
                        failure_reason=failure_reason,
                        elapsed_seconds=step_record['elapsed_seconds'],
                        elapsed_time_text=step_record['elapsed_time_text'],
                    )
                    if self.verbose:
                        print(f"  解析失败: {failure_reason}")
                        print(
                            f"  步耗时: {self._format_elapsed_time(step_elapsed_seconds)}"
                        )
                    continue

                self._append_assistant_message(response)

                if self.verbose:
                    print(f"  解析结果: {action['action_type']}")
                
                # 4. 检查是否完成
                if action['action_type'] == 'finished':
                    result['success'] = True
                    result['final_response'] = action['action_inputs'].get('content', '')
                    step_elapsed_seconds = time.perf_counter() - step_start_time
                    step_record = self._build_step_record(
                        step=self.current_step,
                        screenshot_path=screenshot_path,
                        model_input=text_input,
                        response=response,
                        action=action,
                        thought_summary=thought_summary,
                        execution_status='finished',
                        execution_result=result['final_response'],
                        failure_reason=None,
                        elapsed_seconds=step_elapsed_seconds,
                    )
                    result['steps'].append(step_record)
                    self._record_history_entry(step_record, parsed_action=parsed_action)
                    self._append_execution_feedback(step_record, parsed_action=parsed_action)
                    self.context_logger.log_event(
                        'step_result',
                        instruction=instruction,
                        step=self.current_step,
                        thought_summary=thought_summary,
                        parsed_action=parsed_action,
                        execution_status='finished',
                        execution_result=result['final_response'],
                        failure_reason=None,
                        elapsed_seconds=step_record['elapsed_seconds'],
                        elapsed_time_text=step_record['elapsed_time_text'],
                    )
                    
                    result['elapsed_seconds'] = time.perf_counter() - task_start_time
                    result['elapsed_time_text'] = self._format_elapsed_time(
                        result['elapsed_seconds']
                    )
                    if self.verbose:
                        print(f"  步耗时: {self._format_elapsed_time(step_elapsed_seconds)}")
                        print(f"\n{'='*60}")
                        print(
                            f"[任务完成] {result['final_response']} "
                            f"(总耗时: {result['elapsed_time_text']})"
                        )
                        print(f"{'='*60}")
                    break
                
                # 5. 执行动作
                executor = ActionExecutor(
                    image_width=img_width,
                    image_height=img_height,
                    scale_factor=config.coordinate_scale,
                    verbose=self.verbose,
                    natural_scroll=self.natural_scroll,
                )
                
                try:
                    exec_result = executor.execute(action)
                except Exception as e:
                    failure_reason = str(e)
                    step_elapsed_seconds = time.perf_counter() - step_start_time
                    step_record = self._build_step_record(
                        step=self.current_step,
                        screenshot_path=screenshot_path,
                        model_input=text_input,
                        response=response,
                        action=action,
                        thought_summary=thought_summary,
                        execution_status='failed',
                        execution_result=None,
                        failure_reason=failure_reason,
                        elapsed_seconds=step_elapsed_seconds,
                    )
                    result['steps'].append(step_record)
                    self._record_history_entry(step_record, parsed_action=parsed_action)
                    self._append_execution_feedback(step_record, parsed_action=parsed_action)
                    self.context_logger.log_event(
                        'step_result',
                        instruction=instruction,
                        step=self.current_step,
                        thought_summary=thought_summary,
                        parsed_action=parsed_action,
                        execution_status='failed',
                        execution_result=None,
                        failure_reason=failure_reason,
                        elapsed_seconds=step_record['elapsed_seconds'],
                        elapsed_time_text=step_record['elapsed_time_text'],
                    )
                    if self.verbose:
                        print(f"  执行失败: {failure_reason}")
                        print(
                            f"  步耗时: {self._format_elapsed_time(step_elapsed_seconds)}"
                        )
                    continue
                
                if exec_result == 'DONE':
                    result['success'] = True
                    step_elapsed_seconds = time.perf_counter() - step_start_time
                    step_record = self._build_step_record(
                        step=self.current_step,
                        screenshot_path=screenshot_path,
                        model_input=text_input,
                        response=response,
                        action=action,
                        thought_summary=thought_summary,
                        execution_status='finished',
                        execution_result='DONE',
                        failure_reason=None,
                        elapsed_seconds=step_elapsed_seconds,
                    )
                    result['steps'].append(step_record)
                    self._record_history_entry(step_record, parsed_action=parsed_action)
                    self.context_logger.log_event(
                        'step_result',
                        instruction=instruction,
                        step=self.current_step,
                        thought_summary=thought_summary,
                        parsed_action=parsed_action,
                        execution_status='finished',
                        execution_result='DONE',
                        failure_reason=None,
                        elapsed_seconds=step_record['elapsed_seconds'],
                        elapsed_time_text=step_record['elapsed_time_text'],
                    )
                    result['elapsed_seconds'] = time.perf_counter() - task_start_time
                    result['elapsed_time_text'] = self._format_elapsed_time(
                        result['elapsed_seconds']
                    )
                    if self.verbose:
                        print(f"  步耗时: {self._format_elapsed_time(step_elapsed_seconds)}")
                        print(f"\n{'='*60}")
                        print(f"[任务完成] (总耗时: {result['elapsed_time_text']})")
                        print(f"{'='*60}")
                    break

                step_elapsed_seconds = time.perf_counter() - step_start_time
                step_record = self._build_step_record(
                    step=self.current_step,
                    screenshot_path=screenshot_path,
                    model_input=text_input,
                    response=response,
                    action=action,
                    thought_summary=thought_summary,
                    execution_status='success',
                    execution_result=exec_result,
                    failure_reason=None,
                    elapsed_seconds=step_elapsed_seconds,
                )
                result['steps'].append(step_record)
                self._record_history_entry(step_record, parsed_action=parsed_action)
                self._append_execution_feedback(step_record, parsed_action=parsed_action)
                self.context_logger.log_event(
                    'step_result',
                    instruction=instruction,
                    step=self.current_step,
                    thought_summary=thought_summary,
                    parsed_action=parsed_action,
                    execution_status='success',
                    execution_result=exec_result,
                    failure_reason=None,
                    elapsed_seconds=step_record['elapsed_seconds'],
                    elapsed_time_text=step_record['elapsed_time_text'],
                )
                if self.verbose:
                    print(f"  步耗时: {self._format_elapsed_time(step_elapsed_seconds)}")
                
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

        if result['elapsed_seconds'] is None:
            result['elapsed_seconds'] = time.perf_counter() - task_start_time
            result['elapsed_time_text'] = self._format_elapsed_time(
                result['elapsed_seconds']
            )

        self.context_logger.end_task(
            success=result['success'],
            final_response=result['final_response'],
            error=result['error'],
            elapsed_seconds=result['elapsed_seconds'],
            elapsed_time_text=result['elapsed_time_text'],
        )
        
        return result
    
    def _call_model(
        self,
        text_input: str,
        screenshot,
    ) -> tuple[Any, str]:
        """
        调用模型进行推理
        
        Args:
            screenshot: 截图对象
            
        Returns:
            tuple[Any, str]: (完整响应对象, 模型响应文本)
        """
        # 编码截图
        img_buffer = io.BytesIO()
        screenshot.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        base64_image = base64.b64encode(img_buffer.read()).decode('utf-8')

        messages = [
            {
                'role': 'system',
                'content': self._build_system_prompt(),
            },
            *self.conversation_messages,
            {
                'role': 'user',
                'content': text_input,
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
            temperature=self.temperature,
            thinking={
                'type': self.thinking_mode,
            },
            reasoning_effort=self.reasoning_effort,
        )
        
        return response, response.choices[0].message.content

    def _build_text_input(
        self,
        instruction: str,
        step_no: int,
    ) -> str:
        """构建当前轮发送给模型的文本输入。"""
        if step_no == 1:
            return (
                f"Current Task:\n{instruction}\n\n"
                f"Current Step: {step_no}\n"
                "Analyze the current screenshot and decide the next action."
            )

        return (
            f"Current Step: {step_no}\n"
            "Review the prior conversation, especially the execution feedback, "
            "then analyze the current screenshot and decide the next action."
        )

    def _build_system_prompt(self) -> str:
        """构建单次请求共用的 system prompt。"""
        return COMPUTER_USE_DOUBAO.format(language=self.language)

    def _extract_usage(self, response: Any) -> Optional[Dict[str, Any]]:
        """提取响应中的 token 使用量信息。"""
        usage = getattr(response, 'usage', None)
        if usage is None:
            return None

        usage_dict: Dict[str, Any] = {}
        for field in (
            'prompt_tokens',
            'completion_tokens',
            'total_tokens',
            'prompt_tokens_details',
            'completion_tokens_details',
        ):
            value = getattr(usage, field, None)
            if value is None:
                continue
            usage_dict[field] = self._serialize_usage_value(value)

        return usage_dict or None

    def _serialize_usage_value(self, value: Any) -> Any:
        """将 usage 对象转换为可写入 JSON 的结构。"""
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        if isinstance(value, dict):
            return {
                key: self._serialize_usage_value(item)
                for key, item in value.items()
            }

        if hasattr(value, 'model_dump'):
            return value.model_dump(exclude_none=True)

        if hasattr(value, '__dict__'):
            return {
                key: self._serialize_usage_value(item)
                for key, item in vars(value).items()
                if not key.startswith('_') and item is not None
            }

        return str(value)

    def _format_action(self, action: Dict[str, Any]) -> str:
        """将解析后的动作转换为稳定字符串。"""
        action_type = action.get('action_type', '')
        action_inputs = action.get('action_inputs', {})

        if not action_inputs:
            return f'{action_type}()'

        params = ', '.join(
            f"{key}={repr(value)}"
            for key, value in action_inputs.items()
        )
        return f'{action_type}({params})'

    def _build_logged_model_response(self, response_obj: Any) -> Dict[str, str]:
        """提取方舟响应中的 reasoning 字段用于日志记录。"""
        message = None
        choices = getattr(response_obj, 'choices', None) or []
        if choices:
            message = getattr(choices[0], 'message', None)

        reasoning = ''
        if message is not None:
            reasoning = getattr(message, 'reasoning_content', '') or ''

        return {
            'reasoning': reasoning.strip(),
        }

    def _format_parse_failure_reason(self, error: Exception, response: str) -> str:
        """将解析失败原因整理成简洁单行文本。"""
        message = ' '.join(str(error).split())
        if message:
            return self._truncate_text(message)

        response_preview = ' '.join(response.split())
        return f'无法解析动作: {self._truncate_text(response_preview)}'

    def _format_elapsed_time(self, elapsed_seconds: float) -> str:
        """将耗时秒数格式化为易读文本。"""
        elapsed_seconds = max(0.0, elapsed_seconds)
        if elapsed_seconds < 60:
            return f'{elapsed_seconds:.1f} 秒'

        minutes, seconds = divmod(elapsed_seconds, 60)
        if minutes < 60:
            return f'{int(minutes)} 分 {seconds:.1f} 秒'

        hours, minutes = divmod(int(minutes), 60)
        return f'{hours} 小时 {minutes} 分 {seconds:.1f} 秒'

    def _truncate_text(self, text: str, max_length: int = 200) -> str:
        """截断过长文本，避免错误信息污染日志和控制台。"""
        if len(text) <= max_length:
            return text
        return f'{text[: max_length - 3]}...'

    def _build_step_record(
        self,
        step: int,
        screenshot_path: Optional[str],
        model_input: str,
        response: str,
        action: Optional[Dict[str, Any]],
        thought_summary: str,
        execution_status: str,
        execution_result: Optional[str],
        failure_reason: Optional[str],
        elapsed_seconds: float,
    ) -> Dict[str, Any]:
        """构建返回结果中的单步记录。"""
        return {
            'step': step,
            'screenshot': screenshot_path,
            'model_input': model_input,
            'response': response,
            'action': action,
            'thought_summary': thought_summary,
            'execution_status': execution_status,
            'execution_result': execution_result,
            'failure_reason': failure_reason,
            'elapsed_seconds': elapsed_seconds,
            'elapsed_time_text': self._format_elapsed_time(elapsed_seconds),
        }

    def _record_history_entry(
        self,
        step_record: Dict[str, Any],
        parsed_action: str
    ) -> None:
        """记录可回放的结构化历史。"""
        self.history.append(
            {
                'step': step_record['step'],
                'model_input_snapshot': step_record['model_input'],
                'thought_summary': step_record['thought_summary'],
                'parsed_action': parsed_action,
                'execution_status': step_record['execution_status'],
                'execution_result': step_record['execution_result'],
                'failure_reason': step_record['failure_reason'],
            }
        )

    def _append_assistant_message(self, response: str) -> None:
        """将模型原始回复加入对话历史。"""
        self.conversation_messages.append(
            {
                'role': 'assistant',
                'content': response,
            }
        )

    def _append_user_input_message(self, text_input: str) -> None:
        """将本轮用户输入加入后续对话历史。"""
        self.conversation_messages.append(
            {
                'role': 'user',
                'content': text_input,
            }
        )

    def _append_execution_feedback(
        self,
        step_record: Dict[str, Any],
        parsed_action: str
    ) -> None:
        """将动作执行反馈作为用户消息加入对话历史。"""
        lines = [
            f"Step {step_record['step']} Execution Feedback",
            f"Model Input: {step_record['model_input']}",
            f"Thought Summary: {step_record['thought_summary'] or '(empty)'}",
            f"Parsed Action: {parsed_action or '(unavailable)'}",
            f"Execution Status: {step_record['execution_status']}",
            f"Execution Result: {step_record['execution_result'] or '(none)'}",
            f"Failure Reason: {step_record['failure_reason'] or '(none)'}",
        ]
        self.conversation_messages.append(
            {
                'role': 'user',
                'content': '\n'.join(lines),
            }
        )
