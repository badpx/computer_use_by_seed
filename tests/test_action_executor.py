import importlib
import sys
import types
import unittest

from computer_use.devices.base import DeviceCommand
from computer_use.devices.coordinates import (
    normalize_command_coordinates,
)


class FakePyAutoGUI(types.ModuleType):
    def __init__(self):
        super().__init__('pyautogui')
        self.FAILSAFE = False
        self.PAUSE = 0
        self.hotkey_calls = []
        self.write_calls = []
        self.press_calls = []
        self.click_calls = []
        self.move_to_calls = []
        self.drag_to_calls = []
        self.scroll_calls = []

    def hotkey(self, *keys):
        self.hotkey_calls.append(keys)

    def click(self, *args, **kwargs):
        self.click_calls.append((args, kwargs))

    def moveTo(self, *args, **kwargs):
        self.move_to_calls.append((args, kwargs))

    def dragTo(self, *args, **kwargs):
        self.drag_to_calls.append((args, kwargs))

    def keyDown(self, *args, **kwargs):
        pass

    def keyUp(self, *args, **kwargs):
        pass

    def write(self, *args, **kwargs):
        self.write_calls.append((args, kwargs))

    def press(self, *args, **kwargs):
        self.press_calls.append((args, kwargs))

    def scroll(self, *args, **kwargs):
        self.scroll_calls.append((args, kwargs))


class LocalActionExecutorTests(unittest.TestCase):
    def setUp(self):
        self.fake_pyautogui = FakePyAutoGUI()
        self.fake_pyperclip = types.ModuleType('pyperclip')
        self.fake_pyperclip.copied_text = None
        self.fake_pyperclip.copy = self._copy_to_clipboard
        self.sleep_calls = []
        sys.modules['pyautogui'] = self.fake_pyautogui
        sys.modules['pyperclip'] = self.fake_pyperclip
        sys.modules.pop('computer_use.devices.plugins.local.executor', None)
        self.executor_module = importlib.import_module(
            'computer_use.devices.plugins.local.executor'
        )
        self.executor_module.time.sleep = lambda seconds: self.sleep_calls.append(seconds)

    def tearDown(self):
        sys.modules.pop('pyautogui', None)
        sys.modules.pop('pyperclip', None)
        sys.modules.pop('computer_use.devices.plugins.local.executor', None)

    def _copy_to_clipboard(self, text):
        self.fake_pyperclip.copied_text = text

    def _make_executor(self, **kwargs):
        return self.executor_module.LocalActionExecutor(verbose=False, **kwargs)

    def _normalize(self, payload, *, coordinate_space='relative', coordinate_scale=1000,
                   image_width=200, image_height=100, model_image_width=None,
                   model_image_height=None):
        command = DeviceCommand(command_type='click', payload=dict(payload))
        return normalize_command_coordinates(
            command,
            image_width=image_width,
            image_height=image_height,
            model_image_width=model_image_width or image_width,
            model_image_height=model_image_height or image_height,
            coordinate_space=coordinate_space,
            coordinate_scale=coordinate_scale,
        ).payload

    def test_hotkey_normalizes_cmd_plus_space_for_macos(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'hotkey', 'action_inputs': {'key': 'cmd + space'}})
        self.assertEqual(self.fake_pyautogui.hotkey_calls, [('command', 'space')])
        self.assertEqual(result, '热键: command + space')

    def test_hotkey_ignores_plus_delimiters_and_keeps_ctrl_combo(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'hotkey', 'action_inputs': {'key': 'ctrl + c'}})
        self.assertEqual(self.fake_pyautogui.hotkey_calls, [('ctrl', 'c')])
        self.assertEqual(result, '热键: ctrl + c')

    def test_type_uses_command_v_for_clipboard_paste_on_macos(self):
        self.executor_module.sys.platform = 'darwin'
        executor = self._make_executor()
        result = executor.execute({'action_type': 'type', 'action_inputs': {'content': '计算器'}})
        self.assertEqual(self.fake_pyperclip.copied_text, '计算器')
        self.assertEqual(self.fake_pyautogui.hotkey_calls, [('command', 'v')])
        self.assertEqual(result, '输入文本(剪贴板): 计算器')

    def test_type_uses_clipboard_for_single_unicode_character_on_all_platforms(self):
        for platform_name, expected_hotkey in (
            ('darwin', ('command', 'v')),
            ('linux', ('ctrl', 'v')),
            ('win32', ('ctrl', 'v')),
        ):
            with self.subTest(platform=platform_name):
                self.executor_module.sys.platform = platform_name
                self.fake_pyperclip.copied_text = None
                self.fake_pyautogui.hotkey_calls.clear()
                self.fake_pyautogui.write_calls.clear()
                executor = self._make_executor()
                result = executor.execute({'action_type': 'type', 'action_inputs': {'content': '酒'}})
                self.assertEqual(self.fake_pyperclip.copied_text, '酒')
                self.assertEqual(self.fake_pyautogui.hotkey_calls, [expected_hotkey])
                self.assertEqual(self.fake_pyautogui.write_calls, [])
                self.assertEqual(result, '输入文本(剪贴板): 酒')

    def test_scroll_moves_pointer_to_target_and_uses_visible_amount(self):
        executor = self._make_executor()
        result = executor.execute(
            {'action_type': 'scroll', 'action_inputs': {'direction': 'down', 'steps': 50, 'point': [498, 558]}}
        )
        self.assertEqual(self.fake_pyautogui.move_to_calls, [((498, 558), {})])
        self.assertEqual(self.fake_pyautogui.scroll_calls, [((50,), {})])
        self.assertEqual(result, '滚动down 50步: (498, 558)')

    def test_pixel_coordinates_are_executed_without_extra_scaling(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'click', 'action_inputs': {'point': [500, 250]}})
        self.assertEqual(self.fake_pyautogui.click_calls, [((500, 250), {'button': 'left', 'clicks': 1})])
        self.assertEqual(result, '单击 (500, 250)')

    def test_drag_uses_left_button_explicitly(self):
        executor = self._make_executor()
        result = executor.execute(
            {'action_type': 'drag', 'action_inputs': {'start_point': [242, 475], 'end_point': [540, 475]}}
        )
        self.assertEqual(self.fake_pyautogui.move_to_calls, [((242, 475), {})])
        self.assertEqual(self.fake_pyautogui.drag_to_calls, [((540, 475), {'duration': 0.5, 'button': 'left'})])
        self.assertEqual(result, '拖拽 (242, 475) -> (540, 475)')

    def test_scroll_interprets_direction_literally_after_global_normalization(self):
        executor = self._make_executor()
        result = executor.execute(
            {'action_type': 'scroll', 'action_inputs': {'direction': 'down', 'steps': 50, 'point': [498, 558]}}
        )
        self.assertEqual(self.fake_pyautogui.move_to_calls, [((498, 558), {})])
        self.assertEqual(self.fake_pyautogui.scroll_calls, [((50,), {})])
        self.assertEqual(result, '滚动down 50步: (498, 558)')

    def test_scroll_uses_model_provided_steps(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'scroll', 'action_inputs': {'direction': 'up', 'steps': 7}})
        self.assertEqual(self.fake_pyautogui.scroll_calls, [((-7,), {})])
        self.assertEqual(result, '滚动up 7步')

    def test_left_double_uses_two_clicks_with_interval(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'left_double', 'action_inputs': {'point': [250, 750]}})
        self.assertEqual(
            self.fake_pyautogui.click_calls,
            [((250, 750), {'button': 'left', 'clicks': 2, 'interval': 0.12})],
        )
        self.assertEqual(result, '双击 (250, 750)')

    def test_relative_coordinates_are_normalized_before_execution(self):
        executor = self._make_executor()
        action_inputs = self._normalize({'point': [25, 50]}, coordinate_space='relative', coordinate_scale=100)
        result = executor.execute({'action_type': 'click', 'action_inputs': action_inputs})
        self.assertEqual(self.fake_pyautogui.click_calls, [((50, 50), {'button': 'left', 'clicks': 1})])
        self.assertEqual(result, '单击 (50, 50)')

    def test_scaled_model_pixel_coordinates_are_normalized_before_execution(self):
        executor = self._make_executor()
        action_inputs = self._normalize(
            {'point': [250, 125]},
            coordinate_space='pixel',
            image_width=2000,
            image_height=1000,
            model_image_width=1000,
            model_image_height=500,
        )
        result = executor.execute({'action_type': 'click', 'action_inputs': action_inputs})
        self.assertEqual(self.fake_pyautogui.click_calls, [((500, 250), {'button': 'left', 'clicks': 1})])
        self.assertEqual(result, '单击 (500, 250)')

    def test_click_accepts_space_separated_point_string(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'click', 'action_inputs': {'point': '1000 0'}})
        self.assertEqual(self.fake_pyautogui.click_calls, [((1000, 0), {'button': 'left', 'clicks': 1})])
        self.assertEqual(result, '单击 (1000, 0)')

    def test_click_adds_display_offset_to_absolute_coordinates(self):
        executor = self._make_executor(display_offset_x=-1440, display_offset_y=90)
        result = executor.execute({'action_type': 'click', 'action_inputs': {'point': [25, 50]}})
        self.assertEqual(self.fake_pyautogui.click_calls, [((-1415, 140), {'button': 'left', 'clicks': 1})])
        self.assertEqual(result, '单击 (-1415, 140)')

    def test_wait_uses_explicit_seconds(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'wait', 'action_inputs': {'seconds': 7}})
        self.assertEqual(self.sleep_calls, [7.0])
        self.assertEqual(result, '等待 7 秒')

    def test_wait_uses_three_seconds_by_default(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'wait', 'action_inputs': {}})
        self.assertEqual(self.sleep_calls, [3.0])
        self.assertEqual(result, '等待 3 秒')

    def test_wait_clamps_values_below_one_second(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'wait', 'action_inputs': {'seconds': 0}})
        self.assertEqual(self.sleep_calls, [1.0])
        self.assertEqual(result, '等待 1 秒')

    def test_wait_clamps_values_above_sixty_seconds(self):
        executor = self._make_executor()
        result = executor.execute({'action_type': 'wait', 'action_inputs': {'seconds': 120}})
        self.assertEqual(self.sleep_calls, [60.0])
        self.assertEqual(result, '等待 60 秒')


if __name__ == '__main__':
    unittest.main()
