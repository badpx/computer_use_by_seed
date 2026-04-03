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
        self.move_to_calls = []
        self.scroll_calls = []

    def hotkey(self, *keys):
        self.hotkey_calls.append(keys)

    def click(self, *args, **kwargs):
        pass

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


if __name__ == '__main__':
    unittest.main()
