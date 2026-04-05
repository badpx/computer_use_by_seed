import argparse
import contextlib
import importlib
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .compat import ensure_supported_python
from .config import config


DEFAULT_HISTORY_FILE = Path.home() / '.computer_use_history'
CONTEXT_WINDOW_BYTES = 256 * 1024
TOKEN_ESTIMATE_BYTES = 4


class InteractiveStatusBar:
    """交互模式输入栏底部状态栏。"""

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
        self.completed_elapsed_seconds = 0.0
        self.current_task_started_at: Optional[float] = None

    def render(self) -> str:
        """渲染底部状态栏文本。"""
        return (
            f"{self.model} {self.reasoning_effort} | "
            f"Context: {self.context_percent}% | "
            f"Skills: {self.active_skills}/{self.total_skills} | "
            f"Duration: {self._format_elapsed_time(self._current_total_elapsed_seconds())}"
        )

    def update_live_status(self, runtime_status: Dict[str, Any]) -> None:
        """根据运行时状态更新状态栏。"""
        usage_total_tokens = runtime_status.get('usage_total_tokens')
        if usage_total_tokens is not None:
            try:
                used_bytes = int(usage_total_tokens) * TOKEN_ESTIMATE_BYTES
            except (TypeError, ValueError):
                used_bytes = 0
        else:
            try:
                used_bytes = int(runtime_status.get('context_estimated_bytes') or 0)
            except (TypeError, ValueError):
                used_bytes = 0

        self.context_percent = self._to_percent(used_bytes)
        self.active_skills = len(runtime_status.get('activated_skills') or [])

    def start_task(self) -> None:
        """标记当前任务开始。"""
        self.current_task_started_at = time.perf_counter()
        self.context_percent = 0
        self.active_skills = 0

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

    def _current_total_elapsed_seconds(self) -> float:
        """返回当前应展示的累计耗时。"""
        return self.completed_elapsed_seconds + self._current_task_elapsed_seconds()

    def _current_task_elapsed_seconds(self) -> float:
        """返回当前正在执行任务的耗时。"""
        if self.current_task_started_at is None:
            return 0.0
        return max(0.0, time.perf_counter() - self.current_task_started_at)

    def _to_percent(self, used_bytes: int) -> int:
        """将上下文字节数转换为百分比。"""
        percent = round(max(0, used_bytes) * 100 / CONTEXT_WINDOW_BYTES)
        return max(0, min(100, percent))

    def _format_elapsed_time(self, elapsed_seconds: float) -> str:
        """将累计耗时格式化为 HH:MM:SS。"""
        total_seconds = max(0, int(elapsed_seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


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
        """定时刷新状态线，以更新执行中的耗时。"""
        while self._running:
            time.sleep(self.refresh_interval)
            if not self._running:
                break
            with self._lock:
                self._clear_status_locked()
                self._render_status_locked()
                self.stream.flush()

    def _render_status_locked(self) -> None:
        self.stream.write('\r\033[2K')
        self.stream.write(self.status_provider())
        self._status_visible = True

    def _clear_status_locked(self) -> None:
        if not self._status_visible:
            return
        self.stream.write('\r\033[2K')
        self._status_visible = False


def _resolve_history_file(history_file: Optional[Path] = None) -> Path:
    """解析交互模式历史记录文件路径。"""
    if history_file is not None:
        return Path(history_file).expanduser()

    env_path = os.getenv('COMPUTER_USE_HISTORY_FILE')
    if env_path:
        return Path(env_path).expanduser()

    return DEFAULT_HISTORY_FILE


def _create_prompt_session(history_file: Optional[Path] = None):
    """优先使用 prompt_toolkit 创建带文件历史的输入会话。"""
    try:
        prompt_toolkit = importlib.import_module('prompt_toolkit')
        prompt_toolkit_history = importlib.import_module('prompt_toolkit.history')
    except ImportError:
        return None

    history_path = _resolve_history_file(history_file)
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history = prompt_toolkit_history.FileHistory(str(history_path))
        return prompt_toolkit.PromptSession(history=history)
    except OSError:
        return prompt_toolkit.PromptSession()


def _read_instruction(
    prompt_session,
    prompt_text: str = '> ',
    bottom_toolbar=None,
) -> str:
    """从 prompt_toolkit 或内建 input 读取用户指令。"""
    if prompt_session is not None:
        return prompt_session.prompt(
            prompt_text,
            bottom_toolbar=bottom_toolbar,
        ).strip()

    return input(prompt_text).strip()


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════╗
║              Computer Use Tool - 本地 GUI 自动化         ║
║                     Powered by 火山方舟                  ║
╚══════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_config_info(
    log_full_messages: bool = False,
    screenshot_size: Optional[int] = None,
):
    """打印调试用配置信息。"""
    print("[配置信息]")
    print(f"  API地址: {config.base_url}")
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
    thinking_mode: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    coordinate_space: Optional[str] = None,
    coordinate_scale: Optional[float] = None,
    screenshot_size: Optional[int] = None,
    max_context_screenshots: Optional[int] = None,
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
        thinking_mode: 方舟思考模式
        reasoning_effort: 方舟思考档位
        coordinate_space: 坐标空间
        coordinate_scale: 相对坐标量程
        screenshot_size: 传给模型前的截图缩放尺寸
        max_context_screenshots: 多轮上下文截图窗口
        include_execution_feedback: 是否注入执行反馈
        log_full_messages: 是否在上下文日志中记录完整 messages
        natural_scroll: 是否使用自然滚动
        verbose: 是否打印详细日志
    """
    print_banner()
    if log_full_messages:
        print_config_info(
            log_full_messages=log_full_messages,
            screenshot_size=screenshot_size,
        )
    
    print("[交互模式]")
    print("请输入您的指令（输入 'quit' 或 'exit' 退出）\n")

    ensure_supported_python()
    from .agent import ComputerUseAgent
    prompt_session = _create_prompt_session()

    if verbose and prompt_session is None:
        print("[提示] 未检测到 prompt_toolkit，回退到基础输入模式")
        print()

    # 初始化代理
    try:
        agent = ComputerUseAgent(
            model=model,
            max_steps=max_steps,
            thinking_mode=thinking_mode,
            reasoning_effort=reasoning_effort,
            coordinate_space=coordinate_space,
            coordinate_scale=coordinate_scale,
            screenshot_size=screenshot_size,
            max_context_screenshots=max_context_screenshots,
            include_execution_feedback=include_execution_feedback,
            log_full_messages=log_full_messages,
            natural_scroll=natural_scroll,
            skills_dir=skills_dir,
            enable_skills=enable_skills,
            verbose=verbose,
            runtime_status_callback=None,
        )
    except Exception as e:
        print(f"[错误] 初始化失败: {e}")
        return

    status_bar = None
    if prompt_session is not None:
        status_bar = InteractiveStatusBar(
            model=getattr(agent, 'model', config.model),
            thinking_mode=getattr(agent, 'thinking_mode', config.thinking_mode),
            reasoning_effort=getattr(agent, 'reasoning_effort', config.reasoning_effort),
            total_skills=len(getattr(agent, 'skills', [])),
        )
        agent.runtime_status_callback = status_bar.update_live_status
    
    while True:
        try:
            # 获取用户输入
            instruction = _read_instruction(
                prompt_session,
                bottom_toolbar=status_bar.render if status_bar is not None else None,
            )
            
            # 检查退出命令
            if instruction.lower() in ['quit', 'exit', 'q']:
                print("\n感谢使用，再见！")
                break
            
            # 跳过空输入
            if not instruction:
                continue
            
            # 执行任务
            print(f"\n[开始执行] {instruction}")
            if status_bar is not None:
                status_bar.start_task()
            renderer = LiveStatusRenderer(status_bar.render) if status_bar is not None else None
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
            print("\n\n[中断] 用户取消操作")
            continue
        except EOFError:
            print("\n感谢使用，再见！")
            break
        except Exception as e:
            print(f"\n[错误] {e}")
            continue


def single_task_mode(
    instruction: str,
    model: Optional[str] = None,
    max_steps: Optional[int] = None,
    thinking_mode: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    coordinate_space: Optional[str] = None,
    coordinate_scale: Optional[float] = None,
    screenshot_size: Optional[int] = None,
    max_context_screenshots: Optional[int] = None,
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
        thinking_mode: 方舟思考模式
        reasoning_effort: 方舟思考档位
        coordinate_space: 坐标空间
        coordinate_scale: 相对坐标量程
        screenshot_size: 传给模型前的截图缩放尺寸
        max_context_screenshots: 多轮上下文截图窗口
        include_execution_feedback: 是否注入执行反馈
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
            )
        print(f"[任务] {instruction}\n")

    ensure_supported_python()
    from .agent import ComputerUseAgent
    
    # 初始化代理
    agent = ComputerUseAgent(
        model=model,
        max_steps=max_steps,
        thinking_mode=thinking_mode,
        reasoning_effort=reasoning_effort,
        coordinate_space=coordinate_space,
        coordinate_scale=coordinate_scale,
        screenshot_size=screenshot_size,
        max_context_screenshots=max_context_screenshots,
        include_execution_feedback=include_execution_feedback,
        log_full_messages=log_full_messages,
        natural_scroll=natural_scroll,
        skills_dir=skills_dir,
        enable_skills=enable_skills,
        verbose=verbose
    )

    # 执行任务
    result = agent.run(instruction)
    
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

    parser.add_argument(
        '--thinking',
        '-t',
        choices=['enabled', 'disabled', 'auto'],
        help='设置方舟思考模式：enabled / disabled / auto（默认从配置读取）'
    )

    parser.add_argument(
        '--reasoning-effort',
        '-r',
        choices=['minimal', 'low', 'medium', 'high'],
        help='设置方舟思考档位：minimal / low / medium / high（默认从配置读取）'
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

    execution_feedback_group = parser.add_mutually_exclusive_group()
    execution_feedback_group.add_argument(
        '--include-execution-feedback',
        action='store_true',
        help='启用执行反馈注入'
    )
    execution_feedback_group.add_argument(
        '--no-execution-feedback',
        action='store_true',
        help='禁用执行反馈注入'
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
    thinking_mode = None
    reasoning_effort = None
    coordinate_space = None
    coordinate_scale = None
    screenshot_size = None
    max_context_screenshots = None
    include_execution_feedback = None
    log_full_messages = args.verbose
    if args.natural_scroll:
        natural_scroll = True
    elif args.traditional_scroll:
        natural_scroll = False

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
                thinking_mode=thinking_mode,
                reasoning_effort=reasoning_effort,
                coordinate_space=coordinate_space,
                coordinate_scale=coordinate_scale,
                screenshot_size=screenshot_size,
                max_context_screenshots=max_context_screenshots,
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
                thinking_mode=thinking_mode,
                reasoning_effort=reasoning_effort,
                coordinate_space=coordinate_space,
                coordinate_scale=coordinate_scale,
                screenshot_size=screenshot_size,
                max_context_screenshots=max_context_screenshots,
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
    except Exception as e:
        if verbose:
            print(f"\n[错误] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
