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
    def __init__(self, history=None, responses=None):
        self.history = history
        self.responses = list(responses or [])
        self.prompts = []

    def prompt(self, text, **kwargs):
        toolbar = kwargs.get('bottom_toolbar')
        rendered_toolbar = toolbar() if callable(toolbar) else toolbar
        self.prompts.append(
            {
                'text': text,
                'bottom_toolbar': rendered_toolbar,
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

    def test_create_prompt_session_uses_file_history_when_prompt_toolkit_is_available(self):
        fake_prompt_toolkit = types.ModuleType('prompt_toolkit')
        fake_history_module = types.ModuleType('prompt_toolkit.history')
        history_calls = []

        class FakeFileHistory:
            def __init__(self, filename):
                history_calls.append(filename)
                self.filename = filename

        fake_prompt_toolkit.PromptSession = FakePromptSession
        fake_history_module.FileHistory = FakeFileHistory
        sys.modules['prompt_toolkit'] = fake_prompt_toolkit
        sys.modules['prompt_toolkit.history'] = fake_history_module

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / 'history.txt'
            session = self.cli._create_prompt_session(history_file=history_path)

        self.assertIsInstance(session, FakePromptSession)
        self.assertEqual(history_calls, [str(history_path)])
        self.assertEqual(session.history.filename, str(history_path))

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
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {
                    'success': True,
                    'steps': [],
                    'final_response': 'done',
                }

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        fake_session = FakePromptSession(responses=['打开计算器', 'exit'])

        with mock.patch.object(self.cli, 'ensure_supported_python'), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=fake_session
        ), mock.patch.object(builtins, 'input', side_effect=AssertionError('input() should not be used')):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, ['打开计算器'])
        self.assertEqual(
            [prompt['text'] for prompt in fake_session.prompts],
            ['> ', '> '],
        )
        self.assertIn('Context: 0%', fake_session.prompts[0]['bottom_toolbar'])

    def test_interactive_mode_falls_back_to_builtin_input_when_prompt_toolkit_is_unavailable(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {
                    'success': True,
                    'steps': [],
                    'final_response': 'done',
                }

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module

        with mock.patch.object(self.cli, 'ensure_supported_python'), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=None
        ), mock.patch.object(builtins, 'input', side_effect=['粘贴的一长串指令', 'exit']) as mock_input:
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        self.assertEqual(fake_agent_instances[0].run_calls, ['粘贴的一长串指令'])
        self.assertEqual(mock_input.call_count, 2)

    def test_interactive_mode_updates_status_bar_after_task(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
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
                        'context_estimated_bytes': 0,
                        'activated_skills': ['open-browser'],
                    },
                }

        fake_agent_module = types.ModuleType('computer_use.agent')
        fake_agent_module.ComputerUseAgent = FakeAgent
        sys.modules['computer_use.agent'] = fake_agent_module
        fake_session = FakePromptSession(responses=['打开计算器', 'exit'])

        with mock.patch.object(self.cli, 'ensure_supported_python'), mock.patch.object(
            self.cli, '_create_prompt_session', return_value=fake_session
        ):
            self.cli.interactive_mode(verbose=False)

        self.assertEqual(len(fake_agent_instances), 1)
        first_toolbar = fake_session.prompts[0]['bottom_toolbar']
        second_toolbar = fake_session.prompts[1]['bottom_toolbar']
        self.assertIn('fake-model high', first_toolbar)
        self.assertIn('Context: 0%', first_toolbar)
        self.assertIn('Skills: 0/3', first_toolbar)
        self.assertIn('Duration: 00:00:00', first_toolbar)
        self.assertIn('Context: 6%', second_toolbar)
        self.assertIn('Skills: 1/3', second_toolbar)
        self.assertIn('Duration: 00:00:12', second_toolbar)

    def test_interactive_mode_exits_on_ctrl_d_with_prompt_toolkit(self):
        fake_agent_instances = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.run_calls = []
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

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
                fake_agent_instances.append(self)

            def run(self, instruction):
                self.run_calls.append(instruction)
                return {'success': True, 'steps': [], 'final_response': 'done'}

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
                fake_agent_instances.append(self)

            def run(self, instruction):
                return {
                    'success': True,
                    'steps': [],
                    'final_response': instruction,
                }

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


if __name__ == '__main__':
    unittest.main()
