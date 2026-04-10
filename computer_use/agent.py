"""
核心代理模块
多轮自动执行直到任务完成
"""

import json
import io
import os
import platform
import time
import base64
from datetime import datetime
from typing import Callable, Dict, Any, List, Optional, Set, Tuple

from volcenginesdkarkruntime import Ark

from .config import config, normalize_coordinate_space, resolve_thinking_settings
from .action_parser import parse_action
from .devices import create_device_adapter, discover_device_plugins
from .devices.base import DeviceAdapter, DeviceCommand, DeviceFrame
from .devices.command_mapper import map_action_to_command
from .devices.coordinates import (
    normalize_command_coordinates,
    normalize_scroll_direction,
)
from .devices.helpers import frame_to_data_url, prepare_model_frame
from .logging_utils import ContextLogger
from .prompts import COMPUTER_USE_DOUBAO, PHONE_USE_DOUBAO, SKILLS_PROMPT_ADDENDUM
from .skills import Skill, discover_skills, skills_to_tools, load_skill

SCREENSHOT_TOKEN_ESTIMATE = 2000
CONTEXT_WINDOW_TOKENS = 256 * 1024
CONTEXT_COMPACTION_WARNING_TOKENS = int(CONTEXT_WINDOW_TOKENS * 0.85)
CONTEXT_COMPACTION_THRESHOLD_TOKENS = int(CONTEXT_WINDOW_TOKENS * 0.9)
COMPACTION_MAX_TOKENS_BASE = 400
COMPACTION_MAX_TOKENS_MIN = 50
COMPACTION_TURNS_PER_BUCKET = 10
COMPACTION_SUMMARY_SYSTEM_PROMPT = '''You condense historical GUI-agent conversation turns.

You will receive one historical user turn that may include:
- one or more original user instructions
- one or more assistant Thought/Action replies
- optional execution feedback messages

Return a compact JSON object with exactly these keys:
- "condensed_user_instruction"
- "condensed_assistant_response"

Requirements:
- Preserve the user's real goal, constraints, corrections, and latest intent
- Preserve important assistant findings, decisions, failure reasons, and progress
- Fold execution feedback into the assistant summary instead of keeping it separate
- Keep both fields concise but specific
- Output valid JSON only, with no markdown fences or extra text
'''

PROMPT_PROFILE_TEMPLATES = {
    'computer': COMPUTER_USE_DOUBAO,
    'cellphone': PHONE_USE_DOUBAO,
}
USER_INTERRUPT_MESSAGE = 'The current task was interrupted by the user.'


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
        display_index: Optional[int] = None,
        device_name: Optional[str] = None,
        device_config: Optional[Dict[str, Any]] = None,
        devices_dir: Optional[str] = None,
        device_adapter: Optional[DeviceAdapter] = None,
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
            reasoning_effort: 方舟思考档位，low / medium / high
            coordinate_space: 坐标空间，relative / pixel
            coordinate_scale: 相对坐标量程
            screenshot_size: 传给模型前的截图缩放尺寸，仅支持正方形
            max_context_screenshots: 多轮上下文中最多保留的截图数量（含当前轮）
            include_execution_feedback: 是否注入成功执行的历史反馈
            log_full_messages: 是否在上下文日志中记录完整 messages
            max_steps: 最大执行步数，默认从配置读取
            natural_scroll: 是否使用自然滚动
            display_index: 目标显示器编号
            device_name: 设备插件名称
            device_config: 设备插件私有配置
            devices_dir: 外部设备插件目录
            device_adapter: 显式注入的设备适配器实例
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
        thinking_mode_explicit = (
            thinking_mode is not None or config.has_explicit_value('THINKING_MODE')
        )
        reasoning_effort_explicit = (
            reasoning_effort is not None or config.has_explicit_value('REASONING_EFFORT')
        )
        self.requested_thinking_mode = (
            thinking_mode
            if thinking_mode is not None
            else (config.thinking_mode if config.has_explicit_value('THINKING_MODE') else None)
        )
        self.requested_reasoning_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else (
                config.reasoning_effort
                if config.has_explicit_value('REASONING_EFFORT')
                else None
            )
        )
        self.thinking_mode, self.reasoning_effort = resolve_thinking_settings(
            self.requested_thinking_mode,
            self.requested_reasoning_effort,
            thinking_mode_explicit=thinking_mode_explicit,
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
        self.display_index = (
            config.display_index if display_index is None else int(display_index)
        )
        if self.display_index < 0:
            raise ValueError('display_index 不能小于 0')
        self.device_name = (device_name or config.device_name).strip() or 'local'
        self.device_config = dict(config.device_config)
        if device_config:
            self.device_config.update(device_config)
        self.devices_dir = devices_dir or config.devices_dir
        self.device_config.setdefault('display_index', self.display_index)
        self.device_config.setdefault('natural_scroll', self.natural_scroll)
        self.save_context_log = (
            save_context_log if save_context_log is not None else config.save_context_log
        )
        self.context_log_dir = context_log_dir or config.context_log_dir
        self.save_debug_screenshots = self.save_context_log and self.log_full_messages
        self.language = language
        self.verbose = verbose
        self.print_init_status = print_init_status
        self.persistent_session = persistent_session
        self.device_config.setdefault('verbose', self.verbose)
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
        self.last_context_estimated_tokens = 0
        self._runtime_status_note = ''
        self._suppress_auto_compact_warning = False

        # 上下文日志
        self.context_logger = ContextLogger(
            enabled=self.save_context_log,
            log_dir=self.context_log_dir,
        )
        self._is_compacting = False
        self.device: DeviceAdapter = create_device_adapter(
            device_name=self.device_name,
            device_config=self.device_config,
            devices_dir=self.devices_dir,
            adapter=device_adapter,
        )
        self.device_name = getattr(self.device, 'device_name', self.device_name)
        self.device_control_method_description = (
            self._resolve_device_control_method_description()
        )
        self.device.connect()
        self.current_display_info = self._extract_display_info_from_device_status()

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
        self.current_display_info = self._extract_display_info_from_device_status()
        device_status = self._safe_device_status()

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
            display_index=self._display_index_for_logging(device_status),
            display_bounds=self._display_bounds_for_logging(device_status),
            display_is_primary=self._display_is_primary_for_logging(device_status),
            device_name=self.device_name,
            device_status=device_status,
            device_target=self._safe_device_target(),
        )
        result['context_log_path'] = self.context_logger.current_log_path
        self._notify_runtime_status()
        interrupted = False
        
        try:
            # 多轮执行循环
            for step in range(self.max_steps):
                self.current_step = step + 1
                step_start_time = time.perf_counter()
                
                if self.verbose:
                    print(f"\n[步骤 {self.current_step}/{self.max_steps}]")
                
                # 1. 截图
                frame = self.device.capture_frame()
                self.current_display_info = self._extract_display_info_from_frame(frame)
                img_width, img_height = frame.width, frame.height
                model_frame = prepare_model_frame(frame, screenshot_size=self.screenshot_size)
                model_img_width, model_img_height = model_frame.width, model_frame.height
                logged_screenshot_path = self._save_debug_screenshot(model_frame)
                current_screenshot_item = self._build_screenshot_item(
                    model_frame,
                    logged_screenshot_path=logged_screenshot_path,
                )
                
                if self.verbose and logged_screenshot_path:
                    print(
                        f"  调试截图: "
                        f"{self.context_logger.resolve_path(logged_screenshot_path)}"
                    )
                
                # 2. 调用模型
                text_input = ''
                self._maybe_compact_before_model_call(
                    current_screenshot_item=current_screenshot_item,
                )
                messages, logged_messages, message_summary, retained_screenshot_count = (
                    self._build_request_messages(
                        current_screenshot_item=current_screenshot_item,
                    )
                )
                self._set_context_estimated_tokens(
                    self._estimate_context_tokens(messages)
                )
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
                    'device_name': self.device_name,
                    'device_status': self._safe_device_status(),
                    'device_target': self._safe_device_target(),
                    'display_index': self._display_index_for_logging(),
                    'display_bounds': self._display_bounds_for_logging(),
                    'display_is_primary': self._display_is_primary_for_logging(),
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
                    raw_response=self._extract_message_content(response_obj),
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
                    self._set_context_estimated_tokens(
                        self._estimate_next_context_tokens()
                    )
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
                    self._set_context_estimated_tokens(
                        self._estimate_next_context_tokens()
                    )
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
                try:
                    exec_result = self.device.execute_command(
                        self._build_device_command(
                            action=action,
                            image_width=img_width,
                            image_height=img_height,
                            model_image_width=model_img_width,
                            model_image_height=model_img_height,
                        )
                    )
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
                    self._set_context_estimated_tokens(
                        self._estimate_next_context_tokens()
                    )
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
                    self._set_context_estimated_tokens(
                        self._estimate_next_context_tokens()
                    )
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
                self._set_context_estimated_tokens(
                    self._estimate_next_context_tokens()
                )
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
        except KeyboardInterrupt:
            interrupted = True
            result['error'] = USER_INTERRUPT_MESSAGE
            self._append_user_interrupt_message_once()
        except Exception as e:
            result['error'] = str(e)
            if self.verbose:
                print(f"\n[错误] {e}")
                import traceback
                traceback.print_exc()
        finally:
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

        if interrupted:
            raise KeyboardInterrupt
        return result

    def _reset_session_state(self) -> None:
        """重置跨 run 的会话上下文。"""
        self.session_history = []
        self.activated_skills = set()

    def clear_session_context(self) -> None:
        """清理当前会话的多轮上下文历史。"""
        self._reset_session_state()
        self.last_usage_total_tokens = None
        self._set_context_estimated_tokens(0)
        self._notify_runtime_status()

    def close(self) -> None:
        """释放 agent 持有的底层设备资源。"""
        self.device.close()

    def compact_session_context(self, manual: bool = False) -> bool:
        """压缩当前持久会话的历史上下文。"""
        if not self.persistent_session or self._is_compacting:
            return False
        return self._compact_session_context(
            trigger_reason='manual' if manual else 'auto'
        )

    def _reset_run_state(self) -> None:
        """重置单次 run 的临时状态。"""
        self.history = []
        self.last_usage_total_tokens = None
        self._set_context_estimated_tokens(0)
        self.current_step = 0
        self._runtime_status_note = ''
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

    def _append_user_interrupt_message_once(self) -> None:
        """将用户中断消息加入会话历史，避免连续重复写入。"""
        if self.session_history:
            last_item = self.session_history[-1]
            last_message = last_item.get('api_message') or {}
            if (
                last_item.get('kind') == 'user_instruction'
                and last_message.get('role') == 'user'
                and last_message.get('content') == USER_INTERRUPT_MESSAGE
            ):
                return

        self._append_user_instruction_message(USER_INTERRUPT_MESSAGE)

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

    def _count_history_kinds(self, items: List[Dict[str, Any]]) -> Dict[str, int]:
        """统计历史项类型数量。"""
        counts: Dict[str, int] = {}
        for item in items:
            kind = item.get('kind', 'unknown')
            counts[kind] = counts.get(kind, 0) + 1
        return counts

    def _extract_text_message_content(self, item: Dict[str, Any]) -> str:
        """提取历史项中的纯文本内容。"""
        api_message = item.get('api_message') or {}
        content = api_message.get('content')
        return content if isinstance(content, str) else ''

    def _build_compaction_turns(
        self,
        preserve_latest_pending_user: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """将会话历史拆分为技能消息与按用户输入分组的 turn。"""
        skill_items: List[Dict[str, Any]] = []
        trailing_user_items: List[Dict[str, Any]] = []
        source_items = list(self.session_history)

        if preserve_latest_pending_user:
            pending_items: List[Dict[str, Any]] = []
            for item in reversed(source_items):
                kind = item.get('kind')
                if kind == 'user_instruction':
                    pending_items.append(item)
                    continue
                if kind == 'persistent_skill':
                    continue
                if pending_items:
                    break
                pending_items = []
                break
            if pending_items:
                trailing_user_items = list(reversed(pending_items))
                source_items = source_items[: len(source_items) - len(trailing_user_items)]

        turns: List[Dict[str, Any]] = []
        current_turn: Optional[Dict[str, Any]] = None

        for item in source_items:
            kind = item.get('kind')
            if kind == 'persistent_skill':
                skill_items.append(item)
                continue
            if kind == 'screenshot':
                continue

            text_content = self._extract_text_message_content(item)
            if not text_content:
                continue

            if kind == 'user_instruction':
                if current_turn is not None:
                    turns.append(current_turn)
                current_turn = {
                    'user_messages': [text_content],
                    'assistant_messages': [],
                    'feedback_messages': [],
                }
                continue

            if current_turn is None:
                current_turn = {
                    'user_messages': [],
                    'assistant_messages': [],
                    'feedback_messages': [],
                }

            if kind == 'assistant':
                current_turn['assistant_messages'].append(text_content)
            elif kind == 'execution_feedback':
                current_turn['feedback_messages'].append(text_content)

        if current_turn is not None:
            turns.append(current_turn)

        merged_turns: List[Dict[str, Any]] = []
        for turn in turns:
            if (
                merged_turns
                and not merged_turns[-1]['assistant_messages']
                and not merged_turns[-1]['feedback_messages']
            ):
                merged_turns[-1]['user_messages'].extend(turn['user_messages'])
                merged_turns[-1]['assistant_messages'].extend(turn['assistant_messages'])
                merged_turns[-1]['feedback_messages'].extend(turn['feedback_messages'])
            else:
                merged_turns.append(turn)

        return skill_items, merged_turns, trailing_user_items

    def _get_compaction_max_tokens(self, turn_index: int, total_turns: int) -> int:
        """按从近到远的分组动态收缩总结输出上限。"""
        distance_from_latest = max(0, total_turns - 1 - turn_index)
        bucket_index = distance_from_latest // COMPACTION_TURNS_PER_BUCKET
        max_tokens = COMPACTION_MAX_TOKENS_BASE // (2 ** bucket_index)
        return max(COMPACTION_MAX_TOKENS_MIN, max_tokens)

    def _build_compaction_turn_prompt(self, turn: Dict[str, Any]) -> str:
        """构建单个历史 turn 的总结输入。"""
        sections = ['Summarize this historical GUI turn.']
        user_messages = turn.get('user_messages') or []
        assistant_messages = turn.get('assistant_messages') or []
        feedback_messages = turn.get('feedback_messages') or []

        if user_messages:
            sections.append('Original User Instructions:')
            for index, message in enumerate(user_messages, start=1):
                sections.append(f'{index}. {message}')
        if assistant_messages:
            sections.append('Assistant Responses:')
            for index, message in enumerate(assistant_messages, start=1):
                sections.append(f'{index}. {message}')
        if feedback_messages:
            sections.append('Execution Feedback:')
            for index, message in enumerate(feedback_messages, start=1):
                sections.append(f'{index}. {message}')
        return '\n'.join(sections)

    def _parse_compaction_response(self, response_text: str) -> Dict[str, str]:
        """解析历史压缩总结调用返回的 JSON。"""
        cleaned = response_text.strip()
        if cleaned.startswith('```'):
            cleaned = cleaned.strip('`')
            cleaned = cleaned.removeprefix('json').strip()
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start != -1 and end != -1 and end >= start:
            cleaned = cleaned[start:end + 1]
        data = json.loads(cleaned)
        user_text = str(data.get('condensed_user_instruction') or '').strip()
        assistant_text = str(data.get('condensed_assistant_response') or '').strip()
        if not user_text:
            user_text = '(empty summary)'
        if not assistant_text:
            assistant_text = '(empty summary)'
        return {
            'condensed_user_instruction': user_text,
            'condensed_assistant_response': assistant_text,
        }

    def _summarize_turn_for_compaction(
        self,
        turn: Dict[str, Any],
        max_tokens: int,
    ) -> Dict[str, str]:
        """调用模型总结单个历史 turn。"""
        request_kwargs: Dict[str, Any] = dict(
            model=self.model,
            messages=[
                {
                    'role': 'system',
                    'content': COMPACTION_SUMMARY_SYSTEM_PROMPT,
                },
                {
                    'role': 'user',
                    'content': self._build_compaction_turn_prompt(turn),
                },
            ],
            temperature=self.temperature,
            max_tokens=max_tokens,
        )
        if self.thinking_mode is not None:
            request_kwargs['thinking'] = {'type': self.thinking_mode}
        if self.reasoning_effort is not None:
            request_kwargs['reasoning_effort'] = self.reasoning_effort
        response = self.client.chat.completions.create(**request_kwargs)
        response_text = self._extract_response_text(response)
        return self._parse_compaction_response(response_text)

    def _compact_session_context(
        self,
        trigger_reason: str,
        preserve_latest_pending_user: bool = False,
    ) -> bool:
        """执行一次会话历史压缩。"""
        if not self.session_history:
            return False

        skill_items, turns, trailing_user_items = self._build_compaction_turns(
            preserve_latest_pending_user=preserve_latest_pending_user,
        )
        if not turns:
            rebuilt_history = list(skill_items) + list(trailing_user_items)
            changed = rebuilt_history != self.session_history
            if changed:
                self.session_history = rebuilt_history
                self._set_context_estimated_tokens(
                    self._estimate_next_context_tokens(),
                    suppress_warning=(trigger_reason == 'auto'),
                )
                self._notify_runtime_status()
            return changed

        before_items = list(self.session_history)
        before_counts = self._count_history_kinds(before_items)
        compacted_turns: List[Dict[str, str]] = []

        if trigger_reason == 'auto':
            self._runtime_status_note = 'Auto compacting...'
            self._notify_runtime_status()
        self._is_compacting = True
        try:
            for turn_index, turn in enumerate(turns):
                summary = self._summarize_turn_for_compaction(
                    turn,
                    max_tokens=self._get_compaction_max_tokens(turn_index, len(turns)),
                )
                compacted_turns.append(summary)
        except Exception:
            return False
        finally:
            self._is_compacting = False
            if trigger_reason == 'auto':
                self._runtime_status_note = ''

        rebuilt_history: List[Dict[str, Any]] = list(skill_items)
        for summary in compacted_turns:
            rebuilt_history.append(
                self._build_history_item(
                    kind='user_instruction',
                    api_message={
                        'role': 'user',
                        'content': summary['condensed_user_instruction'],
                    },
                )
            )
            rebuilt_history.append(
                self._build_history_item(
                    kind='assistant',
                    api_message={
                        'role': 'assistant',
                        'content': summary['condensed_assistant_response'],
                    },
                )
            )
        rebuilt_history.extend(trailing_user_items)

        changed = rebuilt_history != before_items
        self.session_history = rebuilt_history
        self.last_usage_total_tokens = None
        self._set_context_estimated_tokens(
            self._estimate_next_context_tokens(),
            suppress_warning=(trigger_reason == 'auto'),
        )
        self._notify_runtime_status()

        after_counts = self._count_history_kinds(rebuilt_history)
        self.context_logger.log_event(
            'history_compaction',
            trigger_reason=trigger_reason,
            changed=changed,
            before_message_count=len(before_items),
            after_message_count=len(rebuilt_history),
            before_turn_count=len(turns),
            after_turn_count=len(compacted_turns),
            before_screenshot_count=before_counts.get('screenshot', 0),
            after_screenshot_count=after_counts.get('screenshot', 0),
            persistent_skill_count=after_counts.get('persistent_skill', 0),
            context_estimated_tokens=self.last_context_estimated_tokens,
        )
        return changed

    def _maybe_compact_before_model_call(
        self,
        current_screenshot_item: Dict[str, Any],
    ) -> None:
        """在正式主模型调用前按阈值自动压缩历史。"""
        if not self.persistent_session or self._is_compacting:
            return

        messages, _, _, _ = self._build_request_messages(
            current_screenshot_item=current_screenshot_item,
        )
        estimated_tokens = self._estimate_context_tokens(messages)
        if estimated_tokens <= CONTEXT_COMPACTION_THRESHOLD_TOKENS:
            return

        self._compact_session_context(
            trigger_reason='auto',
            preserve_latest_pending_user=True,
        )

    def _normalize_display_info(self, display_info: Any) -> Dict[str, Any]:
        """将显示器信息标准化为日志和执行器可用的字典。"""
        if hasattr(display_info, 'to_dict'):
            payload = display_info.to_dict()
        elif isinstance(display_info, dict):
            payload = dict(display_info)
        else:
            raise ValueError(f'无法解析显示器信息: {display_info}')

        payload['index'] = int(payload.get('index', 0))
        payload['x'] = int(payload.get('x', 0))
        payload['y'] = int(payload.get('y', 0))
        payload['width'] = int(payload.get('width', 0))
        payload['height'] = int(payload.get('height', 0))
        payload['is_primary'] = bool(payload.get('is_primary', payload['index'] == 0))
        payload['bounds'] = self._display_bounds_list(payload)
        return payload

    def _display_bounds_list(self, display_info: Dict[str, Any]) -> List[int]:
        """返回 [x, y, width, height] 形式的显示器区域。"""
        return [
            int(display_info.get('x', 0)),
            int(display_info.get('y', 0)),
            int(display_info.get('width', 0)),
            int(display_info.get('height', 0)),
        ]

    def _safe_device_status(self) -> Dict[str, Any]:
        """获取设备状态；失败时回退为空字典。"""
        try:
            status = self.device.get_status()
        except Exception:
            return {}
        return dict(status or {})

    def _safe_device_target(self) -> Optional[Dict[str, Any]]:
        """返回当前设备目标摘要。"""
        target = getattr(self.device, 'target_summary', None)
        if target is None:
            return None
        if isinstance(target, dict):
            return dict(target)
        return None

    def _extract_display_info_from_frame(self, frame: DeviceFrame) -> Optional[Dict[str, Any]]:
        """从设备帧元数据中提取显示区域信息。"""
        display_info = (frame.metadata or {}).get('display')
        if not isinstance(display_info, dict):
            return self._extract_display_info_from_device_status()
        return self._normalize_display_info(display_info)

    def _extract_display_info_from_device_status(self) -> Optional[Dict[str, Any]]:
        """从设备状态中提取显示区域信息。"""
        status = self._safe_device_status()
        display_info = None
        if isinstance(status.get('display'), dict):
            display_info = status['display']
        elif {'display_index', 'display_bounds'}.issubset(status.keys()):
            bounds = status.get('display_bounds') or [0, 0, 0, 0]
            if len(bounds) == 4:
                display_info = {
                    'index': status.get('display_index', self.display_index),
                    'x': bounds[0],
                    'y': bounds[1],
                    'width': bounds[2],
                    'height': bounds[3],
                    'is_primary': status.get('display_is_primary', False),
                }
        if not isinstance(display_info, dict):
            return None
        normalized = self._normalize_display_info(display_info)
        self.display_index = int(normalized.get('index', self.display_index))
        self.device_config['display_index'] = self.display_index
        return normalized

    def _display_index_for_logging(
        self,
        device_status: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        display_info = self.current_display_info or self._extract_display_info_from_device_status()
        if display_info is not None:
            return int(display_info.get('index', 0))
        status = device_status or self._safe_device_status()
        value = status.get('display_index')
        return int(value) if value is not None else None

    def _display_bounds_for_logging(
        self,
        device_status: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[int]]:
        display_info = self.current_display_info or self._extract_display_info_from_device_status()
        if display_info is not None:
            return self._display_bounds_list(display_info)
        status = device_status or self._safe_device_status()
        bounds = status.get('display_bounds')
        if isinstance(bounds, list):
            return [int(item) for item in bounds]
        return None

    def _display_is_primary_for_logging(
        self,
        device_status: Optional[Dict[str, Any]] = None,
    ) -> Optional[bool]:
        display_info = self.current_display_info or self._extract_display_info_from_device_status()
        if display_info is not None:
            return bool(display_info.get('is_primary', False))
        status = device_status or self._safe_device_status()
        value = status.get('display_is_primary')
        return bool(value) if value is not None else None

    def set_display_index(self, display_index: int) -> Dict[str, Any]:
        """切换当前运行态目标显示器。"""
        if not self.device.supports_target_selection():
            raise ValueError(f'当前设备 {self.device_name} 不支持目标切换')
        target_index = int(display_index)
        if target_index < 0:
            raise ValueError('display_index 不能小于 0')
        display_info = self._normalize_display_info(self.device.set_target(target_index))
        self.display_index = int(display_info.get('index', target_index))
        self.device_config['display_index'] = self.display_index
        self.current_display_info = display_info
        return display_info

    def persist_display_index(self) -> str:
        """将当前目标显示器持久化到项目配置。"""
        if self.device_name != 'local':
            raise ValueError(f'当前设备 {self.device_name} 不支持持久化显示器配置')
        return config.persist_display_index(self.display_index)

    def format_effective_status(self) -> str:
        """格式化当前运行的生效参数。"""
        try:
            display_info = self.current_display_info or self._extract_display_info_from_device_status()
        except Exception:
            display_info = None

        device_status = self._safe_device_status()
        thinking_label = self.thinking_mode or 'default'
        reasoning_label = self.reasoning_effort or 'default'
        lines = [
            '[生效参数]',
            f"  模型: {self.model}",
            f"  设备: {self.device_name}",
            f"  最大步数: {self.max_steps}",
            f"  思考: {thinking_label} / {reasoning_label}",
            f"  坐标空间: {self.coordinate_space}",
        ]
        if display_info is not None:
            lines.append(f"  目标显示器: {display_info.get('index', self.display_index)}")
        if display_info is not None:
            lines.append(
                '  显示器区域: '
                f"{display_info['width']}x{display_info['height']} @ "
                f"({display_info['x']}, {display_info['y']})"
            )
        elif device_status:
            lines.append(f"  设备状态: {device_status}")
        if self.coordinate_space == 'relative':
            lines.append(f"  坐标量程: {self.coordinate_scale}")
        if self.screenshot_size is not None:
            lines.append(
                f"  模型截图尺寸: {self.screenshot_size} x {self.screenshot_size}"
            )
        lines.extend(
            [
                f"  上下文截图窗口: {self.max_context_screenshots}",
                (
                    '  成功执行反馈注入: '
                    f"{'启用' if self.include_execution_feedback else '禁用'}"
                ),
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
            )
            if self.thinking_mode is not None:
                kwargs['thinking'] = {'type': self.thinking_mode}
            if self.reasoning_effort is not None:
                kwargs['reasoning_effort'] = self.reasoning_effort
            if self.skill_tools:
                kwargs['tools'] = self.skill_tools

            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            tool_calls = getattr(choice.message, 'tool_calls', None) or []
            if getattr(choice, 'finish_reason', None) != 'tool_calls':
                # 正常文本响应，直接返回
                return response, self._extract_response_text(response)
            if not self._should_load_skills_from_tool_calls(tool_calls):
                return response, self._extract_response_text(response)

            # 模型请求加载 Skill：注入内容后重新调用
            # TODO: Level 3 — 区分 skill__ 前缀（加载指南）与 resource__/script__ 前缀
            #   （按需加载附加资源文件或执行脚本并注入输出），以支持完整的三层渐进式披露。
            messages.append(choice.message.model_dump())
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
        return response, self._extract_response_text(response) if response else ''

    def _should_load_skills_from_tool_calls(self, tool_calls: List[Any]) -> bool:
        """仅当 tool_calls 全部为 skill__ 前缀时，才进入技能加载分支。"""
        if not tool_calls:
            return False
        return all(
            str(getattr(getattr(tc, 'function', None), 'name', '')).startswith('skill__')
            for tc in tool_calls
        )

    def _extract_response_text(self, response_obj: Any) -> str:
        """提取模型可解析文本，优先 content，缺失时回退 reasoning_content。"""
        content = self._extract_message_content(response_obj)
        if content.strip():
            return content

        reasoning_content = self._extract_reasoning_content(response_obj)
        if isinstance(reasoning_content, str):
            return reasoning_content

        return ''

    def _extract_message_content(self, response_obj: Any) -> str:
        """提取模型 message.content 原文，用于日志等需要保留原始语义的场景。"""
        message = None
        choices = getattr(response_obj, 'choices', None) or []
        if choices:
            message = getattr(choices[0], 'message', None)
        if message is None:
            return ''

        content = getattr(message, 'content', None)
        if isinstance(content, str):
            return content

        return ''

    def _extract_reasoning_content(self, response_obj: Any) -> str:
        """提取模型 message.reasoning_content 原文。"""
        message = None
        choices = getattr(response_obj, 'choices', None) or []
        if choices:
            message = getattr(choices[0], 'message', None)
        if message is None:
            return ''

        reasoning_content = getattr(message, 'reasoning_content', None)
        if isinstance(reasoning_content, str):
            return reasoning_content

        return ''

    def _build_system_prompt(self) -> str:
        """构建稳定的 system prompt。若技能系统启用则追加技能说明。"""
        prompt_template = PROMPT_PROFILE_TEMPLATES.get(
            self._safe_prompt_profile(),
            COMPUTER_USE_DOUBAO,
        )
        prompt = prompt_template.format(
            instruction='',
            language=self.language,
        )
        prompt += self._build_runtime_context_prompt()
        if self.skills:
            prompt += SKILLS_PROMPT_ADDENDUM
        return prompt

    def _safe_prompt_profile(self) -> str:
        """获取设备提示词档位，异常或未知值回退到 computer。"""
        try:
            profile = self.device.get_prompt_profile()
        except Exception:
            return 'computer'

        if not isinstance(profile, str):
            return 'computer'

        normalized = profile.strip().lower()
        return normalized if normalized in PROMPT_PROFILE_TEMPLATES else 'computer'

    def _build_runtime_context_prompt(self) -> str:
        """构建注入到 system prompt 的当前运行时上下文。"""
        runtime_context = self._get_runtime_context()
        operating_system = (
            runtime_context.get('operating_system')
            or self._get_operating_system_description()
        )
        lines = [
            '',
            '## Runtime Context',
            f"- Operating system: {operating_system}",
            f"- Local timezone: {runtime_context['timezone']}",
            f"- Local date: {runtime_context['date']}",
            f"- Local weekday: {runtime_context['weekday']}",
        ]
        device_control_method = runtime_context.get('device_control_method')
        if device_control_method:
            lines.append(f'- Device control method: {device_control_method}')
        location = runtime_context.get('location')
        if location:
            lines.append(f'- Approximate location: {location}')
        return '\n'.join(lines)

    def _get_runtime_context(self) -> Dict[str, str]:
        """获取当前可注入提示词的本地时间与位置上下文。"""
        current_local_time = datetime.now().astimezone()
        timezone_name = self._get_local_timezone_name(current_local_time)
        timezone_offset = self._format_timezone_offset(current_local_time.strftime('%z'))
        timezone_display = timezone_name
        timezone_abbreviation = current_local_time.tzname()
        if timezone_abbreviation and timezone_abbreviation not in timezone_display:
            timezone_display = f'{timezone_display} ({timezone_abbreviation})'
        if timezone_offset:
            timezone_display = f'{timezone_display}, {timezone_offset}'

        device_environment = self._safe_device_environment_info()
        operating_system = (
            str(device_environment.get('operating_system') or '').strip()
            or self._get_operating_system_description()
        )

        runtime_context = {
            'operating_system': operating_system,
            'timezone': timezone_display,
            'date': current_local_time.strftime('%Y-%m-%d'),
            'weekday': current_local_time.strftime('%A'),
        }
        if self.device_control_method_description:
            runtime_context['device_control_method'] = (
                self.device_control_method_description
            )
        location = self._get_approximate_location()
        if location:
            runtime_context['location'] = location
        return runtime_context

    def _resolve_device_control_method_description(self) -> str:
        """从设备插件清单中解析当前设备的操控方式描述。"""
        try:
            plugins = discover_device_plugins([self.devices_dir] if self.devices_dir else None)
        except Exception:
            return ''

        spec = plugins.get(self.device_name)
        if spec is None:
            return ''
        return str(spec.description or '').strip()

    def _safe_device_environment_info(self) -> Dict[str, Any]:
        """获取设备环境信息；失败时回退为空。"""
        try:
            payload = self.device.get_environment_info()
        except Exception:
            return {}
        return dict(payload or {})

    def _get_local_timezone_name(self, current_local_time: datetime) -> str:
        """尽量解析稳定的 IANA 时区名，否则退回缩写。"""
        tz_env = os.getenv('TZ')
        if tz_env:
            return tz_env

        localtime_path = '/etc/localtime'
        try:
            if os.path.exists(localtime_path):
                resolved_path = os.path.realpath(localtime_path)
                marker = '/zoneinfo/'
                if marker in resolved_path:
                    return resolved_path.split(marker, 1)[1]
        except OSError:
            pass

        tzinfo = current_local_time.tzinfo
        timezone_key = getattr(tzinfo, 'key', None)
        if timezone_key:
            return timezone_key
        return current_local_time.tzname() or 'Local'

    def _format_timezone_offset(self, raw_offset: str) -> str:
        """将 +0800 格式化为 UTC+08:00。"""
        if not raw_offset or len(raw_offset) != 5:
            return ''
        return f'UTC{raw_offset[:3]}:{raw_offset[3:]}'

    def _get_operating_system_description(self) -> str:
        """返回适合注入 prompt 的人类可读操作系统描述。"""
        system_name = platform.system()

        if system_name == 'Darwin':
            macos_version = platform.mac_ver()[0]
            return f'macOS {macos_version}' if macos_version else 'macOS'

        if system_name == 'Windows':
            windows_release = platform.release()
            return f'Windows {windows_release}' if windows_release else 'Windows'

        if system_name == 'Linux':
            linux_name = self._read_linux_os_release_name()
            return linux_name or 'Linux'

        return system_name or 'Unknown'

    def _read_linux_os_release_name(self) -> Optional[str]:
        """从 /etc/os-release 读取 Linux 发行版名称。"""
        os_release_path = '/etc/os-release'
        try:
            with open(os_release_path, 'r', encoding='utf-8') as file_obj:
                for raw_line in file_obj:
                    line = raw_line.strip()
                    if line.startswith('PRETTY_NAME='):
                        return line.split('=', 1)[1].strip().strip('"')
        except OSError:
            return None

        return None

    def _get_approximate_location(self) -> Optional[str]:
        """返回可用的城镇级大致位置；当前默认不可用。"""
        return None

    def _save_debug_screenshot(self, screenshot: DeviceFrame) -> Optional[str]:
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

        if isinstance(value, (list, tuple)):
            return [self._serialize_usage_value(item) for item in value]

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

    def _build_device_command(
        self,
        action: Dict[str, Any],
        image_width: int,
        image_height: int,
        model_image_width: int,
        model_image_height: int,
    ) -> DeviceCommand:
        """构建标准化设备命令。"""
        base_command = map_action_to_command(action)
        metadata = dict(base_command.metadata or {})
        metadata.update(
            {
                'image_width': image_width,
                'image_height': image_height,
                'model_image_width': model_image_width,
                'model_image_height': model_image_height,
                'coordinate_space': self.coordinate_space,
                'coordinate_scale': self.coordinate_scale,
                'natural_scroll': self.natural_scroll,
                'verbose': self.verbose,
            }
        )
        command = DeviceCommand(
            command_type=base_command.command_type,
            payload=dict(base_command.payload or {}),
            metadata=metadata,
        )
        command = normalize_command_coordinates(
            command,
            image_width=image_width,
            image_height=image_height,
            model_image_width=model_image_width,
            model_image_height=model_image_height,
            coordinate_space=self.coordinate_space,
            coordinate_scale=self.coordinate_scale,
        )
        return normalize_scroll_direction(
            command,
            natural_scroll=self.natural_scroll,
        )

    def _build_logged_model_response(self, response_obj: Any) -> Dict[str, Any]:
        """提取方舟响应中的调试字段用于日志记录。"""
        choice = self._get_first_choice(response_obj)
        message = getattr(choice, 'message', None) if choice is not None else None
        tool_calls = getattr(message, 'tool_calls', None) if message is not None else None

        return {
            'reasoning': self._extract_reasoning_content(response_obj).strip(),
            'finish_reason': getattr(choice, 'finish_reason', None),
            'tool_calls': self._serialize_usage_value(tool_calls) if tool_calls else None,
        }

    def _get_first_choice(self, response_obj: Any) -> Optional[Any]:
        """获取响应对象中的首个 choice。"""
        choices = getattr(response_obj, 'choices', None) or []
        return choices[0] if choices else None

    def _build_screenshot_item(
        self,
        screenshot: Any,
        logged_screenshot_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构建截图历史项，分别服务于模型调用和日志落盘。"""
        if isinstance(screenshot, DeviceFrame):
            frame = screenshot
        else:
            img_buffer = io.BytesIO()
            screenshot.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            frame = DeviceFrame(
                image_data_url=(
                    'data:image/png;base64,'
                    f"{base64.b64encode(img_buffer.read()).decode('utf-8')}"
                ),
                width=int(getattr(screenshot, 'size', [0, 0])[0]),
                height=int(getattr(screenshot, 'size', [0, 0])[1]),
                metadata={},
            )
        api_message = {
            'role': 'user',
            'content': [
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': frame_to_data_url(frame)
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

    def _estimate_context_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算消息上下文占用 token 数，文本按字符数近似，截图按固定 token 数计入。"""
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

        serialized_text = json.dumps(sanitized_messages, ensure_ascii=False)
        text_tokens = len(serialized_text)
        screenshot_tokens = screenshot_count * SCREENSHOT_TOKEN_ESTIMATE
        return text_tokens + screenshot_tokens

    def _estimate_next_context_tokens(self) -> int:
        """估算下一轮模型调用会携带的上下文 token 数。"""
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
        return self._estimate_context_tokens(messages)

    def _build_runtime_status(self, elapsed_seconds: float) -> Dict[str, Any]:
        """构建供 CLI 状态栏消费的运行时状态。"""
        return {
            'usage_total_tokens': self.last_usage_total_tokens,
            'context_estimated_tokens': self.last_context_estimated_tokens,
            'activated_skills': sorted(self.activated_skills),
            'elapsed_seconds': elapsed_seconds,
            'status_note': self._get_runtime_status_note(),
        }

    def _get_runtime_status_note(self) -> str:
        """返回当前应显示在状态栏中的运行时备注。"""
        if self._runtime_status_note:
            return self._runtime_status_note
        if (
            self.persistent_session
            and not self._suppress_auto_compact_warning
            and self.last_context_estimated_tokens > CONTEXT_COMPACTION_WARNING_TOKENS
        ):
            return 'Auto compact soon'
        return ''

    def _notify_runtime_status(self, elapsed_seconds: float = 0.0) -> None:
        """向外部回调最新的运行时状态。"""
        if self.runtime_status_callback is None:
            return

        self.runtime_status_callback(
            self._build_runtime_status(elapsed_seconds=elapsed_seconds)
        )

    def _format_parse_failure_reason(self, error: Exception, response: str) -> str:
        """将解析失败原因整理成简洁单行文本。"""
        format_hint = (
            'Failed to parse Action. '
            'Reply using exactly this format: '
            'Thought: <your reasoning> '
            'Action: <one valid action call> '
            'Do not use markdown fences or extra commentary. '
            'Action must be a single function-style call such as click(...), wait(), or finished(...).'
        )
        return self._truncate_text(format_hint, max_length=500)

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
            f"Parsed Action: {parsed_action or '(unavailable)'}",
            f"Execution Status: {step_record['execution_status']}",
        ]
        if step_record['execution_status'] == 'success':
            lines.append(
                f"Execution Result: {step_record['execution_result'] or '(none)'}"
            )
        else:
            lines.append(f"Failure Reason: {step_record['failure_reason'] or '(none)'}")
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

        should_include_feedback = (
            include_feedback and (
                step_record.get('execution_status') == 'failed'
                or self.include_execution_feedback
            )
        )
        if should_include_feedback:
            feedback_message = self._build_execution_feedback_message(
                step_record,
                parsed_action,
            )
            self._append_history_item(feedback_message)
    def _set_context_estimated_tokens(
        self,
        estimated_tokens: int,
        suppress_warning: bool = False,
    ) -> None:
        """更新上下文 token 估算值，并维护自动压缩提示抑制状态。"""
        previous_tokens = self.last_context_estimated_tokens
        self.last_context_estimated_tokens = estimated_tokens
        if suppress_warning:
            self._suppress_auto_compact_warning = True
            return
        if (
            estimated_tokens <= CONTEXT_COMPACTION_WARNING_TOKENS
            or estimated_tokens > previous_tokens
        ):
            self._suppress_auto_compact_warning = False
