"""
截图模块
支持全屏截图、保存、开关控制
"""

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional

import pyautogui
from PIL import Image

from .config import config


class ScreenshotManager:
    """截图管理器"""
    
    def __init__(self):
        self.save_enabled = config.save_screenshot
        self.save_dir = Path(config.screenshot_dir)
        self.format = 'png'
        
        # 确保保存目录存在（如果启用了保存）
        if self.save_enabled:
            self.save_dir.mkdir(parents=True, exist_ok=True)
    
    def capture(
        self,
        filename: Optional[str] = None,
        save: Optional[bool] = None
    ) -> Tuple[Image.Image, Optional[str]]:
        """
        捕获全屏截图
        
        Args:
            filename: 自定义文件名，默认使用时间戳
            save: 是否保存截图，None 则使用全局配置
            
        Returns:
            Tuple[Image.Image, Optional[str]]: (截图对象, 保存路径或None)
        """
        # 获取屏幕尺寸
        screen_width, screen_height = pyautogui.size()
        
        # 捕获全屏
        screenshot = pyautogui.screenshot(
            region=(0, 0, screen_width, screen_height)
        )
        
        # 确定是否保存
        should_save = self.save_enabled if save is None else save
        
        if should_save:
            # 生成文件名
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"screenshot_{timestamp}.{self.format}"
            
            # 构建完整路径
            save_path = self.save_dir / filename
            
            # 保存截图
            screenshot.save(save_path)
            
            return screenshot, str(save_path)
        
        return screenshot, None
    
    def get_save_dir(self) -> Path:
        """获取截图保存目录"""
        return self.save_dir
    
    def is_save_enabled(self) -> bool:
        """检查是否启用了截图保存"""
        return self.save_enabled


# 全局截图管理器实例
screenshot_manager = ScreenshotManager()


def capture_screenshot(
    filename: Optional[str] = None,
    save: Optional[bool] = None
) -> Tuple[Image.Image, Optional[str]]:
    """
    便捷函数：捕获截图
    
    Args:
        filename: 自定义文件名
        save: 是否保存截图
        
    Returns:
        Tuple[Image.Image, Optional[str]]: (截图对象, 保存路径或None)
    """
    return screenshot_manager.capture(filename, save)
