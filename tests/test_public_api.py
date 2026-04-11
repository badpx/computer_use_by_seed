import importlib
import sys
import unittest


class PublicApiTests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop('computer_use', None)
        sys.modules.pop('computer_use.devices', None)
        sys.modules.pop('computer_use.devices.plugins', None)
        sys.modules.pop('computer_use.devices.plugins.vnc', None)

    def test_top_level_module_no_longer_exports_action_executor(self):
        module = importlib.import_module('computer_use')

        with self.assertRaises(AttributeError):
            getattr(module, 'ActionExecutor')

        with self.assertRaises(AttributeError):
            getattr(module, 'execute_action')

    def test_top_level_module_exposes_devices_subpackage_for_patch_lookups(self):
        module = importlib.import_module('computer_use')

        devices_module = getattr(module, 'devices')

        self.assertIs(devices_module, sys.modules['computer_use.devices'])
        self.assertTrue(hasattr(devices_module, 'create_device_adapter'))

    def test_nested_plugin_packages_are_visible_for_patch_lookups(self):
        module = importlib.import_module('computer_use')

        adapter_module = module.devices.plugins.vnc.adapter

        self.assertIs(adapter_module, sys.modules['computer_use.devices.plugins.vnc.adapter'])
