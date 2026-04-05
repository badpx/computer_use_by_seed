import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .compat import ensure_supported_python
from .config import config


DEFAULT_HISTORY_FILE = Path.home() / '.computer_use_history'


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


def _read_instruction(prompt_session, prompt_text: str = '> ') -> str:
    """从 prompt_toolkit 或内建 input 读取用户指令。"""
    if prompt_session is not None:
        return prompt_session.prompt(prompt_text).strip()

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
    enable_skills: Optional[bool] = None,
    skill_paths: Optional[List[str]] = None,
):
    """打印调试用配置信息。"""
    print("[配置信息]")
    print(f"  API地址: {config.base_url}")
    effective_screenshot_size = (
        config.screenshot_size if screenshot_size is None else screenshot_size
    )
    if effective_screenshot_size is not None:
        print(f"  模型截图尺寸: {effective_screenshot_size} x {effective_screenshot_size}")
    save_screenshot = config.save_screenshot
    print(f"  保存截图: {'是' if save_screenshot else '否'}")
    if save_screenshot:
        print(f"  截图目录: {config.screenshot_dir}")
    print(f"  上下文日志: {'是' if config.save_context_log else '否'}")
    print(f"  日志目录: {config.context_log_dir}")
    print(f"  完整上下文日志: {'是' if log_full_messages else '否'}")
    effective_skills = config.enable_skills if enable_skills is None else enable_skills
    print(f"  Skills: {'是' if effective_skills else '否'}")
    effective_skill_paths = config.skill_paths if skill_paths is None else skill_paths
    if effective_skills:
        print(f"  Skills目录: {', '.join(effective_skill_paths) if effective_skill_paths else '(空)'}")
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
    enable_skills: Optional[bool] = None,
    skill_paths: Optional[List[str]] = None,
    max_candidate_skills: Optional[int] = None,
    max_skill_tool_rounds: Optional[int] = None,
    log_full_messages: bool = False,
    natural_scroll: Optional[bool] = None,
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
        enable_skills: 是否启用 skills
        skill_paths: skills 搜索路径
        max_candidate_skills: 候选 skills 上限
        max_skill_tool_rounds: 单步 skill tool 调用轮数上限
        log_full_messages: 是否在上下文日志中记录完整 messages
        natural_scroll: 是否使用自然滚动
        verbose: 是否打印详细日志
    """
    print_banner()
    if log_full_messages:
        print_config_info(
            log_full_messages=log_full_messages,
            screenshot_size=screenshot_size,
            enable_skills=enable_skills,
            skill_paths=skill_paths,
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
            enable_skills=enable_skills,
            skill_paths=skill_paths,
            max_candidate_skills=max_candidate_skills,
            max_skill_tool_rounds=max_skill_tool_rounds,
            log_full_messages=log_full_messages,
            natural_scroll=natural_scroll,
            verbose=verbose
        )
    except Exception as e:
        print(f"[错误] 初始化失败: {e}")
        return
    
    while True:
        try:
            # 获取用户输入
            instruction = _read_instruction(prompt_session)
            
            # 检查退出命令
            if instruction.lower() in ['quit', 'exit', 'q']:
                print("\n感谢使用，再见！")
                break
            
            # 跳过空输入
            if not instruction:
                continue
            
            # 执行任务
            print(f"\n[开始执行] {instruction}")
            result = agent.run(instruction)
            
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
    enable_skills: Optional[bool] = None,
    skill_paths: Optional[List[str]] = None,
    max_candidate_skills: Optional[int] = None,
    max_skill_tool_rounds: Optional[int] = None,
    log_full_messages: bool = False,
    natural_scroll: Optional[bool] = None,
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
        enable_skills: 是否启用 skills
        skill_paths: skills 搜索路径
        max_candidate_skills: 候选 skills 上限
        max_skill_tool_rounds: 单步 skill tool 调用轮数上限
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
                enable_skills=enable_skills,
                skill_paths=skill_paths,
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
        enable_skills=enable_skills,
        skill_paths=skill_paths,
        max_candidate_skills=max_candidate_skills,
        max_skill_tool_rounds=max_skill_tool_rounds,
        log_full_messages=log_full_messages,
        natural_scroll=natural_scroll,
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

    skills_group = parser.add_mutually_exclusive_group()
    skills_group.add_argument(
        '--skills',
        action='store_true',
        help='启用 skills'
    )
    skills_group.add_argument(
        '--no-skills',
        action='store_true',
        help='禁用 skills'
    )

    parser.add_argument(
        '--skill-path',
        action='append',
        default=None,
        help='增加一个 skills 搜索目录，可重复传入'
    )

    parser.add_argument(
        '--max-candidate-skills',
        type=int,
        help='候选 skills 上限（默认从配置读取）'
    )

    parser.add_argument(
        '--max-skill-tool-rounds',
        type=int,
        help='单步最多允许的 skill tool 调用轮数（默认从配置读取）'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='在上下文日志的 model_call 事件中记录完整 messages'
    )
    
    parser.add_argument(
        '--screenshot-dir',
        help='截图保存目录'
    )

    screenshot_group = parser.add_mutually_exclusive_group()
    screenshot_group.add_argument(
        '--save-screenshot',
        action='store_true',
        help='启用截图保存'
    )
    screenshot_group.add_argument(
        '--no-screenshot',
        action='store_true',
        help='禁用截图保存'
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
    
    # 处理截图配置
    if args.save_screenshot:
        import os
        os.environ['SAVE_SCREENSHOT'] = 'true'
    elif args.no_screenshot:
        import os
        os.environ['SAVE_SCREENSHOT'] = 'false'
    
    if args.screenshot_dir:
        import os
        os.environ['SCREENSHOT_DIR'] = args.screenshot_dir
    
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
    enable_skills = None
    skill_paths = None
    max_candidate_skills = None
    max_skill_tool_rounds = None
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
    if args.skills:
        enable_skills = True
    elif args.no_skills:
        enable_skills = False
    if args.skill_path:
        skill_paths = args.skill_path
    if args.max_candidate_skills is not None:
        max_candidate_skills = args.max_candidate_skills
    if args.max_skill_tool_rounds is not None:
        max_skill_tool_rounds = args.max_skill_tool_rounds
    
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
                enable_skills=enable_skills,
                skill_paths=skill_paths,
                max_candidate_skills=max_candidate_skills,
                max_skill_tool_rounds=max_skill_tool_rounds,
                log_full_messages=log_full_messages,
                natural_scroll=natural_scroll,
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
                enable_skills=enable_skills,
                skill_paths=skill_paths,
                max_candidate_skills=max_candidate_skills,
                max_skill_tool_rounds=max_skill_tool_rounds,
                log_full_messages=log_full_messages,
                natural_scroll=natural_scroll,
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
