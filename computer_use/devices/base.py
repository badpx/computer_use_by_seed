"""Base types for device adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass(frozen=True)
class DeviceFrame:
    image_data_url: str
    width: int
    height: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceCommand:
    command_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DevicePluginSpec:
    name: str
    description: str
    entrypoint: str
    directory: Path
    plugin_path: Path
    manifest_path: Path
    metadata: Dict[str, Any] = field(default_factory=dict)


class DeviceAdapter(ABC):
    """Abstract device adapter interface."""

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def capture_frame(self) -> DeviceFrame:
        raise NotImplementedError

    @abstractmethod
    def execute_command(self, command: DeviceCommand) -> Union[str, List[str]]:
        raise NotImplementedError

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        raise NotImplementedError

    def get_environment_info(self) -> Dict[str, Any]:
        """Return stable environment details for prompt injection."""
        return {}

    def supports_target_selection(self) -> bool:
        return False

    def list_targets(self) -> List[Dict[str, Any]]:
        return []

    def set_target(self, target_id: Union[str, int]) -> Dict[str, Any]:
        raise NotImplementedError('当前设备不支持目标切换')

    @property
    def device_name(self) -> str:
        return self.__class__.__name__

    @property
    def target_summary(self) -> Optional[Dict[str, Any]]:
        return None
