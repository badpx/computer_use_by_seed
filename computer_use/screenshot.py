"""
截图模块
支持全屏截图和按需保存
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pyautogui
from PIL import Image

try:
    import mss
except ImportError:
    mss = None


@dataclass(frozen=True)
class DisplayInfo:
    """显示器几何信息。"""

    index: int
    x: int
    y: int
    width: int
    height: int
    is_primary: bool = False

    def to_dict(self) -> Dict[str, int]:
        payload = asdict(self)
        payload['bounds'] = [self.x, self.y, self.width, self.height]
        return payload


def list_displays() -> List[DisplayInfo]:
    """返回当前可用显示器列表。"""
    if mss is not None:
        with mss.mss() as sct:
            monitors = sct.monitors[1:]
        if monitors:
            return [
                DisplayInfo(
                    index=index,
                    x=int(monitor['left']),
                    y=int(monitor['top']),
                    width=int(monitor['width']),
                    height=int(monitor['height']),
                    is_primary=(index == 0),
                )
                for index, monitor in enumerate(monitors)
            ]

    screen_width, screen_height = pyautogui.size()
    return [
        DisplayInfo(
            index=0,
            x=0,
            y=0,
            width=int(screen_width),
            height=int(screen_height),
            is_primary=True,
        )
    ]


def resolve_display(display_index: Optional[int] = None) -> Dict[str, int]:
    """根据编号解析目标显示器。"""
    target_index = 0 if display_index is None else int(display_index)
    if target_index < 0:
        raise ValueError('display_index 不能小于 0')

    displays = list_displays()
    if target_index >= len(displays):
        raise ValueError(
            f'显示器索引 {target_index} 超出范围，当前仅检测到 {len(displays)} 台显示器'
        )
    return displays[target_index].to_dict()


class ScreenshotManager:
    """截图管理器"""
    
    def __init__(self):
        self.format = 'png'
    
    def capture(
        self,
        filename: Optional[str] = None,
        save: bool = False,
        save_dir: Optional[str] = None,
        display_index: Optional[int] = None,
    ) -> Tuple[Image.Image, Optional[str]]:
        """
        捕获目标显示器截图
        
        Args:
            filename: 自定义文件名，默认使用时间戳
            save: 是否保存截图
            save_dir: 保存目录；未指定时使用当前目录
            display_index: 目标显示器编号，默认主显示器
            
        Returns:
            Tuple[Image.Image, Optional[str]]: (截图对象, 保存路径或None)
        """
        display = resolve_display(display_index)

        if mss is not None:
            with mss.mss() as sct:
                raw = sct.grab(
                    {
                        'left': display['x'],
                        'top': display['y'],
                        'width': display['width'],
                        'height': display['height'],
                    }
                )
            screenshot = Image.frombytes('RGB', raw.size, raw.rgb)
        else:
            if display['index'] != 0:
                raise RuntimeError('多显示器截图需要安装 mss')
            screenshot = pyautogui.screenshot(
                region=(0, 0, display['width'], display['height'])
            )
        
        if save:
            # 生成文件名
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filename = f"screenshot_{timestamp}.{self.format}"
            
            # 构建完整路径
            target_dir = Path(save_dir or '.')
            target_dir.mkdir(parents=True, exist_ok=True)
            save_path = target_dir / filename
            
            # 保存截图
            screenshot.save(save_path)
            
            return screenshot, str(save_path)
        
        return screenshot, None
    
screenshot_manager = ScreenshotManager()


def capture_screenshot(
    filename: Optional[str] = None,
    save: bool = False,
    save_dir: Optional[str] = None,
    display_index: Optional[int] = None,
) -> Tuple[Image.Image, Optional[str]]:
    """
    便捷函数：捕获截图
    
    Args:
        filename: 自定义文件名
        save: 是否保存截图
        save_dir: 保存目录
        display_index: 目标显示器编号
        
    Returns:
        Tuple[Image.Image, Optional[str]]: (截图对象, 保存路径或None)
    """
    return screenshot_manager.capture(filename, save, save_dir, display_index)
