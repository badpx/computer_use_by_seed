import unittest
from unittest.mock import patch

import computer_use.devices.plugins.vnc.adapter  # noqa: F401


class VncDeviceAdapterConfigTests(unittest.TestCase):
    def _make_adapter(self, plugin_config):
        from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter

        return VncDeviceAdapter(plugin_config)

    def test_missing_host_raises_value_error(self):
        from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter

        with self.assertRaisesRegex(ValueError, 'host'):
            VncDeviceAdapter({})

    def test_prompt_profile_defaults_to_computer(self):
        adapter = self._make_adapter({'host': '127.0.0.1'})

        self.assertEqual(adapter.get_prompt_profile(), 'computer')

    def test_prompt_profile_can_be_cellphone(self):
        adapter = self._make_adapter(
            {'host': '127.0.0.1', 'prompt_profile': 'cellphone'}
        )

        self.assertEqual(adapter.get_prompt_profile(), 'cellphone')

    def test_port_and_password_are_stored_on_adapter(self):
        adapter = self._make_adapter(
            {'host': '127.0.0.1', 'port': '6001', 'password': 'secret'}
        )

        self.assertEqual(adapter.port, 6001)
        self.assertEqual(adapter.password, 'secret')

    def test_invalid_port_raises_value_error(self):
        from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter

        with self.assertRaisesRegex(ValueError, 'port'):
            VncDeviceAdapter({'host': '127.0.0.1', 'port': 'not-a-number'})

    def test_environment_info_uses_default_operating_system(self):
        adapter = self._make_adapter({'host': '127.0.0.1'})

        self.assertEqual(
            adapter.get_environment_info(),
            {'operating_system': 'Remote VNC Device'},
        )

    def test_environment_info_uses_configured_operating_system(self):
        adapter = self._make_adapter(
            {'host': '127.0.0.1', 'operating_system': 'Windows 11'}
        )

        self.assertEqual(
            adapter.get_environment_info(),
            {'operating_system': 'Windows 11'},
        )

    def test_get_status_returns_connection_metadata(self):
        adapter = self._make_adapter({'host': '127.0.0.1', 'port': 6001})

        self.assertEqual(
            adapter.get_status(),
            {
                'device_name': 'vnc',
                'connected_via': 'vnc',
                'host': '127.0.0.1',
                'port': 6001,
                'connected': False,
            },
        )

        sentinel = object()
        adapter._client = sentinel

        self.assertEqual(
            adapter.get_status(),
            {
                'device_name': 'vnc',
                'connected_via': 'vnc',
                'host': '127.0.0.1',
                'port': 6001,
                'connected': True,
            },
        )


class VncDeviceAdapterFailureTests(unittest.TestCase):
    def _make_adapter(self, plugin_config):
        from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter

        return VncDeviceAdapter(plugin_config)

    def test_unsupported_command_raises_value_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})

        with self.assertRaisesRegex(ValueError, r'^vnc 不支持命令类型: nope$'):
            adapter.execute_command(DeviceCommand('nope', {}))

    def test_malformed_coordinate_payload_raises_value_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        adapter._client = unittest.mock.Mock()

        with self.assertRaisesRegex(ValueError, r'^vnc 坐标格式无效: bad$'):
            adapter.execute_command(DeviceCommand('click', {'point': 'bad'}))

    def test_status_reports_connection_target_metadata(self):
        adapter = self._make_adapter({'host': '127.0.0.1', 'port': 6001})

        self.assertEqual(
            adapter.get_status(),
            {
                'device_name': 'vnc',
                'connected_via': 'vnc',
                'host': '127.0.0.1',
                'port': 6001,
                'connected': False,
            },
        )

        adapter._client = object()

        self.assertEqual(
            adapter.get_status(),
            {
                'device_name': 'vnc',
                'connected_via': 'vnc',
                'host': '127.0.0.1',
                'port': 6001,
                'connected': True,
            },
        )


class VncDeviceAdapterMouseCommandTests(unittest.TestCase):
    def _make_adapter(self, plugin_config):
        from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter

        return VncDeviceAdapter(plugin_config)

    def test_click_moves_then_left_clicks(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(DeviceCommand('click', {'point': [12, 34]}))

        self.assertEqual(result, 'click 执行成功')
        self.assertEqual(
            client.method_calls,
            [unittest.mock.call.mouseMove(12, 34), unittest.mock.call.mousePress(1)],
        )

    def test_double_click_moves_then_clicks_twice(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(
            DeviceCommand('double_click', {'point': [20, 40]})
        )

        self.assertEqual(result, 'double_click 执行成功')
        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.mouseMove(20, 40),
                unittest.mock.call.mousePress(1),
                unittest.mock.call.mousePress(1),
            ],
        )

    def test_right_click_uses_button_three(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(
            DeviceCommand('right_click', {'point': [50, 60]})
        )

        self.assertEqual(result, 'right_click 执行成功')
        self.assertEqual(
            client.method_calls,
            [unittest.mock.call.mouseMove(50, 60), unittest.mock.call.mousePress(3)],
        )

    def test_move_only_moves_pointer(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(DeviceCommand('move', {'point': [70, 80]}))

        self.assertEqual(result, 'move 执行成功')
        self.assertEqual(client.method_calls, [unittest.mock.call.mouseMove(70, 80)])

    def test_drag_presses_moves_and_releases(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(
            DeviceCommand(
                'drag',
                {'start_point': [10, 20], 'end_point': [30, 40]},
            )
        )

        self.assertEqual(result, 'drag 执行成功')
        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.mouseMove(10, 20),
                unittest.mock.call.mouseDown(1),
                unittest.mock.call.mouseMove(30, 40),
                unittest.mock.call.mouseUp(1),
            ],
        )

    def test_click_rejects_invalid_point_payload(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        with self.assertRaisesRegex(ValueError, 'vnc 坐标格式无效'):
            adapter.execute_command(DeviceCommand('click', {'point': 'bad'}))

        client.mouseMove.assert_not_called()
        client.mousePress.assert_not_called()

    def test_drag_uses_start_and_end_box_fallbacks(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(
            DeviceCommand(
                'drag',
                {'start_box': [11, 22], 'end_box': [33, 44]},
            )
        )

        self.assertEqual(result, 'drag 执行成功')
        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.mouseMove(11, 22),
                unittest.mock.call.mouseDown(1),
                unittest.mock.call.mouseMove(33, 44),
                unittest.mock.call.mouseUp(1),
            ],
        )

    def test_unsupported_command_raises_clear_value_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})

        with self.assertRaisesRegex(ValueError, 'vnc 不支持命令类型: swipe'):
            adapter.execute_command(DeviceCommand('swipe', {}))

    def test_drag_calls_mouseup_when_second_move_fails(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        client.mouseMove.side_effect = [None, RuntimeError('move failed')]
        adapter._client = client

        with self.assertRaisesRegex(RuntimeError, 'vnc drag 失败: move failed'):
            adapter.execute_command(
                DeviceCommand(
                    'drag',
                    {'start_point': [10, 20], 'end_point': [30, 40]},
                )
            )

        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.mouseMove(10, 20),
                unittest.mock.call.mouseDown(1),
                unittest.mock.call.mouseMove(30, 40),
                unittest.mock.call.mouseUp(1),
            ],
        )


class VncDeviceAdapterKeyboardCommandTests(unittest.TestCase):
    def _make_adapter(self, plugin_config):
        from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter

        return VncDeviceAdapter(plugin_config)

    def test_type_text_uses_key_type(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(
            DeviceCommand('type_text', {'content': 'hello world'})
        )

        self.assertEqual(result, 'type_text 执行成功')
        client.keyType.assert_called_once_with('hello world')

    def test_hotkey_presses_and_releases_in_order(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(DeviceCommand('hotkey', {'key': 'ctrl+shift+a'}))

        self.assertEqual(result, 'hotkey 执行成功')
        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.keyDown('ctrl'),
                unittest.mock.call.keyDown('shift'),
                unittest.mock.call.keyPress('a'),
                unittest.mock.call.keyUp('shift'),
                unittest.mock.call.keyUp('ctrl'),
            ],
        )

    def test_key_down_and_key_up_forward_single_key(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        down_result = adapter.execute_command(DeviceCommand('key_down', {'key': 'A'}))
        up_result = adapter.execute_command(DeviceCommand('key_up', {'key': 'A'}))

        self.assertEqual(down_result, 'key_down 执行成功')
        self.assertEqual(up_result, 'key_up 执行成功')
        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.keyDown('a'),
                unittest.mock.call.keyUp('a'),
            ],
        )

    def test_scroll_uses_vnc_wheel_buttons(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        result = adapter.execute_command(
            DeviceCommand(
                'scroll',
                {'point': [100, 120], 'direction': 'left', 'steps': 2},
            )
        )

        self.assertEqual(result, 'scroll 执行成功')
        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.mouseMove(100, 120),
                unittest.mock.call.mousePress(6),
                unittest.mock.call.mousePress(6),
            ],
        )

    def test_wait_sleeps_locally(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        adapter._client = unittest.mock.Mock()

        with patch(
            'computer_use.devices.plugins.vnc.adapter.time.sleep'
        ) as sleep_mock, patch.object(
            adapter,
            '_require_client',
            side_effect=AssertionError('should not connect'),
        ):
            result = adapter.execute_command(DeviceCommand('wait', {'seconds': 3}))

        self.assertEqual(result, '等待 3 秒')
        sleep_mock.assert_called_once_with(3.0)

    def test_wait_invalid_input_raises_validation_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})

        with patch(
            'computer_use.devices.plugins.vnc.adapter.time.sleep'
        ) as sleep_mock, patch.object(
            adapter,
            '_require_client',
            side_effect=AssertionError('should not connect'),
        ):
            with self.assertRaisesRegex(ValueError, 'vnc wait seconds 格式无效'):
                adapter.execute_command(DeviceCommand('wait', {'seconds': 'fast'}))

        sleep_mock.assert_not_called()

    def test_hotkey_rejects_missing_key(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        with self.assertRaisesRegex(ValueError, 'vnc hotkey 需要 key'):
            adapter.execute_command(DeviceCommand('hotkey', {'key': ''}))

        client.keyDown.assert_not_called()
        client.keyUp.assert_not_called()
        client.keyPress.assert_not_called()

    def test_type_text_wraps_client_failure(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        client.keyType.side_effect = RuntimeError('boom')
        adapter._client = client

        with self.assertRaisesRegex(RuntimeError, 'vnc type_text 失败: boom'):
            adapter.execute_command(DeviceCommand('type_text', {'content': 'hello'}))

        client.keyType.assert_called_once_with('hello')

    def test_hotkey_releases_only_pressed_modifiers_and_preserves_primary_failure(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        client.keyDown.side_effect = [None, RuntimeError('down failed')]
        client.keyUp.side_effect = RuntimeError('up failed')
        adapter._client = client

        with self.assertRaisesRegex(RuntimeError, 'vnc hotkey 失败: down failed'):
            adapter.execute_command(DeviceCommand('hotkey', {'key': 'ctrl shift a'}))

        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.keyDown('ctrl'),
                unittest.mock.call.keyDown('shift'),
                unittest.mock.call.keyUp('ctrl'),
            ],
        )
        client.keyPress.assert_not_called()

    def test_hotkey_raises_keyup_failure_after_success(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        client.keyUp.side_effect = [RuntimeError('up failed'), None]
        adapter._client = client

        with self.assertRaisesRegex(RuntimeError, 'vnc hotkey 失败: up failed'):
            adapter.execute_command(DeviceCommand('hotkey', {'key': 'ctrl shift a'}))

        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.keyDown('ctrl'),
                unittest.mock.call.keyDown('shift'),
                unittest.mock.call.keyPress('a'),
                unittest.mock.call.keyUp('shift'),
                unittest.mock.call.keyUp('ctrl'),
            ],
        )

    def test_scroll_invalid_direction_raises_validation_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        with self.assertRaisesRegex(ValueError, 'vnc 不支持滚动方向: diagonal'):
            adapter.execute_command(
                DeviceCommand(
                    'scroll',
                    {'point': [10, 20], 'direction': 'diagonal', 'steps': 2},
                )
            )

        client.mouseMove.assert_not_called()
        client.mousePress.assert_not_called()

    def test_scroll_non_positive_steps_raise_validation_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        with self.assertRaisesRegex(ValueError, 'vnc scroll steps 必须大于 0'):
            adapter.execute_command(
                DeviceCommand(
                    'scroll',
                    {'point': [10, 20], 'direction': 'down', 'steps': 0},
                )
            )

        with self.assertRaisesRegex(ValueError, 'vnc scroll steps 必须大于 0'):
            adapter.execute_command(
                DeviceCommand(
                    'scroll',
                    {'point': [10, 20], 'direction': 'down', 'steps': 'many'},
                )
            )

        client.mouseMove.assert_not_called()
        client.mousePress.assert_not_called()

    def test_scroll_wraps_client_failure(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        client.mousePress.side_effect = RuntimeError('wheel failed')
        adapter._client = client

        with self.assertRaisesRegex(RuntimeError, 'vnc scroll 失败: wheel failed'):
            adapter.execute_command(
                DeviceCommand(
                    'scroll',
                    {'point': [100, 120], 'direction': 'down', 'steps': 2},
                )
            )

        self.assertEqual(
            client.method_calls,
            [
                unittest.mock.call.mouseMove(100, 120),
                unittest.mock.call.mousePress(5),
            ],
        )

    def test_key_down_missing_key_raises_validation_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        adapter._client = client

        with self.assertRaisesRegex(ValueError, 'vnc key event 需要 key'):
            adapter.execute_command(DeviceCommand('key_down', {}))

        client.keyDown.assert_not_called()

    def test_key_up_wraps_client_failure(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'host': '127.0.0.1'})
        client = unittest.mock.Mock()
        client.keyUp.side_effect = RuntimeError('key up failed')
        adapter._client = client

        with self.assertRaisesRegex(RuntimeError, 'vnc key_up 失败: key up failed'):
            adapter.execute_command(DeviceCommand('key_up', {'key': 'CTRL'}))

        client.keyUp.assert_called_once_with('ctrl')


class VncDeviceAdapterConnectionTests(unittest.TestCase):
    def _make_adapter(self, plugin_config):
        from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter

        return VncDeviceAdapter(plugin_config)

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_connect_creates_client_with_password(self, api_mock):
        client = object()
        api_mock.connect.return_value = client
        adapter = self._make_adapter(
            {'host': '10.0.0.8', 'port': 5901, 'password': 'secret'}
        )

        adapter.connect()

        api_mock.connect.assert_called_once_with(
            '10.0.0.8::5901', password='secret'
        )
        self.assertIs(adapter._client, client)

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_connect_wraps_connection_error(self, api_mock):
        api_mock.connect.side_effect = ConnectionError('timeout')
        adapter = self._make_adapter(
            {'host': '10.0.0.8', 'port': 5901, 'password': 'secret'}
        )

        with self.assertRaisesRegex(RuntimeError, 'vnc connect 失败'):
            adapter.connect()

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_connect_wraps_auth_error(self, api_mock):
        api_mock.connect.side_effect = ConnectionError('auth failed')
        adapter = self._make_adapter(
            {'host': '10.0.0.8', 'port': 5901, 'password': 'secret'}
        )

        with self.assertRaisesRegex(RuntimeError, 'vnc 认证失败'):
            adapter.connect()

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_connect_short_circuits_when_client_exists(self, api_mock):
        adapter = self._make_adapter({'host': '10.0.0.8', 'port': 5901})
        sentinel = object()
        adapter._client = sentinel

        adapter.connect()

        api_mock.connect.assert_not_called()
        self.assertIs(adapter._client, sentinel)

    @patch('computer_use.devices.plugins.vnc.adapter.api', None)
    def test_connect_raises_when_dependency_missing(self):
        adapter = self._make_adapter({'host': '10.0.0.8', 'port': 5901})

        with self.assertRaisesRegex(
            RuntimeError, '缺少 vncdotool 依赖，请先安装 vncdotool'
        ):
            adapter.connect()

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_require_client_returns_existing_client(self, api_mock):
        adapter = self._make_adapter({'host': '10.0.0.8', 'port': 5901})
        sentinel = object()
        adapter._client = sentinel

        self.assertIs(adapter._require_client(), sentinel)
        api_mock.connect.assert_not_called()

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_require_client_connects_and_returns_client(self, api_mock):
        client = object()
        api_mock.connect.return_value = client
        adapter = self._make_adapter(
            {'host': '10.0.0.8', 'port': 5901, 'password': 'secret'}
        )

        self.assertIs(adapter._require_client(), client)
        api_mock.connect.assert_called_once_with(
            '10.0.0.8::5901', password='secret'
        )

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_close_disconnects_existing_client(self, api_mock):
        client = unittest.mock.Mock()
        adapter = self._make_adapter({'host': '10.0.0.8', 'port': 5901})
        adapter._client = client

        adapter.close()

        self.assertIsNone(adapter._client)
        client.disconnect.assert_called_once_with()


class VncDeviceAdapterCaptureTests(unittest.TestCase):
    def _make_adapter(self, plugin_config):
        from computer_use.devices.plugins.vnc.adapter import VncDeviceAdapter

        return VncDeviceAdapter(plugin_config)

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_capture_frame_returns_png_data_url(self, api_mock):
        from PIL import Image

        image = Image.new('RGB', (1, 1), color='white')
        client = unittest.mock.Mock()
        client.captureScreen.return_value = image
        api_mock.connect.return_value = client
        adapter = self._make_adapter(
            {'host': '10.0.0.8', 'port': 5901, 'password': 'secret'}
        )

        frame = adapter.capture_frame()

        self.assertTrue(frame.image_data_url.startswith('data:image/png;base64,'))
        self.assertEqual(frame.width, 1)
        self.assertEqual(frame.height, 1)
        self.assertEqual(
            frame.metadata,
            {
                'device_name': 'vnc',
                'capture_method': 'vncdotool',
                'host': '10.0.0.8',
                'port': 5901,
            },
        )
        client.captureScreen.assert_called_once_with()
        api_mock.connect.assert_called_once_with(
            '10.0.0.8::5901', password='secret'
        )

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_capture_frame_wraps_errors(self, api_mock):
        client = unittest.mock.Mock()
        client.captureScreen.side_effect = RuntimeError('boom')
        api_mock.connect.return_value = client
        adapter = self._make_adapter({'host': '10.0.0.8', 'port': 5901})

        with self.assertRaisesRegex(RuntimeError, 'vnc capture screenshot 失败'):
            adapter.capture_frame()

        client.captureScreen.assert_called_once_with()

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_capture_frame_wraps_downstream_pipeline_errors(self, api_mock):
        from PIL import Image

        image = Image.new('RGB', (1, 1), color='white')
        client = unittest.mock.Mock()
        client.captureScreen.return_value = image
        api_mock.connect.return_value = client
        adapter = self._make_adapter({'host': '10.0.0.8', 'port': 5901})

        with patch.object(image, 'save', side_effect=RuntimeError('save failed')):
            with self.assertRaisesRegex(
                RuntimeError, 'vnc capture screenshot 失败: save failed'
            ):
                adapter.capture_frame()

        client.captureScreen.assert_called_once_with()

    @patch('computer_use.devices.plugins.vnc.adapter.api')
    def test_close_swallows_disconnect_failure(self, api_mock):
        client = unittest.mock.Mock()
        client.disconnect.side_effect = RuntimeError('disconnect failed')
        adapter = self._make_adapter({'host': '10.0.0.8', 'port': 5901})
        adapter._client = client

        adapter.close()

        self.assertIsNone(adapter._client)
        client.disconnect.assert_called_once_with()
