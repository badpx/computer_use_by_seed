import unittest


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
