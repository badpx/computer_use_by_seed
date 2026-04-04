import importlib
import sys
import types
import unittest


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
        self.scroll_calls = []

    def hotkey(self, *keys):
        self.hotkey_calls.append(keys)

    def click(self, *args, **kwargs):
        self.click_calls.append((args, kwargs))

    def doubleClick(self, *args, **kwargs):
        pass

    def moveTo(self, *args, **kwargs):
        self.move_to_calls.append((args, kwargs))

    def dragTo(self, *args, **kwargs):
        pass

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


class ActionExecutorHotkeyTests(unittest.TestCase):
    def setUp(self):
        self.fake_pyautogui = FakePyAutoGUI()
        self.fake_pyperclip = types.ModuleType('pyperclip')
        self.fake_pyperclip.copied_text = None
        self.fake_pyperclip.copy = self._copy_to_clipboard
        sys.modules['pyautogui'] = self.fake_pyautogui
        sys.modules['pyperclip'] = self.fake_pyperclip
        sys.modules.pop('computer_use.action_executor', None)
        self.action_executor = importlib.import_module('computer_use.action_executor')

    def _copy_to_clipboard(self, text):
        self.fake_pyperclip.copied_text = text

    def test_hotkey_normalizes_cmd_plus_space_for_macos(self):
        executor = self.action_executor.ActionExecutor(
            image_width=100,
            image_height=100,
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'hotkey',
                'action_inputs': {'key': 'cmd + space'},
            }
        )

        self.assertEqual(self.fake_pyautogui.hotkey_calls, [('command', 'space')])
        self.assertEqual(result, '热键: command + space')

    def test_hotkey_ignores_plus_delimiters_and_keeps_ctrl_combo(self):
        executor = self.action_executor.ActionExecutor(
            image_width=100,
            image_height=100,
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'hotkey',
                'action_inputs': {'key': 'ctrl + c'},
            }
        )

        self.assertEqual(self.fake_pyautogui.hotkey_calls, [('ctrl', 'c')])
        self.assertEqual(result, '热键: ctrl + c')

    def test_type_uses_command_v_for_clipboard_paste_on_macos(self):
        self.action_executor.sys.platform = 'darwin'
        executor = self.action_executor.ActionExecutor(
            image_width=100,
            image_height=100,
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'type',
                'action_inputs': {'content': '计算器'},
            }
        )

        self.assertEqual(self.fake_pyperclip.copied_text, '计算器')
        self.assertEqual(self.fake_pyautogui.hotkey_calls, [('command', 'v')])
        self.assertEqual(result, '输入文本(剪贴板): 计算器')

    def test_scroll_moves_pointer_to_target_and_uses_visible_amount(self):
        executor = self.action_executor.ActionExecutor(
            image_width=1000,
            image_height=1000,
            coordinate_space='pixel',
            natural_scroll=False,
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'scroll',
                'action_inputs': {
                    'direction': 'down',
                    'start_box': [498, 558],
                },
            }
        )

        self.assertEqual(self.fake_pyautogui.move_to_calls, [((498, 558), {})])
        self.assertEqual(self.fake_pyautogui.scroll_calls, [((500,), {})])
        self.assertEqual(result, '滚动down: (498, 558)')

    def test_scroll_respects_natural_scroll_setting(self):
        executor = self.action_executor.ActionExecutor(
            image_width=1000,
            image_height=1000,
            coordinate_space='pixel',
            natural_scroll=True,
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'scroll',
                'action_inputs': {
                    'direction': 'down',
                    'start_box': [498, 558],
                },
            }
        )

        self.assertEqual(self.fake_pyautogui.move_to_calls, [((498, 558), {})])
        self.assertEqual(self.fake_pyautogui.scroll_calls, [((-500,), {})])
        self.assertEqual(result, '滚动down: (498, 558)')

    def test_left_double_uses_two_clicks_with_interval(self):
        executor = self.action_executor.ActionExecutor(
            image_width=1000,
            image_height=1000,
            coordinate_space='pixel',
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'left_double',
                'action_inputs': {
                    'start_box': [250, 750],
                },
            }
        )

        self.assertEqual(
            self.fake_pyautogui.click_calls,
            [((250, 750), {'button': 'left', 'clicks': 2, 'interval': 0.12})],
        )
        self.assertEqual(result, '双击 (250, 750)')

    def test_click_uses_relative_coordinate_scale_one(self):
        executor = self.action_executor.ActionExecutor(
            image_width=200,
            image_height=100,
            coordinate_space='relative',
            coordinate_scale=1,
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'click',
                'action_inputs': {
                    'start_box': [0.25, 0.5],
                },
            }
        )

        self.assertEqual(
            self.fake_pyautogui.click_calls,
            [((50, 50), {'button': 'left', 'clicks': 1})],
        )
        self.assertEqual(result, '单击 (50, 50)')

    def test_click_uses_relative_coordinate_scale_hundred(self):
        executor = self.action_executor.ActionExecutor(
            image_width=200,
            image_height=100,
            coordinate_space='relative',
            coordinate_scale=100,
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'click',
                'action_inputs': {
                    'start_box': [25, 50],
                },
            }
        )

        self.assertEqual(
            self.fake_pyautogui.click_calls,
            [((50, 50), {'button': 'left', 'clicks': 1})],
        )
        self.assertEqual(result, '单击 (50, 50)')

    def test_click_uses_pixel_coordinates_without_scaling(self):
        executor = self.action_executor.ActionExecutor(
            image_width=200,
            image_height=100,
            coordinate_space='pixel',
            verbose=False,
        )

        result = executor.execute(
            {
                'action_type': 'click',
                'action_inputs': {
                    'start_box': [25, 50],
                },
            }
        )

        self.assertEqual(
            self.fake_pyautogui.click_calls,
            [((25, 50), {'button': 'left', 'clicks': 1})],
        )
        self.assertEqual(result, '单击 (25, 50)')


if __name__ == '__main__':
    unittest.main()
