"""Device plugin system for computer_use."""

import importlib

from .base import DeviceAdapter, DeviceCommand, DeviceFrame, DevicePluginSpec
from .factory import create_device_adapter
from .registry import discover_device_plugins


def __getattr__(name):
    qualified_name = f'{__name__}.{name}'
    try:
        module = importlib.import_module(f'.{name}', __name__)
    except ModuleNotFoundError as exc:
        if exc.name == qualified_name:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
        raise
    globals()[name] = module
    return module

__all__ = [
    'DeviceAdapter',
    'DeviceCommand',
    'DeviceFrame',
    'DevicePluginSpec',
    'create_device_adapter',
    'discover_device_plugins',
    'plugins',
]
