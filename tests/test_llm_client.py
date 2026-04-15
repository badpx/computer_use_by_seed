import types
import unittest
from unittest import mock


class OpenAiLlmAdapterTests(unittest.TestCase):
    def test_openai_chat_client_delegates_extra_body_building_to_provider_profile(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        provider_profile = mock.Mock()
        provider_profile.build_extra_body.return_value = {'custom': 'value'}
        provider_profile.build_extra_headers.return_value = {'X-Test': 'value'}
        client = OpenAiChatClient(
            sdk_client=sdk_client,
            provider='demo',
            provider_profile=provider_profile,
            provider_config={'demo': True},
        )

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.2,
            thinking_mode='enabled',
            reasoning_effort='high',
        )

        provider_profile.build_extra_body.assert_called_once_with(
            thinking_mode='enabled',
            reasoning_effort='high',
            provider_config={'demo': True},
        )
        provider_profile.build_extra_headers.assert_called_once_with(
            thinking_mode='enabled',
            reasoning_effort='high',
            provider_config={'demo': True},
        )
        sdk_client.chat.completions.create.assert_called_once_with(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.2,
            extra_body={'custom': 'value'},
            extra_headers={'X-Test': 'value'},
        )

    def test_ark_provider_puts_thinking_and_reasoning_effort_into_extra_body(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        client = OpenAiChatClient(sdk_client=sdk_client, provider='ark')

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.2,
            thinking_mode='enabled',
            reasoning_effort='high',
            tools=[{'type': 'function', 'function': {'name': 'noop'}}],
        )

        sdk_client.chat.completions.create.assert_called_once_with(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.2,
            tools=[{'type': 'function', 'function': {'name': 'noop'}}],
            extra_body={
                'thinking': {'type': 'enabled'},
                'reasoning_effort': 'high',
            },
        )

    def test_adapter_omits_extra_body_when_no_provider_extensions_are_requested(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        client = OpenAiChatClient(sdk_client=sdk_client, provider='ark')

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.0,
        )

        sdk_client.chat.completions.create.assert_called_once_with(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.0,
        )

    def test_adapter_passes_stream_when_explicitly_configured(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        client = OpenAiChatClient(sdk_client=sdk_client, provider='openai')

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.0,
            stream=True,
        )

        sdk_client.chat.completions.create.assert_called_once_with(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.0,
            stream=True,
        )

    def test_adapter_omits_stream_when_unconfigured(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        client = OpenAiChatClient(sdk_client=sdk_client, provider='openai')

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.0,
        )

        self.assertNotIn(
            'stream',
            sdk_client.chat.completions.create.call_args.kwargs,
        )

    def test_create_llm_client_uses_openai_sdk_with_provider_and_connection_settings(self):
        from computer_use.llm.factory import create_llm_client

        openai_client = mock.Mock()
        with mock.patch(
            'computer_use.llm.openai_adapter.OpenAI',
            return_value=openai_client,
        ) as openai_cls:
            chat_client = create_llm_client(
                provider='ark',
                api_key='test-key',
                base_url='https://ark.example/v3',
                provider_config={},
            )

        openai_cls.assert_called_once_with(
            api_key='test-key',
            base_url='https://ark.example/v3',
        )
        self.assertEqual(chat_client.provider, 'ark')
        self.assertIs(chat_client.sdk_client, openai_client)

    def test_create_llm_client_supports_openrouter_provider(self):
        from computer_use.llm.factory import create_llm_client

        openai_client = mock.Mock()
        with mock.patch(
            'computer_use.llm.openai_adapter.OpenAI',
            return_value=openai_client,
        ):
            chat_client = create_llm_client(
                provider='openrouter',
                api_key='test-key',
                base_url='https://openrouter.ai/api/v1',
                provider_config={
                    'http_referer': 'https://example.com',
                    'title': 'Computer Use Tool',
                },
            )

        self.assertEqual(chat_client.provider, 'openrouter')
        self.assertIs(chat_client.sdk_client, openai_client)

    def test_create_llm_client_supports_openai_provider(self):
        from computer_use.llm.factory import create_llm_client

        openai_client = mock.Mock()
        with mock.patch(
            'computer_use.llm.openai_adapter.OpenAI',
            return_value=openai_client,
        ):
            chat_client = create_llm_client(
                provider='openai',
                api_key='test-key',
                base_url='https://api.openai.com/v1',
                provider_config={},
            )

        self.assertEqual(chat_client.provider, 'openai')
        self.assertIs(chat_client.sdk_client, openai_client)

    def test_create_llm_client_supports_ollama_provider(self):
        from computer_use.llm.factory import create_llm_client

        openai_client = mock.Mock()
        with mock.patch(
            'computer_use.llm.openai_adapter.OpenAI',
            return_value=openai_client,
        ):
            chat_client = create_llm_client(
                provider='ollama',
                api_key='test-key',
                base_url='http://localhost:11434/v1',
                provider_config={},
            )

        self.assertEqual(chat_client.provider, 'ollama')
        self.assertIs(chat_client.sdk_client, openai_client)

    def test_openrouter_profile_builds_recommended_headers_from_provider_config(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        client = OpenAiChatClient(
            sdk_client=sdk_client,
            provider='openrouter',
            provider_config={
                'http_referer': 'https://example.com/app',
                'title': 'Computer Use Tool',
            },
        )

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.1,
        )

        sdk_client.chat.completions.create.assert_called_once_with(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.1,
            extra_headers={
                'HTTP-Referer': 'https://example.com/app',
                'X-OpenRouter-Title': 'Computer Use Tool',
            },
        )

    def test_ollama_profile_maps_enabled_thinking_to_enabled_payload(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        client = OpenAiChatClient(
            sdk_client=sdk_client,
            provider='ollama',
            provider_config={},
        )

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.1,
            thinking_mode='enabled',
            reasoning_effort='high',
        )

        sdk_client.chat.completions.create.assert_called_once_with(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.1,
            extra_body={'thinking': {'type': 'enabled'}},
        )

    def test_ollama_profile_maps_disabled_thinking_to_disabled_payload(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        client = OpenAiChatClient(
            sdk_client=sdk_client,
            provider='ollama',
            provider_config={},
        )

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.1,
            thinking_mode='disabled',
        )

        sdk_client.chat.completions.create.assert_called_once_with(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.1,
            extra_body={'thinking': {'type': 'disabled'}},
        )

    def test_ollama_profile_omits_auto_thinking_and_reasoning_effort(self):
        from computer_use.llm.openai_adapter import OpenAiChatClient

        sdk_client = mock.Mock()
        sdk_client.chat.completions.create.return_value = object()
        client = OpenAiChatClient(
            sdk_client=sdk_client,
            provider='ollama',
            provider_config={},
        )

        client.create_chat_completion(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.1,
            thinking_mode='auto',
            reasoning_effort='high',
        )

        sdk_client.chat.completions.create.assert_called_once_with(
            model='demo-model',
            messages=[{'role': 'user', 'content': 'hello'}],
            temperature=0.1,
        )


class AgentUsesLlmAdapterTests(unittest.TestCase):
    def test_agent_initializes_with_llm_adapter_not_ark_sdk(self):
        from computer_use.devices.base import DeviceFrame

        class FakeDevice:
            device_name = 'local'

            def connect(self):
                return None

            def close(self):
                return None

            def capture_frame(self):
                return DeviceFrame(
                    image_data_url='data:image/png;base64,iVBORw0KGgo=',
                    width=1,
                    height=1,
                    metadata={},
                )

            def execute_command(self, command):
                return 'DONE'

            def get_status(self):
                return {'device_name': 'local'}

        fake_response = types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(
                        content="Thought: done\nAction: finished(content='ok')",
                        reasoning_content=None,
                        tool_calls=None,
                    ),
                    finish_reason='stop',
                )
            ],
            usage=None,
        )

        fake_llm_client = mock.Mock()
        fake_llm_client.create_chat_completion.return_value = fake_response
        fake_llm_client.reasoning_field_name = 'reasoning_content'

        with mock.patch.dict(
            __import__('os').environ,
            {'API_KEY': 'test-key'},
            clear=False,
        ), mock.patch(
            'computer_use.agent.create_llm_client',
            return_value=fake_llm_client,
        ):
            from computer_use.agent import ComputerUseAgent

            agent = ComputerUseAgent(
                device_adapter=FakeDevice(),
                device_name='local',
                api_key='test-key',
                max_steps=1,
                verbose=False,
                print_init_status=False,
            )
            result = agent.run('Do a thing')

        self.assertTrue(result['success'])
        fake_llm_client.create_chat_completion.assert_called()


class ProviderRegistryTests(unittest.TestCase):
    def test_get_provider_profile_returns_registered_ark_profile(self):
        from computer_use.llm.providers import get_provider_profile

        profile = get_provider_profile('ark')

        self.assertEqual(profile.name, 'ark')
        self.assertEqual(profile.reasoning_field_name, 'reasoning_content')
        self.assertEqual(
            profile.build_extra_body(
                thinking_mode='enabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {
                'thinking': {'type': 'enabled'},
                'reasoning_effort': 'high',
            },
        )

    def test_get_provider_profile_rejects_unknown_provider(self):
        from computer_use.llm.providers import get_provider_profile

        with self.assertRaisesRegex(ValueError, '不支持的 provider'):
            get_provider_profile('unknown-provider')

    def test_get_provider_profile_returns_registered_openrouter_profile(self):
        from computer_use.llm.providers import get_provider_profile

        profile = get_provider_profile('openrouter')

        self.assertEqual(profile.name, 'openrouter')
        self.assertEqual(profile.reasoning_field_name, 'reasoning')
        self.assertEqual(
            profile.build_extra_body(
                thinking_mode='enabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {},
        )
        self.assertEqual(
            profile.build_extra_headers(
                thinking_mode='enabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {},
        )

    def test_get_provider_profile_returns_registered_openai_profile(self):
        from computer_use.llm.providers import get_provider_profile

        profile = get_provider_profile('openai')

        self.assertEqual(profile.name, 'openai')
        self.assertEqual(profile.reasoning_field_name, 'reasoning')
        self.assertEqual(
            profile.build_extra_body(
                thinking_mode='enabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {},
        )
        self.assertEqual(
            profile.build_extra_headers(
                thinking_mode='enabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {},
        )

    def test_get_provider_profile_returns_registered_ollama_profile(self):
        from computer_use.llm.providers import get_provider_profile

        profile = get_provider_profile('ollama')

        self.assertEqual(profile.name, 'ollama')
        self.assertEqual(profile.reasoning_field_name, 'reasoning')
        self.assertEqual(
            profile.build_extra_body(
                thinking_mode='enabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {'thinking': {'type': 'enabled'}},
        )
        self.assertEqual(
            profile.build_extra_body(
                thinking_mode='disabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {'thinking': {'type': 'disabled'}},
        )
        self.assertEqual(
            profile.build_extra_body(
                thinking_mode='auto',
                reasoning_effort='high',
                provider_config={},
            ),
            {},
        )
        self.assertEqual(
            profile.build_extra_headers(
                thinking_mode='enabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {},
        )

    def test_default_provider_profile_returns_no_extra_headers(self):
        from computer_use.llm.providers import get_provider_profile

        profile = get_provider_profile('ark')

        self.assertEqual(
            profile.build_extra_headers(
                thinking_mode='enabled',
                reasoning_effort='high',
                provider_config={},
            ),
            {},
        )
