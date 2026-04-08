"""Factory for constructing device adapters."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import DeviceAdapter
from .registry import discover_device_plugins, load_plugin_factory


def create_device_adapter(
    device_name: Optional[str] = None,
    device_config: Optional[Dict[str, Any]] = None,
    devices_dir: Optional[str] = None,
    adapter: Optional[DeviceAdapter] = None,
) -> DeviceAdapter:
    if adapter is not None:
        return adapter

    resolved_name = str(device_name or 'local').strip() or 'local'
    plugins = discover_device_plugins([devices_dir] if devices_dir else None)
    spec = plugins.get(resolved_name)
    if spec is None:
        available = ', '.join(sorted(plugins)) or '(none)'
        raise ValueError(
            f'未找到设备插件: {resolved_name}，当前可用插件: {available}'
        )

    factory = load_plugin_factory(spec)
    instance = factory(dict(device_config or {}))
    if instance is None:
        raise RuntimeError(f'设备插件 {resolved_name} 未返回适配器实例')
    return instance
