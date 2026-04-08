"""Translate parsed model actions to standardized device commands."""

from __future__ import annotations

from typing import Any, Dict

from .base import DeviceCommand


def map_action_to_command(action: Dict[str, Any]) -> DeviceCommand:
    action_type = str(action.get('action_type') or '').lower()
    action_inputs = dict(action.get('action_inputs') or {})

    command_type = {
        'click': 'click',
        'left_single': 'click',
        'left_double': 'double_click',
        'right_single': 'right_click',
        'hover': 'move',
        'drag': 'drag',
        'hotkey': 'hotkey',
        'press': 'key_down',
        'keydown': 'key_down',
        'release': 'key_up',
        'keyup': 'key_up',
        'type': 'type_text',
        'scroll': 'scroll',
        'wait': 'wait',
    }.get(action_type, action_type)
    if not command_type:
        raise ValueError('动作缺少 action_type')
    return DeviceCommand(
        command_type=command_type,
        payload=action_inputs,
        metadata={'source_action_type': action_type},
    )
