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


if __name__ == '__main__':
    unittest.main()
