import base64
import subprocess
import unittest
from unittest import mock


PNG_1X1_BASE64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8'
    '/w8AAgMBgJ0XGfQAAAAASUVORK5CYII='
)
PNG_1X1_BYTES = base64.b64decode(PNG_1X1_BASE64)


class AndroidAdbPluginTests(unittest.TestCase):
    def test_create_device_adapter_loads_android_adb_plugin(self):
        from computer_use.devices.factory import create_device_adapter

        adapter = create_device_adapter(device_name='android_adb')

        self.assertEqual(adapter.device_name, 'android_adb')
        self.assertEqual(adapter.get_prompt_profile(), 'cellphone')
        self.assertEqual(
            adapter.get_environment_info(),
            {'operating_system': 'Android'},
        )
        self.assertFalse(adapter.supports_target_selection())


class AndroidAdbDeviceAdapterTests(unittest.TestCase):
    def _make_adapter(self, plugin_config=None):
        from computer_use.devices.plugins.android_adb.adapter import AndroidAdbDeviceAdapter

        return AndroidAdbDeviceAdapter(plugin_config or {})

    def _completed(self, args, returncode=0, stdout=b'', stderr=b''):
        return subprocess.CompletedProcess(
            args=args,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )

    def test_capture_frame_accepts_png_stdout(self):
        adapter = self._make_adapter()

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'exec-out', 'screencap', '-p'],
                stdout=PNG_1X1_BYTES,
            ),
        ) as run_mock:
            frame = adapter.capture_frame()

        self.assertEqual(frame.width, 1)
        self.assertEqual(frame.height, 1)
        self.assertTrue(frame.image_data_url.startswith('data:image/png;base64,'))
        self.assertEqual(frame.metadata['device_name'], 'android_adb')
        self.assertEqual(frame.metadata['capture_method'], 'adb exec-out screencap -p')
        self.assertFalse(frame.metadata['png_prefix_stripped'])
        run_mock.assert_called_once_with(
            ['adb', 'exec-out', 'screencap', '-p'],
            capture_output=True,
            check=False,
        )

    def test_capture_frame_strips_prefix_before_png_signature(self):
        adapter = self._make_adapter()

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'exec-out', 'screencap', '-p'],
                stdout=b'WARNING: fallback\n' + PNG_1X1_BYTES,
            ),
        ):
            frame = adapter.capture_frame()

        self.assertEqual((frame.width, frame.height), (1, 1))
        self.assertTrue(frame.metadata['png_prefix_stripped'])

    def test_capture_frame_raises_clear_error_when_png_missing(self):
        adapter = self._make_adapter()

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'exec-out', 'screencap', '-p'],
                stdout=b'warning: no screenshot available',
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'PNG'):
                adapter.capture_frame()

    def test_get_status_reports_adb_connection(self):
        adapter = self._make_adapter()

        self.assertEqual(
            adapter.get_status(),
            {
                'device_name': 'android_adb',
                'connected_via': 'adb',
            },
        )

    def test_click_maps_to_input_tap(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand('click', {'point': [12, 34]})

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(['adb', 'shell', 'input', 'tap', '12', '34']),
        ) as run_mock:
            result = adapter.execute_command(command)

        self.assertEqual(result, 'click 执行成功')
        run_mock.assert_called_once_with(
            ['adb', 'shell', 'input', 'tap', '12', '34'],
            capture_output=True,
            check=False,
        )

    def test_long_press_maps_to_same_point_swipe_with_duration(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand('long_press', {'point': [12, 34], 'duration_ms': 800})

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'shell', 'input', 'swipe', '12', '34', '12', '34', '800']
            ),
        ) as run_mock:
            adapter.execute_command(command)

        run_mock.assert_called_once_with(
            ['adb', 'shell', 'input', 'swipe', '12', '34', '12', '34', '800'],
            capture_output=True,
            check=False,
        )

    def test_drag_maps_to_draganddrop(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand(
            'drag',
            {'start_point': [1, 2], 'end_point': [3, 4], 'duration_ms': 900},
        )

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                [
                    'adb',
                    'shell',
                    'input',
                    'draganddrop',
                    '1',
                    '2',
                    '3',
                    '4',
                    '900',
                ]
            ),
        ) as run_mock:
            adapter.execute_command(command)

        run_mock.assert_called_once_with(
            ['adb', 'shell', 'input', 'draganddrop', '1', '2', '3', '4', '900'],
            capture_output=True,
            check=False,
        )

    def test_swipe_maps_to_input_swipe(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand(
            'swipe',
            {'start_point': [1, 2], 'end_point': [3, 4], 'duration_ms': 900},
        )

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.time.sleep'
        ) as sleep_mock, mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                [
                    'adb',
                    'shell',
                    'input',
                    'swipe',
                    '1',
                    '2',
                    '3',
                    '4',
                    '900',
                ]
            ),
        ) as run_mock:
            adapter.execute_command(command)

        run_mock.assert_called_once_with(
            ['adb', 'shell', 'input', 'swipe', '1', '2', '3', '4', '900'],
            capture_output=True,
            check=False,
        )
        sleep_mock.assert_called_once_with(1.0)

    def test_swipe_uses_configured_settle_seconds(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'swipe_settle_seconds': 2.5})
        command = DeviceCommand(
            'swipe',
            {'start_point': [1, 2], 'end_point': [3, 4], 'duration_ms': 900},
        )

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.time.sleep'
        ) as sleep_mock, mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'shell', 'input', 'swipe', '1', '2', '3', '4', '900']
            ),
        ):
            adapter.execute_command(command)

        sleep_mock.assert_called_once_with(2.5)

    def test_swipe_allows_zero_settle_seconds(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter({'swipe_settle_seconds': 0})
        command = DeviceCommand(
            'swipe',
            {'start_point': [1, 2], 'end_point': [3, 4], 'duration_ms': 900},
        )

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.time.sleep'
        ) as sleep_mock, mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'shell', 'input', 'swipe', '1', '2', '3', '4', '900']
            ),
        ):
            adapter.execute_command(command)

        sleep_mock.assert_called_once_with(0.0)

    def test_invalid_swipe_settle_seconds_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, 'swipe_settle_seconds'):
            self._make_adapter({'swipe_settle_seconds': 'bad'})

        with self.assertRaisesRegex(ValueError, 'swipe_settle_seconds'):
            self._make_adapter({'swipe_settle_seconds': -1})

    def test_swipe_failure_does_not_wait(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand(
            'swipe',
            {'start_point': [1, 2], 'end_point': [3, 4], 'duration_ms': 900},
        )

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.time.sleep'
        ) as sleep_mock, mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'shell', 'input', 'swipe', '1', '2', '3', '4', '900'],
                returncode=1,
                stderr=b'gesture failed',
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'android_adb swipe'):
                adapter.execute_command(command)

        sleep_mock.assert_not_called()

    def test_wait_sleeps_for_explicit_seconds_without_adb_call(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand('wait', {'seconds': 3})

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.time.sleep'
        ) as sleep_mock, mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run'
        ) as run_mock:
            result = adapter.execute_command(command)

        self.assertEqual(result, '等待 3 秒')
        sleep_mock.assert_called_once_with(3.0)
        run_mock.assert_not_called()

    def test_wait_clamps_to_one_and_sixty_seconds(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.time.sleep'
        ) as sleep_mock:
            low_result = adapter.execute_command(DeviceCommand('wait', {'seconds': 0}))
            high_result = adapter.execute_command(DeviceCommand('wait', {'seconds': 120}))

        self.assertEqual(low_result, '等待 1 秒')
        self.assertEqual(high_result, '等待 60 秒')
        sleep_mock.assert_has_calls([mock.call(1.0), mock.call(60.0)])

    def test_type_text_trailing_newline_sends_enter(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand('type_text', {'content': 'hello\n'})

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            side_effect=[
                self._completed(['adb', 'shell', 'input', 'text', 'hello']),
                self._completed(
                    ['adb', 'shell', 'input', 'keyevent', 'KEYCODE_ENTER']
                ),
            ],
        ) as run_mock:
            result = adapter.execute_command(command)

        self.assertEqual(result, ['type_text 执行成功', 'press_enter 执行成功'])
        self.assertEqual(run_mock.call_count, 2)
        run_mock.assert_has_calls(
            [
                mock.call(
                    ['adb', 'shell', 'input', 'text', 'hello'],
                    capture_output=True,
                    check=False,
                ),
                mock.call(
                    ['adb', 'shell', 'input', 'keyevent', 'KEYCODE_ENTER'],
                    capture_output=True,
                    check=False,
                ),
            ]
        )

    def test_type_text_escapes_spaces_and_percent(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand('type_text', {'content': 'hello 50% done'})

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'shell', 'input', 'text', 'hello%s50%25%sdone']
            ),
        ) as run_mock:
            result = adapter.execute_command(command)

        self.assertEqual(result, 'type_text 执行成功')
        run_mock.assert_called_once_with(
            ['adb', 'shell', 'input', 'text', 'hello%s50%25%sdone'],
            capture_output=True,
            check=False,
        )

    def test_type_text_unicode_failure_raises_clear_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand('type_text', {'content': '中文文本'})

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'shell', 'input', 'text', '中文文本'],
                returncode=255,
                stderr=(
                    b"Exception occurred while executing 'text': "
                    b"java.lang.NullPointerException at sendText"
                ),
            ),
        ) as run_mock:
            with self.assertRaisesRegex(RuntimeError, 'Unicode|中文'):
                adapter.execute_command(command)

        run_mock.assert_called_once_with(
            ['adb', 'shell', 'input', 'text', '中文文本'],
            capture_output=True,
            check=False,
        )


    def test_open_app_maps_to_monkey_launcher(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand('open_app', {'app_name': 'com.demo.app'})

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                [
                    'adb',
                    'shell',
                    'monkey',
                    '-p',
                    'com.demo.app',
                    '-c',
                    'android.intent.category.LAUNCHER',
                    '1',
                ]
            ),
        ) as run_mock:
            adapter.execute_command(command)

        run_mock.assert_called_once_with(
            [
                'adb',
                'shell',
                'monkey',
                '-p',
                'com.demo.app',
                '-c',
                'android.intent.category.LAUNCHER',
                '1',
            ],
            capture_output=True,
            check=False,
        )

    def test_open_app_accepts_package_name_alias(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand('open_app', {'package_name': 'com.demo.app'})

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                [
                    'adb',
                    'shell',
                    'monkey',
                    '-p',
                    'com.demo.app',
                    '-c',
                    'android.intent.category.LAUNCHER',
                    '1',
                ]
            ),
        ) as run_mock:
            result = adapter.execute_command(command)

        self.assertEqual(result, 'open_app 执行成功')
        run_mock.assert_called_once_with(
            [
                'adb',
                'shell',
                'monkey',
                '-p',
                'com.demo.app',
                '-c',
                'android.intent.category.LAUNCHER',
                '1',
            ],
            capture_output=True,
            check=False,
        )

    def test_scroll_missing_point_raises_clear_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with self.assertRaisesRegex(ValueError, 'android_adb'):
            adapter.execute_command(DeviceCommand('scroll', {'direction': 'down', 'steps': 2}))

    def test_scroll_malformed_point_raises_clear_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with self.assertRaisesRegex(ValueError, 'android_adb 坐标格式无效'):
            adapter.execute_command(
                DeviceCommand('scroll', {'point': ['bad', 60], 'direction': 'down', 'steps': 2})
            )

    def test_scroll_maps_to_touchscreen_scroll_axis_argument(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()
        command = DeviceCommand(
            'scroll',
            {'point': [50, 60], 'direction': 'down', 'steps': 2},
        )

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                [
                    'adb',
                    'shell',
                    'input',
                    'touchscreen',
                    'scroll',
                    '50',
                    '60',
                    '--axis',
                    'VSCROLL,2',
                ]
            ),
        ) as run_mock:
            result = adapter.execute_command(command)

        self.assertEqual(result, 'scroll 执行成功')
        run_mock.assert_called_once_with(
            [
                'adb',
                'shell',
                'input',
                'touchscreen',
                'scroll',
                '50',
                '60',
                '--axis',
                'VSCROLL,2',
            ],
            capture_output=True,
            check=False,
        )

    def test_long_press_invalid_duration_raises_clear_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with self.assertRaisesRegex(ValueError, 'android_adb duration_ms 格式无效'):
            adapter.execute_command(
                DeviceCommand('long_press', {'point': [12, 34], 'duration_ms': 'fast'})
            )

    def test_scroll_invalid_steps_raises_clear_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with self.assertRaisesRegex(ValueError, 'android_adb scroll steps 格式无效'):
            adapter.execute_command(
                DeviceCommand('scroll', {'point': [50, 60], 'direction': 'down', 'steps': 'many'})
            )

    def test_press_home_and_back_map_to_keyevents(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            side_effect=[
                self._completed(['adb', 'shell', 'input', 'keyevent', 'KEYCODE_HOME']),
                self._completed(['adb', 'shell', 'input', 'keyevent', 'KEYCODE_BACK']),
            ],
        ) as run_mock:
            adapter.execute_command(DeviceCommand('press_home'))
            adapter.execute_command(DeviceCommand('press_back'))

        run_mock.assert_has_calls(
            [
                mock.call(
                    ['adb', 'shell', 'input', 'keyevent', 'KEYCODE_HOME'],
                    capture_output=True,
                    check=False,
                ),
                mock.call(
                    ['adb', 'shell', 'input', 'keyevent', 'KEYCODE_BACK'],
                    capture_output=True,
                    check=False,
                ),
            ]
        )

    def test_unsupported_action_raises_clear_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with self.assertRaisesRegex(ValueError, '不支持'):
            adapter.execute_command(DeviceCommand('double_click'))

    def test_missing_adb_raises_clear_dependency_error(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            side_effect=FileNotFoundError('adb'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'adb'):
                adapter.execute_command(DeviceCommand('press_home'))

    def test_non_zero_exit_code_includes_stderr(self):
        from computer_use.devices.base import DeviceCommand

        adapter = self._make_adapter()

        with mock.patch(
            'computer_use.devices.plugins.android_adb.adapter.subprocess.run',
            return_value=self._completed(
                ['adb', 'shell', 'input', 'tap', '1', '2'],
                returncode=1,
                stderr=b'device offline',
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'device offline'):
                adapter.execute_command(DeviceCommand('click', {'point': [1, 2]}))
