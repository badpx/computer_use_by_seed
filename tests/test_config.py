import os
import unittest

from computer_use.config import Config


class ConfigDefaultsTests(unittest.TestCase):
    def test_max_steps_defaults_to_one_hundred(self):
        original_env = os.environ.pop('MAX_STEPS', None)
        original_load_from_file = Config._load_from_file
        try:
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.max_steps, 100)
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is not None:
                os.environ['MAX_STEPS'] = original_env

    def test_display_index_defaults_to_zero(self):
        original_env = os.environ.pop('DISPLAY_INDEX', None)
        original_load_from_file = Config._load_from_file
        try:
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.display_index, 0)
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is not None:
                os.environ['DISPLAY_INDEX'] = original_env

    def test_device_name_defaults_to_local(self):
        original_env = os.environ.pop('DEVICE_NAME', None)
        original_load_from_file = Config._load_from_file
        try:
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.device_name, 'local')
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is not None:
                os.environ['DEVICE_NAME'] = original_env

    def test_device_config_json_defaults_to_empty_dict(self):
        original_env = os.environ.pop('DEVICE_CONFIG_JSON', None)
        original_load_from_file = Config._load_from_file
        try:
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.device_config, {})
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is not None:
                os.environ['DEVICE_CONFIG_JSON'] = original_env

    def test_enable_ask_user_for_single_task_defaults_to_false(self):
        original_env = os.environ.pop('ENABLE_ASK_USER_FOR_SINGLE_TASK', None)
        original_load_from_file = Config._load_from_file
        try:
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertFalse(config.enable_ask_user_for_single_task)
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is not None:
                os.environ['ENABLE_ASK_USER_FOR_SINGLE_TASK'] = original_env

    def test_enable_ask_user_for_single_task_can_be_enabled_from_env(self):
        original_env = os.environ.get('ENABLE_ASK_USER_FOR_SINGLE_TASK')
        original_load_from_file = Config._load_from_file
        try:
            os.environ['ENABLE_ASK_USER_FOR_SINGLE_TASK'] = 'true'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertTrue(config.enable_ask_user_for_single_task)
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('ENABLE_ASK_USER_FOR_SINGLE_TASK', None)
            else:
                os.environ['ENABLE_ASK_USER_FOR_SINGLE_TASK'] = original_env


if __name__ == '__main__':
    unittest.main()
