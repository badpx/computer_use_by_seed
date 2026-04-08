"""Device plugin system for computer_use."""

from .base import DeviceAdapter, DeviceCommand, DeviceFrame, DevicePluginSpec
from .factory import create_device_adapter
from .registry import discover_device_plugins

__all__ = [
    'DeviceAdapter',
    'DeviceCommand',
    'DeviceFrame',
    'DevicePluginSpec',
    'create_device_adapter',
    'discover_device_plugins',
]
