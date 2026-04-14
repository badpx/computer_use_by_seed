"""
配置管理模块
支持环境变量 > 配置文件 > 默认值的优先级加载
"""

import json
import os
import subprocess
import sys
from typing import Any, Optional
from pathlib import Path

THINKING_MODES = ('enabled', 'disabled', 'auto')
REASONING_EFFORTS = ('low', 'medium', 'high')
COORDINATE_SPACES = ('relative', 'pixel')
PROVIDERS = ('ark', 'openrouter', 'openai', 'ollama')
PROVIDER_DEFAULT_BASE_URLS = {
    'ark': 'http://ark.cn-beijing.volces.com/api/v3',
    'openrouter': 'https://openrouter.ai/api/v1',
    'openai': 'https://api.openai.com/v1',
    'ollama': 'http://localhost:11434/v1',
}


def normalize_thinking_mode(
    thinking_mode: Optional[str],
    default: str = 'auto',
) -> str:
    """标准化思考模式。"""
    mode = str(thinking_mode or default).strip().lower()
    if mode in THINKING_MODES:
        return mode
    return default


def normalize_reasoning_effort(
    reasoning_effort: Optional[str],
    default: Optional[str] = None,
) -> Optional[str]:
    """标准化思考档位。"""
    effort = str(reasoning_effort or default or '').strip().lower()
    if not effort:
        return default
    if effort in REASONING_EFFORTS:
        return effort
    return default


def resolve_thinking_settings(
    thinking_mode: Optional[str],
    reasoning_effort: Optional[str],
    thinking_mode_explicit: bool = False,
    reasoning_effort_explicit: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """根据思考模式和思考档位，计算最终请求参数。"""
    normalized_mode = (
        normalize_thinking_mode(thinking_mode)
        if thinking_mode_explicit
        else None
    )
    normalized_effort = (
        normalize_reasoning_effort(reasoning_effort)
        if reasoning_effort_explicit
        else None
    )

    if not thinking_mode_explicit and not reasoning_effort_explicit:
        return None, None

    if thinking_mode_explicit and not reasoning_effort_explicit:
        return normalized_mode, None

    if not thinking_mode_explicit and reasoning_effort_explicit:
        return 'enabled', normalized_effort

    if normalized_mode == 'disabled':
        return 'disabled', None

    return normalized_mode, normalized_effort


def normalize_coordinate_space(
    coordinate_space: Optional[str],
    default: str = 'relative',
) -> str:
    """标准化坐标空间。"""
    space = str(coordinate_space or default).strip().lower()
    if space in COORDINATE_SPACES:
        return space
    return default


def normalize_provider(
    provider: Optional[str],
    default: str = 'ark',
) -> str:
    """标准化 provider 名称。"""
    normalized = str(provider or default).strip().lower()
    if normalized in PROVIDERS:
        return normalized
    return default


class Config:
    """配置类，支持多层级配置加载"""
    
    # 默认值
    DEFAULTS = {
        'PROVIDER': 'ark',
        'MODEL': 'doubao-seed-1-6-vision-250815',
        'BASE_URL': PROVIDER_DEFAULT_BASE_URLS['ark'],
        'PROVIDER_CONFIG_JSON': '',
        'DEVICE_NAME': 'local',
        'DEVICE_CONFIG_JSON': '',
        'DEVICES_DIR': './devices',
        'DISPLAY_INDEX': '0',
        'NATURAL_SCROLL': '',
        'CONTEXT_LOG_DIR': './logs',
        'SAVE_CONTEXT_LOG': 'true',
        'MAX_STEPS': '100',
        'TEMPERATURE': '0.0',
        'THINKING_MODE': '',
        'REASONING_EFFORT': '',
        'COORDINATE_SPACE': 'relative',
        'COORDINATE_SCALE': '1000',
        'SCREENSHOT_SIZE': '',
        'MAX_CONTEXT_SCREENSHOTS': '5',
        'INCLUDE_EXECUTION_FEEDBACK': 'false',
        'MAX_PIXELS': '12845056',  # 16384 * 28 * 28
        'MIN_PIXELS': '78400',     # 100 * 28 * 28
        'SKILLS_DIR': './skills',
        'ENABLE_SKILLS': 'true',
        'ENABLE_ASK_USER_FOR_SINGLE_TASK': 'false',
    }
    
    # 必需配置项
    REQUIRED = ['API_KEY']
    
    def __init__(self):
        """初始化配置"""
        self._config = {}
        self._explicit_keys = set()
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
                            normalized_key = key.strip()
                            self._config[normalized_key] = value.strip()
                            self._explicit_keys.add(normalized_key)
                break
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        for key in list(self.DEFAULTS.keys()) + self.REQUIRED:
            env_value = os.getenv(key)
            if env_value is not None:
                self._config[key] = env_value
                self._explicit_keys.add(key)
    
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

    def has_explicit_value(self, key: str) -> bool:
        """判断配置项是否由环境变量或配置文件显式设置。"""
        return key in self._explicit_keys
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """获取布尔类型配置项"""
        value = self._config.get(key, str(default).lower())
        return value.lower() in ('true', '1', 'yes', 'on')

    def get_optional_bool(self, key: str) -> Optional[bool]:
        """获取可选布尔配置项，未设置时返回 None。"""
        value = self._config.get(key)
        if value is None:
            return None

        value = str(value).strip().lower()
        if value == '':
            return None
        if value in ('true', '1', 'yes', 'on'):
            return True
        if value in ('false', '0', 'no', 'off'):
            return False
        return None
    
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
        return self._config.get('API_KEY', '')

    @property
    def provider(self) -> str:
        """LLM provider 名称。"""
        return normalize_provider(
            self._config.get('PROVIDER'),
            default=self.DEFAULTS['PROVIDER'],
        )
    
    @property
    def model(self) -> str:
        """模型名称"""
        return self._config.get('MODEL', self.DEFAULTS['MODEL'])

    @property
    def provider_config(self) -> dict[str, Any]:
        """LLM provider 私有配置。"""
        raw = self._config.get(
            'PROVIDER_CONFIG_JSON',
            self.DEFAULTS['PROVIDER_CONFIG_JSON'],
        )
        text = str(raw or '').strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f'PROVIDER_CONFIG_JSON 不是合法 JSON: {exc}') from exc
        if not isinstance(payload, dict):
            raise ValueError('PROVIDER_CONFIG_JSON 必须是 JSON 对象')
        return payload

    @property
    def device_name(self) -> str:
        """设备插件名称。"""
        return self._config.get('DEVICE_NAME', self.DEFAULTS['DEVICE_NAME']).strip() or 'local'

    @property
    def device_config(self) -> dict[str, Any]:
        """设备插件私有配置。"""
        raw = self._config.get('DEVICE_CONFIG_JSON', self.DEFAULTS['DEVICE_CONFIG_JSON'])
        text = str(raw or '').strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f'DEVICE_CONFIG_JSON 不是合法 JSON: {exc}') from exc
        if not isinstance(payload, dict):
            raise ValueError('DEVICE_CONFIG_JSON 必须是 JSON 对象')
        return payload

    @property
    def devices_dir(self) -> str:
        """外部设备插件目录。"""
        return self._config.get('DEVICES_DIR', self.DEFAULTS['DEVICES_DIR'])
    
    @property
    def base_url(self) -> str:
        """API 基础 URL"""
        if self.has_explicit_value('BASE_URL'):
            return self._config.get('BASE_URL', self.DEFAULTS['BASE_URL'])
        return PROVIDER_DEFAULT_BASE_URLS.get(
            self.provider,
            self.DEFAULTS['BASE_URL'],
        )
    
    @property
    def temperature(self) -> float:
        """模型温度参数"""
        return self.get_float('TEMPERATURE', 0.0)

    @property
    def display_index(self) -> int:
        """目标显示器编号。"""
        index = self.get_int('DISPLAY_INDEX', 0)
        if index < 0:
            raise ValueError('DISPLAY_INDEX 不能小于 0')
        return index
    
    @property
    def max_steps(self) -> int:
        """最大执行步数"""
        return self.get_int('MAX_STEPS', 100)

    @property
    def natural_scroll(self) -> bool:
        """是否使用自然滚动方向。"""
        configured = self.get_optional_bool('NATURAL_SCROLL')
        if configured is not None:
            return configured
        return self._detect_natural_scroll()

    @property
    def save_context_log(self) -> bool:
        """是否保存上下文日志"""
        return self.get_bool('SAVE_CONTEXT_LOG', True)

    @property
    def context_log_dir(self) -> str:
        """上下文日志目录"""
        return self._config.get('CONTEXT_LOG_DIR', self.DEFAULTS['CONTEXT_LOG_DIR'])
    
    @property
    def coordinate_scale(self) -> float:
        """相对坐标的量程。"""
        scale = self.get_float('COORDINATE_SCALE', 1000.0)
        if scale <= 0:
            return 1000.0
        return scale

    @property
    def coordinate_space(self) -> str:
        """坐标空间：relative / pixel。"""
        return normalize_coordinate_space(
            self._config.get('COORDINATE_SPACE'),
            default=self.DEFAULTS['COORDINATE_SPACE'],
        )

    @property
    def screenshot_size(self) -> Optional[int]:
        """传给模型前的截图缩放尺寸；仅支持正方形。"""
        size = self.get_int('SCREENSHOT_SIZE', 0)
        if size <= 0:
            return None
        return size

    @property
    def max_context_screenshots(self) -> int:
        """多轮上下文中最多保留的截图数量（包含当前轮）。"""
        count = self.get_int('MAX_CONTEXT_SCREENSHOTS', 5)
        if count < 1:
            return 5
        return count

    @property
    def include_execution_feedback(self) -> bool:
        """是否将成功执行反馈注入多轮上下文。"""
        return self.get_bool('INCLUDE_EXECUTION_FEEDBACK', False)

    @property
    def thinking_mode(self) -> str:
        """模型思考模式：enabled / disabled / auto。"""
        return normalize_thinking_mode(
            self._config.get('THINKING_MODE'),
            default='auto',
        )

    @property
    def reasoning_effort(self) -> str:
        """模型思考档位：low / medium / high。"""
        return normalize_reasoning_effort(
            self._config.get('REASONING_EFFORT'),
            default='medium',
        )

    @property
    def skills_dir(self) -> str:
        return self._config.get('SKILLS_DIR', self.DEFAULTS['SKILLS_DIR'])

    @property
    def enable_skills(self) -> bool:
        return self.get_bool('ENABLE_SKILLS', True)

    @property
    def enable_ask_user_for_single_task(self) -> bool:
        return self.get_bool('ENABLE_ASK_USER_FOR_SINGLE_TASK', False)

    def _detect_natural_scroll(self) -> bool:
        """自动检测系统滚动方向设置。"""
        if sys.platform != 'darwin':
            return False

        try:
            result = subprocess.run(
                ['defaults', 'read', '-g', 'com.apple.swipescrolldirection'],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip() == '1'
        except Exception:
            return True

    def persist_value(
        self,
        key: str,
        value: str,
        env_path: Optional[Path] = None,
    ) -> str:
        """将配置项持久化到项目 .env 文件。"""
        target_path = Path(env_path or '.env').expanduser()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        if target_path.exists():
            lines = target_path.read_text(encoding='utf-8').splitlines()

        serialized_value = str(value)
        updated = False
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and '=' in line:
                existing_key, _ = line.split('=', 1)
                if existing_key.strip() == key:
                    new_lines.append(f'{key}={serialized_value}')
                    updated = True
                    continue
            new_lines.append(line)

        if not updated:
            new_lines.append(f'{key}={serialized_value}')

        content = '\n'.join(new_lines).rstrip('\n') + '\n'
        target_path.write_text(content, encoding='utf-8')
        self._config[key] = serialized_value
        self._explicit_keys.add(key)
        return str(target_path)

    def persist_display_index(self, display_index: int) -> str:
        """将目标显示器编号持久化到项目配置。"""
        if int(display_index) < 0:
            raise ValueError('display_index 不能小于 0')
        return self.persist_value('DISPLAY_INDEX', str(int(display_index)))


# 全局配置实例
config = Config()
