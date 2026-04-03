"""
配置管理模块
支持环境变量 > 配置文件 > 默认值的优先级加载
"""

import os
from typing import Optional
from pathlib import Path


class Config:
    """配置类，支持多层级配置加载"""
    
    # 默认值
    DEFAULTS = {
        'ARK_MODEL': 'doubao-seed-1-6-vision-250815',
        'ARK_BASE_URL': 'http://ark.cn-beijing.volces.com/api/v3',
        'SCREENSHOT_DIR': './screenshots',
        'SAVE_SCREENSHOT': 'true',
        'MAX_STEPS': '20',
        'TEMPERATURE': '0.0',
        'COORDINATE_SCALE': '1000',
        'MAX_PIXELS': '12845056',  # 16384 * 28 * 28
        'MIN_PIXELS': '78400',     # 100 * 28 * 28
    }
    
    # 必需配置项
    REQUIRED = ['ARK_API_KEY']
    
    def __init__(self):
        """初始化配置"""
        self._config = {}
        self._load()
    
    def _load(self):
        """
        按优先级加载配置：
        1. 默认值
        2. 配置文件 (.env)
        3. 环境变量（最高优先级）
        """
        # 1. 加载默认值
        self._config.update(self.DEFAULTS)
        
        # 2. 加载配置文件
        self._load_from_file()
        
        # 3. 加载环境变量（覆盖配置文件）
        self._load_from_env()
    
    def _load_from_file(self):
        """从 .env 文件加载配置"""
        env_paths = [
            Path('.env'),
            Path.home() / '.computer_use' / '.env',
        ]
        
        for env_path in env_paths:
            if env_path.exists():
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            self._config[key.strip()] = value.strip()
                break
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        for key in list(self.DEFAULTS.keys()) + self.REQUIRED:
            env_value = os.getenv(key)
            if env_value is not None:
                self._config[key] = env_value
    
    def _validate(self):
        """验证必需配置项"""
        missing = []
        for key in self.REQUIRED:
            if not self._config.get(key):
                missing.append(key)
        
        if missing:
            raise ValueError(
                f"缺少必需配置项: {', '.join(missing)}\n"
                f"请通过环境变量或 .env 文件设置"
            )

    def validate(self):
        """对外暴露的显式配置校验。"""
        self._validate()
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取配置项"""
        return self._config.get(key, default)
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔类型配置项"""
        value = self._config.get(key, str(default).lower())
        return value.lower() in ('true', '1', 'yes', 'on')
    
    def get_int(self, key: str, default: int = 0) -> int:
        """获取整数类型配置项"""
        try:
            return int(self._config.get(key, default))
        except (ValueError, TypeError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """获取浮点数类型配置项"""
        try:
            return float(self._config.get(key, default))
        except (ValueError, TypeError):
            return default
    
    @property
    def api_key(self) -> str:
        """API 密钥"""
        return self._config.get('ARK_API_KEY', '')
    
    @property
    def model(self) -> str:
        """模型名称"""
        return self._config.get('ARK_MODEL', self.DEFAULTS['ARK_MODEL'])
    
    @property
    def base_url(self) -> str:
        """API 基础 URL"""
        return self._config.get('ARK_BASE_URL', self.DEFAULTS['ARK_BASE_URL'])
    
    @property
    def temperature(self) -> float:
        """模型温度参数"""
        return self.get_float('TEMPERATURE', 0.0)
    
    @property
    def max_steps(self) -> int:
        """最大执行步数"""
        return self.get_int('MAX_STEPS', 20)
    
    @property
    def save_screenshot(self) -> bool:
        """是否保存截图"""
        return self.get_bool('SAVE_SCREENSHOT', True)
    
    @property
    def screenshot_dir(self) -> str:
        """截图保存目录"""
        return self._config.get('SCREENSHOT_DIR', self.DEFAULTS['SCREENSHOT_DIR'])
    
    @property
    def coordinate_scale(self) -> int:
        """坐标缩放比例"""
        return self.get_int('COORDINATE_SCALE', 1000)


# 全局配置实例
config = Config()
