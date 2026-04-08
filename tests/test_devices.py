import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


PNG_1X1_BASE64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8'
    '/w8AAgMBgJ0XGfQAAAAASUVORK5CYII='
)
JPEG_1X1_BASE64 = (
    '/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBAQEA8QDw8PEA8PDw8QDw8P'
    'DxAPFREWFhURFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0O'
    'FQ8QFSsdFR0rKysrKysrKysrKysrKysrKysrKysrKysrKysrKysrKysrKysrKysr'
    'KysrKysrK//AABEIAAEAAQMBIgACEQEDEQH/xAAXAAADAQAAAAAAAAAAAAAAAAAA'
    'AgME/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEAMQAAAB6A//xAAVEAEA'
    'AAAAAAAAAAAAAAAAAAABEP/aAAgBAQABBQL/xAAVEQEBAAAAAAAAAAAAAAAAAAAA'
    'Ef/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAEP/aAAgBAgEBPwB//8QA'
    'FhABAQEAAAAAAAAAAAAAAAAAARAR/9oACAEBAAY/Apf/xAAWEAEBAQAAAAAAAAAA'
    'AAAAAAABABH/2gAIAQEAAT8hZ//Z'
)


class DeviceHelpersTests(unittest.TestCase):
    def test_prepare_model_frame_keeps_original_frame_without_resize(self):
        from computer_use.devices.base import DeviceFrame
        from computer_use.devices.helpers import prepare_model_frame

        frame = DeviceFrame(
            image_data_url=f'data:image/jpeg;base64,{JPEG_1X1_BASE64}',
            width=1,
            height=1,
            metadata={'source': 'test'},
        )

        prepared = prepare_model_frame(frame, screenshot_size=None)

        self.assertEqual(prepared.image_data_url, f'data:image/jpeg;base64,{JPEG_1X1_BASE64}')
        self.assertEqual((prepared.width, prepared.height), (1, 1))
        self.assertEqual(prepared.metadata.get('source'), 'test')

    def test_frame_to_data_url_returns_original_data_url(self):
        from computer_use.devices.base import DeviceFrame
        from computer_use.devices.helpers import frame_to_data_url

        frame = DeviceFrame(
            image_data_url=f'data:image/png;base64,{PNG_1X1_BASE64}',
            width=1,
            height=1,
            metadata={},
        )

        self.assertEqual(
            frame_to_data_url(frame),
            f'data:image/png;base64,{PNG_1X1_BASE64}',
        )

    def test_extractors_parse_mime_type_and_base64_from_data_url(self):
        from computer_use.devices.base import DeviceFrame
        from computer_use.devices.helpers import extract_frame_base64, extract_frame_mime_type

        frame = DeviceFrame(
            image_data_url=f'data:image/jpeg;base64,{JPEG_1X1_BASE64}',
            width=1,
            height=1,
            metadata={},
        )

        self.assertEqual(extract_frame_mime_type(frame), 'image/jpeg')
        self.assertEqual(extract_frame_base64(frame), JPEG_1X1_BASE64)


class DeviceRegistryTests(unittest.TestCase):
    def test_discover_device_plugins_finds_external_plugin(self):
        from computer_use.devices.registry import discover_device_plugins

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / 'demo-device'
            plugin_dir.mkdir(parents=True)
            (plugin_dir / 'plugin.json').write_text(
                json.dumps(
                    {
                        'name': 'demo-device',
                        'description': 'Demo device',
                        'entrypoint': 'plugin:create_adapter',
                    }
                ),
                encoding='utf-8',
            )
            (plugin_dir / 'plugin.py').write_text(
                'def create_adapter(config):\n'
                '    return {"config": config}\n',
                encoding='utf-8',
            )

            plugins = discover_device_plugins([tmpdir])

        self.assertIn('demo-device', plugins)
        self.assertEqual(plugins['demo-device'].name, 'demo-device')
        self.assertEqual(plugins['demo-device'].entrypoint, 'plugin:create_adapter')

    def test_create_device_adapter_loads_plugin_and_passes_config(self):
        from computer_use.devices.factory import create_device_adapter

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / 'demo-device'
            plugin_dir.mkdir(parents=True)
            (plugin_dir / 'plugin.json').write_text(
                json.dumps(
                    {
                        'name': 'demo-device',
                        'description': 'Demo device',
                        'entrypoint': 'plugin:create_adapter',
                    }
                ),
                encoding='utf-8',
            )
            (plugin_dir / 'plugin.py').write_text(
                'class DemoAdapter:\n'
                '    def __init__(self, config):\n'
                '        self.config = dict(config)\n'
                '    def connect(self):\n'
                '        return None\n'
                '    def close(self):\n'
                '        return None\n'
                '    def capture_frame(self):\n'
                '        raise NotImplementedError\n'
                '    def execute_command(self, command):\n'
                '        raise NotImplementedError\n'
                '    def get_status(self):\n'
                '        return {"plugin": "demo-device"}\n'
                '    def supports_target_selection(self):\n'
                '        return False\n'
                '    def list_targets(self):\n'
                '        return []\n'
                '    def set_target(self, target_id):\n'
                '        raise NotImplementedError\n'
                'def create_adapter(config):\n'
                '    return DemoAdapter(config)\n',
                encoding='utf-8',
            )

            adapter = create_device_adapter(
                device_name='demo-device',
                device_config={'token': 'abc'},
                devices_dir=tmpdir,
            )

        self.assertEqual(adapter.config, {'token': 'abc'})


class LocalDeviceAdapterTests(unittest.TestCase):
    def test_capture_frame_returns_complete_data_url(self):
        import importlib

        adapter_module = importlib.import_module(
            'computer_use.devices.plugins.local.adapter'
        )
        LocalDeviceAdapter = adapter_module.LocalDeviceAdapter

        class FakeScreenshot:
            format = 'JPEG'
            size = (1, 1)

            def save(self, buffer, format=None):
                del format
                import base64

                buffer.write(base64.b64decode(JPEG_1X1_BASE64.encode('utf-8')))

        fake_screenshot_module = types.SimpleNamespace(
            capture_screenshot=lambda display_index=None: (FakeScreenshot(), None),
            resolve_display=lambda display_index=None: {
                'index': 0,
                'x': 0,
                'y': 0,
                'width': 1,
                'height': 1,
                'is_primary': True,
            },
        )

        with mock.patch.object(
            LocalDeviceAdapter,
            '_screenshot_module',
            return_value=fake_screenshot_module,
        ):
            adapter = LocalDeviceAdapter(
                {
                    'display_index': 0,
                    'verbose': False,
                }
            )
            frame = adapter.capture_frame()

        self.assertEqual(
            frame.image_data_url,
            f'data:image/jpeg;base64,{JPEG_1X1_BASE64}',
        )
        self.assertEqual((frame.width, frame.height), (1, 1))

class DeviceCommandMapperTests(unittest.TestCase):
    def test_map_click_action_to_device_command(self):
        from computer_use.devices.command_mapper import map_action_to_command

        command = map_action_to_command(
            {
                'action_type': 'click',
                'action_inputs': {'point': [120, 55]},
            }
        )

        self.assertEqual(command.command_type, 'click')
        self.assertEqual(command.payload['point'], [120, 55])


class AgentDeviceInjectionTests(unittest.TestCase):
    def setUp(self):
        os.environ['ARK_API_KEY'] = 'test-key'
        self.responses = [
            "Thought: first\nAction: click(point='10 20')",
            "Thought: done\nAction: finished(content='ok')",
        ]
        self.calls = []
        self.command_calls = []
        self.capture_calls = 0
        self.connected = False

        ark_stub = types.ModuleType('volcenginesdkarkruntime')

        class PlaceholderArk:
            def __init__(inner_self, *args, **kwargs):
                del args, kwargs
                inner_self.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=self._create_response)
                )

        ark_stub.Ark = PlaceholderArk
        sys.modules['volcenginesdkarkruntime'] = ark_stub
        sys.modules.pop('computer_use.agent', None)

    def _create_response(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        message = types.SimpleNamespace(content=content, reasoning_content=None, tool_calls=None)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=message, finish_reason='stop')],
            usage=None,
        )

    def _make_adapter(self):
        from computer_use.devices.base import DeviceFrame

        test_case = self

        class FakeAdapter:
            device_name = 'fake-remote'

            def connect(self):
                test_case.connected = True

            def close(self):
                return None

            def capture_frame(self):
                test_case.capture_calls += 1
                return DeviceFrame(
                    image_data_url=f'data:image/png;base64,{PNG_1X1_BASE64}',
                    width=1,
                    height=1,
                    metadata={'device_name': 'fake-remote'},
                )

            def execute_command(self, command):
                test_case.command_calls.append(command)
                return 'clicked'

            def get_status(self):
                return {'device_name': 'fake-remote'}

            def supports_target_selection(self):
                return False

            def list_targets(self):
                return []

            def set_target(self, target_id):
                raise NotImplementedError

        return FakeAdapter()

    def test_agent_can_run_with_injected_device_adapter(self):
        import importlib

        agent_module = importlib.import_module('computer_use.agent')
        agent_module.time.sleep = lambda _: None

        agent = agent_module.ComputerUseAgent(
            model='fake-model',
            max_steps=3,
            screenshot_size=0,
            verbose=False,
            save_context_log=False,
            device_adapter=self._make_adapter(),
        )

        result = agent.run('click somewhere')

        self.assertTrue(self.connected)
        self.assertTrue(result['success'])
        self.assertEqual(self.capture_calls, 2)
        self.assertEqual(len(self.command_calls), 1)
        self.assertEqual(self.command_calls[0].command_type, 'click')
        self.assertEqual(self.command_calls[0].payload['point'], [10.0, 20.0])
        self.assertEqual(agent.device_name, 'fake-remote')
