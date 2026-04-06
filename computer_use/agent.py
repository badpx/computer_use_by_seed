"""
核心代理模块
多轮自动执行直到任务完成
"""

import json
import io
import time
import base64
from typing import Callable, Dict, Any, List, Optional, Set

from volcenginesdkarkruntime import Ark

from .config import config, normalize_coordinate_space, resolve_thinking_settings
from .screenshot import capture_screenshot
from .action_parser import parse_action
from .action_executor import ActionExecutor
from .logging_utils import ContextLogger
from .prompts import COMPUTER_USE_DOUBAO, SKILLS_PROMPT_ADDENDUM
from .skills import Skill, discover_skills, skills_to_tools, load_skill

TOKEN_ESTIMATE_BYTES = 4
SCREENSHOT_TOKEN_ESTIMATE = 2000


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
        coordinate_space: Optional[str] = None,
        coordinate_scale: Optional[float] = None,
        screenshot_size: Optional[int] = None,
        max_context_screenshots: Optional[int] = None,
        include_execution_feedback: Optional[bool] = None,
        log_full_messages: bool = False,
        max_steps: Optional[int] = None,
        natural_scroll: Optional[bool] = None,
        save_context_log: Optional[bool] = None,
        context_log_dir: Optional[str] = None,
        language: str = 'Chinese',
        verbose: bool = True,
        print_init_status: bool = True,
        persistent_session: bool = False,
        skills_dir: Optional[str] = None,
        enable_skills: Optional[bool] = None,
        runtime_status_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
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
            coordinate_space: 坐标空间，relative / pixel
            coordinate_scale: 相对坐标量程
            screenshot_size: 传给模型前的截图缩放尺寸，仅支持正方形
            max_context_screenshots: 多轮上下文中最多保留的截图数量（含当前轮）
            include_execution_feedback: 是否注入历史执行反馈
            log_full_messages: 是否在上下文日志中记录完整 messages
            max_steps: 最大执行步数，默认从配置读取
            natural_scroll: 是否使用自然滚动
            save_context_log: 是否保存上下文日志
            context_log_dir: 上下文日志目录
            language: 提示词语言
            verbose: 是否打印详细日志
            print_init_status: 是否在初始化时打印生效参数
            persistent_session: 是否在多次 run 之间保留会话上下文
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
        self.coordinate_space = normalize_coordinate_space(
            coordinate_space or config.coordinate_space
        )
        self.coordinate_scale = (
            config.coordinate_scale if coordinate_scale is None else coordinate_scale
        )
        if self.coordinate_scale <= 0:
            raise ValueError("coordinate_scale 必须大于 0")
        self.screenshot_size = (
            config.screenshot_size if screenshot_size is None else int(screenshot_size)
        )
        if self.screenshot_size is not None and self.screenshot_size <= 0:
            self.screenshot_size = None
        self.max_context_screenshots = (
            config.max_context_screenshots
            if max_context_screenshots is None else int(max_context_screenshots)
        )
        if self.max_context_screenshots < 1:
            self.max_context_screenshots = config.max_context_screenshots
        self.include_execution_feedback = (
            include_execution_feedback
            if include_execution_feedback is not None
            else config.include_execution_feedback
        )
        self.log_full_messages = log_full_messages
        self.max_steps = max_steps if max_steps is not None else config.max_steps
        self.natural_scroll = (
            natural_scroll if natural_scroll is not None else config.natural_scroll
        )
        self.save_context_log = (
            save_context_log if save_context_log is not None else config.save_context_log
        )
        self.context_log_dir = context_log_dir or config.context_log_dir
        self.save_debug_screenshots = self.save_context_log and self.log_full_messages
        self.language = language
        self.verbose = verbose
        self.print_init_status = print_init_status
        self.persistent_session = persistent_session
        self.enable_skills = enable_skills if enable_skills is not None else config.enable_skills
        self.skills_dir = skills_dir or config.skills_dir
        self.skills: List[Skill] = discover_skills(self.skills_dir) if self.enable_skills else []
        self.skill_tools: List[dict] = skills_to_tools(self.skills) if self.skills else []
        self.runtime_status_callback = runtime_status_callback

        config.validate()

        # 初始化客户端
        self.client = Ark(
            base_url=self.base_url,
            api_key=self.api_key
        )
        
        # 会话级上下文与运行态
        self.session_history: List[Dict[str, Any]] = []
        self.activated_skills: Set[str] = set()
        self.history: List[Dict[str, Any]] = []
        self.last_usage_total_tokens: Optional[int] = None
        self.last_context_estimated_bytes = 0

        # 上下文日志
        self.context_logger = ContextLogger(
            enabled=self.save_context_log,
            log_dir=self.context_log_dir,
        )

        # 当前步骤
        self.current_step = 0
        
        if self.verbose and self.print_init_status:
            self._print_init_info()
    
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

        if not self.persistent_session:
            self._reset_session_state()
        self._reset_run_state()
        self._append_user_instruction_message(instruction)

        self.context_logger.start_task(
            instruction=instruction,
            model=self.model,
            max_steps=self.max_steps,
            temperature=self.temperature,
            thinking_mode=self.thinking_mode,
            reasoning_effort=self.reasoning_effort,
            coordinate_space=self.coordinate_space,
            coordinate_scale=self.coordinate_scale,
            screenshot_size=self.screenshot_size,
            max_context_screenshots=self.max_context_screenshots,
            include_execution_feedback=self.include_execution_feedback,
            log_full_messages=self.log_full_messages,
        )
        result['context_log_path'] = self.context_logger.current_log_path
        self._notify_runtime_status()
        
        try:
            # 多轮执行循环
            for step in range(self.max_steps):
                self.current_step = step + 1
                step_start_time = time.perf_counter()
                
                if self.verbose:
                    print(f"\n[步骤 {self.current_step}/{self.max_steps}]")
                
                # 1. 截图
                screenshot, _ = capture_screenshot()
                img_width, img_height = screenshot.size
                model_screenshot = self._prepare_model_screenshot(screenshot)
                model_img_width, model_img_height = model_screenshot.size
                logged_screenshot_path = self._save_debug_screenshot(model_screenshot)
                current_screenshot_item = self._build_screenshot_item(
                    model_screenshot,
                    logged_screenshot_path=logged_screenshot_path,
                )
                
                if self.verbose and logged_screenshot_path:
                    print(
                        f"  调试截图: "
                        f"{self.context_logger.resolve_path(logged_screenshot_path)}"
                    )
                
                # 2. 调用模型
                text_input = ''
                messages, logged_messages, message_summary, retained_screenshot_count = (
                    self._build_request_messages(
                        current_screenshot_item=current_screenshot_item,
                    )
                )
                self.last_context_estimated_bytes = self._estimate_context_bytes(messages)
                self._notify_runtime_status()

                model_call_payload = {
                    'instruction': instruction,
                    'step': self.current_step,
                    'model': self.model,
                    'thinking_mode': self.thinking_mode,
                    'reasoning_effort': self.reasoning_effort,
                    'coordinate_space': self.coordinate_space,
                    'coordinate_scale': self.coordinate_scale,
                    'max_context_screenshots': self.max_context_screenshots,
                    'include_execution_feedback': self.include_execution_feedback,
                    'screenshot_resize': self.screenshot_size,
                    'text_input': text_input,
                    'message_summary': message_summary,
                    'retained_screenshot_count': retained_screenshot_count,
                    'screenshot_path': logged_screenshot_path,
                    'screenshot_size': [model_img_width, model_img_height],
                    'original_screenshot_size': [img_width, img_height],
                }
                if logged_messages is not None:
                    model_call_payload['messages'] = logged_messages

                self.context_logger.log_event(
                    'model_call',
                    **model_call_payload,
                )

                response_obj, response = self._call_model(
                    messages=messages,
                )
                usage = self._extract_usage(response_obj)
                self._record_usage_total_tokens(usage)
                self._notify_runtime_status()

                self.context_logger.log_event(
                    'model_response',
                    instruction=instruction,
                    step=self.current_step,
                    **self._build_logged_model_response(response_obj),
                    raw_response=response,
                    usage=usage,
                )
                
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
                        screenshot_path=logged_screenshot_path,
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
                    self._append_step_context(
                        current_screenshot_item=current_screenshot_item,
                        response=response,
                        step_record=step_record,
                        parsed_action='',
                        include_feedback=True,
                    )
                    self.last_context_estimated_bytes = self._estimate_next_context_bytes()
                    self._notify_runtime_status()
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

                if self.verbose:
                    print(f"  解析结果: {action['action_type']}")
                
                # 4. 检查是否完成
                if action['action_type'] == 'finished':
                    result['success'] = True
                    result['final_response'] = action['action_inputs'].get('content', '')
                    step_elapsed_seconds = time.perf_counter() - step_start_time
                    step_record = self._build_step_record(
                        step=self.current_step,
                        screenshot_path=logged_screenshot_path,
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
                    self._append_step_context(
                        current_screenshot_item=current_screenshot_item,
                        response=response,
                        step_record=step_record,
                        parsed_action=parsed_action,
                        include_feedback=False,
                    )
                    self.last_context_estimated_bytes = self._estimate_next_context_bytes()
                    self._notify_runtime_status()
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
                    model_image_width=model_img_width,
                    model_image_height=model_img_height,
                    coordinate_space=self.coordinate_space,
                    coordinate_scale=self.coordinate_scale,
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
                        screenshot_path=logged_screenshot_path,
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
                    self._append_step_context(
                        current_screenshot_item=current_screenshot_item,
                        response=response,
                        step_record=step_record,
                        parsed_action=parsed_action,
                        include_feedback=True,
                    )
                    self.last_context_estimated_bytes = self._estimate_next_context_bytes()
                    self._notify_runtime_status()
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
                        screenshot_path=logged_screenshot_path,
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
                    self._append_step_context(
                        current_screenshot_item=current_screenshot_item,
                        response=response,
                        step_record=step_record,
                        parsed_action=parsed_action,
                        include_feedback=False,
                    )
                    self.last_context_estimated_bytes = self._estimate_next_context_bytes()
                    self._notify_runtime_status()
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
                    screenshot_path=logged_screenshot_path,
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
                self._append_step_context(
                    current_screenshot_item=current_screenshot_item,
                    response=response,
                    step_record=step_record,
                    parsed_action=parsed_action,
                    include_feedback=True,
                )
                self.last_context_estimated_bytes = self._estimate_next_context_bytes()
                self._notify_runtime_status()
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
        result['runtime_status'] = self._build_runtime_status(
            elapsed_seconds=result['elapsed_seconds'],
        )
        self._notify_runtime_status(elapsed_seconds=result['elapsed_seconds'])

        self.context_logger.end_task(
            success=result['success'],
            final_response=result['final_response'],
            error=result['error'],
            elapsed_seconds=result['elapsed_seconds'],
            elapsed_time_text=result['elapsed_time_text'],
        )
        
        return result

    def _reset_session_state(self) -> None:
        """重置跨 run 的会话上下文。"""
        self.session_history = []
        self.activated_skills = set()

    def clear_session_context(self) -> None:
        """清理当前会话的多轮上下文历史。"""
        self._reset_session_state()
        self.last_usage_total_tokens = None
        self.last_context_estimated_bytes = 0
        self._notify_runtime_status()

    def _reset_run_state(self) -> None:
        """重置单次 run 的临时状态。"""
        self.history = []
        self.last_usage_total_tokens = None
        self.last_context_estimated_bytes = 0
        self.current_step = 0
        self.context_logger = ContextLogger(
            enabled=self.save_context_log,
            log_dir=self.context_log_dir,
        )

    def _build_history_item(
        self,
        kind: str,
        api_message: Dict[str, Any],
        logged_message: Optional[Dict[str, Any]] = None,
        **metadata: Any,
    ) -> Dict[str, Any]:
        """构建统一的会话历史项。"""
        item = {
            'kind': kind,
            'api_message': api_message,
            'logged_message': logged_message or api_message,
        }
        item.update(metadata)
        return item

    def _append_history_item(self, item: Dict[str, Any]) -> None:
        """向会话历史追加一条消息。"""
        self.session_history.append(item)

    def _append_user_instruction_message(self, instruction: str) -> None:
        """将用户指令作为普通 user 消息加入会话历史。"""
        self._append_history_item(
            self._build_history_item(
                kind='user_instruction',
                api_message={
                    'role': 'user',
                    'content': instruction,
                },
            )
        )

    def _build_persistent_skill_message(
        self,
        skill_name: str,
        skill_content: str,
    ) -> Dict[str, Any]:
        """将已加载 skill 压缩为可持久保留的普通 user 消息。"""
        return self._build_history_item(
            kind='persistent_skill',
            api_message={
                'role': 'user',
                'content': (
                    f"Loaded Skill Instructions ({skill_name})\n"
                    f"{skill_content}"
                ),
            },
            skill_name=skill_name,
        )

    def _append_persistent_skill_message_once(
        self,
        skill_name: str,
        skill_content: str,
    ) -> None:
        """仅在首次加载 skill 时向会话历史写入其说明。"""
        for item in self.session_history:
            if item.get('kind') == 'persistent_skill' and item.get('skill_name') == skill_name:
                return
        self._append_history_item(
            self._build_persistent_skill_message(skill_name, skill_content)
        )

    def format_effective_status(self) -> str:
        """格式化当前运行的生效参数。"""
        lines = [
            '[生效参数]',
            f"  模型: {self.model}",
            f"  最大步数: {self.max_steps}",
            f"  思考: {self.thinking_mode} / {self.reasoning_effort}",
            f"  坐标空间: {self.coordinate_space}",
        ]
        if self.coordinate_space == 'relative':
            lines.append(f"  坐标量程: {self.coordinate_scale}")
        if self.screenshot_size is not None:
            lines.append(
                f"  模型截图尺寸: {self.screenshot_size} x {self.screenshot_size}"
            )
        lines.extend(
            [
                f"  上下文截图窗口: {self.max_context_screenshots}",
                f"  注入执行反馈: {'启用' if self.include_execution_feedback else '禁用'}",
                f"  日志完整上下文: {'启用' if self.log_full_messages else '禁用'}",
            ]
        )
        if self.save_debug_screenshots:
            lines.append(f"  调试截图目录: {self.context_log_dir}/screenshots")
        lines.extend(
            [
                f"  自然滚动: {'启用' if self.natural_scroll else '禁用'}",
                f"  上下文日志: {'启用' if self.save_context_log else '禁用'}",
                f"  语言: {self.language}",
            ]
        )
        if self.enable_skills:
            lines.append(f"  技能: {len(self.skills)} 个已加载")
        else:
            lines.append("  技能: 禁用")
        return '\n'.join(lines)

    def _print_init_info(self) -> None:
        """打印当前运行的生效参数。"""
        print(self.format_effective_status())

    def _call_model(
        self,
        messages: List[Dict[str, Any]],
    ) -> tuple[Any, str]:
        """
        调用模型进行推理，支持 Skill 工具调用的渐进式加载。

        若模型请求加载 Skill（finish_reason == 'tool_calls'），
        则注入 Skill 内容后重新调用，直到模型输出最终文本响应。

        Args:
            messages: 完整请求消息（会在 skill 加载子循环中被原地修改）

        Returns:
            tuple[Any, str]: (完整响应对象, 模型响应文本)
        """
        max_skill_rounds = 5  # 防止无限循环的安全上限
        response = None
        choice = None

        for _ in range(max_skill_rounds):
            kwargs: Dict[str, Any] = dict(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                thinking={'type': self.thinking_mode},
                reasoning_effort=self.reasoning_effort,
            )
            if self.skill_tools:
                kwargs['tools'] = self.skill_tools

            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if getattr(choice, 'finish_reason', None) != 'tool_calls':
                # 正常文本响应，直接返回
                return response, choice.message.content

            # 模型请求加载 Skill：注入内容后重新调用
            # TODO: Level 3 — 区分 skill__ 前缀（加载指南）与 resource__/script__ 前缀
            #   （按需加载附加资源文件或执行脚本并注入输出），以支持完整的三层渐进式披露。
            messages.append(choice.message.model_dump())
            tool_calls = choice.message.tool_calls or []
            for tc in tool_calls:
                skill_name = tc.function.name.removeprefix('skill__')
                self.activated_skills.add(skill_name)
                skill_content = load_skill(self.skills, tc.function.name)
                self._append_persistent_skill_message_once(skill_name, skill_content)
                messages.append({
                    'role': 'tool',
                    'content': skill_content,
                    'tool_call_id': tc.id,
                })
            if self.verbose:
                names = [tc.function.name for tc in tool_calls]
                print(f"  加载技能: {', '.join(names)}")
            self.context_logger.log_event(
                'skill_loaded',
                step=self.current_step,
                skills=[tc.function.name for tc in tool_calls],
            )
            self._notify_runtime_status()

        # 超出 skill 加载轮数上限，返回最后一次响应
        return response, (choice.message.content or '') if choice else ''

    def _build_system_prompt(self) -> str:
        """构建稳定的 system prompt。若技能系统启用则追加技能说明。"""
        prompt = COMPUTER_USE_DOUBAO.format(
            language=self.language,
        )
        if self.skills:
            prompt += SKILLS_PROMPT_ADDENDUM
        return prompt

    def _prepare_model_screenshot(self, screenshot: Any) -> Any:
        """按配置缩放传给模型的截图。"""
        if self.screenshot_size is None:
            return screenshot

        return screenshot.resize(
            (self.screenshot_size, self.screenshot_size),
            resample=self._get_resize_resample(),
        )

    def _get_resize_resample(self) -> int:
        """兼容不同 Pillow 版本的重采样常量。"""
        try:
            from PIL import Image as PILImage
        except ImportError:
            return 1

        resampling = getattr(PILImage, 'Resampling', None)
        if resampling is not None:
            return resampling.LANCZOS
        return PILImage.LANCZOS

    def _save_debug_screenshot(self, screenshot: Any) -> Optional[str]:
        """在完整上下文日志模式下保存当前模型截图。"""
        if not self.save_debug_screenshots:
            return None
        return self.context_logger.save_screenshot(screenshot, step=self.current_step)

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

    def _record_usage_total_tokens(self, usage: Optional[Dict[str, Any]]) -> None:
        """记录最近一次模型调用的 total_tokens。"""
        if not usage:
            return

        total_tokens = usage.get('total_tokens')
        if total_tokens is None:
            return

        try:
            self.last_usage_total_tokens = int(total_tokens)
        except (TypeError, ValueError):
            return

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

    def _build_screenshot_item(
        self,
        screenshot: Any,
        logged_screenshot_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构建截图历史项，分别服务于模型调用和日志落盘。"""
        img_buffer = io.BytesIO()
        screenshot.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        base64_image = base64.b64encode(img_buffer.read()).decode('utf-8')
        api_message = {
            'role': 'user',
            'content': [
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': f'data:image/png;base64,{base64_image}'
                    }
                }
            ],
        }
        return self._build_history_item(
            kind='screenshot',
            api_message=api_message,
            logged_message=self._build_logged_screenshot_message(logged_screenshot_path),
            logged_screenshot_path=logged_screenshot_path,
        )

    def _build_request_messages(
        self,
        current_screenshot_item: Dict[str, Any],
    ) -> tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]], str, int]:
        """组装发送给模型的 messages。"""
        retained_history_items = self._get_retained_session_history()
        user_instruction_count = 0
        persistent_skill_count = 0
        assistant_count = 0
        feedback_count = 0
        historical_screenshot_count = 0

        system_message = {
            'role': 'system',
            'content': self._build_system_prompt(),
        }
        messages: List[Dict[str, Any]] = [system_message]
        logged_messages: Optional[List[Dict[str, Any]]] = None
        if self.log_full_messages:
            logged_messages = [dict(system_message)]

        for item in retained_history_items:
            messages.append(item['api_message'])
            if logged_messages is not None:
                logged_messages.append(item['logged_message'])

            kind = item.get('kind')
            if kind == 'user_instruction':
                user_instruction_count += 1
            elif kind == 'persistent_skill':
                persistent_skill_count += 1
            elif kind == 'assistant':
                assistant_count += 1
            elif kind == 'execution_feedback':
                feedback_count += 1
            elif kind == 'screenshot':
                historical_screenshot_count += 1

        messages.append(current_screenshot_item['api_message'])
        if logged_messages is not None:
            logged_messages.append(current_screenshot_item['logged_message'])

        retained_screenshot_count = historical_screenshot_count + 1
        message_summary = (
            f'1 system + {user_instruction_count} user instructions + '
            f'{persistent_skill_count} persistent skills + '
            f'{assistant_count} historical assistant + '
            f'{feedback_count} feedback + '
            f'{retained_screenshot_count} screenshots'
        )
        return messages, logged_messages, message_summary, retained_screenshot_count

    def _get_retained_session_history(self) -> List[Dict[str, Any]]:
        """返回应用截图窗口裁剪后的会话历史。"""
        historical_screenshot_limit = max(0, self.max_context_screenshots - 1)
        screenshot_indexes = [
            index
            for index, item in enumerate(self.session_history)
            if item.get('kind') == 'screenshot'
        ]
        kept_screenshot_indexes = set(screenshot_indexes[-historical_screenshot_limit:])

        retained_items = []
        for index, item in enumerate(self.session_history):
            if item.get('kind') == 'screenshot' and index not in kept_screenshot_indexes:
                continue
            retained_items.append(item)
        return retained_items

    def _build_logged_screenshot_message(
        self,
        logged_screenshot_path: Optional[str],
    ) -> Dict[str, Any]:
        """将截图消息转换为日志友好的相对路径引用。"""
        relative_path = logged_screenshot_path or ''
        return {
            'role': 'user',
            'content': [
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': relative_path,
                    }
                }
            ],
        }

    def _estimate_context_bytes(self, messages: List[Dict[str, Any]]) -> int:
        """估算消息上下文占用字节数，截图统一按固定 token 数计入。"""
        sanitized_messages: List[Dict[str, Any]] = []
        screenshot_count = 0

        for message in messages:
            sanitized_message: Dict[str, Any] = {'role': message.get('role')}
            content = message.get('content')
            if isinstance(content, list):
                sanitized_content = []
                for item in content:
                    sanitized_item = dict(item)
                    if sanitized_item.get('type') == 'image_url':
                        screenshot_count += 1
                        sanitized_item['image_url'] = {'url': '<estimated-screenshot>'}
                    sanitized_content.append(sanitized_item)
                sanitized_message['content'] = sanitized_content
            else:
                sanitized_message['content'] = content

            for optional_key in ('tool_call_id', 'name', 'tool_calls'):
                if optional_key in message:
                    sanitized_message[optional_key] = message[optional_key]
            sanitized_messages.append(sanitized_message)

        serialized_bytes = len(
            json.dumps(sanitized_messages, ensure_ascii=False).encode('utf-8')
        )
        screenshot_bytes = screenshot_count * SCREENSHOT_TOKEN_ESTIMATE * TOKEN_ESTIMATE_BYTES
        return serialized_bytes + screenshot_bytes

    def _estimate_next_context_bytes(self) -> int:
        """估算下一轮模型调用会携带的上下文字节数。"""
        placeholder_screenshot_item = self._build_history_item(
            kind='screenshot',
            api_message={
                'role': 'user',
                'content': [
                    {
                        'type': 'image_url',
                        'image_url': {
                            'url': '<estimated-screenshot>'
                        }
                    }
                ],
            },
            logged_message=self._build_logged_screenshot_message(None),
            logged_screenshot_path=None,
        )
        messages, _, _, _ = self._build_request_messages(
            current_screenshot_item=placeholder_screenshot_item,
        )
        return self._estimate_context_bytes(messages)

    def _build_runtime_status(self, elapsed_seconds: float) -> Dict[str, Any]:
        """构建供 CLI 状态栏消费的运行时状态。"""
        return {
            'usage_total_tokens': self.last_usage_total_tokens,
            'context_estimated_bytes': self.last_context_estimated_bytes,
            'activated_skills': sorted(self.activated_skills),
            'elapsed_seconds': elapsed_seconds,
        }

    def _notify_runtime_status(self, elapsed_seconds: float = 0.0) -> None:
        """向外部回调最新的运行时状态。"""
        if self.runtime_status_callback is None:
            return

        self.runtime_status_callback(
            self._build_runtime_status(elapsed_seconds=elapsed_seconds)
        )

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

    def _build_execution_feedback_message(
        self,
        step_record: Dict[str, Any],
        parsed_action: str
    ) -> Dict[str, Any]:
        """构建动作执行反馈消息项。"""
        lines = [
            f"Step {step_record['step']} Execution Feedback",
            f"Model Input: {step_record['model_input']}",
            f"Thought Summary: {step_record['thought_summary'] or '(empty)'}",
            f"Parsed Action: {parsed_action or '(unavailable)'}",
            f"Execution Status: {step_record['execution_status']}",
            f"Execution Result: {step_record['execution_result'] or '(none)'}",
            f"Failure Reason: {step_record['failure_reason'] or '(none)'}",
        ]
        return self._build_history_item(
            kind='execution_feedback',
            api_message={
                'role': 'user',
                'content': '\n'.join(lines),
            },
        )

    def _append_step_context(
        self,
        current_screenshot_item: Dict[str, Any],
        response: str,
        step_record: Dict[str, Any],
        parsed_action: str,
        include_feedback: bool,
    ) -> None:
        """将本轮上下文写入历史。"""
        self._append_history_item(current_screenshot_item)
        self._append_history_item(
            self._build_history_item(
                kind='assistant',
                api_message={
                    'role': 'assistant',
                    'content': response,
                },
            )
        )

        if self.include_execution_feedback and include_feedback:
            feedback_message = self._build_execution_feedback_message(
                step_record,
                parsed_action,
            )
            self._append_history_item(feedback_message)
