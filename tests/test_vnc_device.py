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
    def test_close_disconnects_existing_client(self, api_mock):
        client = unittest.mock.Mock()
        adapter = self._make_adapter({'host': '10.0.0.8', 'port': 5901})
        adapter._client = client

        adapter.close()

        self.assertIsNone(adapter._client)
        client.disconnect.assert_called_once_with()
