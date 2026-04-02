"""
Computer Use Tool - 本地 GUI 自动化工具
"""

from .config import config, Config
from .agent import ComputerUseAgent
from .screenshot import capture_screenshot, screenshot_manager
from .action_parser import parse_action, ActionParser
from .action_executor import execute_action, ActionExecutor

__version__ = '1.0.0'
__author__ = 'Computer Use Tool'

__all__ = [
    # 配置
    'config',
    'Config',
    
    # 核心类
    'ComputerUseAgent',
    
    # 截图
    'capture_screenshot',
    'screenshot_manager',
    
    # 动作解析
    'parse_action',
    'ActionParser',
    
    # 动作执行
    'execute_action',
    'ActionExecutor',
]
