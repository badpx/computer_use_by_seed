import argparse
import contextlib
import importlib
import json
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .compat import ensure_supported_python
from .config import config


DEFAULT_HISTORY_FILE = Path.home() / '.computer_use_history'
CONTEXT_WINDOW_TOKENS = 256 * 1024
CONTEXT_WARNING_PERCENT = 85


def _parse_device_config_json(raw_json: str) -> Dict[str, Any]:
    """解析设备插件 JSON 配置。"""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f'设备配置 JSON 非法: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('设备配置 JSON 必须是对象')
    return payload


@dataclass
class EofConfirmationState:
    """管理交互式输入中的 Ctrl+D 二次确认退出。"""

    pending_confirmation: bool = False
    warning_message: str = '[提示] 再按一次 Ctrl+D 将退出'

    def confirm_or_raise(self) -> None:
        """首次 EOF 给出提示，连续第二次 EOF 才真正退出。"""
        if self.pending_confirmation:
            raise EOFError
        self.pending_confirmation = True
        print()
        print(self.warning_message)

    def reset(self) -> None:
        """在用户继续输入后清空退出确认状态。"""
        self.pending_confirmation = False


class InteractiveStatusBar:
    """交互模式输入栏底部状态栏。"""

    _SPINNER_FRAMES = '⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'

    def __init__(
        self,
        model: str,
        thinking_mode: str,
        reasoning_effort: str,
        total_skills: int,
    ):
        self.model = model
        self.thinking_mode = thinking_mode
        self.reasoning_effort = reasoning_effort
        self.total_skills = total_skills
        self.active_skills = 0
        self.context_percent = 0
        self.status_note = ''
        self.completed_elapsed_seconds = 0.0
        self.current_task_started_at: Optional[float] = None
        self.is_running = False
        self._spinner_index = 0

    def render(self) -> str:
        """渲染底部状态栏文本。"""
        context_icon = '🪫' if self.context_percent >= CONTEXT_WARNING_PERCENT else '🔋'
        if self.is_running:
            prefix = f"{self._SPINNER_FRAMES[self._spinner_index]} {self.model} {self.reasoning_effort}"
        else:
            prefix = f"🧠 {self.model} {self.reasoning_effort}"
        parts = [
            f"{prefix} | "
            f"{context_icon} {self.context_percent}% | "
            f"🛠️ {self.active_skills}/{self.total_skills} | "
            f"⏱️ {self._format_elapsed_time(self._current_total_elapsed_seconds())}"
        ]
        if self.status_note:
            parts.append(f" | {self.status_note}")
        return ''.join(parts)

    def update_live_status(self, runtime_status: Dict[str, Any]) -> None:
        """根据运行时状态更新状态栏。"""
        usage_total_tokens = runtime_status.get('usage_total_tokens')
        if usage_total_tokens is not None:
            try:
                used_tokens = int(usage_total_tokens)
            except (TypeError, ValueError):
                used_tokens = 0
        else:
            try:
                used_tokens = int(runtime_status.get('context_estimated_tokens') or 0)
            except (TypeError, ValueError):
                used_tokens = 0

        self.context_percent = self._to_percent(used_tokens)
        self.active_skills = len(runtime_status.get('activated_skills') or [])
        self.status_note = str(runtime_status.get('status_note') or '')

    def start_task(self) -> None:
        """标记当前任务开始。"""
        self.current_task_started_at = time.perf_counter()
        self.context_percent = 0
        self.active_skills = 0
        self.status_note = ''
        self.is_running = True
        self._spinner_index = 0

    def finish_task(self, result: Dict[str, Any]) -> None:
        """根据任务结果收尾状态栏。"""
        runtime_status = result.get('runtime_status') or {}
        self.update_live_status(runtime_status)

        elapsed_seconds = result.get('elapsed_seconds')
        try:
            if elapsed_seconds is None:
                elapsed = self._current_task_elapsed_seconds()
            else:
                elapsed = max(0.0, float(elapsed_seconds))
        except (TypeError, ValueError):
            elapsed = self._current_task_elapsed_seconds()

        self.completed_elapsed_seconds += elapsed
        self.current_task_started_at = None
        self.is_running = False

    def _current_total_elapsed_seconds(self) -> float:
        """返回当前应展示的累计耗时。"""
        return self.completed_elapsed_seconds + self._current_task_elapsed_seconds()

    def _current_task_elapsed_seconds(self) -> float:
        """返回当前正在执行任务的耗时。"""
        if self.current_task_started_at is None:
            return 0.0
        return max(0.0, time.perf_counter() - self.current_task_started_at)

    def _to_percent(self, used_tokens: int) -> int:
        """将上下文 token 数转换为百分比。"""
        percent = round(max(0, used_tokens) * 100 / CONTEXT_WINDOW_TOKENS)
        return max(0, min(100, percent))

    def _format_elapsed_time(self, elapsed_seconds: float) -> str:
        """将累计耗时格式化为分钟展示。"""
        total_seconds = max(0, int(elapsed_seconds))
        total_minutes = total_seconds // 60
        hours, minutes = divmod(total_minutes, 60)
        if hours <= 0:
            return f'{total_minutes}m'
        return f'{hours}h{minutes:02d}m'

    def advance_spinner(self) -> None:
        """推进 spinner 动画帧索引。"""
        self._spinner_index = (self._spinner_index + 1) % len(self._SPINNER_FRAMES)


class LiveStatusStreamProxy:
    """将普通 stdout/stderr 输出与底部状态线协调渲染。"""

    def __init__(self, renderer: 'LiveStatusRenderer'):
        self.renderer = renderer

    def write(self, text: str) -> int:
        self.renderer.write_output(text)
        return len(text)

    def flush(self) -> None:
        self.renderer.flush()

    def isatty(self) -> bool:
        return self.renderer.is_enabled()


class LiveStatusRenderer:
    """任务执行期间持续渲染底部状态线。"""

    def __init__(self, status_provider, stream=None, refresh_interval: float = 1.0):
        self.status_provider = status_provider
        self.stream = stream or sys.stdout
        self.refresh_interval = refresh_interval
        self._lock = threading.Lock()
        self._thread = None
        self._running = False
        self._status_visible = False

    def is_enabled(self) -> bool:
        """仅在真实 TTY 中启用状态线覆盖。"""
        isatty = getattr(self.stream, 'isatty', None)
        return bool(callable(isatty) and isatty())

    def proxy(self) -> LiveStatusStreamProxy:
        """返回给 redirect_stdout/redirect_stderr 使用的代理流。"""
        return LiveStatusStreamProxy(self)

    def start(self) -> None:
        """开始持续刷新状态线。"""
        if not self.is_enabled() or self._running:
            return

        self._running = True
        with self._lock:
            self._render_status_locked()
            self.stream.flush()
        self._thread = threading.Thread(
            target=self._refresh_loop,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """停止刷新并清理状态线。"""
        if not self._running:
            return

        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self.refresh_interval + 0.2)
            self._thread = None

        with self._lock:
            self._clear_status_locked()
            self.stream.flush()

    def write_output(self, text: str) -> None:
        """在普通输出与底部状态线之间协调写入。"""
        if not self._running:
            self.stream.write(text)
            self.stream.flush()
            return

        with self._lock:
            self._clear_status_locked()
            self.stream.write(text)
            if text and not text.endswith(('\n', '\r')):
                self.stream.write('\n')
            self._render_status_locked()
            self.stream.flush()

    def flush(self) -> None:
        """透传 flush。"""
        self.stream.flush()

    def _refresh_loop(self) -> None:
        """定时刷新状态线，以更新执行中的耗时和动画帧。"""
        while self._running:
            time.sleep(self.refresh_interval)
            if not self._running:
                break
            with self._lock:
                self._clear_status_locked()
                if hasattr(self.status_provider, 'advance_spinner'):
                    self.status_provider.advance_spinner()
                self._render_status_locked()
                self.stream.flush()

    def _render_status_locked(self) -> None:
        self.stream.write('\r\033[2K')
        self.stream.write(self.status_provider.render())
        self._status_visible = True

    def _clear_status_locked(self) -> None:
        if not self._status_visible:
            return
        self.stream.write('\r\033[2K')
        self._status_visible = False


@dataclass(frozen=True)
class InteractiveCommand:
    """交互模式本地命令定义。"""

    name: str
    handler: Callable[['InteractiveCommandContext', str], None]
    summary: str


@dataclass
class InteractiveCommandContext:
    """交互模式本地命令上下文。"""

    agent: Any
    should_exit: bool = False


def _handle_status_command(context: InteractiveCommandContext, args_text: str) -> None:
    """显示当前会话实际生效的参数。"""
    del args_text
    print()
    print(context.agent.format_effective_status())
    print()


def _handle_display_command(context: InteractiveCommandContext, args_text: str) -> None:
    """切换当前交互会话的目标显示器并持久化配置。"""
    target_text = args_text.strip()
    if not target_text:
        print()
        print('[命令错误] 用法: /display <index>')
        print()
        return

    try:
        target_index = int(target_text)
    except ValueError:
        print()
        print(f'[命令错误] 显示器编号必须是整数: {target_text}')
        print()
        return

    try:
        display_info = context.agent.set_display_index(target_index)
    except Exception as exc:
        print()
        print(f'[切换失败] {exc}')
        print()
        return

    print()
    print(
        f"[已切换] 当前目标显示器: {display_info['index']} "
        f"({display_info['width']}x{display_info['height']} @ "
        f"{display_info['x']},{display_info['y']})"
    )

    try:
        context.agent.persist_display_index()
    except Exception as exc:
        print(f'[持久化失败] 运行时已切换，但写入配置失败: {exc}')

    print()


def _handle_clear_command(context: InteractiveCommandContext, args_text: str) -> None:
    """清理当前交互会话的多轮上下文历史。"""
    del args_text
    context.agent.clear_session_context()
    print()
    print('[已清理] 多轮对话上下文历史已清空')
    print()


def _handle_compact_command(context: InteractiveCommandContext, args_text: str) -> None:
    """压缩当前交互会话的多轮上下文历史。"""
    del args_text
    print()
    print('[处理中] 正在压缩多轮对话上下文历史...')
    changed = context.agent.compact_session_context(manual=True)
    if changed:
        print('[已压缩] 多轮对话上下文历史已精炼')
    else:
        print('[无需压缩] 当前会话历史没有可压缩内容')
    print()


def _handle_exit_command(context: InteractiveCommandContext, args_text: str) -> None:
    """退出交互模式。"""
    del args_text
    context.should_exit = True
    print("\n感谢使用，再见！")


def _close_agent_quietly(agent: Any) -> None:
    """尽力关闭 agent 持有的外部资源。"""
    close = getattr(agent, 'close', None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        pass


def _build_interactive_commands() -> Dict[str, InteractiveCommand]:
    """返回交互模式支持的本地命令。"""
    return {
        '/clear': InteractiveCommand(
            name='/clear',
            handler=_handle_clear_command,
            summary='清理多轮对话上下文',
        ),
        '/compact': InteractiveCommand(
            name='/compact',
            handler=_handle_compact_command,
            summary='压缩多轮对话上下文',
        ),
        '/display': InteractiveCommand(
            name='/display',
            handler=_handle_display_command,
            summary='切换目标显示器并持久化',
        ),
        '/exit': InteractiveCommand(
            name='/exit',
            handler=_handle_exit_command,
            summary='退出交互模式',
        ),
        '/status': InteractiveCommand(
            name='/status',
            handler=_handle_status_command,
            summary='显示当前生效参数',
        ),
    }


def _create_command_completer(commands: Mapping[str, InteractiveCommand]):
    """为 slash 命令创建 prompt_toolkit 补齐器。"""
    try:
        prompt_toolkit_completion = importlib.import_module('prompt_toolkit.completion')
    except ImportError:
        return None

    completer_base_cls = prompt_toolkit_completion.Completer
    completion_cls = prompt_toolkit_completion.Completion
    command_names = tuple(sorted(commands))

    class SlashCommandCompleter(completer_base_cls):
        def get_completions(self, document, complete_event):
            del complete_event
            text_before_cursor = document.text_before_cursor
            stripped_text = text_before_cursor.lstrip()
            if not stripped_text.startswith('/'):
                return
            if ' ' in stripped_text:
                return

            for command_name in command_names:
                if command_name.startswith(stripped_text.lower()):
                    yield completion_cls(
                        command_name,
                        start_position=-len(stripped_text),
                    )

    return SlashCommandCompleter()


def _dispatch_interactive_command(
    raw_input: str,
    context: InteractiveCommandContext,
    commands: Mapping[str, InteractiveCommand],
) -> bool:
    """尝试执行交互模式本地命令。"""
    stripped = raw_input.lstrip()
    if not stripped.startswith('/'):
        return False

    command_name, _, args_text = stripped.partition(' ')
    command = commands.get(command_name.lower())
    if command is None:
        available_commands = ', '.join(sorted(commands))
        print()
        print(f"[命令错误] 未知命令: {command_name}")
        print(f"[可用命令] {available_commands}")
        print()
        return True

    command.handler(context, args_text.strip())
    return True


def _resolve_history_file(history_file: Optional[Path] = None) -> Path:
    """解析交互模式历史记录文件路径。"""
    if history_file is not None:
        return Path(history_file).expanduser()

    env_path = os.getenv('COMPUTER_USE_HISTORY_FILE')
    if env_path:
        return Path(env_path).expanduser()

    return DEFAULT_HISTORY_FILE


def _create_prompt_key_bindings():
    """为交互输入创建多行编辑按键绑定。"""
    try:
        prompt_toolkit_key_binding = importlib.import_module('prompt_toolkit.key_binding')
    except ImportError:
        return None

    key_bindings = prompt_toolkit_key_binding.KeyBindings()

    @key_bindings.add('enter', eager=True)
    def _submit_input(event):
        event.current_buffer.validate_and_handle()

    @key_bindings.add('c-j', eager=True)
    def _insert_newline_ctrl_j(event):
        event.current_buffer.insert_text('\n')

    @key_bindings.add('c-p', eager=True)
    def _auto_up_or_history_previous(event):
        event.current_buffer.auto_up(count=event.arg)

    @key_bindings.add('c-n', eager=True)
    def _auto_down_or_history_next(event):
        event.current_buffer.auto_down(count=event.arg)

    return key_bindings


def _create_prompt_session(history_file: Optional[Path] = None):
    """优先使用 prompt_toolkit 创建带文件历史的输入会话。"""
    try:
        prompt_toolkit = importlib.import_module('prompt_toolkit')
        prompt_toolkit_history = importlib.import_module('prompt_toolkit.history')
    except ImportError:
        return None

    history_path = _resolve_history_file(history_file)
    key_bindings = _create_prompt_key_bindings()
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history = prompt_toolkit_history.FileHistory(str(history_path))
        return prompt_toolkit.PromptSession(
            history=history,
            multiline=True,
            key_bindings=key_bindings,
        )
    except OSError:
        return prompt_toolkit.PromptSession(
            multiline=True,
            key_bindings=key_bindings,
        )


def _read_instruction(
    prompt_session,
    prompt_text: str = '> ',
    bottom_toolbar=None,
    completer=None,
    eof_confirmation_state: Optional[EofConfirmationState] = None,
) -> str:
    """从 prompt_toolkit 或内建 input 读取用户指令。"""
    while True:
        try:
            if prompt_session is not None:
                instruction = prompt_session.prompt(
                    prompt_text,
                    bottom_toolbar=bottom_toolbar,
                    completer=completer,
                    complete_while_typing=completer is not None,
                ).strip()
            else:
                instruction = input(prompt_text).strip()
        except EOFError:
            if eof_confirmation_state is None:
                raise
            eof_confirmation_state.confirm_or_raise()
            continue

        if eof_confirmation_state is not None:
            eof_confirmation_state.reset()
        return instruction


def _ask_user_with_cli(
    question: str,
    options: Optional[list[str]] = None,
    prompt_session=None,
    eof_confirmation_state: Optional[EofConfirmationState] = None,
) -> str:
    """在 CLI 中向用户提问并返回最终回答文本。"""
    print()
    print(f'[需要用户确认] {question}')

    if not options:
        return _read_instruction(
            prompt_session,
            prompt_text='? ',
            eof_confirmation_state=eof_confirmation_state,
        )

    display_options = [str(option).strip() for option in options if str(option).strip()]
    display_options.append('Other')

    while True:
        for index, option in enumerate(display_options, start=1):
            print(f'{index}. {option}')
        selected = _read_instruction(
            prompt_session,
            prompt_text='? ',
            eof_confirmation_state=eof_confirmation_state,
        )
        try:
            selected_index = int(selected)
        except ValueError:
            print('[输入无效] 请输入选项编号')
            continue

        if selected_index < 1 or selected_index > len(display_options):
            print('[输入无效] 请输入有效的选项编号')
            continue

        chosen_option = display_options[selected_index - 1]
        if chosen_option != 'Other':
            return chosen_option

        return _read_instruction(
            prompt_session,
            prompt_text='> ',
            eof_confirmation_state=eof_confirmation_state,
        )


def _build_cli_ask_user_callback(
    prompt_session=None,
    active_renderer: Optional[Dict[str, Optional['LiveStatusRenderer']]] = None,
    eof_confirmation_state: Optional[EofConfirmationState] = None,
) -> Callable[[str, Optional[list[str]]], str]:
    """构造供 CLI 模式使用的 ask_user 回调。"""
    renderer_state = active_renderer or {'renderer': None}

    def ask_user_callback(question: str, options: Optional[list[str]] = None) -> str:
        renderer = renderer_state['renderer']
        if renderer is not None:
            renderer.stop()
        try:
            with contextlib.redirect_stdout(sys.__stdout__), contextlib.redirect_stderr(sys.__stderr__):
                return _ask_user_with_cli(
                    question=question,
                    options=options,
                    prompt_session=prompt_session,
                    eof_confirmation_state=eof_confirmation_state,
                )
        finally:
            if renderer is not None:
                renderer.start()

    return ask_user_callback


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════╗
║              Computer Use Tool - 本地 GUI 自动化         ║
║                     Powered by OpenAI SDK               ║
╚══════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_config_info(
    log_full_messages: bool = False,
    screenshot_size: Optional[int] = None,
    display_index: Optional[int] = None,
    device_name: Optional[str] = None,
):
    """打印调试用配置信息。"""
    print("[配置信息]")
    print(f"  Provider: {config.provider}")
    print(f"  API地址: {config.base_url}")
    effective_device_name = config.device_name if device_name is None else device_name
    print(f"  设备: {effective_device_name}")
    effective_display_index = (
        config.display_index if display_index is None else display_index
    )
    print(f"  目标显示器: {effective_display_index}")
    effective_screenshot_size = (
        config.screenshot_size if screenshot_size is None else screenshot_size
    )
    if effective_screenshot_size is not None:
        print(f"  模型截图尺寸: {effective_screenshot_size} x {effective_screenshot_size}")
    print(f"  上下文日志: {'是' if config.save_context_log else '否'}")
    print(f"  日志目录: {config.context_log_dir}")
    print(f"  完整上下文日志: {'是' if log_full_messages else '否'}")
    if log_full_messages and config.save_context_log:
        print(f"  调试截图目录: {Path(config.context_log_dir) / 'screenshots'}")
    print()


def interactive_mode(
    model: Optional[str] = None,
    max_steps: Optional[int] = None,
    stream: Optional[bool] = None,
    thinking_mode: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    coordinate_space: Optional[str] = None,
    coordinate_scale: Optional[float] = None,
    screenshot_size: Optional[int] = None,
    max_context_screenshots: Optional[int] = None,
    display_index: Optional[int] = None,
    device_name: Optional[str] = None,
    device_config: Optional[Dict[str, Any]] = None,
    devices_dir: Optional[str] = None,
    include_execution_feedback: Optional[bool] = None,
    log_full_messages: bool = False,
    natural_scroll: Optional[bool] = None,
    skills_dir: Optional[str] = None,
    enable_skills: Optional[bool] = None,
    verbose: bool = True
):
    """
    交互式模式
    
    Args:
        model: 模型名称
        max_steps: 最大执行步数
        stream: 是否启用流式响应
        thinking_mode: 模型思考模式
        reasoning_effort: 模型思考档位
        coordinate_space: 坐标空间
        coordinate_scale: 相对坐标量程
        screenshot_size: 传给模型前的截图缩放尺寸
        max_context_screenshots: 多轮上下文截图窗口
        display_index: 目标显示器编号
        include_execution_feedback: 是否注入成功执行反馈
        log_full_messages: 是否在上下文日志中记录完整 messages
        natural_scroll: 是否使用自然滚动
        verbose: 是否打印详细日志
    """
    print_banner()
    if log_full_messages:
        print_config_info(
            log_full_messages=log_full_messages,
            screenshot_size=screenshot_size,
            display_index=display_index,
            device_name=device_name,
        )
    
    print("[交互模式]")
    print("请输入您的指令（输入 '/exit' 退出）\n")

    ensure_supported_python()
    from .agent import ComputerUseAgent
    prompt_session = _create_prompt_session()

    if verbose and prompt_session is None:
        print("[提示] 未检测到 prompt_toolkit，回退到基础输入模式")
        print()

    active_renderer: Dict[str, Optional[LiveStatusRenderer]] = {'renderer': None}
    eof_confirmation_state = EofConfirmationState()
    ask_user_callback = _build_cli_ask_user_callback(
        prompt_session=prompt_session,
        active_renderer=active_renderer,
        eof_confirmation_state=eof_confirmation_state,
    )

    # 初始化代理
    agent = None
    try:
        agent = ComputerUseAgent(
            model=model,
            max_steps=max_steps,
            stream=stream,
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
            coordinate_space=coordinate_space,
            coordinate_scale=coordinate_scale,
            screenshot_size=screenshot_size,
            max_context_screenshots=max_context_screenshots,
            display_index=display_index,
            device_name=device_name,
            device_config=device_config,
            devices_dir=devices_dir,
            include_execution_feedback=include_execution_feedback,
            log_full_messages=log_full_messages,
            natural_scroll=natural_scroll,
            skills_dir=skills_dir,
            enable_skills=enable_skills,
            verbose=verbose,
            print_init_status=False,
            persistent_session=True,
            runtime_status_callback=None,
            ask_user_callback=ask_user_callback,
        )
    except Exception as e:
        print(f"[错误] 初始化失败: {e}")
        return

    status_bar = None
    commands = _build_interactive_commands()
    command_context = InteractiveCommandContext(agent=agent)
    command_completer = _create_command_completer(commands) if prompt_session is not None else None
    if prompt_session is not None:
        status_bar = InteractiveStatusBar(
            model=getattr(agent, 'model', config.model),
            thinking_mode=(getattr(agent, 'thinking_mode', None) or 'default'),
            reasoning_effort=(getattr(agent, 'reasoning_effort', None) or 'default'),
            total_skills=len(getattr(agent, 'skills', [])),
        )
        agent.runtime_status_callback = status_bar.update_live_status

    try:
        while True:
            try:
                # 获取用户输入
                instruction = _read_instruction(
                    prompt_session,
                    bottom_toolbar=status_bar.render if status_bar is not None else None,
                    completer=command_completer,
                    eof_confirmation_state=eof_confirmation_state,
                )
                
                if _dispatch_interactive_command(
                    instruction,
                    context=command_context,
                    commands=commands,
                ):
                    if command_context.should_exit:
                        break
                    continue
                
                # 跳过空输入
                if not instruction:
                    continue
                
                # 执行任务
                print(f"\n[开始执行] {instruction}")
                if status_bar is not None:
                    status_bar.start_task()
                renderer = LiveStatusRenderer(status_bar) if status_bar is not None else None
                active_renderer['renderer'] = renderer
                if renderer is not None:
                    renderer.start()
                try:
                    if renderer is not None and renderer.is_enabled():
                        proxy = renderer.proxy()
                        with contextlib.redirect_stdout(proxy), contextlib.redirect_stderr(proxy):
                            result = agent.run(instruction)
                    else:
                        result = agent.run(instruction)
                finally:
                    active_renderer['renderer'] = None
                    if renderer is not None:
                        renderer.stop()
                if status_bar is not None:
                    status_bar.finish_task(result)
                
                # 显示结果
                if result['success']:
                    print(
                        f"\n[执行成功] 共执行 {len(result['steps'])} 步，"
                        f"总耗时 {result.get('elapsed_time_text', '未知')}"
                    )
                    if result['final_response']:
                        print(f"[最终回复] {result['final_response']}")
                else:
                    print(
                        f"\n[执行失败] {result.get('error', '未知错误')}，"
                        f"总耗时 {result.get('elapsed_time_text', '未知')}"
                    )
                
                print()
                
            except KeyboardInterrupt:
                if status_bar is not None:
                    status_bar.is_running = False
                print("\n\n[中断] 用户取消操作")
                continue
            except EOFError:
                print("\n感谢使用，再见！")
                break
            except Exception as e:
                print(f"\n[错误] {e}")
                continue
    finally:
        if agent is not None:
            _close_agent_quietly(agent)


def single_task_mode(
    instruction: str,
    model: Optional[str] = None,
    max_steps: Optional[int] = None,
    stream: Optional[bool] = None,
    thinking_mode: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    coordinate_space: Optional[str] = None,
    coordinate_scale: Optional[float] = None,
    screenshot_size: Optional[int] = None,
    max_context_screenshots: Optional[int] = None,
    display_index: Optional[int] = None,
    device_name: Optional[str] = None,
    device_config: Optional[Dict[str, Any]] = None,
    devices_dir: Optional[str] = None,
    include_execution_feedback: Optional[bool] = None,
    log_full_messages: bool = False,
    natural_scroll: Optional[bool] = None,
    skills_dir: Optional[str] = None,
    enable_skills: Optional[bool] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    单次任务模式
    
    Args:
        instruction: 任务指令
        model: 模型名称
        max_steps: 最大执行步数
        stream: 是否启用流式响应
        thinking_mode: 模型思考模式
        reasoning_effort: 模型思考档位
        coordinate_space: 坐标空间
        coordinate_scale: 相对坐标量程
        screenshot_size: 传给模型前的截图缩放尺寸
        max_context_screenshots: 多轮上下文截图窗口
        display_index: 目标显示器编号
        include_execution_feedback: 是否注入成功执行反馈
        log_full_messages: 是否在上下文日志中记录完整 messages
        natural_scroll: 是否使用自然滚动
        verbose: 是否打印详细日志
        
    Returns:
        Dict[str, Any]: 执行结果
    """
    if verbose:
        print_banner()
        if log_full_messages:
            print_config_info(
                log_full_messages=log_full_messages,
                screenshot_size=screenshot_size,
                display_index=display_index,
                device_name=device_name,
            )
        print(f"[任务] {instruction}\n")

    ensure_supported_python()
    from .agent import ComputerUseAgent
    ask_user_callback = None
    if config.enable_ask_user_for_single_task:
        prompt_session = _create_prompt_session()
        if verbose and prompt_session is None:
            print("[提示] 未检测到 prompt_toolkit，回退到基础输入模式")
            print()
        ask_user_callback = _build_cli_ask_user_callback(
            prompt_session=prompt_session,
            eof_confirmation_state=EofConfirmationState(),
        )
    
    # 初始化代理
    agent = ComputerUseAgent(
        model=model,
        max_steps=max_steps,
        stream=stream,
        thinking_mode=thinking_mode,
        reasoning_effort=reasoning_effort,
        coordinate_space=coordinate_space,
        coordinate_scale=coordinate_scale,
        screenshot_size=screenshot_size,
        max_context_screenshots=max_context_screenshots,
        display_index=display_index,
        device_name=device_name,
        device_config=device_config,
        devices_dir=devices_dir,
        include_execution_feedback=include_execution_feedback,
        log_full_messages=log_full_messages,
        natural_scroll=natural_scroll,
        skills_dir=skills_dir,
        enable_skills=enable_skills,
        verbose=verbose,
        print_init_status=True,
        persistent_session=False,
        ask_user_callback=ask_user_callback,
    )

    # 执行任务
    try:
        result = agent.run(instruction)
    finally:
        _close_agent_quietly(agent)
    
    if verbose:
        print()
        if result['success']:
            print(
                f"[成功] 任务完成，共执行 {len(result['steps'])} 步，"
                f"总耗时 {result.get('elapsed_time_text', '未知')}"
            )
        else:
            print(
                f"[失败] {result.get('error', '未知错误')}，"
                f"总耗时 {result.get('elapsed_time_text', '未知')}"
            )
    
    return result


def main():
    """主入口函数"""
    ensure_supported_python()

    parser = argparse.ArgumentParser(
        description='Computer Use Tool - 本地 GUI 自动化工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 交互模式
  python -m computer_use
  
  # 单次任务
  python -m computer_use "打开浏览器"
  
  # 指定模型和参数
  python -m computer_use "打开微信" --model doubao-seed-1-6-vision-250815 --max-steps 10
        """
    )
    
    # 位置参数：指令
    parser.add_argument(
        'instruction',
        nargs='?',
        help='任务指令（如果不提供则进入交互模式）'
    )
    
    # 可选参数
    parser.add_argument(
        '--model',
        '-m',
        help='模型名称（默认从配置读取）'
    )
    
    parser.add_argument(
        '--max-steps',
        '-s',
        type=int,
        help='最大执行步数（默认从配置读取）'
    )

    stream_group = parser.add_mutually_exclusive_group()
    stream_group.add_argument(
        '--stream',
        action='store_true',
        help='启用模型流式响应参数'
    )
    stream_group.add_argument(
        '--no-stream',
        action='store_true',
        help='禁用模型流式响应参数'
    )

    parser.add_argument(
        '--thinking',
        '-t',
        choices=['enabled', 'disabled', 'auto'],
        help='设置模型思考模式：enabled / disabled / auto（默认从配置读取）'
    )

    parser.add_argument(
        '--reasoning-effort',
        '-r',
        choices=['low', 'medium', 'high'],
        help='设置模型思考档位：low / medium / high（默认从配置读取）'
    )

    parser.add_argument(
        '--coordinate-space',
        choices=['relative', 'pixel'],
        help='设置坐标空间：relative / pixel（默认从配置读取）'
    )

    parser.add_argument(
        '--coordinate-scale',
        type=float,
        help='设置 relative 坐标的量程，例如 1 / 100 / 1000（默认从配置读取）'
    )

    parser.add_argument(
        '--screenshot-size',
        type=int,
        help='设置传给模型的截图宽高，仅支持正方形缩放，例如 1024 表示 1024x1024'
    )

    parser.add_argument(
        '--max-context-screenshots',
        type=int,
        help='多轮上下文中最多保留的截图数量（包含当前轮，默认从配置读取）'
    )

    parser.add_argument(
        '--display-index',
        type=int,
        help='设置目标显示器编号，0 表示主显示器（默认从配置读取）'
    )

    parser.add_argument(
        '--device',
        help='设置设备插件名称（默认从配置读取）'
    )

    parser.add_argument(
        '--device-config-json',
        help='设置设备插件私有 JSON 配置（默认从配置读取）'
    )

    parser.add_argument(
        '--devices-dir',
        help='设置外部设备插件目录（默认从配置读取）'
    )

    execution_feedback_group = parser.add_mutually_exclusive_group()
    execution_feedback_group.add_argument(
        '--include-execution-feedback',
        action='store_true',
        help='启用成功执行反馈注入'
    )
    execution_feedback_group.add_argument(
        '--no-execution-feedback',
        action='store_true',
        help='禁用成功执行反馈注入'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='在上下文日志中记录完整 messages，并将截图保存到 CONTEXT_LOG_DIR/screenshots/'
    )

    scroll_group = parser.add_mutually_exclusive_group()
    scroll_group.add_argument(
        '--natural-scroll',
        action='store_true',
        help='启用自然滚动方向'
    )
    scroll_group.add_argument(
        '--traditional-scroll',
        action='store_true',
        help='启用传统滚动方向'
    )

    parser.add_argument(
        '--skills-dir',
        help='技能目录路径（默认从配置读取）'
    )

    skills_group = parser.add_mutually_exclusive_group()
    skills_group.add_argument(
        '--enable-skills',
        action='store_true',
        help='启用技能系统'
    )
    skills_group.add_argument(
        '--no-skills',
        action='store_true',
        help='禁用技能系统'
    )

    parser.add_argument(
        '--quiet',
        '-q',
        action='store_true',
        help='安静模式，减少输出'
    )
    
    parser.add_argument(
        '--version',
        '-v',
        action='version',
        version='%(prog)s 1.0.0'
    )
    
    # 解析参数
    args = parser.parse_args()
    
    # 确定运行模式
    verbose = not args.quiet
    natural_scroll = None
    stream = None
    thinking_mode = None
    reasoning_effort = None
    coordinate_space = None
    coordinate_scale = None
    screenshot_size = None
    max_context_screenshots = None
    display_index = None
    device_name = None
    device_config = None
    devices_dir = None
    include_execution_feedback = None
    log_full_messages = args.verbose
    if args.natural_scroll:
        natural_scroll = True
    elif args.traditional_scroll:
        natural_scroll = False
    if args.stream:
        stream = True
    elif args.no_stream:
        stream = False

    if args.thinking:
        thinking_mode = args.thinking
    if args.reasoning_effort:
        reasoning_effort = args.reasoning_effort
    if args.coordinate_space:
        coordinate_space = args.coordinate_space
    if args.coordinate_scale is not None:
        coordinate_scale = args.coordinate_scale
    if args.screenshot_size is not None:
        screenshot_size = args.screenshot_size
    if args.max_context_screenshots is not None:
        max_context_screenshots = args.max_context_screenshots
    if args.display_index is not None:
        display_index = args.display_index
    if args.device:
        device_name = args.device
    if args.device_config_json:
        device_config = _parse_device_config_json(args.device_config_json)
    if args.devices_dir:
        devices_dir = args.devices_dir
    if args.include_execution_feedback:
        include_execution_feedback = True
    elif args.no_execution_feedback:
        include_execution_feedback = False

    skills_dir = args.skills_dir or None
    enable_skills: Optional[bool] = None
    if args.enable_skills:
        enable_skills = True
    elif args.no_skills:
        enable_skills = False

    try:
        if args.instruction:
            # 单次任务模式
            result = single_task_mode(
                instruction=args.instruction,
                model=args.model,
                max_steps=args.max_steps,
                stream=stream,
                thinking_mode=thinking_mode,
                reasoning_effort=reasoning_effort,
                coordinate_space=coordinate_space,
                coordinate_scale=coordinate_scale,
                screenshot_size=screenshot_size,
                max_context_screenshots=max_context_screenshots,
                display_index=display_index,
                device_name=device_name,
                device_config=device_config,
                devices_dir=devices_dir,
                include_execution_feedback=include_execution_feedback,
                log_full_messages=log_full_messages,
                natural_scroll=natural_scroll,
                skills_dir=skills_dir,
                enable_skills=enable_skills,
                verbose=verbose
            )
            
            # 根据结果设置退出码
            sys.exit(0 if result['success'] else 1)
        else:
            # 交互模式
            interactive_mode(
                model=args.model,
                max_steps=args.max_steps,
                stream=stream,
                thinking_mode=thinking_mode,
                reasoning_effort=reasoning_effort,
                coordinate_space=coordinate_space,
                coordinate_scale=coordinate_scale,
                screenshot_size=screenshot_size,
                max_context_screenshots=max_context_screenshots,
                display_index=display_index,
                device_name=device_name,
                device_config=device_config,
                devices_dir=devices_dir,
                include_execution_feedback=include_execution_feedback,
                log_full_messages=log_full_messages,
                natural_scroll=natural_scroll,
                skills_dir=skills_dir,
                enable_skills=enable_skills,
                verbose=verbose
            )
    
    except KeyboardInterrupt:
        if verbose:
            print("\n\n[退出] 用户中断")
        sys.exit(130)
    except EOFError:
        print("\n感谢使用，再见！")
        sys.exit(0)
    except Exception as e:
        print(f"\n[错误] {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
