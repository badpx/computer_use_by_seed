import importlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
import base64
from contextlib import redirect_stdout
from pathlib import Path


_MISSING_MODULE = object()


class FakeScreenshot:
    def __init__(self, size=(1280, 720)):
        self.size = size

    def resize(self, size, resample=None):
        return FakeScreenshot(size=size)

    def save(self, target, format='PNG'):
        payload = f'{self.size[0]}x{self.size[1]}'.encode('utf-8')
        if hasattr(target, 'write'):
            target.write(payload)
            return

        Path(target).write_bytes(payload)


class FakeToolCall:
    """Simulates a single tool call in a model response."""
    def __init__(self, name, tool_call_id='tc-1'):
        self.id = tool_call_id
        self.function = types.SimpleNamespace(name=name, arguments='{}')


class FakeResponse:
    def __init__(self, content, usage=None, reasoning_content=None,
                 finish_reason='stop', tool_calls=None):
        serialised_tool_calls = None
        if tool_calls:
            serialised_tool_calls = [
                {'id': tc.id, 'function': {'name': tc.function.name, 'arguments': '{}'}}
                for tc in tool_calls
            ]
        message = types.SimpleNamespace(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
        )
        message.model_dump = lambda: {
            'role': 'assistant',
            'content': content,
            'tool_calls': serialised_tool_calls,
        }
        self.choices = [types.SimpleNamespace(
            message=message,
            finish_reason=finish_reason,
        )]
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
                item.get('content', ''),
                usage=item.get('usage'),
                reasoning_content=item.get('reasoning_content'),
                finish_reason=item.get('finish_reason', 'stop'),
                tool_calls=item.get('tool_calls'),
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
        os.environ['DEVICE_NAME'] = 'local'
        os.environ.pop('DEVICE_CONFIG_JSON', None)
        self._original_modules = {}
        self.temp_dir = tempfile.TemporaryDirectory()
        self.responses = []
        self.calls = []
        self.exec_outcomes = []
        self.executor_inits = []
        self.capture_index = 0
        self.capture_calls = []
        self.log_dir = Path(self.temp_dir.name) / 'logs'
        self.capture_dir = Path(self.temp_dir.name) / 'screens'
        self.capture_dir.mkdir(parents=True, exist_ok=True)

        self.agent_module = self._load_agent_module()

    def tearDown(self):
        # Avoid leaking injected modules beyond this test harness.
        for module_name in ('vncdotool', 'vncdotool.api'):
            original = self._original_modules.get(module_name, _MISSING_MODULE)
            if original is _MISSING_MODULE:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = original
        self.temp_dir.cleanup()

    def _load_agent_module(self):
        screenshot_stub = types.ModuleType('computer_use.screenshot')
        screenshot_stub.screenshot_manager = types.SimpleNamespace()
        screenshot_stub.capture_screenshot = self._fake_capture
        screenshot_stub.resolve_display = self._fake_resolve_display
        screenshot_stub.list_displays = lambda: [
            types.SimpleNamespace(to_dict=lambda payload=display: dict(payload))
            for display in (
                self._fake_resolve_display(0),
                self._fake_resolve_display(1),
            )
        ]

        local_executor_stub = types.ModuleType('computer_use.devices.plugins.local.executor')
        local_executor_stub.LocalActionExecutor = self._build_executor()

        ark_stub = types.ModuleType('volcenginesdkarkruntime')

        class PlaceholderArk:
            def __init__(self, *args, **kwargs):
                self.chat = types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=lambda **_: None)
                )

        ark_stub.Ark = PlaceholderArk

        # VNC plugin depends on vncdotool. Stub it so tests can exercise the
        # prompt-profile integration without installing external dependencies.
        for module_name in ('vncdotool', 'vncdotool.api'):
            if module_name not in self._original_modules:
                self._original_modules[module_name] = sys.modules.get(
                    module_name,
                    _MISSING_MODULE,
                )
        vncdotool_api_stub = types.ModuleType('vncdotool.api')
        png_bytes = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8'
            '/w8AAgMBgJ0XGfQAAAAASUVORK5CYII='
        )

        class FakeVncImage:
            def save(self, fp, format='PNG'):
                fp.write(png_bytes)

        class FakeVncClient:
            def captureScreen(self):
                return FakeVncImage()

            def disconnect(self):
                return None

        vncdotool_api_stub.connect = lambda *args, **kwargs: FakeVncClient()
        vncdotool_stub = types.ModuleType('vncdotool')
        vncdotool_stub.api = vncdotool_api_stub

        sys.modules['computer_use.screenshot'] = screenshot_stub
        sys.modules['computer_use.devices.plugins.local.executor'] = local_executor_stub
        sys.modules['volcenginesdkarkruntime'] = ark_stub
        sys.modules['vncdotool'] = vncdotool_stub
        sys.modules['vncdotool.api'] = vncdotool_api_stub
        sys.modules.pop('computer_use.agent', None)

        agent_module = importlib.import_module('computer_use.agent')

        agent_module.Ark = lambda base_url, api_key: FakeArkClient(
            self.responses,
            self.calls,
        )
        agent_module.time.sleep = lambda _: None
        agent_module.prepare_model_frame = self._fake_prepare_model_frame
        return agent_module

    def _fake_resolve_display(self, display_index=None):
        index = 0 if display_index is None else int(display_index)
        return {
            'index': index,
            'x': -1440 if index == 1 else index * 100,
            'y': 90 if index == 1 else index * 10,
            'width': 1280,
            'height': 720,
            'is_primary': index == 0,
        }

    def _fake_capture(self, *args, **kwargs):
        self.capture_calls.append(kwargs)
        self.capture_index += 1
        screenshot_path = self.capture_dir / f'step_{self.capture_index}.png'
        FakeScreenshot().save(screenshot_path)
        return FakeScreenshot(), None

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

    def _fake_prepare_model_frame(self, frame, screenshot_size=None):
        if screenshot_size is None or int(screenshot_size) <= 0:
            return frame
        payload = f'{int(screenshot_size)}x{int(screenshot_size)}'.encode('utf-8')
        return self.agent_module.DeviceFrame(
            image_data_url=(
                'data:image/png;base64,'
                f"{base64.b64encode(payload).decode('utf-8')}"
            ),
            width=int(screenshot_size),
            height=int(screenshot_size),
            metadata=dict(frame.metadata or {}),
        )

    def _make_agent(self, **kwargs):
        return self.agent_module.ComputerUseAgent(
            model='fake-model',
            max_steps=kwargs.pop('max_steps', 5),
            screenshot_size=kwargs.pop('screenshot_size', 0),
            device_name=kwargs.pop('device_name', 'local'),
            verbose=kwargs.pop('verbose', False),
            **kwargs,
        )

    def test_second_model_call_keeps_single_system_prompt_and_replays_recent_screenshot_context(self):
        self.responses[:] = [
            "Thought: first step\nAction: wait()",
            "Thought: done\nAction: finished(content='done')",
        ]
        self.exec_outcomes[:] = ['waited']

        agent = self._make_agent(include_execution_feedback=True)
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
        self.assertNotIn('Open the calculator', system_messages[0]['content'])
        self.assertEqual(len(image_messages), 2)
        self.assertEqual(len(user_texts), 2)
        self.assertEqual(user_texts[0], 'Open the calculator')
        self.assertIn('Execution Status: success', user_texts[1])
        self.assertIn('Execution Result: waited', user_texts[1])
        self.assertIn("Action: wait()", second_messages[3]['content'])
        self.assertEqual(second_messages[0]['role'], 'system')
        self.assertEqual(second_messages[1]['role'], 'user')
        self.assertEqual(second_messages[2]['content'][0]['type'], 'image_url')
        self.assertEqual(second_messages[3]['role'], 'assistant')
        self.assertEqual(second_messages[-1]['content'][0]['type'], 'image_url')

    def test_context_window_keeps_all_assistant_responses_and_latest_five_screenshots(self):
        self.responses[:] = [
            f"Thought: step {index}\nAction: wait()"
            for index in range(1, 8)
        ] + [
            "Thought: done\nAction: finished(content='ok')"
        ]
        self.exec_outcomes[:] = [f'waited-{index}' for index in range(1, 8)]

        agent = self._make_agent(max_steps=8, max_context_screenshots=5)
        result = agent.run('Keep recent screenshots only')

        self.assertTrue(result['success'])
        self.assertEqual(len(self.calls), 8)

        final_messages = self.calls[-1]['messages']
        assistant_messages = [
            message['content']
            for message in final_messages
            if message['role'] == 'assistant'
        ]
        image_message_indexes = [
            index
            for index, message in enumerate(final_messages)
            if isinstance(message.get('content'), list)
        ]

        self.assertEqual(len(assistant_messages), 7)
        self.assertEqual(len(image_message_indexes), 5)
        self.assertEqual(
            assistant_messages[:3],
            [
                "Thought: step 1\nAction: wait()",
                "Thought: step 2\nAction: wait()",
                "Thought: step 3\nAction: wait()",
            ],
        )
        self.assertEqual(final_messages[image_message_indexes[0] - 1]['role'], 'assistant')
        self.assertEqual(
            final_messages[image_message_indexes[0] - 1]['content'],
            "Thought: step 3\nAction: wait()",
        )
        self.assertEqual(final_messages[-1]['content'][0]['type'], 'image_url')

    def test_execution_feedback_can_be_disabled(self):
        self.responses[:] = [
            "Thought: first step\nAction: wait()",
            "Thought: done\nAction: finished(content='done')",
        ]
        self.exec_outcomes[:] = ['waited']

        agent = self._make_agent(include_execution_feedback=False)
        result = agent.run('Run without execution feedback')

        self.assertTrue(result['success'])
        second_messages = self.calls[1]['messages']
        user_texts = [
            message['content']
            for message in second_messages
            if message['role'] == 'user' and isinstance(message.get('content'), str)
        ]

        self.assertEqual(user_texts, ['Run without execution feedback'])

    def test_parse_failure_is_recorded_and_next_round_receives_failure_reason(self):
        self.responses[:] = [
            'this is not a valid action',
            "Thought: now finish\nAction: finished(content='done')",
        ]

        agent = self._make_agent(include_execution_feedback=True)
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
            include_execution_feedback=True,
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

        task_start = next(record for record in records if record['event'] == 'task_start')
        model_call = next(record for record in records if record['event'] == 'model_call')
        model_response = next(record for record in records if record['event'] == 'model_response')
        self.assertEqual(task_start['max_context_screenshots'], agent.max_context_screenshots)
        self.assertEqual(task_start['include_execution_feedback'], True)
        self.assertEqual(
            model_call['message_summary'],
            '1 system + 1 user instructions + 0 persistent skills + '
            '0 historical assistant + 0 feedback + 1 screenshots',
        )
        self.assertEqual(model_call['retained_screenshot_count'], 1)
        self.assertEqual(model_call['screenshot_size'], [1280, 720])
        self.assertEqual(model_call['text_input'], '')
        self.assertNotIn('base64', json.dumps(model_call, ensure_ascii=False).lower())
        self.assertNotIn('messages', model_call)
        self.assertFalse((self.log_dir / 'screenshots').exists())
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
        self.assertEqual(model_response['finish_reason'], 'stop')
        self.assertIsNone(model_response['tool_calls'])

    def test_run_uses_reasoning_content_when_content_is_empty(self):
        self.responses[:] = [
            {
                'content': '',
                'reasoning_content': "Thought: done\nAction: finished(content='ok')",
            }
        ]

        agent = self._make_agent()
        result = agent.run('Finish via reasoning fallback')

        self.assertTrue(result['success'])
        self.assertEqual(result['final_response'], 'ok')

    def test_model_response_log_keeps_raw_response_equal_to_content_only(self):
        self.responses[:] = [
            {
                'content': '',
                'reasoning_content': "Thought: done\nAction: finished(content='ok')",
            }
        ]

        agent = self._make_agent(
            save_context_log=True,
            context_log_dir=str(self.log_dir),
        )
        result = agent.run('Keep raw response semantic stable')

        self.assertTrue(result['success'])
        log_files = list(self.log_dir.glob('task_*.jsonl'))
        self.assertEqual(len(log_files), 1)

        records = [
            json.loads(line)
            for line in log_files[0].read_text(encoding='utf-8').splitlines()
        ]
        model_response = next(record for record in records if record['event'] == 'model_response')

        self.assertEqual(model_response['raw_response'], '')
        self.assertEqual(model_response['reasoning'], "Thought: done\nAction: finished(content='ok')")

    def test_model_response_log_includes_finish_reason_and_tool_calls(self):
        self.responses[:] = [
            {
                'content': "Thought: action text should still finish\nAction: finished(content='done')",
                'finish_reason': 'tool_calls',
                'tool_calls': [FakeToolCall('drag', 'tc-drag')],
            }
        ]

        agent = self._make_agent(
            save_context_log=True,
            context_log_dir=str(self.log_dir),
        )
        result = agent.run('Log tool call metadata')

        self.assertTrue(result['success'])
        log_files = list(self.log_dir.glob('task_*.jsonl'))
        self.assertEqual(len(log_files), 1)

        records = [
            json.loads(line)
            for line in log_files[0].read_text(encoding='utf-8').splitlines()
        ]
        model_response = next(record for record in records if record['event'] == 'model_response')

        self.assertEqual(model_response['finish_reason'], 'tool_calls')
        self.assertEqual(
            model_response['tool_calls'],
            [{'id': 'tc-drag', 'function': {'name': 'drag', 'arguments': '{}'}}],
        )

    def test_run_prefers_content_over_reasoning_content(self):
        self.responses[:] = [
            {
                'content': "Thought: done\nAction: finished(content='from-content')",
                'reasoning_content': "Thought: done\nAction: finished(content='from-reasoning')",
            }
        ]

        agent = self._make_agent()
        result = agent.run('Prefer content over reasoning')

        self.assertTrue(result['success'])
        self.assertEqual(result['final_response'], 'from-content')

    def test_compaction_uses_reasoning_content_when_content_is_empty(self):
        self.responses[:] = [
            {
                'content': '',
                'reasoning_content': json.dumps(
                    {
                        'condensed_user_instruction': 'Compressed first user',
                        'condensed_assistant_response': 'Compressed first assistant',
                    },
                    ensure_ascii=False,
                ),
            }
        ]

        agent = self._make_agent(persistent_session=True)
        summary = agent._summarize_turn_for_compaction(
            {
                'user_messages': ['First task'],
                'assistant_messages': ['Thought: first\nAction: wait()'],
                'feedback_messages': [],
            },
            max_tokens=200,
        )

        self.assertEqual(
            summary,
            {
                'condensed_user_instruction': 'Compressed first user',
                'condensed_assistant_response': 'Compressed first assistant',
            },
        )

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

    def test_init_output_prints_effective_parameters(self):
        output = io.StringIO()

        with redirect_stdout(output):
            self._make_agent(
                verbose=True,
                print_init_status=True,
                thinking_mode='disabled',
                reasoning_effort='minimal',
            )

        printed = output.getvalue()
        self.assertIn('[生效参数]', printed)
        self.assertIn('模型: fake-model', printed)
        self.assertIn('最大步数:', printed)
        self.assertIn('思考: disabled / minimal', printed)
        self.assertIn('日志完整上下文', printed)
        self.assertIn('语言: Chinese', printed)
        self.assertNotIn('[初始化] Computer Use Agent', printed)

    def test_format_effective_status_returns_current_parameters(self):
        agent = self._make_agent(
            coordinate_space='relative',
            coordinate_scale=1000,
            max_context_screenshots=3,
            include_execution_feedback=True,
            display_index=1,
            verbose=False,
        )

        rendered = agent.format_effective_status()
        self.assertIn('[生效参数]', rendered)
        self.assertIn('模型: fake-model', rendered)
        self.assertIn('坐标量程: 1000', rendered)
        self.assertIn('上下文截图窗口: 3', rendered)
        self.assertIn('注入执行反馈: 启用', rendered)
        self.assertIn('目标显示器: 1', rendered)

    def test_system_prompt_includes_runtime_timezone_date_and_weekday(self):
        agent = self._make_agent(verbose=False)
        agent._get_runtime_context = lambda: {
            'timezone': 'Asia/Shanghai (CST), UTC+08:00',
            'date': '2026-04-06',
            'weekday': 'Monday',
            'operating_system': 'macOS 15.4',
        }

        prompt = agent._build_system_prompt()

        self.assertIn('## Runtime Context', prompt)
        self.assertIn('- Operating system: macOS 15.4', prompt)
        self.assertIn('- Local timezone: Asia/Shanghai (CST), UTC+08:00', prompt)
        self.assertIn('- Local date: 2026-04-06', prompt)
        self.assertIn('- Local weekday: Monday', prompt)
        self.assertNotIn('Approximate location', prompt)

    def test_agent_uses_phone_prompt_for_cellphone_device_profile(self):
        self.responses[:] = [
            "Thought: done\nAction: finished(content='ok')",
        ]

        agent = self._make_agent(
            device_name='vnc',
            device_config={
                'host': '127.0.0.1',
                'port': 5900,
                'prompt_profile': 'cellphone',
                'operating_system': 'Android',
            },
            verbose=False,
            print_init_status=False,
            max_steps=1,
        )
        agent._get_runtime_context = lambda: {
            'timezone': 'Asia/Shanghai (CST), UTC+08:00',
            'date': '2026-04-06',
            'weekday': 'Monday',
            'operating_system': 'Android',
        }

        result = agent.run('Open something on the phone')

        self.assertTrue(result['success'])
        self.assertEqual(len(self.calls), 1)
        system_prompt = self.calls[0]['messages'][0]['content']
        self.assertIn("press_home()", system_prompt)
        self.assertIn("open_app(app_name='')", system_prompt)
        self.assertNotIn("hotkey(key='ctrl c')", system_prompt)

    def test_system_prompt_uses_phone_prompt_for_cellphone_profile(self):
        class FakeCellphoneDevice:
            def connect(self):
                return None

            def close(self):
                return None

            def capture_frame(self):
                return self_device_frame

            def execute_command(self, command):
                return 'DONE'

            def get_status(self):
                return {
                    'operating_system': 'Android',
                    'display_index': 0,
                    'display_bounds': [0, 0, 1, 1],
                    'display_is_primary': True,
                }

            def get_environment_info(self):
                return {'operating_system': 'Android'}

            def get_prompt_profile(self):
                return 'cellphone'

            def supports_target_selection(self):
                return False

            def list_targets(self):
                return []

            def set_target(self, target_id):
                raise NotImplementedError

        self_device_frame = self.agent_module.DeviceFrame(
            image_data_url=(
                'data:image/png;base64,'
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8'
                '/w8AAgMBgJ0XGfQAAAAASUVORK5CYII='
            ),
            width=1,
            height=1,
            metadata={},
        )

        agent = self._make_agent(device_adapter=FakeCellphoneDevice(), verbose=False)
        agent._get_runtime_context = lambda: {
            'timezone': 'Asia/Shanghai (CST), UTC+08:00',
            'date': '2026-04-06',
            'weekday': 'Monday',
            'operating_system': 'Android',
        }

        prompt = agent._build_system_prompt()

        self.assertIn("press_home()", prompt)
        self.assertIn("open_app(app_name='')", prompt)
        self.assertNotIn("hotkey(key='ctrl c')", prompt)
        self.assertNotIn('## User Instruction', prompt)

    def test_system_prompt_falls_back_to_computer_prompt_for_unknown_profile(self):
        class FakeUnknownProfileDevice:
            def connect(self):
                return None

            def close(self):
                return None

            def capture_frame(self):
                return self_device_frame

            def execute_command(self, command):
                return 'DONE'

            def get_status(self):
                return {
                    'operating_system': 'Windows 11',
                    'display_index': 0,
                    'display_bounds': [0, 0, 1, 1],
                    'display_is_primary': True,
                }

            def get_environment_info(self):
                return {'operating_system': 'Windows 11'}

            def get_prompt_profile(self):
                return 'tablet'

            def supports_target_selection(self):
                return False

            def list_targets(self):
                return []

            def set_target(self, target_id):
                raise NotImplementedError

        self_device_frame = self.agent_module.DeviceFrame(
            image_data_url=(
                'data:image/png;base64,'
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8'
                '/w8AAgMBgJ0XGfQAAAAASUVORK5CYII='
            ),
            width=1,
            height=1,
            metadata={},
        )

        agent = self._make_agent(device_adapter=FakeUnknownProfileDevice(), verbose=False)
        agent._get_runtime_context = lambda: {
            'timezone': 'Asia/Shanghai (CST), UTC+08:00',
            'date': '2026-04-06',
            'weekday': 'Monday',
            'operating_system': 'Windows 11',
        }

        prompt = agent._build_system_prompt()

        self.assertIn("hotkey(key='ctrl c')", prompt)
        self.assertNotIn("press_home()", prompt)

    def test_system_prompt_falls_back_to_computer_prompt_when_profile_lookup_raises(self):
        class FakeBrokenProfileDevice:
            def connect(self):
                return None

            def close(self):
                return None

            def capture_frame(self):
                return self_device_frame

            def execute_command(self, command):
                return 'DONE'

            def get_status(self):
                return {
                    'operating_system': 'Windows 11',
                    'display_index': 0,
                    'display_bounds': [0, 0, 1, 1],
                    'display_is_primary': True,
                }

            def get_environment_info(self):
                return {'operating_system': 'Windows 11'}

            def get_prompt_profile(self):
                raise RuntimeError('profile lookup failed')

            def supports_target_selection(self):
                return False

            def list_targets(self):
                return []

            def set_target(self, target_id):
                raise NotImplementedError

        self_device_frame = self.agent_module.DeviceFrame(
            image_data_url=(
                'data:image/png;base64,'
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8'
                '/w8AAgMBgJ0XGfQAAAAASUVORK5CYII='
            ),
            width=1,
            height=1,
            metadata={},
        )

        agent = self._make_agent(device_adapter=FakeBrokenProfileDevice(), verbose=False)
        agent._get_runtime_context = lambda: {
            'timezone': 'Asia/Shanghai (CST), UTC+08:00',
            'date': '2026-04-06',
            'weekday': 'Monday',
            'operating_system': 'Windows 11',
        }

        prompt = agent._build_system_prompt()

        self.assertIn("hotkey(key='ctrl c')", prompt)
        self.assertNotIn("press_home()", prompt)

    def test_system_prompt_includes_approximate_location_when_available(self):
        agent = self._make_agent(verbose=False)
        agent._get_runtime_context = lambda: {
            'timezone': 'Asia/Shanghai (CST), UTC+08:00',
            'date': '2026-04-06',
            'weekday': 'Monday',
            'location': 'Shanghai',
        }

        prompt = agent._build_system_prompt()

        self.assertIn('- Approximate location: Shanghai', prompt)

    def test_runtime_context_prefers_device_operating_system_over_host(self):
        agent = self._make_agent(verbose=False)
        agent.device.get_environment_info = lambda: {
            'operating_system': 'Windows 11',
        }
        agent._get_operating_system_description = lambda: 'macOS 15.4'

        runtime_context = agent._get_runtime_context()

        self.assertEqual(runtime_context['operating_system'], 'Windows 11')

    def test_runtime_context_falls_back_to_host_operating_system_when_device_omits_it(self):
        agent = self._make_agent(verbose=False)
        agent.device.get_environment_info = lambda: {}
        agent._get_operating_system_description = lambda: 'macOS 15.4'

        runtime_context = agent._get_runtime_context()

        self.assertEqual(runtime_context['operating_system'], 'macOS 15.4')

    def test_get_operating_system_description_formats_macos_versions(self):
        agent = self._make_agent(verbose=False)

        self.agent_module.platform.system = lambda: 'Darwin'
        self.agent_module.platform.mac_ver = lambda: ('15.4', ('', '', ''), '')

        self.assertEqual(agent._get_operating_system_description(), 'macOS 15.4')

    def test_get_operating_system_description_falls_back_to_generic_linux(self):
        agent = self._make_agent(verbose=False)

        self.agent_module.platform.system = lambda: 'Linux'
        self.agent_module.platform.release = lambda: '6.8.0'
        agent._read_linux_os_release_name = lambda: None

        self.assertEqual(agent._get_operating_system_description(), 'Linux')

    def test_init_output_can_be_suppressed(self):
        output = io.StringIO()

        with redirect_stdout(output):
            self._make_agent(verbose=True, print_init_status=False)

        self.assertEqual(output.getvalue(), '')

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
        self.assertIsNone(result['runtime_status']['usage_total_tokens'])
        self.assertGreater(result['runtime_status']['context_estimated_bytes'], 8000)

    def test_context_log_verbose_includes_full_messages(self):
        self.responses[:] = ["Thought: done\nAction: finished(content='ok')"]

        agent = self._make_agent(
            save_context_log=True,
            context_log_dir=str(self.log_dir),
            log_full_messages=True,
        )
        result = agent.run('Write a verbose context log')

        self.assertTrue(result['success'])
        log_files = list(self.log_dir.glob('task_*.jsonl'))
        records = [
            json.loads(line)
            for line in log_files[0].read_text(encoding='utf-8').splitlines()
        ]

        task_start = next(record for record in records if record['event'] == 'task_start')
        model_call = next(record for record in records if record['event'] == 'model_call')
        self.assertEqual(task_start['log_full_messages'], True)
        self.assertIn('messages', model_call)
        self.assertEqual(model_call['messages'][0]['role'], 'system')
        self.assertEqual(model_call['messages'][1]['role'], 'user')
        self.assertEqual(model_call['messages'][1]['content'], 'Write a verbose context log')
        self.assertEqual(model_call['messages'][-1]['content'][0]['type'], 'image_url')
        screenshot_ref = model_call['messages'][-1]['content'][0]['image_url']['url']
        self.assertTrue(screenshot_ref.startswith('screenshots/'), screenshot_ref)
        self.assertTrue((self.log_dir / screenshot_ref).exists())

    def test_persistent_session_keeps_prior_user_and_assistant_messages_across_runs(self):
        self.responses[:] = [
            "Thought: first\nAction: finished(content='done-1')",
            "Thought: second\nAction: finished(content='done-2')",
        ]

        agent = self._make_agent(persistent_session=True)
        first_result = agent.run('First task')
        second_result = agent.run('Second task')

        self.assertTrue(first_result['success'])
        self.assertTrue(second_result['success'])
        self.assertEqual(len(self.calls), 2)
        second_messages = self.calls[1]['messages']
        user_texts = [
            message['content']
            for message in second_messages
            if message['role'] == 'user' and isinstance(message.get('content'), str)
        ]
        assistant_texts = [
            message['content']
            for message in second_messages
            if message['role'] == 'assistant'
        ]

        self.assertEqual(user_texts, ['First task', 'Second task'])
        self.assertIn("Thought: first\nAction: finished(content='done-1')", assistant_texts)

    def test_compaction_max_tokens_shrinks_by_recency_bucket(self):
        agent = self._make_agent(persistent_session=True)

        self.assertEqual(agent._get_compaction_max_tokens(29, 30), 400)
        self.assertEqual(agent._get_compaction_max_tokens(20, 30), 400)
        self.assertEqual(agent._get_compaction_max_tokens(19, 30), 200)
        self.assertEqual(agent._get_compaction_max_tokens(10, 30), 200)
        self.assertEqual(agent._get_compaction_max_tokens(9, 30), 100)
        self.assertEqual(agent._get_compaction_max_tokens(0, 50), 50)

    def test_runtime_status_shows_auto_compact_warning_after_eighty_five_percent(self):
        agent = self._make_agent(persistent_session=True)
        agent.last_context_estimated_bytes = int(
            self.agent_module.CONTEXT_WINDOW_BYTES * 0.86
        )

        runtime_status = agent._build_runtime_status(elapsed_seconds=0.0)

        self.assertEqual(runtime_status['status_note'], 'Auto compact soon')

    def test_compact_session_context_rebuilds_pairs_and_moves_skills_first(self):
        self.responses[:] = [
            json.dumps(
                {
                    'condensed_user_instruction': 'Compressed first user',
                    'condensed_assistant_response': 'Compressed first assistant',
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    'condensed_user_instruction': 'Compressed second user',
                    'condensed_assistant_response': 'Compressed second assistant',
                },
                ensure_ascii=False,
            ),
        ]

        agent = self._make_agent(persistent_session=True)
        agent.session_history = [
            agent._build_history_item(
                kind='user_instruction',
                api_message={'role': 'user', 'content': 'First task'},
            ),
            agent._build_screenshot_item(FakeScreenshot()),
            agent._build_history_item(
                kind='assistant',
                api_message={'role': 'assistant', 'content': 'Thought: first\nAction: wait()'},
            ),
            agent._build_execution_feedback_message(
                {
                    'step': 1,
                    'model_input': '',
                    'thought_summary': 'first',
                    'execution_status': 'success',
                    'execution_result': 'ok',
                    'failure_reason': None,
                },
                "wait()",
            ),
            agent._build_persistent_skill_message('open-browser', 'Use hotkey ctrl+n.'),
            agent._build_history_item(
                kind='user_instruction',
                api_message={'role': 'user', 'content': 'Second task'},
            ),
            agent._build_history_item(
                kind='assistant',
                api_message={'role': 'assistant', 'content': "Thought: second\nAction: finished(content='done')"},
            ),
        ]

        changed = agent.compact_session_context(manual=True)

        self.assertTrue(changed)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0]['max_tokens'], 400)
        self.assertEqual(self.calls[1]['max_tokens'], 400)
        self.assertEqual(
            [item['kind'] for item in agent.session_history],
            [
                'persistent_skill',
                'user_instruction',
                'assistant',
                'user_instruction',
                'assistant',
            ],
        )
        self.assertTrue(
            agent.session_history[0]['api_message']['content'].startswith(
                'Loaded Skill Instructions (open-browser)'
            )
        )
        self.assertEqual(agent.session_history[1]['api_message']['content'], 'Compressed first user')
        self.assertEqual(agent.session_history[2]['api_message']['content'], 'Compressed first assistant')
        self.assertEqual(agent.session_history[3]['api_message']['content'], 'Compressed second user')
        self.assertEqual(agent.session_history[4]['api_message']['content'], 'Compressed second assistant')
        self.assertIsNone(agent.last_usage_total_tokens)

    def test_auto_compaction_emits_compacting_status_note_during_callback(self):
        self.responses[:] = [
            json.dumps(
                {
                    'condensed_user_instruction': 'Compressed user',
                    'condensed_assistant_response': 'Compressed assistant',
                },
                ensure_ascii=False,
            ),
        ]

        agent = self._make_agent(persistent_session=True)
        agent.session_history = [
            agent._build_history_item(
                kind='user_instruction',
                api_message={'role': 'user', 'content': 'Older task'},
            ),
            agent._build_history_item(
                kind='assistant',
                api_message={'role': 'assistant', 'content': 'Thought: older\nAction: wait()'},
            ),
        ]
        status_notes = []
        agent.runtime_status_callback = lambda runtime_status: status_notes.append(
            runtime_status.get('status_note')
        )

        changed = agent._compact_session_context(trigger_reason='auto')

        self.assertTrue(changed)
        self.assertIn('Auto compacting...', status_notes)
        self.assertEqual(status_notes[-1], '')

    def test_auto_compaction_runs_before_main_model_call_and_keeps_current_user_instruction(self):
        original_threshold = self.agent_module.CONTEXT_COMPACTION_THRESHOLD_BYTES
        self.agent_module.CONTEXT_COMPACTION_THRESHOLD_BYTES = 1
        try:
            self.responses[:] = [
                json.dumps(
                    {
                        'condensed_user_instruction': 'Compressed prior user',
                        'condensed_assistant_response': 'Compressed prior assistant',
                    },
                    ensure_ascii=False,
                ),
                "Thought: done\nAction: finished(content='ok')",
            ]

            agent = self._make_agent(persistent_session=True)
            agent.session_history = [
                agent._build_history_item(
                    kind='user_instruction',
                    api_message={'role': 'user', 'content': 'Older task'},
                ),
                agent._build_screenshot_item(FakeScreenshot()),
                agent._build_history_item(
                    kind='assistant',
                    api_message={'role': 'assistant', 'content': 'Thought: older\nAction: wait()'},
                ),
                agent._build_execution_feedback_message(
                    {
                        'step': 1,
                        'model_input': '',
                        'thought_summary': 'older',
                        'execution_status': 'success',
                        'execution_result': 'waited',
                        'failure_reason': None,
                    },
                    "wait()",
                ),
            ]

            result = agent.run('Fresh task')
        finally:
            self.agent_module.CONTEXT_COMPACTION_THRESHOLD_BYTES = original_threshold

        self.assertTrue(result['success'])
        self.assertEqual(len(self.calls), 2)
        summary_call, main_call = self.calls
        self.assertEqual(summary_call['max_tokens'], 400)
        self.assertNotIn('tools', summary_call)

        main_messages = main_call['messages']
        text_messages = [
            (message['role'], message['content'])
            for message in main_messages
            if isinstance(message.get('content'), str)
        ]
        image_messages = [
            message for message in main_messages
            if isinstance(message.get('content'), list)
        ]

        self.assertEqual(
            text_messages,
            [
                ('system', main_messages[0]['content']),
                ('user', 'Compressed prior user'),
                ('assistant', 'Compressed prior assistant'),
                ('user', 'Fresh task'),
            ],
        )
        self.assertEqual(len(image_messages), 1)
        self.assertEqual(
            [item['kind'] for item in agent.session_history[:3]],
            ['user_instruction', 'assistant', 'user_instruction'],
        )

    def test_skill_persists_as_user_message_across_runs(self):
        with tempfile.TemporaryDirectory() as skills_dir:
            skill_path = Path(skills_dir) / 'open-browser'
            skill_path.mkdir()
            (skill_path / 'SKILL.md').write_text(
                '---\nname: open-browser\ndescription: Open a browser\n---\n\nUse hotkey ctrl+n.',
                encoding='utf-8',
            )

            self.responses[:] = [
                {
                    'content': '',
                    'finish_reason': 'tool_calls',
                    'tool_calls': [FakeToolCall('skill__open-browser', 'tc-42')],
                },
                "Thought: first\nAction: finished(content='done-1')",
                "Thought: second\nAction: finished(content='done-2')",
            ]

            agent = self._make_agent(
                skills_dir=skills_dir,
                enable_skills=True,
                persistent_session=True,
            )
            first_result = agent.run('First task')
            second_result = agent.run('Second task')

        self.assertTrue(first_result['success'])
        self.assertTrue(second_result['success'])
        self.assertEqual(len(self.calls), 3)
        second_run_messages = self.calls[2]['messages']
        persisted_skill_messages = [
            message['content']
            for message in second_run_messages
            if message['role'] == 'user'
            and isinstance(message.get('content'), str)
            and message['content'].startswith('Loaded Skill Instructions (open-browser)')
        ]
        self.assertEqual(len(persisted_skill_messages), 1)
        self.assertIn('Use hotkey ctrl+n.', persisted_skill_messages[0])
        self.assertEqual(second_result['runtime_status']['activated_skills'], ['open-browser'])

    def test_clear_session_context_resets_history_and_activated_skills(self):
        agent = self._make_agent(persistent_session=True)
        agent.session_history = [
            {
                'kind': 'user_instruction',
                'api_message': {'role': 'user', 'content': 'task'},
                'logged_message': {'role': 'user', 'content': 'task'},
            }
        ]
        agent.activated_skills = {'open-browser'}
        agent.last_usage_total_tokens = 123
        agent.last_context_estimated_bytes = 456

        agent.clear_session_context()

        self.assertEqual(agent.session_history, [])
        self.assertEqual(agent.activated_skills, set())
        self.assertIsNone(agent.last_usage_total_tokens)
        self.assertEqual(agent.last_context_estimated_bytes, 0)

    def test_screenshot_size_resizes_image_before_model_call(self):
        self.responses[:] = [
            "Thought: first step\nAction: wait()",
            "Thought: done\nAction: finished(content='ok')",
        ]
        self.exec_outcomes[:] = ['waited']

        agent = self._make_agent(
            save_context_log=True,
            context_log_dir=str(self.log_dir),
            screenshot_size=512,
            log_full_messages=True,
        )
        result = agent.run('Resize screenshot for the model')

        self.assertTrue(result['success'])
        self.assertTrue(self.executor_inits)
        self.assertNotIn('image_width', self.executor_inits[0])
        self.assertNotIn('image_height', self.executor_inits[0])
        self.assertNotIn('model_image_width', self.executor_inits[0])
        self.assertNotIn('model_image_height', self.executor_inits[0])

        log_files = list(self.log_dir.glob('task_*.jsonl'))
        records = [
            json.loads(line)
            for line in log_files[0].read_text(encoding='utf-8').splitlines()
        ]
        task_start = next(record for record in records if record['event'] == 'task_start')
        model_call = next(record for record in records if record['event'] == 'model_call')
        self.assertEqual(task_start['screenshot_size'], 512)
        self.assertEqual(model_call['screenshot_size'], [512, 512])
        self.assertEqual(model_call['original_screenshot_size'], [1280, 720])
        screenshot_ref = model_call['messages'][-1]['content'][0]['image_url']['url']
        self.assertEqual((self.log_dir / screenshot_ref).read_text(encoding='utf-8'), '512x512')

    def test_agent_passes_natural_scroll_override_to_executor(self):
        self.responses[:] = [
            "Thought: scroll\nAction: scroll(direction='down', point='<point>500 500</point>')",
            "Thought: done\nAction: finished(content='ok')",
        ]
        self.exec_outcomes[:] = ['scrolled']

        agent = self._make_agent(max_steps=2)
        agent.natural_scroll = False
        result = agent.run('Use traditional scroll')

        self.assertTrue(result['success'])
        self.assertTrue(self.executor_inits)
        self.assertEqual(self.executor_inits[0]['natural_scroll'], False)

    def test_agent_passes_display_index_to_capture_executor_and_logs(self):
        self.responses[:] = [
            "Thought: first step\nAction: wait()",
            "Thought: done\nAction: finished(content='ok')",
        ]
        self.exec_outcomes[:] = ['waited']

        agent = self._make_agent(
            max_steps=2,
            display_index=1,
            save_context_log=True,
            context_log_dir=str(self.log_dir),
        )
        result = agent.run('Use second display')

        self.assertTrue(result['success'])
        self.assertEqual(self.capture_calls[0]['display_index'], 1)
        self.assertEqual(self.executor_inits[0]['display_offset_x'], -1440)
        self.assertEqual(self.executor_inits[0]['display_offset_y'], 90)

        log_files = list(self.log_dir.glob('task_*.jsonl'))
        records = [
            json.loads(line)
            for line in log_files[0].read_text(encoding='utf-8').splitlines()
        ]
        task_start = next(record for record in records if record['event'] == 'task_start')
        model_call = next(record for record in records if record['event'] == 'model_call')
        self.assertEqual(task_start['display_index'], 1)
        self.assertEqual(task_start['display_bounds'], [-1440, 90, 1280, 720])
        self.assertEqual(model_call['display_index'], 1)
        self.assertEqual(model_call['display_bounds'], [-1440, 90, 1280, 720])

    def test_invalid_configured_display_falls_back_to_primary_and_warns(self):
        self.responses[:] = [
            "Thought: done\nAction: finished(content='ok')",
        ]

        screenshot_module = sys.modules['computer_use.screenshot']
        original_resolve_display = screenshot_module.resolve_display

        def fake_resolve_display(display_index=None):
            index = 0 if display_index is None else int(display_index)
            if index == 2:
                raise ValueError('显示器索引 2 超出范围，当前仅检测到 2 台显示器')
            return self._fake_resolve_display(index)

        screenshot_module.resolve_display = fake_resolve_display
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                agent = self._make_agent(display_index=2, verbose=True)
                result = agent.run('Fallback to the primary display')
        finally:
            screenshot_module.resolve_display = original_resolve_display

        self.assertTrue(result['success'])
        self.assertEqual(agent.display_index, 0)
        self.assertEqual(self.capture_calls[0]['display_index'], 0)
        printed = output.getvalue()
        self.assertIn('[警告] 目标显示器 2 不可用，已回退到主显示器 0', printed)

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

    def test_tools_passed_to_api_when_skills_are_enabled(self):
        """When skills are loaded, the 'tools' kwarg is included in every API call."""
        self.responses[:] = ["Thought: done\nAction: finished(content='ok')"]

        with tempfile.TemporaryDirectory() as skills_dir:
            skill_path = Path(skills_dir) / 'my-skill'
            skill_path.mkdir()
            (skill_path / 'SKILL.md').write_text(
                '---\nname: my-skill\ndescription: A test skill\n---\n\n## Instructions\nDo something.',
                encoding='utf-8',
            )

            agent = self._make_agent(skills_dir=skills_dir, enable_skills=True)
            agent.run('Use skills')

        self.assertEqual(len(self.calls), 1)
        self.assertIn('tools', self.calls[0])
        tool_names = [t['function']['name'] for t in self.calls[0]['tools']]
        self.assertIn('skill__my-skill', tool_names)

    def test_no_tools_kwarg_when_skills_are_disabled(self):
        """When skills are disabled, no 'tools' kwarg is sent to the API."""
        self.responses[:] = ["Thought: done\nAction: finished(content='ok')"]

        agent = self._make_agent(enable_skills=False)
        agent.run('No skills here')

        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('tools', self.calls[0])

    def test_skill_tool_call_loads_instructions_and_retries(self):
        """When the model returns finish_reason='tool_calls', skill content is
        injected as a tool result and the model is called again."""
        with tempfile.TemporaryDirectory() as skills_dir:
            skill_path = Path(skills_dir) / 'open-browser'
            skill_path.mkdir()
            (skill_path / 'SKILL.md').write_text(
                '---\nname: open-browser\ndescription: Open a browser\n---\n\nUse hotkey ctrl+n.',
                encoding='utf-8',
            )

            self.responses[:] = [
                {
                    'content': '',
                    'finish_reason': 'tool_calls',
                    'tool_calls': [FakeToolCall('skill__open-browser', 'tc-42')],
                },
                "Thought: open browser\nAction: finished(content='done')",
            ]

            agent = self._make_agent(skills_dir=skills_dir, enable_skills=True)
            result = agent.run('Open a browser')

        self.assertTrue(result['success'])
        self.assertEqual(result['runtime_status']['activated_skills'], ['open-browser'])
        # Two API calls: one skill-load round + one final answer
        self.assertEqual(len(self.calls), 2)
        second_call_messages = self.calls[1]['messages']
        roles = [m['role'] for m in second_call_messages]
        self.assertIn('tool', roles)
        tool_msg = next(m for m in second_call_messages if m['role'] == 'tool')
        self.assertIn('hotkey ctrl+n', tool_msg['content'])
        self.assertEqual(tool_msg['tool_call_id'], 'tc-42')

    def test_non_skill_tool_call_does_not_trigger_skill_loading(self):
        self.responses[:] = [
            {
                'content': (
                    "Thought: action text should be parsed directly\n"
                    "Action: finished(content='done')"
                ),
                'finish_reason': 'tool_calls',
                'tool_calls': [FakeToolCall('drag', 'tc-drag')],
            }
        ]

        agent = self._make_agent(enable_skills=True)
        result = agent.run('Move cursor to bottom-right')

        self.assertTrue(result['success'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(result['final_response'], 'done')
        self.assertEqual(result['runtime_status']['activated_skills'], [])

    def test_max_skill_rounds_prevents_infinite_loop(self):
        """If the model keeps requesting skills, the loop stops after max_skill_rounds."""
        with tempfile.TemporaryDirectory() as skills_dir:
            skill_path = Path(skills_dir) / 'loop-skill'
            skill_path.mkdir()
            (skill_path / 'SKILL.md').write_text(
                '---\nname: loop-skill\ndescription: Looping skill\n---\n\nInstructions.',
                encoding='utf-8',
            )

            # 6 tool_call responses — one more than max_skill_rounds (5)
            self.responses[:] = [
                {
                    'content': '',
                    'finish_reason': 'tool_calls',
                    'tool_calls': [FakeToolCall('skill__loop-skill', f'tc-{i}')],
                }
                for i in range(6)
            ]

            agent = self._make_agent(
                skills_dir=skills_dir,
                enable_skills=True,
                max_steps=1,
            )
            # Should not raise; the skill loop cap prevents consuming all 6 responses
            agent.run('Trigger skill loop')

        # max_skill_rounds=5: only 5 of the 6 responses are consumed within one step.
        # The 6th must remain unconsumed.
        remaining = len(self.responses)
        self.assertEqual(remaining, 1, f'Expected 1 response left after capping, got {remaining}')


if __name__ == '__main__':
    unittest.main()
