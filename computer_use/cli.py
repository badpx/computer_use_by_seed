"""
CLI 交互入口模块
支持交互式命令行和单次任务执行
"""

import sys
import argparse
from typing import Dict, Any, Optional

from .compat import ensure_supported_python
from .config import config


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════╗
║              Computer Use Tool - 本地 GUI 自动化         ║
║                     Powered by 火山方舟                  ║
╚══════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_config_info():
    """打印配置信息"""
    print("[配置信息]")
    print(f"  模型: {config.model}")
    print(f"  API地址: {config.base_url}")
    print(f"  最大步数: {config.max_steps}")
    print(f"  保存截图: {'是' if config.save_screenshot else '否'}")
    print(f"  截图目录: {config.screenshot_dir}")
    print(f"  自然滚动: {'是' if config.natural_scroll else '否'}")
    print(f"  上下文日志: {'是' if config.save_context_log else '否'}")
    print(f"  日志目录: {config.context_log_dir}")
    print()


def interactive_mode(
    model: Optional[str] = None,
    max_steps: Optional[int] = None,
    natural_scroll: Optional[bool] = None,
    verbose: bool = True
):
    """
    交互式模式
    
    Args:
        model: 模型名称
        max_steps: 最大执行步数
        natural_scroll: 是否使用自然滚动
        verbose: 是否打印详细日志
    """
    print_banner()
    print_config_info()
    
    print("[交互模式]")
    print("请输入您的指令（输入 'quit' 或 'exit' 退出）\n")

    ensure_supported_python()
    from .agent import ComputerUseAgent
    
    # 初始化代理
    try:
        agent = ComputerUseAgent(
            model=model,
            max_steps=max_steps,
            natural_scroll=natural_scroll,
            verbose=verbose
        )
    except Exception as e:
        print(f"[错误] 初始化失败: {e}")
        return
    
    while True:
        try:
            # 获取用户输入
            instruction = input("> ").strip()
            
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
                print(f"\n[执行成功] 共执行 {len(result['steps'])} 步")
                if result['final_response']:
                    print(f"[最终回复] {result['final_response']}")
            else:
                print(f"\n[执行失败] {result.get('error', '未知错误')}")
            
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
    natural_scroll: Optional[bool] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    单次任务模式
    
    Args:
        instruction: 任务指令
        model: 模型名称
        max_steps: 最大执行步数
        natural_scroll: 是否使用自然滚动
        verbose: 是否打印详细日志
        
    Returns:
        Dict[str, Any]: 执行结果
    """
    if verbose:
        print_banner()
        print(f"[任务] {instruction}\n")

    ensure_supported_python()
    from .agent import ComputerUseAgent
    
    # 初始化代理
    agent = ComputerUseAgent(
        model=model,
        max_steps=max_steps,
        natural_scroll=natural_scroll,
        verbose=verbose
    )
    
    # 执行任务
    result = agent.run(instruction)
    
    if verbose:
        print()
        if result['success']:
            print(f"[成功] 任务完成，共执行 {len(result['steps'])} 步")
        else:
            print(f"[失败] {result.get('error', '未知错误')}")
    
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
        '--no-screenshot',
        action='store_true',
        help='禁用截图保存'
    )
    
    parser.add_argument(
        '--screenshot-dir',
        help='截图保存目录'
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
    if args.no_screenshot:
        import os
        os.environ['SAVE_SCREENSHOT'] = 'false'
    
    if args.screenshot_dir:
        import os
        os.environ['SCREENSHOT_DIR'] = args.screenshot_dir
    
    # 确定运行模式
    verbose = not args.quiet
    natural_scroll = None
    if args.natural_scroll:
        natural_scroll = True
    elif args.traditional_scroll:
        natural_scroll = False
    
    try:
        if args.instruction:
            # 单次任务模式
            result = single_task_mode(
                instruction=args.instruction,
                model=args.model,
                max_steps=args.max_steps,
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
