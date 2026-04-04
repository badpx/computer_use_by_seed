import importlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path


class FakeScreenshot:
    def __init__(self, size=(1280, 720)):
        self.size = size

    def save(self, target, format='PNG'):
        if hasattr(target, 'write'):
            target.write(b'fake-png-bytes')
            return

        Path(target).write_bytes(b'fake-png-bytes')


class FakeResponse:
    def __init__(self, content, usage=None, reasoning_content=None):
        message = types.SimpleNamespace(
            content=content,
            reasoning_content=reasoning_content,
        )
        self.choices = [types.SimpleNamespace(message=message)]
        self.usage = usage


class FakeCompletionAPI:
    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        if not self._responses:
            raise AssertionError('No fake model responses left')
        item = self._responses.pop(0)
        if isinstance(item, dict):
            return FakeResponse(
                item['content'],
                usage=item.get('usage'),
                reasoning_content=item.get('reasoning_content'),
            )
        return FakeResponse(item)


class FakeArkClient:
    def __init__(self, responses, calls):
        self.chat = types.SimpleNamespace(
            completions=FakeCompletionAPI(responses, calls)
        )


class AgentContextTests(unittest.TestCase):
    def setUp(self):
        os.environ['ARK_API_KEY'] = 'test-key'
        self.temp_dir = tempfile.TemporaryDirectory()
        self.responses = []
        self.calls = []
        self.exec_outcomes = []
        self.executor_inits = []
        self.capture_index = 0
        self.log_dir = Path(self.temp_dir.name) / 'logs'
        self.screenshot_dir = Path(self.temp_dir.name) / 'screens'
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self.agent_module = self._load_agent_module()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _load_agent_module(self):
        screenshot_stub = types.ModuleType('computer_use.screenshot')
        screenshot_stub.screenshot_manager = object()
        screenshot_stub.capture_screenshot = lambda *args, **kwargs: (
            FakeScreenshot(),
            str(self.screenshot_dir / 'stub.png'),
        )

        action_executor_stub = types.ModuleType('computer_use.action_executor')

        class PlaceholderExecutor:
            def __init__(self, *args, **kwargs):
                pass

            def execute(self, action):
                return 'placeholder'

        action_executor_stub.ActionExecutor = PlaceholderExecutor

        ark_stub = types.ModuleType('volcenginesdkarkruntime')

        class PlaceholderArk:
            def __init__(self, *args, **kwargs):
                self.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=lambda **_: None)
                )

        ark_stub.Ark = PlaceholderArk

        sys.modules['computer_use.screenshot'] = screenshot_stub
        sys.modules['computer_use.action_executor'] = action_executor_stub
        sys.modules['volcenginesdkarkruntime'] = ark_stub
        sys.modules.pop('computer_use.agent', None)

        agent_module = importlib.import_module('computer_use.agent')

        agent_module.Ark = lambda base_url, api_key: FakeArkClient(
            self.responses,
            self.calls,
        )
        agent_module.time.sleep = lambda _: None
        agent_module.capture_screenshot = self._fake_capture
        agent_module.ActionExecutor = self._build_executor()
        return agent_module

    def _fake_capture(self):
        self.capture_index += 1
        screenshot_path = self.screenshot_dir / f'step_{self.capture_index}.png'
        FakeScreenshot().save(screenshot_path)
        return FakeScreenshot(), str(screenshot_path)

    def _build_executor(self):
        test_case = self

        class FakeExecutor:
            def __init__(self, *args, **kwargs):
                test_case.executor_inits.append(kwargs)

            def execute(self, action):
                if not test_case.exec_outcomes:
                    return 'executed'
                outcome = test_case.exec_outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        return FakeExecutor

    def _make_agent(self, **kwargs):
        return self.agent_module.ComputerUseAgent(
            model='fake-model',
            max_steps=kwargs.pop('max_steps', 5),
            verbose=kwargs.pop('verbose', False),
            **kwargs,
        )

    def test_second_model_call_keeps_single_system_prompt_and_replays_text_history_only(self):
        self.responses[:] = [
            "Thought: first step\nAction: wait()",
            "Thought: done\nAction: finished(content='done')",
        ]
        self.exec_outcomes[:] = ['waited']

        agent = self._make_agent()
        result = agent.run('Open the calculator')

        self.assertTrue(result['success'])
        self.assertEqual(len(self.calls), 2)
        second_messages = self.calls[1]['messages']
        system_messages = [
            message for message in second_messages if message['role'] == 'system'
        ]
        image_messages = [
            message for message in second_messages
            if isinstance(message.get('content'), list)
        ]
        user_texts = [
            message['content']
            for message in second_messages
            if message['role'] == 'user' and isinstance(message.get('content'), str)
        ]

        self.assertEqual(len(system_messages), 1)
        self.assertEqual(len(image_messages), 1)
        self.assertIn('Open the calculator', user_texts[0])
        self.assertIn('Current Step: 2', user_texts[-1])
        self.assertTrue(
            any('Execution Result: waited' in text for text in user_texts)
        )
        self.assertIn("Action: wait()", second_messages[2]['content'])
        self.assertEqual(second_messages[0]['role'], 'system')
        self.assertEqual(second_messages[1]['role'], 'user')
        self.assertEqual(second_messages[2]['role'], 'assistant')
        self.assertEqual(second_messages[3]['role'], 'user')
        self.assertEqual(second_messages[-1]['content'][0]['type'], 'image_url')

    def test_parse_failure_is_recorded_and_next_round_receives_failure_reason(self):
        self.responses[:] = [
            'this is not a valid action',
            "Thought: now finish\nAction: finished(content='done')",
        ]

        agent = self._make_agent()
        result = agent.run('Recover from parse errors')

        self.assertTrue(result['success'])
        self.assertEqual(len(self.calls), 2)
        second_user_texts = [
            message['content']
            for message in self.calls[1]['messages']
            if message['role'] == 'user' and isinstance(message.get('content'), str)
        ]

        joined_text = '\n'.join(second_user_texts)
        self.assertIn('Execution Status: failed', joined_text)
        self.assertIn('Failure Reason: 无法解析动作', joined_text)

    def test_context_log_writes_jsonl_without_image_base64(self):
        usage = types.SimpleNamespace(
            prompt_tokens=123,
            completion_tokens=45,
            total_tokens=168,
            prompt_tokens_details=types.SimpleNamespace(cached_tokens=10),
            completion_tokens_details=types.SimpleNamespace(reasoning_tokens=7),
        )
        self.responses[:] = [
            {
                'content': "Thought: done\nAction: finished(content='ok')",
                'reasoning_content': 'deep reasoning trace',
                'usage': usage,
            }
        ]

        agent = self._make_agent(
            save_context_log=True,
            context_log_dir=str(self.log_dir),
        )
        result = agent.run('Write a context log')

        self.assertTrue(result['success'])
        log_files = list(self.log_dir.glob('task_*.jsonl'))
        self.assertEqual(len(log_files), 1)

        records = [
            json.loads(line)
            for line in log_files[0].read_text(encoding='utf-8').splitlines()
        ]

        self.assertEqual(records[0]['event'], 'task_start')
        self.assertIn('model_call', [record['event'] for record in records])
        self.assertIn('task_end', [record['event'] for record in records])

        model_call = next(record for record in records if record['event'] == 'model_call')
        model_response = next(record for record in records if record['event'] == 'model_response')
        self.assertEqual(model_call['message_summary'], '1 system + text history + 1 current screenshot')
        self.assertEqual(model_call['screenshot_size'], [1280, 720])
        self.assertIn('Current Step: 1', model_call['text_input'])
        self.assertNotIn('You are a GUI agent', model_call['text_input'])
        self.assertNotIn('base64', json.dumps(model_call, ensure_ascii=False).lower())
        self.assertEqual(
            model_response['usage'],
            {
                'prompt_tokens': 123,
                'completion_tokens': 45,
                'total_tokens': 168,
                'prompt_tokens_details': {'cached_tokens': 10},
                'completion_tokens_details': {'reasoning_tokens': 7},
            },
        )
        self.assertEqual(model_response['reasoning'], 'deep reasoning trace')

    def test_parse_failure_prints_basic_error_detail(self):
        self.responses[:] = ['this is not a valid action']

        agent = self._make_agent(max_steps=1, verbose=True)
        output = io.StringIO()

        with redirect_stdout(output):
            result = agent.run('Show parse error details')

        self.assertFalse(result['success'])
        self.assertIn(
            '解析失败: 无法解析动作: this is not a valid action',
            output.getvalue(),
        )

    def test_parse_failure_reason_is_condensed_to_single_line(self):
        self.responses[:] = [
            "Thought: check\nAction:\n```json\n{\"foo\": \"bar\"}\n```"
        ]

        agent = self._make_agent(max_steps=1, verbose=False)
        result = agent.run('Condense parse errors')

        self.assertFalse(result['success'])
        self.assertEqual(result['steps'][0]['execution_status'], 'failed')
        self.assertIn('无法解析动作:', result['steps'][0]['failure_reason'])
        self.assertNotIn('\n', result['steps'][0]['failure_reason'])

    def test_context_log_omits_usage_when_response_has_no_usage(self):
        self.responses[:] = ["Thought: done\nAction: finished(content='ok')"]

        agent = self._make_agent(
            save_context_log=True,
            context_log_dir=str(self.log_dir),
        )
        result = agent.run('Write a context log without usage')

        self.assertTrue(result['success'])
        log_files = list(self.log_dir.glob('task_*.jsonl'))
        records = [
            json.loads(line)
            for line in log_files[0].read_text(encoding='utf-8').splitlines()
        ]

        model_response = next(record for record in records if record['event'] == 'model_response')
        self.assertIsNone(model_response['usage'])
        self.assertEqual(model_response['reasoning'], '')

    def test_agent_passes_natural_scroll_override_to_executor(self):
        self.responses[:] = [
            "Thought: scroll\nAction: scroll(direction='down', start_box='<point>500 500</point>')",
            "Thought: done\nAction: finished(content='ok')",
        ]
        self.exec_outcomes[:] = ['scrolled']

        agent = self._make_agent(max_steps=2)
        agent.natural_scroll = False
        result = agent.run('Use traditional scroll')

        self.assertTrue(result['success'])
        self.assertTrue(self.executor_inits)
        self.assertEqual(self.executor_inits[0]['natural_scroll'], False)

    def test_agent_passes_reasoning_effort_and_thinking_to_chat_api(self):
        self.responses[:] = ["Thought: done\nAction: finished(content='ok')"]

        agent = self._make_agent(
            thinking_mode='enabled',
            reasoning_effort='low',
        )
        result = agent.run('Use low reasoning effort')

        self.assertTrue(result['success'])
        self.assertEqual(self.calls[0]['thinking'], {'type': 'enabled'})
        self.assertEqual(self.calls[0]['reasoning_effort'], 'low')

    def test_minimal_reasoning_effort_forces_disabled_thinking(self):
        self.responses[:] = ["Thought: done\nAction: finished(content='ok')"]

        agent = self._make_agent(
            thinking_mode='enabled',
            reasoning_effort='minimal',
        )
        result = agent.run('Use minimal reasoning effort')

        self.assertTrue(result['success'])
        self.assertEqual(self.calls[0]['thinking'], {'type': 'disabled'})
        self.assertEqual(self.calls[0]['reasoning_effort'], 'minimal')

    def test_disabled_thinking_rejects_non_minimal_reasoning_effort(self):
        with self.assertRaisesRegex(
            ValueError,
            'reasoning_effort 只能为 minimal',
        ):
            self._make_agent(
                thinking_mode='disabled',
                reasoning_effort='high',
            )


if __name__ == '__main__':
    unittest.main()
