"""
Computer Use Tool - 本地 GUI 自动化工具
"""

from .config import config, Config
from .compat import ensure_supported_python

__version__ = '1.0.0'
__author__ = 'Computer Use Tool'


def __getattr__(name):
    if name == 'ComputerUseAgent':
        ensure_supported_python()
        from .agent import ComputerUseAgent

        return ComputerUseAgent
    if name in {'capture_screenshot', 'screenshot_manager'}:
        from .screenshot import capture_screenshot, screenshot_manager

        return {
            'capture_screenshot': capture_screenshot,
            'screenshot_manager': screenshot_manager,
        }[name]
    if name in {'parse_action', 'ActionParser'}:
        from .action_parser import ActionParser, parse_action

        return {
            'parse_action': parse_action,
            'ActionParser': ActionParser,
        }[name]
    if name in {'execute_action', 'ActionExecutor'}:
        from .action_executor import ActionExecutor, execute_action

        return {
            'execute_action': execute_action,
            'ActionExecutor': ActionExecutor,
        }[name]
    if name in {'Skill', 'discover_skills'}:
        from .skills import Skill, discover_skills

        return {
            'Skill': Skill,
            'discover_skills': discover_skills,
        }[name]
    if name in {'DeviceAdapter', 'DeviceFrame', 'DeviceCommand', 'create_device_adapter'}:
        from .devices import DeviceAdapter, DeviceFrame, DeviceCommand, create_device_adapter

        return {
            'DeviceAdapter': DeviceAdapter,
            'DeviceFrame': DeviceFrame,
            'DeviceCommand': DeviceCommand,
            'create_device_adapter': create_device_adapter,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

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

    # 技能系统
    'Skill',
    'discover_skills',

    # 设备插件
    'DeviceAdapter',
    'DeviceFrame',
    'DeviceCommand',
    'create_device_adapter',
]
