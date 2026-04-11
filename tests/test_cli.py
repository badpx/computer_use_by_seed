import builtins
import io
import importlib
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


class FakePromptSession:
    def __init__(self, history=None, responses=None, multiline=False, key_bindings=None, **kwargs):
        self.history = history
        self.responses = list(responses or [])
        self.multiline = multiline
        self.key_bindings = key_bindings
        self.init_kwargs = kwargs
        self.prompts = []

    def prompt(self, text, **kwargs):
        toolbar = kwargs.get('bottom_toolbar')
        rendered_toolbar = toolbar() if callable(toolbar) else toolbar
        self.prompts.append(
            {
                'text': text,
                'bottom_toolbar': rendered_toolbar,
                'completer': kwargs.get('completer'),
                'complete_while_typing': kwargs.get('complete_while_typing'),
            }
        )
        if not self.responses:
            raise EOFError('No fake prompt responses left')
        return self.responses.pop(0)


class CliPromptTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop('computer_use.cli', None)
        self.cli = importlib.import_module('computer_use.cli')

    def tearDown(self):
        sys.modules.pop('prompt_toolkit', None)
        sys.modules.pop('prompt_toolkit.history', None)
        sys.modules.pop('prompt_toolkit.completion', None)

    def test_create_prompt_session_uses_file_history_when_prompt_toolkit_is_available(self):
        fake_prompt_toolkit = types.ModuleType('prompt_toolkit')
        fake_history_module = types.ModuleType('prompt_toolkit.history')
        fake_key_binding_module = types.ModuleType('prompt_toolkit.key_binding')
        history_calls = []

        class FakeFileHistory:
            def __init__(self, filename):
                history_calls.append(filename)
                self.filename = filename

        class FakeKeyBindings:
            def __init__(self):
                self.handlers = {}

            def add(self, *keys, **kwargs):
                del kwargs

                def decorator(func):
                    self.handlers[keys] = func
                    return func

                return decorator

        fake_prompt_toolkit.PromptSession = FakePromptSession
        fake_history_module.FileHistory = FakeFileHistory
        fake_key_binding_module.KeyBindings = FakeKeyBindings
        sys.modules['prompt_toolkit'] = fake_prompt_toolkit
        sys.modules['prompt_toolkit.history'] = fake_history_module
        sys.modules['prompt_toolkit.key_binding'] = fake_key_binding_module

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / 'history.txt'
            session = self.cli._create_prompt_session(history_file=history_path)

        self.assertIsInstance(session, FakePromptSession)
        self.assertEqual(history_calls, [str(history_path)])
        self.assertEqual(session.history.filename, str(history_path))
        self.assertTrue(session.multiline)
        self.assertIsNotNone(session.key_bindings)
        self.assertIn(('enter',), session.key_bindings.handlers)
        self.assertIn(('c-j',), session.key_bindings.handlers)
        self.assertIn(('c-p',), session.key_bindings.handlers)
        self.assertIn(('c-n',), session.key_bindings.handlers)

    def test_create_prompt_key_bindings_supports_multiline_navigation_and_submit(self):
        fake_key_binding_module = types.ModuleType('prompt_toolkit.key_binding')

        class FakeKeyBindings:
            def __init__(self):
                self.handlers = {}

            def add(self, *keys, **kwargs):
                del kwargs

                def decorator(func):
                    self.handlers[keys] = func
                    return func

                return decorator

        fake_key_binding_module.KeyBindings = FakeKeyBindings
        sys.modules['prompt_toolkit.key_binding'] = fake_key_binding_module

        key_bindings = self.cli._create_prompt_key_bindings()

        buffer = types.SimpleNamespace(
            validate_and_handle=mock.Mock(),
            insert_text=mock.Mock(),
            auto_up=mock.Mock(),
            auto_down=mock.Mock(),
        )
        event = types.SimpleNamespace(current_buffer=buffer, arg=3)

        key_bindings.handlers[('enter',)](event)
        key_bindings.handlers[('c-j',)](event)
        key_bindings.handlers[('c-p',)](event)
        key_bindings.handlers[('c-n',)](event)
        buffer.validate_and_handle.assert_called_once_with()
        self.assertEqual(buffer.insert_text.call_args_list, [mock.call('\n')])
        buffer.auto_up.assert_called_once_with(count=3)
        buffer.auto_down.assert_called_once_with(count=3)

    def test_create_prompt_session_returns_none_when_prompt_toolkit_is_unavailable(self):
        original_import_module = self.cli.importlib.import_module

        def fake_import_module(name):
            if name.startswith('prompt_toolkit'):
                raise ImportError('prompt_toolkit is unavailable')
            return original_import_module(name)

        with mock.patch.object(self.cli.importlib, 'import_module', side_effect=fake_import_module):
            session = self.cli._create_prompt_session(
                history_file=Path('/tmp/missing-history')
            )

        self.assertIsNone(session)

    def test_interactive_mode_prefers_prompt_toolkit_session(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.close_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {
                    'success': True,
                    'steps': [],
                    'final_response': 'done',
                }

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

            def close(self):
                self.close_calls += 1

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        fake_session = FakePromptSession(responses=['打开计算器', '/exit'])

        with mock.patch.object(self.cli, 'ensure_supported_python'), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=fake_session
        ), mock.patch.object(
            self.cli,
            '_create_command_completer',
            return_value=object(),
        ), mock.patch.object(
            builtins,
            'input',
            side_effect=AssertionError('input() should not be used'),
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, ['打开计算器'])
        self.assertEqual(fake_agent_instances[0].close_calls, 1)
        self.assertFalse(fake_agent_instances[0].kwargs['print_init_status'])
        self.assertTrue(fake_agent_instances[0].kwargs['persistent_session'])
        self.assertEqual(
            [prompt['text'] for prompt in fake_session.prompts],
            ['> ', '> '],
        )
        self.assertIn('🔋 0%', fake_session.prompts[0]['bottom_toolbar'])
        self.assertIsNotNone(fake_session.prompts[0]['completer'])
        self.assertTrue(fake_session.prompts[0]['complete_while_typing'])

    def test_interactive_mode_passes_ask_user_callback_to_agent(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.close_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                answer = self.kwargs['ask_user_callback']('Should I continue?')
                return {
                    'success': True,
                    'steps': [],
                    'final_response': answer,
                }

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                pass

            def compact_session_context(self, manual=False):
                return True

            def close(self):
                self.close_calls += 1

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        fake_session = FakePromptSession(responses=['打开计算器', '继续', '/exit'])

        with mock.patch.object(self.cli, 'ensure_supported_python'), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=fake_session
        ), mock.patch.object(
            self.cli,
            '_create_command_completer',
            return_value=object(),
        ), mock.patch.object(
            builtins,
            'input',
            side_effect=AssertionError('input() should not be used'),
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertTrue(callable(fake_agent_instances[0].kwargs['ask_user_callback']))
        self.assertEqual(fake_agent_instances[0].run_calls, ['打开计算器'])
        self.assertEqual(fake_agent_instances[0].close_calls, 1)
        self.assertEqual(
            [prompt['text'] for prompt in fake_session.prompts],
            ['> ', '? ', '> '],
        )

    def test_interactive_mode_falls_back_to_builtin_input_when_prompt_toolkit_is_unavailable(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.close_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {
                    'success': True,
                    'steps': [],
                    'final_response': 'done',
                }

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

            def close(self):
                self.close_calls += 1

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module

        with mock.patch.object(self.cli, 'ensure_supported_python'), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(builtins, 'input', side_effect=['粘贴的一长串指令', '/exit']) as mock_input:
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, ['粘贴的一长串指令'])
        self.assertEqual(fake_agent_instances[0].close_calls, 1)
        self.assertEqual(mock_input.call_count, 2)

    def test_interactive_mode_ctrl_c_during_ask_user_cancels_current_task(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.close_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                self.kwargs['ask_user_callback']('Should I continue?')
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

            def close(self):
                self.close_calls += 1

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['打开计算器', KeyboardInterrupt, '/exit']
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, ['打开计算器'])
        self.assertEqual(fake_agent_instances[0].close_calls, 1)
        self.assertIn('[中断] 用户取消操作', output.getvalue())

    def test_interactive_mode_ctrl_d_during_ask_user_exits(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.close_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                self.kwargs['ask_user_callback']('Should I continue?')
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

            def close(self):
                self.close_calls += 1

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['打开计算器', EOFError]
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, ['打开计算器'])
        self.assertEqual(fake_agent_instances[0].close_calls, 1)
        self.assertIn('感谢使用，再见！', output.getvalue())

    def test_interactive_mode_updates_status_bar_after_task(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'enabled'
                self.reasoning_effort = 'high'
                self.skills = [object(), object(), object()]
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {
                    'success': True,
                    'steps': [],
                    'final_response': 'done',
                    'elapsed_seconds': 12.5,
                    'runtime_status': {
                        'usage_total_tokens': 4096,
                        'context_estimated_tokens': 0,
                        'activated_skills': ['open-browser'],
                    },
                }

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        fake_session = FakePromptSession(responses=['打开计算器', '/exit'])

        with mock.patch.object(self.cli, 'ensure_supported_python'), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=fake_session
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        first_toolbar = fake_session.prompts[0]['bottom_toolbar']
        second_toolbar = fake_session.prompts[1]['bottom_toolbar']
        self.assertIn('🧠 fake-model high', first_toolbar)
        self.assertIn('🔋 0%', first_toolbar)
        self.assertIn('🛠️ 0/3', first_toolbar)
        self.assertIn('⏱️ 0m', first_toolbar)
        self.assertIn('🔋 2%', second_toolbar)
        self.assertIn('🛠️ 1/3', second_toolbar)
        self.assertIn('⏱️ 0m', second_toolbar)

    def test_status_bar_renders_runtime_status_note_at_the_end(self):
        status_bar = self.cli.InteractiveStatusBar(
            model='fake-model',
            thinking_mode='enabled',
            reasoning_effort='high',
            total_skills=3,
        )

        status_bar.update_live_status(
            {
                'context_estimated_tokens': int(self.cli.CONTEXT_WINDOW_TOKENS * 0.86),
                'activated_skills': ['open-browser'],
                'status_note': 'Auto compact soon',
            }
        )

        rendered = status_bar.render()
        self.assertIn('🪫 86%', rendered)
        self.assertIn('🛠️ 1/3', rendered)
        self.assertTrue(rendered.endswith(' | Auto compact soon'))

    def test_status_bar_switches_context_battery_icon_at_warning_threshold(self):
        status_bar = self.cli.InteractiveStatusBar(
            model='fake-model',
            thinking_mode='enabled',
            reasoning_effort='high',
            total_skills=3,
        )

        status_bar.context_percent = 84
        self.assertIn('🔋 84%', status_bar.render())

        status_bar.context_percent = 85
        self.assertIn('🪫 85%', status_bar.render())

    def test_status_bar_formats_duration_in_minutes_or_hours(self):
        status_bar = self.cli.InteractiveStatusBar(
            model='fake-model',
            thinking_mode='enabled',
            reasoning_effort='high',
            total_skills=3,
        )

        self.assertEqual(status_bar._format_elapsed_time(59), '0m')
        self.assertEqual(status_bar._format_elapsed_time(60), '1m')
        self.assertEqual(status_bar._format_elapsed_time(3599), '59m')
        self.assertEqual(status_bar._format_elapsed_time(3600), '1h00m')
        self.assertEqual(status_bar._format_elapsed_time(7260), '2h01m')

    def test_interactive_mode_exits_on_ctrl_d_with_prompt_toolkit(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        fake_session = FakePromptSession(responses=[])
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=fake_session
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, [])
        self.assertIn('感谢使用，再见！', output.getvalue())

    def test_interactive_mode_exits_on_ctrl_d_with_builtin_input(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=EOFError
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, [])
        self.assertIn('感谢使用，再见！', output.getvalue())

    def test_single_task_mode_passes_context_window_options_to_agent(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.clear_calls = 0
                self.compact_calls = 0
                fake_agent_instances.append(self)

            def run(self, instruction):
                return {
                    'success': True,
                    'steps': [],
                    'final_response': instruction,
                }

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module

        with mock.patch.object(self.cli, 'ensure_supported_python'):
            self.cli.single_task_mode(
                instruction='测试上下文参数',
                screenshot_size=1024,
                max_context_screenshots=3,
                include_execution_feedback=False,
                log_full_messages=True,
                verbose=False,
            )

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].kwargs['screenshot_size'], 1024)
        self.assertEqual(fake_agent_instances[0].kwargs['max_context_screenshots'], 3)
        self.assertEqual(
            fake_agent_instances[0].kwargs['include_execution_feedback'],
            False,
        )
        self.assertEqual(fake_agent_instances[0].kwargs['log_full_messages'], True)
        self.assertTrue(fake_agent_instances[0].kwargs['print_init_status'])
        self.assertFalse(fake_agent_instances[0].kwargs['persistent_session'])

    def test_single_task_mode_passes_device_options_to_agent(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                fake_agent_instances.append(self)

            def run(self, instruction):
                return {
                    'success': True,
                    'steps': [],
                    'final_response': instruction,
                }

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                pass

            def compact_session_context(self, manual=False):
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module

        with mock.patch.object(self.cli, 'ensure_supported_python'):
            self.cli.single_task_mode(
                instruction='测试设备参数',
                device_name='remote-sandbox',
                device_config={'sandbox_id': 'sbx-1'},
                devices_dir='/tmp/custom-devices',
                verbose=False,
            )

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].kwargs['device_name'], 'remote-sandbox')
        self.assertEqual(
            fake_agent_instances[0].kwargs['device_config'],
            {'sandbox_id': 'sbx-1'},
        )
        self.assertEqual(
            fake_agent_instances[0].kwargs['devices_dir'],
            '/tmp/custom-devices',
        )

    def test_single_task_mode_prints_config_info_only_in_debug_mode(self):
        fake_agent_module = types.ModuleType('computer_use.agent')

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def run(self, instruction):
                return {
                    'success': True,
                    'steps': [],
                    'final_response': instruction,
                }

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                pass

            def compact_session_context(self, manual=False):
                return True

        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module

        with mock.patch.object(self.cli, 'ensure_supported_python'):
            normal_output = io.StringIO()
            with redirect_stdout(normal_output):
                self.cli.single_task_mode(
                    instruction='普通模式',
                    verbose=True,
                    log_full_messages=False,
                )

            debug_output = io.StringIO()
            with redirect_stdout(debug_output):
                self.cli.single_task_mode(
                    instruction='调试模式',
                    verbose=True,
                    log_full_messages=True,
                )

        self.assertNotIn('[配置信息]', normal_output.getvalue())
        self.assertIn('[配置信息]', debug_output.getvalue())

    def test_single_task_mode_does_not_pass_ask_user_callback_to_agent(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                fake_agent_instances.append(self)

            def run(self, instruction):
                return {
                    'success': True,
                    'steps': [],
                    'final_response': instruction,
                }

            def close(self):
                return None

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module

        with mock.patch.object(self.cli, 'ensure_supported_python'):
            self.cli.single_task_mode(
                instruction='单次任务',
                verbose=False,
            )

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertNotIn('ask_user_callback', fake_agent_instances[0].kwargs)

    def test_ask_user_with_cli_returns_selected_option(self):
        with mock.patch.object(
            builtins,
            'input',
            side_effect=['2'],
        ):
            answer = self.cli._ask_user_with_cli(
                question='Which option?',
                options=['A', 'B'],
                prompt_session=None,
            )

        self.assertEqual(answer, 'B')

    def test_ask_user_with_cli_prompts_for_other_option_text(self):
        with mock.patch.object(
            builtins,
            'input',
            side_effect=['3', '自定义回答'],
        ):
            answer = self.cli._ask_user_with_cli(
                question='Which option?',
                options=['A', 'B'],
                prompt_session=None,
            )

        self.assertEqual(answer, '自定义回答')

    def test_interactive_mode_handles_status_command_without_running_agent(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['/status', '/exit']
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, [])
        printed = output.getvalue()
        self.assertIn('[生效参数]', printed)
        self.assertIn('模型: fake-model', printed)
        self.assertNotIn('[开始执行] /status', printed)

    def test_interactive_mode_handles_display_command_without_running_agent(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.set_display_calls = []
                self.persist_display_calls = []
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                self.display_index = kwargs.get('display_index', 0)
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return f'[生效参数]\n  模型: fake-model\n  目标显示器: {self.display_index}'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

            def set_display_index(self, display_index):
                self.set_display_calls.append(display_index)
                self.display_index = display_index
                return {
                    'index': display_index,
                    'x': -1440,
                    'y': 90,
                    'width': 1280,
                    'height': 720,
                    'is_primary': False,
                }

            def persist_display_index(self):
                self.persist_display_calls.append(self.display_index)
                return '.env'

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['/display 1', '/status', '/exit']
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, [])
        self.assertEqual(fake_agent_instances[0].set_display_calls, [1])
        self.assertEqual(fake_agent_instances[0].persist_display_calls, [1])
        printed = output.getvalue()
        self.assertIn('[已切换] 当前目标显示器: 1', printed)
        self.assertNotIn('[已持久化]', printed)
        self.assertIn('目标显示器: 1', printed)
        self.assertNotIn('[开始执行] /display 1', printed)

    def test_interactive_mode_handles_clear_command_without_running_agent(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['/clear', '/exit']
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, [])
        self.assertEqual(fake_agent_instances[0].clear_calls, 1)
        self.assertIn('[已清理] 多轮对话上下文历史已清空', output.getvalue())

    def test_interactive_mode_reports_unknown_command_and_continues(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['/unknown', '打开计算器', '/exit']
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, ['打开计算器'])
        printed = output.getvalue()
        self.assertIn('[命令错误] 未知命令: /unknown', printed)
        self.assertIn('[可用命令] /clear, /compact, /display, /exit, /status', printed)

    def test_interactive_mode_exits_via_exit_command(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['/exit']
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, [])
        self.assertIn('感谢使用，再见！', output.getvalue())

    def test_interactive_mode_handles_compact_command_without_running_agent(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                self.last_manual = manual
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        output = io.StringIO()

        with redirect_stdout(output), mock.patch.object(
            self.cli, 'ensure_supported_python'
        ), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['/compact', '/exit']
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, [])
        self.assertEqual(fake_agent_instances[0].compact_calls, 1)
        self.assertTrue(fake_agent_instances[0].last_manual)
        self.assertIn('[处理中] 正在压缩多轮对话上下文历史...', output.getvalue())
        self.assertIn('[已压缩] 多轮对话上下文历史已精炼', output.getvalue())

    def test_plain_exit_text_is_no_longer_treated_as_builtin_exit(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                self.clear_calls = 0
                self.compact_calls = 0
                self.model = 'fake-model'
                self.thinking_mode = 'auto'
                self.reasoning_effort = 'medium'
                self.skills = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

            def format_effective_status(self):
                return '[生效参数]\n  模型: fake-model'

            def clear_session_context(self):
                self.clear_calls += 1

            def compact_session_context(self, manual=False):
                self.compact_calls += 1
                return True

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module

        with mock.patch.object(self.cli, 'ensure_supported_python'), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(
            builtins, 'input', side_effect=['exit', '/exit']
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, ['exit'])

    def test_create_command_completer_suggests_status_for_slash_prefix(self):
        sys.modules['prompt_toolkit'] = types.ModuleType('prompt_toolkit')
        fake_completion_module = types.ModuleType('prompt_toolkit.completion')

        class FakeCompleter:
            async def get_completions_async(self, document, complete_event):
                for completion in self.get_completions(document, complete_event):
                    yield completion

        class FakeCompletion:
            def __init__(self, text, start_position=0):
                self.text = text
                self.start_position = start_position

        fake_completion_module.Completer = FakeCompleter
        fake_completion_module.Completion = FakeCompletion
        sys.modules['prompt_toolkit.completion'] = fake_completion_module

        commands = self.cli._build_interactive_commands()
        completer = self.cli._create_command_completer(commands)
        self.assertTrue(hasattr(completer, 'get_completions_async'))

        document = types.SimpleNamespace(text_before_cursor='/st')
        completions = list(completer.get_completions(document, None))
        self.assertEqual(len(completions), 1)
        self.assertEqual(completions[0].text, '/status')
        self.assertEqual(completions[0].start_position, -3)

        compact_document = types.SimpleNamespace(text_before_cursor='/co')
        compact_completions = list(completer.get_completions(compact_document, None))
        self.assertEqual(len(compact_completions), 1)
        self.assertEqual(compact_completions[0].text, '/compact')

        display_document = types.SimpleNamespace(text_before_cursor='/di')
        display_completions = list(completer.get_completions(display_document, None))
        self.assertEqual(len(display_completions), 1)
        self.assertEqual(display_completions[0].text, '/display')

        non_command = types.SimpleNamespace(text_before_cursor='打开计算器')
        self.assertEqual(list(completer.get_completions(non_command, None)), [])


if __name__ == '__main__':
    unittest.main()
