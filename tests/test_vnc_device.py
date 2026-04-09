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
