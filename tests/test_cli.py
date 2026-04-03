import builtins
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


class FakePromptSession:
    def __init__(self, history=None, responses=None):
        self.history = history
        self.responses = list(responses or [])
        self.prompts = []

    def prompt(self, text):
        self.prompts.append(text)
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
        self.assertEqual(fake_session.prompts, ['> ', '> '])

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


if __name__ == '__main__':
    unittest.main()
