import os
import unittest

from computer_use.config import Config


class ConfigDefaultsTests(unittest.TestCase):
    def test_api_key_reads_from_neutral_name(self):
        original_env = os.environ.get('API_KEY')
        original_legacy = os.environ.pop('ARK_API_KEY', None)
        original_load_from_file = Config._load_from_file
        try:
            os.environ['API_KEY'] = 'neutral-key'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.api_key, 'neutral-key')
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('API_KEY', None)
            else:
                os.environ['API_KEY'] = original_env
            if original_legacy is not None:
                os.environ['ARK_API_KEY'] = original_legacy

    def test_provider_defaults_to_ark(self):
        original_env = os.environ.pop('PROVIDER', None)
        original_load_from_file = Config._load_from_file
        try:
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.provider, 'ark')
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is not None:
                os.environ['PROVIDER'] = original_env

    def test_provider_accepts_openrouter(self):
        original_env = os.environ.get('PROVIDER')
        original_load_from_file = Config._load_from_file
        try:
            os.environ['PROVIDER'] = 'openrouter'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.provider, 'openrouter')
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('PROVIDER', None)
            else:
                os.environ['PROVIDER'] = original_env

    def test_provider_accepts_openai(self):
        original_env = os.environ.get('PROVIDER')
        original_load_from_file = Config._load_from_file
        try:
            os.environ['PROVIDER'] = 'openai'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.provider, 'openai')
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('PROVIDER', None)
            else:
                os.environ['PROVIDER'] = original_env

    def test_provider_accepts_ollama(self):
        original_env = os.environ.get('PROVIDER')
        original_load_from_file = Config._load_from_file
        try:
            os.environ['PROVIDER'] = 'ollama'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.provider, 'ollama')
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('PROVIDER', None)
            else:
                os.environ['PROVIDER'] = original_env

    def test_model_reads_from_neutral_name(self):
        original_env = os.environ.get('MODEL')
        original_legacy = os.environ.pop('ARK_MODEL', None)
        original_load_from_file = Config._load_from_file
        try:
            os.environ['MODEL'] = 'neutral-model'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.model, 'neutral-model')
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('MODEL', None)
            else:
                os.environ['MODEL'] = original_env
            if original_legacy is not None:
                os.environ['ARK_MODEL'] = original_legacy

    def test_base_url_reads_from_neutral_name(self):
        original_env = os.environ.get('BASE_URL')
        original_legacy = os.environ.pop('ARK_BASE_URL', None)
        original_load_from_file = Config._load_from_file
        try:
            os.environ['BASE_URL'] = 'https://example.invalid/v1'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.base_url, 'https://example.invalid/v1')
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('BASE_URL', None)
            else:
                os.environ['BASE_URL'] = original_env
            if original_legacy is not None:
                os.environ['ARK_BASE_URL'] = original_legacy

    def test_base_url_defaults_to_provider_specific_openrouter_endpoint(self):
        original_provider = os.environ.get('PROVIDER')
        original_base_url = os.environ.pop('BASE_URL', None)
        original_load_from_file = Config._load_from_file
        try:
            os.environ['PROVIDER'] = 'openrouter'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.base_url, 'https://openrouter.ai/api/v1')
        finally:
            Config._load_from_file = original_load_from_file
            if original_provider is None:
                os.environ.pop('PROVIDER', None)
            else:
                os.environ['PROVIDER'] = original_provider
            if original_base_url is not None:
                os.environ['BASE_URL'] = original_base_url

    def test_base_url_defaults_to_provider_specific_openai_endpoint(self):
        original_provider = os.environ.get('PROVIDER')
        original_base_url = os.environ.pop('BASE_URL', None)
        original_load_from_file = Config._load_from_file
        try:
            os.environ['PROVIDER'] = 'openai'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.base_url, 'https://api.openai.com/v1')
        finally:
            Config._load_from_file = original_load_from_file
            if original_provider is None:
                os.environ.pop('PROVIDER', None)
            else:
                os.environ['PROVIDER'] = original_provider
            if original_base_url is not None:
                os.environ['BASE_URL'] = original_base_url

    def test_base_url_defaults_to_provider_specific_ollama_endpoint(self):
        original_provider = os.environ.get('PROVIDER')
        original_base_url = os.environ.pop('BASE_URL', None)
        original_load_from_file = Config._load_from_file
        try:
            os.environ['PROVIDER'] = 'ollama'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.base_url, 'http://localhost:11434/v1')
        finally:
            Config._load_from_file = original_load_from_file
            if original_provider is None:
                os.environ.pop('PROVIDER', None)
            else:
                os.environ['PROVIDER'] = original_provider
            if original_base_url is not None:
                os.environ['BASE_URL'] = original_base_url

    def test_explicit_base_url_overrides_provider_specific_default(self):
        original_provider = os.environ.get('PROVIDER')
        original_base_url = os.environ.get('BASE_URL')
        original_load_from_file = Config._load_from_file
        try:
            os.environ['PROVIDER'] = 'openai'
            os.environ['BASE_URL'] = 'https://custom.example/v1'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.base_url, 'https://custom.example/v1')
        finally:
            Config._load_from_file = original_load_from_file
            if original_provider is None:
                os.environ.pop('PROVIDER', None)
            else:
                os.environ['PROVIDER'] = original_provider
            if original_base_url is None:
                os.environ.pop('BASE_URL', None)
            else:
                os.environ['BASE_URL'] = original_base_url

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

    def test_provider_config_json_defaults_to_empty_dict(self):
        original_env = os.environ.pop('PROVIDER_CONFIG_JSON', None)
        original_load_from_file = Config._load_from_file
        try:
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(config.provider_config, {})
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is not None:
                os.environ['PROVIDER_CONFIG_JSON'] = original_env

    def test_provider_config_json_reads_valid_json_object(self):
        original_env = os.environ.get('PROVIDER_CONFIG_JSON')
        original_load_from_file = Config._load_from_file
        try:
            os.environ['PROVIDER_CONFIG_JSON'] = '{"http_referer":"https://example.com","title":"Demo"}'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertEqual(
                config.provider_config,
                {'http_referer': 'https://example.com', 'title': 'Demo'},
            )
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('PROVIDER_CONFIG_JSON', None)
            else:
                os.environ['PROVIDER_CONFIG_JSON'] = original_env

    def test_stream_defaults_to_none(self):
        original_env = os.environ.pop('STREAM', None)
        original_load_from_file = Config._load_from_file
        try:
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertIsNone(config.stream)
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is not None:
                os.environ['STREAM'] = original_env

    def test_stream_reads_true_from_env(self):
        original_env = os.environ.get('STREAM')
        original_load_from_file = Config._load_from_file
        try:
            os.environ['STREAM'] = 'true'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertTrue(config.stream)
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('STREAM', None)
            else:
                os.environ['STREAM'] = original_env

    def test_stream_reads_false_from_env(self):
        original_env = os.environ.get('STREAM')
        original_load_from_file = Config._load_from_file
        try:
            os.environ['STREAM'] = 'false'
            Config._load_from_file = lambda self: None
            config = Config()
            self.assertFalse(config.stream)
        finally:
            Config._load_from_file = original_load_from_file
            if original_env is None:
                os.environ.pop('STREAM', None)
            else:
                os.environ['STREAM'] = original_env

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
